"""Loopback-only HTTP broker (standard library). Narrow API; strict validation; bearer auth.

GET    /healthz                              (no auth, reveals nothing)
PUT    /v1/datasets/{sha256}?kind=csv|xlsx   raw body, digest verified
POST   /v1/runs                              JSON {exec_id, code, dataset_id[, sheet, timeout_s]}
DELETE /v1/runs/{exec_id}                    cancel + remove artifacts
GET    /v1/runs/{exec_id}/artifacts/{name}
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sandbox_service.broker.config import BrokerConfig
from sandbox_service.broker.manager import Busy, Conflict, RunManager
from sandbox_service.broker.staging import (
    ARTIFACT_NAME_RE,
    DATASET_KINDS,
    EXEC_ID_RE,
    SHA256_RE,
    store_dataset_stream,
)

log = logging.getLogger("sandbox.server")
RUN_FIELDS_REQUIRED = {"exec_id", "code", "dataset_id"}
RUN_FIELDS_OPTIONAL = {"sheet", "timeout_s"}
DRAIN_LIMIT = 1024 * 1024
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(code)
        self.status, self.code, self.message = status, code, message or code


class BrokerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, cfg: BrokerConfig, manager: RunManager) -> None:
        self.cfg, self.manager = cfg, manager
        if cfg.host == "::1":
            self.address_family = socket.AF_INET6
        super().__init__((cfg.host, cfg.port), Handler)
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    @property
    def port(self) -> int:
        return int(self.server_address[1])


def validate_run_request(body: Any, cfg: BrokerConfig) -> dict[str, Any]:
    """Strict schema: exact fields and types. Anything else (image, flags, mounts) is a 400."""
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_body", "JSON object required")
    keys = set(body)
    if unknown := keys - RUN_FIELDS_REQUIRED - RUN_FIELDS_OPTIONAL:
        raise ApiError(400, "unknown_field", f"not accepted: {sorted(unknown)[:5]}")
    if missing := RUN_FIELDS_REQUIRED - keys:
        raise ApiError(400, "missing_field", f"required: {sorted(missing)}")
    exec_id, code, dataset_id = body["exec_id"], body["code"], body["dataset_id"]
    if not isinstance(exec_id, str) or not EXEC_ID_RE.match(exec_id):
        raise ApiError(400, "invalid_exec_id", "8-64 alphanumeric characters")
    if not isinstance(dataset_id, str) or not SHA256_RE.match(dataset_id):
        raise ApiError(400, "invalid_dataset_id", "64 lowercase hex characters")
    if not isinstance(code, str) or not code.strip() or "\x00" in code:
        raise ApiError(400, "invalid_code", "non-empty text without NUL")
    if len(code.encode("utf-8")) > cfg.max_code_bytes:
        raise ApiError(413, "code_too_large")
    sheet = body.get("sheet")
    if sheet is not None and (
        not isinstance(sheet, str) or not sheet or len(sheet) > 64 or _CONTROL.search(sheet)
    ):
        raise ApiError(400, "invalid_sheet", "1-64 printable characters")
    timeout = body.get("timeout_s", cfg.default_timeout_s)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= cfg.max_timeout_s
    ):
        raise ApiError(400, "invalid_timeout", f"integer 1..{cfg.max_timeout_s}")
    return {
        "exec_id": exec_id,
        "code": code,
        "dataset_id": dataset_id,
        "sheet": sheet,
        "timeout_s": timeout,
    }


class Handler(BaseHTTPRequestHandler):
    server: BrokerServer
    server_version = "datapilot-sandbox"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # never log headers or bodies
        log.info("%s %s", self.command, self.path.split("?")[0][:80])

    # -- plumbing ----------------------------------------------------------------------------
    def _send(self, status: int, payload: Any, *, raw: bytes | None = None, name: str = "") -> None:
        body = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if raw is not None:
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        else:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _dispatch(self) -> None:
        self._body_read = False
        try:
            self._check_host()
            path = urlsplit(self.path)
            parts = [p for p in path.path.split("/") if p]
            if self.command == "GET" and parts == ["healthz"]:
                return self._send(200, {"status": "ok"})
            self._check_auth()
            self._route(parts, parse_qs(path.query))
        except ApiError as err:
            self._drain_small_body()
            self._send(err.status, {"error": err.code, "message": err.message})
        except Exception:
            log.exception("unhandled error")
            self._send(500, {"error": "internal_error"})

    do_GET = do_PUT = do_POST = do_DELETE = _dispatch

    def do_PATCH(self) -> None:
        self._send(405, {"error": "method_not_allowed"})

    def _drain_small_body(self) -> None:
        """Read a small unread body before replying, so the client sees our error, not a reset."""
        if self._body_read:
            return
        raw = self.headers.get("Content-Length", "")
        if self.headers.get("Transfer-Encoding") or not raw.isdigit():
            return
        remaining = int(raw)
        if remaining > DRAIN_LIMIT:
            return  # refused without reading; the connection is closed
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        self._body_read = True

    def _check_host(self) -> None:
        if self.headers.get("Host", "") not in self.server.allowed_hosts:
            raise ApiError(421, "bad_host")

    def _check_auth(self) -> None:
        header = self.headers.get("Authorization", "")
        scheme, _, supplied = header.partition(" ")
        expected = self.server.cfg.token
        if scheme != "Bearer" or not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise ApiError(401, "unauthorized")

    def _content_length(self, limit: int) -> int:
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(411, "length_required", "chunked bodies are not accepted")
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise ApiError(411, "length_required")
        if not raw.isdigit():
            raise ApiError(400, "bad_content_length")
        length = int(raw)
        if length > limit:
            raise ApiError(413, "body_too_large")
        return length

    # -- routes ------------------------------------------------------------------------------
    def _route(self, parts: list[str], query: dict[str, list[str]]) -> None:
        cmd, cfg, mgr = self.command, self.server.cfg, self.server.manager
        if parts[:2] == ["v1", "datasets"] and len(parts) == 3:
            if cmd != "PUT":
                raise ApiError(405, "method_not_allowed")
            return self._put_dataset(parts[2], query)
        if parts == ["v1", "runs"]:
            if cmd != "POST":
                raise ApiError(405, "method_not_allowed")
            return self._post_run()
        if parts[:2] == ["v1", "runs"] and len(parts) == 3:
            if cmd != "DELETE":
                raise ApiError(405, "method_not_allowed")
            if not EXEC_ID_RE.match(parts[2]):
                raise ApiError(400, "invalid_exec_id")
            return self._send(200, {"deleted": mgr.delete(parts[2])})
        if parts[:2] == ["v1", "runs"] and len(parts) == 5 and parts[3] == "artifacts":
            if cmd != "GET":
                raise ApiError(405, "method_not_allowed")
            return self._get_artifact(parts[2], parts[4])
        del cfg
        raise ApiError(404, "not_found")

    def _put_dataset(self, sha: str, query: dict[str, list[str]]) -> None:
        cfg, mgr = self.server.cfg, self.server.manager
        kind = (query.get("kind") or [""])[0]
        if not SHA256_RE.match(sha):
            raise ApiError(400, "invalid_dataset_id")
        if kind not in DATASET_KINDS:
            raise ApiError(400, "invalid_kind", "csv or xlsx")
        length = self._content_length(cfg.max_dataset_bytes)
        if length == 0:
            raise ApiError(400, "empty_body")
        self._body_read = True
        try:
            outcome = store_dataset_stream(mgr.layout, sha, kind, self.rfile.read, length)
        except ValueError as err:
            raise ApiError(400, str(err)) from err
        self._send(200 if outcome == "exists" else 201, {"dataset_id": sha, "status": outcome})

    def _post_run(self) -> None:
        cfg, mgr = self.server.cfg, self.server.manager
        length = self._content_length(cfg.max_json_bytes)
        self._body_read = True
        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise ApiError(400, "invalid_json") from err
        req = validate_run_request(body, cfg)
        found = mgr.layout.find_dataset(req["dataset_id"])
        if found is None:
            raise ApiError(404, "unknown_dataset")
        path, kind = found
        try:
            result = mgr.run(
                req["exec_id"], req["code"], path, kind, req["sheet"], req["timeout_s"]
            )
        except Busy as err:
            raise ApiError(429, "busy", "all execution slots are in use") from err
        except Conflict as err:
            raise ApiError(409, "exec_id_in_use") from err
        self._send(200, result)

    def _get_artifact(self, exec_id: str, name: str) -> None:
        if not EXEC_ID_RE.match(exec_id) or not ARTIFACT_NAME_RE.match(name):
            raise ApiError(400, "invalid_path")
        mgr = self.server.manager
        base = mgr.layout.artifact_dir(exec_id).resolve()
        target = (base / name).resolve()
        if target.parent != base or not target.is_file() or target.is_symlink():
            raise ApiError(404, "not_found")
        self._send(200, None, raw=target.read_bytes(), name=name)


def make_server(cfg: BrokerConfig, manager: RunManager) -> BrokerServer:
    cfg.validate()
    return BrokerServer(cfg, manager)
