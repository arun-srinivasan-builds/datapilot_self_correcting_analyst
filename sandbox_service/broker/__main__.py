"""Run the broker:  .venv\\Scripts\\python.exe -m sandbox_service.broker

Environment: SANDBOX_TOKEN (>=24 chars, required), SANDBOX_BIND_HOST (loopback only),
SANDBOX_PORT, SANDBOX_ROOT, SANDBOX_TIMEOUT_SECONDS, MAX_UPLOAD_MB.
"""

from __future__ import annotations

import logging
import sys

from sandbox_service.broker.config import BrokerConfig, ConfigError, ImageLock
from sandbox_service.broker.manager import RunManager
from sandbox_service.broker.runtime import DockerRuntime
from sandbox_service.broker.server import make_server

log = logging.getLogger("sandbox")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        cfg = BrokerConfig.from_env()
        lock = ImageLock.load(cfg.lock_path)
        runtime = DockerRuntime()
        runtime.verify_image(lock.image_id)
    except (ConfigError, RuntimeError) as err:
        log.error("broker refused to start: %s", err)
        return 2
    manager = RunManager(cfg, runtime, lock)
    manager.startup_reap()
    server = make_server(cfg, manager)
    log.info("broker listening on %s:%s (loopback only)", cfg.host, server.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
