"""`ExecutionBackend` implementation backed by the sandbox broker."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from pathlib import Path

from datapilot.config import Settings
from datapilot.sandbox.client import BrokerClient
from datapilot.sandbox.contracts import ArtifactInfo, ExecutionResult, SandboxUnavailableError

log = logging.getLogger(__name__)
MAX_RESULTS_BYTES = 1024 * 1024


class BrokerBackend:
    """Runs scripts against one dataset. Cancelling `run` kills the container via the broker."""

    def __init__(
        self,
        client: BrokerClient,
        dataset: bytes,
        kind: str,
        *,
        sheet: str | None = None,
        timeout_s: int = 60,
    ) -> None:
        self._client, self._dataset, self._kind = client, dataset, kind
        self._sheet, self._timeout = sheet, timeout_s
        self._dataset_id: str | None = None
        self._upload_lock = asyncio.Lock()

    @classmethod
    def from_settings(
        cls, settings: Settings, path: Path, *, sheet: str | None = None
    ) -> BrokerBackend:
        kind = "xlsx" if path.suffix.lower() in (".xlsx", ".xlsm") else "csv"
        client = BrokerClient(settings.sandbox_url, settings.sandbox_token.get_secret_value())
        return cls(
            client,
            path.read_bytes(),
            kind,
            sheet=sheet,
            timeout_s=settings.sandbox_timeout_seconds,
        )

    async def _ensure_dataset(self) -> str:
        async with self._upload_lock:
            if self._dataset_id is None:
                self._dataset_id = await self._client.upload_dataset(self._dataset, self._kind)
            return self._dataset_id

    async def run(self, code: str, *, run_id: str) -> ExecutionResult:
        exec_id = uuid.uuid4().hex
        dataset_id = await self._ensure_dataset()
        try:
            data = await self._client.run(
                exec_id=exec_id,
                code=code,
                dataset_id=dataset_id,
                sheet=self._sheet,
                timeout_s=self._timeout,
            )
        except asyncio.CancelledError:
            # The caller (stop/timeout) cancelled us: make sure the container does not outlive it.
            with contextlib.suppress(SandboxUnavailableError, asyncio.CancelledError):
                await asyncio.shield(self._client.delete(exec_id))
            raise
        results_json = await self._fetch_results(exec_id, data)
        try:
            return ExecutionResult(
                status=data["status"],
                exit_code=int(data["exit_code"]),
                stdout=str(data["stdout"]),
                stderr=str(data["stderr"]),
                duration_ms=int(data["duration_ms"]),
                artifacts=tuple(
                    ArtifactInfo(a["name"], int(a["size"]), a["sha256"]) for a in data["artifacts"]
                ),
                truncated=bool(data["truncated"]),
                exec_id=exec_id,
                results_json=results_json,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SandboxUnavailableError("broker returned a malformed result") from exc

    async def _fetch_results(self, exec_id: str, data: dict) -> str | None:
        """results.json is small by contract; fetch it so the executor can validate it."""
        entry = next(
            (a for a in data.get("artifacts", []) if a.get("name") == "results.json"), None
        )
        if (
            entry is None
            or data.get("status") != "ok"
            or int(entry.get("size", 0)) > MAX_RESULTS_BYTES
        ):
            return None
        raw = await self._client.artifact(exec_id, "results.json")
        return raw.decode("utf-8", "replace")

    async def fetch_artifact(self, result: ExecutionResult, name: str) -> bytes:
        return await self._client.artifact(result.exec_id, name)

    async def release(self, result: ExecutionResult) -> None:
        """Ask the broker to drop the stored artifacts of this execution."""
        with contextlib.suppress(SandboxUnavailableError):
            await self._client.delete(result.exec_id)
