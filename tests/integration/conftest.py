"""Stage 5 fixtures: the real broker, started with the SANDBOX_TOKEN from the gitignored .env."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from datapilot.config import Settings
from sandbox_service.broker.config import BrokerConfig, ImageLock
from sandbox_service.broker.manager import RunManager
from sandbox_service.broker.server import make_server
from sandbox_service.broker.staging import remove_tree
from tests.sandbox.conftest import ROOT, Api, _no_leaks_after_each_test, engine  # noqa: F401


@pytest.fixture(scope="module")
def api(engine) -> Iterator[Api]:  # noqa: F811 - deliberately overrides the sandbox suite's fixture
    token = Settings().sandbox_token.get_secret_value()  # from .env; never printed or logged
    if len(token) < 24:
        pytest.fail("SANDBOX_TOKEN is not configured in the gitignored .env")
    root = ROOT / ".sandbox" / "stage5-tests"
    remove_tree(root)
    cfg = BrokerConfig(token=token, root=root, port=0)
    manager = RunManager(cfg, engine, ImageLock.load(cfg.lock_path))
    manager.startup_reap()
    server = make_server(cfg, manager)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Api(server, manager, token, cfg)
    manager.shutdown()
    server.shutdown()
    server.server_close()
    remove_tree(root)
