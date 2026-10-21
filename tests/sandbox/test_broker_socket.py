"""Unix-socket transport of the broker (VPS design). Needs AF_UNIX: skipped on Windows hosts and run
inside a Linux container instead (see docs/DEPLOY.md)."""

from __future__ import annotations

import os
import socket
import stat
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from datapilot.sandbox.client import BrokerClient
from datapilot.sandbox.contracts import SandboxUnavailableError
from sandbox_service.broker.config import BrokerConfig, ConfigError, ImageLock
from sandbox_service.broker.manager import RunManager
from sandbox_service.broker.server import make_server

pytestmark = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="needs AF_UNIX (Linux)")
TOKEN = "t" * 32


class _NoRuntime:
    """The health endpoint never touches the container runtime."""

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - only hit on a test bug
        raise AssertionError(f"runtime.{name} must not be used by these tests")


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[str, BrokerConfig]]:
    sock_dir = tmp_path / "run"
    sock_dir.mkdir()
    path = str(sock_dir / "broker.sock")
    cfg = BrokerConfig(token=TOKEN, root=tmp_path / "root", socket_path=path)
    lock = ImageLock.load(cfg.lock_path)
    server = make_server(cfg, RunManager(cfg, _NoRuntime(), lock))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield path, cfg
    server.shutdown()
    server.server_close()


async def test_client_reaches_the_broker_over_the_socket(served: tuple[str, BrokerConfig]) -> None:
    path, _ = served
    assert await BrokerClient(f"unix://{path}", TOKEN).healthy()


def test_socket_is_group_only_never_world_accessible(served: tuple[str, BrokerConfig]) -> None:
    path, _ = served
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode & 0o007 == 0 and mode & 0o060 == 0o060


async def test_wrong_host_header_is_refused_over_the_socket(
    served: tuple[str, BrokerConfig],
) -> None:
    path, _ = served
    transport = httpx.AsyncHTTPTransport(uds=path)
    async with httpx.AsyncClient(transport=transport, base_url="http://evil.example") as client:
        response = await client.get("/healthz")
    assert response.status_code == 421


async def test_missing_token_is_rejected_on_authenticated_routes(
    served: tuple[str, BrokerConfig],
) -> None:
    path, _ = served
    bad = BrokerClient(f"unix://{path}", "x" * 32)
    with pytest.raises(SandboxUnavailableError):
        await bad.upload_dataset(b"a,b\n1,2\n", "csv")


def test_stale_socket_file_is_replaced_but_regular_files_are_never_deleted(tmp_path: Path) -> None:
    stale = tmp_path / "stale.sock"
    old = socket.socket(socket.AF_UNIX)
    old.bind(str(stale))
    old.close()  # leaves a stale socket file behind
    cfg = BrokerConfig(token=TOKEN, root=tmp_path / "r", socket_path=str(stale))
    manager = RunManager(cfg, _NoRuntime(), ImageLock.load(cfg.lock_path))
    make_server(cfg, manager).server_close()
    regular = tmp_path / "keep.txt"
    regular.write_text("precious")
    cfg2 = BrokerConfig(token=TOKEN, root=tmp_path / "r", socket_path=str(regular))
    with pytest.raises(OSError):
        make_server(cfg2, RunManager(cfg2, _NoRuntime(), manager.lock))
    assert regular.read_text() == "precious"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"socket_path": "relative.sock"},
        {"socket_path": "/run/has space/x.sock"},
        {"socket_path": "/run/x.sock", "socket_mode": 0o666},
        {"socket_path": "/run/x.sock", "socket_mode": 0o664},
    ],
)
def test_socket_config_validation(kwargs: dict[str, Any], tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        BrokerConfig(token=TOKEN, root=tmp_path, **kwargs).validate()
