"""Broker request validation, authentication and configuration. No code is executed here."""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path

import pytest

from sandbox_service.broker.config import BrokerConfig, ConfigError
from sandbox_service.broker.runtime import ContainerSpec, build_create_argv
from tests.sandbox.conftest import CSV, CSV_SHA, docker_ps_managed

pytestmark = pytest.mark.sandbox
GOOD = {"exec_id": "abcdef123456", "code": "print(1)", "dataset_id": CSV_SHA}


def raw(api, request_text: str) -> bytes:
    with socket.create_connection(("127.0.0.1", api.server.port), timeout=30) as s:
        s.sendall(request_text.encode())
        s.shutdown(socket.SHUT_WR)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    return data


# ------------------------------------------------------------------ authentication -------------
def test_requests_without_or_with_wrong_bearer_token_are_rejected(api):
    assert api.call("POST", "/v1/runs", GOOD, auth=False)[0] == 401
    assert (
        api.call("POST", "/v1/runs", GOOD, headers={"Authorization": "Bearer nope"}, auth=False)[0]
        == 401
    )
    assert (
        api.call(
            "POST", "/v1/runs", GOOD, headers={"Authorization": f"Basic {api.token}"}, auth=False
        )[0]
        == 401
    )
    assert api.call("PUT", f"/v1/datasets/{CSV_SHA}?kind=csv", CSV, auth=False)[0] == 401
    assert api.call("DELETE", "/v1/runs/abcdef123456", auth=False)[0] == 401
    assert docker_ps_managed() == []


def test_health_endpoint_needs_no_token_and_reveals_nothing(api):
    status, body = api.call("GET", "/healthz", auth=False)
    assert status == 200 and body == {"status": "ok"}


def test_wrong_host_header_is_refused_against_dns_rebinding(api):
    assert api.call("GET", "/healthz", auth=False, host="evil.example.com")[0] == 421
    assert api.call("GET", "/healthz", auth=False, host=f"localhost:{api.server.port}")[0] == 200


def test_broker_listens_on_loopback_only(api):
    assert api.server.server_address[0] == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "::", "example.com", ""])  # noqa: S104
def test_non_loopback_bind_address_is_refused(host, tmp_path):
    with pytest.raises(ConfigError, match="loopback"):
        BrokerConfig(token="t" * 32, root=tmp_path, host=host).validate()


def test_weak_token_and_unsafe_root_are_refused(tmp_path):
    with pytest.raises(ConfigError, match="SANDBOX_TOKEN"):
        BrokerConfig(token="short", root=tmp_path).validate()  # noqa: S106
    with pytest.raises(ConfigError, match="commas"):
        BrokerConfig(token="t" * 32, root=Path("C:/a,b")).validate()  # noqa: S106


def test_config_from_env_requires_a_token():
    with pytest.raises(ConfigError):
        BrokerConfig.from_env({})


# ------------------------------------------------------------------ run request validation ------
@pytest.mark.parametrize(
    "extra",
    [
        {"image": "alpine:latest"},
        {"network": "host"},
        {"privileged": True},
        {"mounts": ["/:/host"]},
        {"volumes": ["/var/run/docker.sock:/var/run/docker.sock"]},
        {"command": ["sh", "-c", "id"]},
        {"cmd": "id"},
        {"env": {"OPENAI_API_KEY": "x"}},
        {"flags": ["--cap-add=ALL"]},
        {"user": "root"},
        {"memory": "64g"},
        {"session_id": "s1"},
    ],
)
def test_unauthorized_configuration_fields_are_rejected_and_nothing_starts(api, extra):
    api.upload()
    status, body = api.call("POST", "/v1/runs", {**GOOD, **extra})
    assert status == 400 and body["error"] == "unknown_field"
    assert docker_ps_managed() == [] and list(api.manager.layout.runs.iterdir()) == []


@pytest.mark.parametrize(
    ("patch", "error"),
    [
        ({"exec_id": "../../etc/passwd"}, "invalid_exec_id"),
        ({"exec_id": "short"}, "invalid_exec_id"),
        ({"exec_id": "abc def 12345"}, "invalid_exec_id"),
        ({"exec_id": 12345678}, "invalid_exec_id"),
        ({"dataset_id": "../x"}, "invalid_dataset_id"),
        ({"dataset_id": CSV_SHA.upper()}, "invalid_dataset_id"),
        ({"code": ""}, "invalid_code"),
        ({"code": 5}, "invalid_code"),
        ({"code": "print(1)\x00"}, "invalid_code"),
        ({"sheet": ""}, "invalid_sheet"),
        ({"sheet": "a\nb"}, "invalid_sheet"),
        ({"sheet": "x" * 65}, "invalid_sheet"),
        ({"timeout_s": 0}, "invalid_timeout"),
        ({"timeout_s": 10_000}, "invalid_timeout"),
        ({"timeout_s": "30"}, "invalid_timeout"),
        ({"timeout_s": True}, "invalid_timeout"),
        ({"timeout_s": 1.5}, "invalid_timeout"),
    ],
)
def test_malformed_run_fields_are_rejected(api, patch, error):
    status, body = api.call("POST", "/v1/runs", {**GOOD, **patch})
    assert status == 400 and body["error"] == error


def test_missing_fields_non_object_and_bad_json_are_rejected(api):
    assert api.call("POST", "/v1/runs", {"exec_id": "abcdef123456"})[1]["error"] == "missing_field"
    assert api.call("POST", "/v1/runs", b"[1,2]")[1]["error"] == "invalid_body"
    assert api.call("POST", "/v1/runs", b"{not json")[1]["error"] == "invalid_json"
    assert api.call("POST", "/v1/runs", b"\xff\xfe")[1]["error"] == "invalid_json"


def test_oversized_code_and_oversized_bodies_are_refused(api):
    api.upload()
    big_code = "x = 1\n" * (api.cfg.max_code_bytes // 3)
    assert api.call("POST", "/v1/runs", {**GOOD, "code": big_code})[0] in (413,)
    head = (
        f"POST /v1/runs HTTP/1.1\r\nHost: 127.0.0.1:{api.server.port}\r\n"
        f"Authorization: Bearer {api.token}\r\nContent-Length: 99999999\r\n\r\n"
    )
    assert b" 413 " in raw(api, head).split(b"\r\n")[0]


def test_chunked_and_length_less_bodies_are_refused(api):
    base = f"POST /v1/runs HTTP/1.1\r\nHost: 127.0.0.1:{api.server.port}\r\nAuthorization: Bearer {api.token}\r\n"
    assert (
        b" 411 " in raw(api, base + "Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n").split(b"\r\n")[0]
    )
    assert b" 411 " in raw(api, base + "\r\n").split(b"\r\n")[0]


def test_unknown_dataset_unknown_routes_and_methods(api):
    assert (
        api.call("POST", "/v1/runs", {**GOOD, "dataset_id": "0" * 64})[1]["error"]
        == "unknown_dataset"
    )
    assert api.call("GET", "/v1/other")[0] == 404
    assert api.call("GET", "/v1/runs")[0] == 405
    assert api.call("POST", f"/v1/datasets/{CSV_SHA}?kind=csv")[0] == 405
    assert api.call("PATCH", "/v1/runs")[0] == 405


def test_artifact_paths_cannot_traverse(api):
    for path in (
        "/v1/runs/abcdef123456/artifacts/..%2f..%2fsecret.txt",
        "/v1/runs/abcdef123456/artifacts/../../datasets/x",
        "/v1/runs/..%2f..%2fdatasets/artifacts/x.json",
        "/v1/runs/abcdef123456/artifacts/CON",
        "/v1/runs/abcdef123456/artifacts/.hidden",
    ):
        assert api.call("GET", path)[0] in (400, 404), path


def test_duplicate_exec_id_conflicts_until_deleted(api):
    keep = "open('/out/results.json', 'w').write('{}')"
    status, body = api.run(keep, exec_id="dupe12345678")
    assert status == 200
    assert api.run("print(2)", exec_id="dupe12345678")[0] == 409
    api.call("DELETE", "/v1/runs/dupe12345678")
    assert api.run(keep, exec_id="dupe12345678")[0] == 200
    api.call("DELETE", "/v1/runs/dupe12345678")


# ------------------------------------------------------------------ dataset upload --------------
def test_dataset_digest_is_verified_and_failed_uploads_leave_nothing(api):
    wrong = "f" * 64
    status, body = api.call("PUT", f"/v1/datasets/{wrong}?kind=csv", CSV)
    assert status == 400 and body["error"] == "digest_mismatch"
    assert not list(api.manager.layout.datasets.glob(f"{wrong}*"))
    assert not list(api.manager.layout.datasets.glob(".upload-*"))


def test_dataset_upload_is_idempotent_and_validated(api):
    assert api.call("PUT", f"/v1/datasets/{CSV_SHA}?kind=csv", CSV)[0] in (200, 201)
    assert api.call("PUT", f"/v1/datasets/{CSV_SHA}?kind=csv", CSV)[1]["status"] == "exists"
    assert api.call("PUT", f"/v1/datasets/{CSV_SHA}?kind=exe", CSV)[1]["error"] == "invalid_kind"
    assert (
        api.call("PUT", "/v1/datasets/not-a-hash?kind=csv", CSV)[1]["error"] == "invalid_dataset_id"
    )
    assert api.call("PUT", f"/v1/datasets/{CSV_SHA}?kind=csv", b"")[1]["error"] == "empty_body"
    fake_xlsx = b"plain text, not a zip"
    sha = hashlib.sha256(fake_xlsx).hexdigest()
    assert api.call("PUT", f"/v1/datasets/{sha}?kind=xlsx", fake_xlsx)[1]["error"] == "bad_content"
    binary = b"a,b\n\x00\x01\x02"
    sha = hashlib.sha256(binary).hexdigest()
    assert api.call("PUT", f"/v1/datasets/{sha}?kind=csv", binary)[1]["error"] == "bad_content"


def test_oversized_dataset_is_refused_before_reading(api):
    head = (
        f"PUT /v1/datasets/{CSV_SHA}?kind=csv HTTP/1.1\r\nHost: 127.0.0.1:{api.server.port}\r\n"
        f"Authorization: Bearer {api.token}\r\nContent-Length: {api.cfg.max_dataset_bytes + 1}\r\n\r\n"
    )
    assert b" 413 " in raw(api, head).split(b"\r\n")[0]


# ------------------------------------------------------------------ the one command builder ----
def spec(tmp_path: Path, **env: str) -> ContainerSpec:
    return ContainerSpec(
        "dpsbx-abc", "abc", "sha256:" + "a" * 64, tmp_path / "in", tmp_path / "out",
        {"DATA_PATH": "/in/data.csv", **env}, "512m", "1.0", 128, 20 * 1024 * 1024,
    )  # fmt: skip


def test_create_command_is_fixed_and_contains_every_isolation_flag(tmp_path):
    argv = build_create_argv("docker", spec(tmp_path))
    joined = " ".join(argv)
    for required in (
        "--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
        "--user 10001:10001", "--memory 512m", "--memory-swap 512m", "--pids-limit 128",
        "--pull never", "--log-driver none",
    ):  # fmt: skip
        assert required in joined, required
    flags = set(argv)
    for forbidden in (
        "--privileged", "--cap-add", "--pid", "--ipc", "--uts", "-v", "--volume", "--device",
        "--add-host", "--env-file", "--userns", "-p", "--publish", "--net",
    ):  # fmt: skip
        assert forbidden not in flags, forbidden
    assert argv[argv.index("--network") + 1] == "none"
    assert "docker.sock" not in joined
    assert argv[-4:] == ["sha256:" + "a" * 64, "python", "-I", "/in/analysis.py"]
    assert sum(1 for a in argv if a == "--mount") == 2


def test_hostile_sheet_value_stays_one_argv_element_and_no_shell_is_used(tmp_path):
    hostile = 'x"; rm -rf / #'
    argv = build_create_argv("docker", spec(tmp_path, SHEET=hostile))
    assert f"SHEET={hostile}" in argv  # a single element: never interpreted by a shell
    assert argv.count("-e") == 2


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"SANDBOX_TOKEN": "t" * 32, "SANDBOX_BIND_HOST": "0.0.0.0"},  # noqa: S104
        {"SANDBOX_TOKEN": "short"},
    ],
)
def test_broker_process_refuses_to_start_with_unsafe_configuration(env):
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "sandbox_service.broker"],
        cwd=Path(__file__).resolve().parents[2],
        env={"PATH": "", "SYSTEMROOT": "C:\Windows", **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 2
    assert "refused to start" in proc.stderr


def test_expired_datasets_and_artifacts_are_removed_but_fresh_ones_kept(api, engine):
    import os
    import time

    from sandbox_service.broker.config import ImageLock
    from sandbox_service.broker.manager import RunManager

    sha = api.upload(b"old,data\n1,2\n")
    old = api.manager.layout.dataset_path(sha, "csv")
    fresh_sha = api.upload(b"fresh,data\n3,4\n")
    stale_art = api.manager.layout.artifact_dir("staleartifact01")
    stale_art.mkdir()
    (stale_art / "results.json").write_text("{}")
    long_ago = time.time() - api.cfg.dataset_ttl_s - 60
    os.utime(old, (long_ago, long_ago))
    os.utime(stale_art, (long_ago, long_ago))
    removed = RunManager(api.cfg, engine, ImageLock.load(api.cfg.lock_path)).startup_reap()
    assert f"datasets/{sha}.csv" in removed["directories"]
    assert "artifacts/staleartifact01" in removed["directories"]
    assert api.manager.layout.find_dataset(fresh_sha) is not None


def test_link_like_entries_are_never_copied(tmp_path, monkeypatch):
    """Host symlinks cannot be created without a Windows privilege, so the branch is driven by a
    stub: any entry flagged link-like must be rejected and its content must not be copied."""
    from sandbox_service.broker import staging

    out, dest = tmp_path / "out", tmp_path / "dest"
    out.mkdir()
    (out / "evil.txt").write_text("SECRET-HOST-CONTENT")
    (out / "good.json").write_text("{}")
    monkeypatch.setattr(staging, "_is_link_like", lambda entry: entry.name == "evil.txt")
    cfg = BrokerConfig(token="t" * 32, root=tmp_path)  # noqa: S106
    result = staging.collect_artifacts(out, dest, cfg)
    assert [a.name for a in result.artifacts] == ["good.json"]
    assert {"name": "evil.txt", "reason": "symlink"} in result.rejected
    assert not (dest / "evil.txt").exists()


def test_collect_enforces_count_and_total_caps(tmp_path):
    from dataclasses import replace

    from sandbox_service.broker import staging

    out, dest = tmp_path / "out", tmp_path / "dest"
    out.mkdir()
    for i in range(5):
        (out / f"f{i}.csv").write_bytes(b"x" * 100)
    cfg = replace(BrokerConfig(token="t" * 32, root=tmp_path), max_artifacts=3)  # noqa: S106
    result = staging.collect_artifacts(out, dest, cfg)
    assert len(result.artifacts) == 3
    assert [r["reason"] for r in result.rejected] == ["too_many_files"] * 2
    tight = replace(cfg, max_artifacts=20, max_out_total_bytes=250)
    result = staging.collect_artifacts(out, tmp_path / "dest2", tight)
    assert len(result.artifacts) == 2 and result.rejected[0]["reason"] == "total_too_large"


def test_a_stalled_engine_cannot_hang_cleanup_calls(monkeypatch, caplog):
    """Docker CLI calls are bounded; cleanup-class calls swallow a stall (logged) instead of hanging."""
    import subprocess

    from sandbox_service.broker import runtime as rt

    def stalled(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(rt.subprocess, "run", stalled)
    docker = rt.DockerRuntime(docker="docker")
    docker.kill("dpsbx-x")  # no exception
    assert docker.state("dpsbx-x") == rt.ContainerState(-1, False)
    with caplog.at_level("ERROR"):
        docker.remove("dpsbx-x")
    assert "engine stalled" in caplog.text
    assert rt.CLI_TIMEOUT <= 30
