"""Fixtures for the sandbox suite: a REAL broker (in-process thread) driving REAL Docker containers.

These tests need a running container engine. If it is unreachable the suite FAILS (it never skips
silently): sandbox security claims must not be vacuously green.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import secrets
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from sandbox_service.broker.config import BrokerConfig, ImageLock
from sandbox_service.broker.manager import RunManager
from sandbox_service.broker.runtime import LABEL, DockerRuntime
from sandbox_service.broker.server import BrokerServer, make_server
from sandbox_service.broker.staging import remove_tree

ROOT = Path(__file__).resolve().parents[2]
CSV = b"category,units\nA,3\nB,5\nA,4\n"
CSV_SHA = hashlib.sha256(CSV).hexdigest()
pytestmark = pytest.mark.sandbox


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/sandbox" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.sandbox)


def docker_ps_managed() -> list[str]:
    out = subprocess.run(  # noqa: S603
        ["docker", "ps", "-a", "--filter", f"label={LABEL}=1", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return [n for n in out.stdout.split() if n]


@dataclass
class Api:
    server: BrokerServer
    manager: RunManager
    token: str
    cfg: BrokerConfig

    def call(
        self,
        method: str,
        path: str,
        body: bytes | dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        host: str | None = None,
    ) -> tuple[int, Any]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=180)
        hdrs = {"Authorization": f"Bearer {self.token}"} if auth else {}
        hdrs.update(headers or {})
        if host:
            hdrs["Host"] = host
        payload = json.dumps(body).encode() if isinstance(body, dict) else body
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(data)
        except ValueError:
            return resp.status, data

    def upload(self, data: bytes = CSV, kind: str = "csv") -> str:
        sha = hashlib.sha256(data).hexdigest()
        status, body = self.call("PUT", f"/v1/datasets/{sha}?kind={kind}", data)
        assert status in (200, 201), body
        return sha

    def run(self, code: str, *, timeout_s: int = 30, dataset: str | None = None, **extra: Any):
        exec_id = extra.pop("exec_id", secrets.token_hex(8))
        req = {
            "exec_id": exec_id,
            "code": code,
            "dataset_id": dataset or self.upload(),
            "timeout_s": timeout_s,
            **extra,
        }
        status, body = self.call("POST", "/v1/runs", req)
        return status, body

    def run_ok(self, code: str, **kw: Any) -> dict[str, Any]:
        status, body = self.run(code, **kw)
        assert status == 200, body
        self.call("DELETE", f"/v1/runs/{body['exec_id']}")
        return body

    def background(self, code: str, *, timeout_s: int = 60) -> Background:
        return Background(self, code, timeout_s)


class Background:
    """A run executing in a thread, so tests can inspect/cancel the live container."""

    def __init__(self, api: Api, code: str, timeout_s: int) -> None:
        self.exec_id = secrets.token_hex(8)
        self.result: tuple[int, Any] | None = None
        self._api = api
        dataset = api.upload()
        self._thread = threading.Thread(
            target=lambda: setattr(
                self,
                "result",
                api.run(code, timeout_s=timeout_s, dataset=dataset, exec_id=self.exec_id),
            ),
            daemon=True,
        )
        self._thread.start()

    def wait_for_container(self, timeout: float = 30.0) -> str:
        name = f"{self._api.cfg.container_prefix}{self.exec_id}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if name in docker_ps_managed():
                state = subprocess.run(  # noqa: S603
                    ["docker", "inspect", name, "--format", "{{.State.Running}}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if state.stdout.strip() == "true":
                    return name
            time.sleep(0.1)
        raise AssertionError("container never started")

    def join(self, timeout: float = 30.0) -> tuple[int, Any]:
        self._thread.join(timeout)
        assert not self._thread.is_alive(), "run did not finish"
        assert self.result is not None
        return self.result


@pytest.fixture(scope="session")
def engine() -> DockerRuntime:
    last: Exception | None = None
    for attempt in range(5):  # the engine can be slow right after the host resumes from standby
        try:
            runtime = DockerRuntime()
            lock = ImageLock.load(BrokerConfig(token="x" * 32, root=ROOT).lock_path)
            runtime.verify_image(lock.image_id)
            return runtime
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(10 * (attempt + 1))
    pytest.fail(f"container engine or pinned sandbox image unavailable after retries: {last}")


@pytest.fixture(scope="module")
def api(engine: DockerRuntime) -> Iterator[Api]:
    token = secrets.token_urlsafe(32)
    root = ROOT / ".sandbox" / f"pytest-{secrets.token_hex(4)}"
    cfg = BrokerConfig(token=token, root=root, port=0)
    lock = ImageLock.load(cfg.lock_path)
    manager = RunManager(cfg, engine, lock)
    manager.startup_reap()
    server = make_server(cfg, manager)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Api(server, manager, token, cfg)
    manager.shutdown()
    server.shutdown()
    server.server_close()
    remove_tree(root)


@pytest.fixture(autouse=True)
def _no_leaks_after_each_test(request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    if "api" not in request.fixturenames:
        return
    api: Api = request.getfixturevalue("api")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and (
        docker_ps_managed() or any(api.manager.layout.runs.iterdir())
    ):
        time.sleep(0.2)
    assert docker_ps_managed() == [], "leaked container"
    assert list(api.manager.layout.runs.iterdir()) == [], "leaked staging directory"
    leftovers = [p.name for p in api.manager.layout.artifacts.iterdir()]
    for name in leftovers:  # artifacts are removed by DELETE; remove then fail loudly, per test
        shutil.rmtree(api.manager.layout.artifacts / name, ignore_errors=True)
    assert leftovers == [], f"leaked artifact directories: {leftovers}"
