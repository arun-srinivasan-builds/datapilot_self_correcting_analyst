"""Async HTTP client for the sandbox broker (transport and auth faults -> SandboxUnavailable)."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from datapilot.sandbox.contracts import SandboxUnavailableError

CONNECT_TIMEOUT = 5.0


class BrokerClient:
    def __init__(self, base_url: str, token: str, *, request_margin_s: float = 20.0) -> None:
        if not token:
            raise SandboxUnavailableError("SANDBOX_TOKEN is not configured")
        self._uds: str | None = None
        if base_url.startswith("unix://"):
            self._uds = base_url.removeprefix("unix://")
            base_url = "http://broker"  # Host header the broker expects over the socket
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._margin = request_margin_s

    def _client(self, timeout: float) -> httpx.AsyncClient:
        transport = httpx.AsyncHTTPTransport(uds=self._uds) if self._uds else None
        return httpx.AsyncClient(
            transport=transport,
            base_url=self._base,
            headers=self._headers,
            timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT),
        )

    async def _request(
        self, method: str, path: str, *, timeout: float = 30.0, **kwargs: Any
    ) -> httpx.Response:
        try:
            async with self._client(timeout) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise SandboxUnavailableError(f"broker unreachable: {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise SandboxUnavailableError("broker rejected the credentials")
        if response.status_code >= 400:
            try:
                code = response.json().get("error", response.status_code)
            except ValueError:
                code = response.status_code
            raise SandboxUnavailableError(f"broker returned an error: {code}")
        return response

    async def healthy(self) -> bool:
        try:
            await self._request("GET", "/healthz", timeout=5.0)
        except SandboxUnavailableError:
            return False
        return True

    async def upload_dataset(self, data: bytes, kind: str) -> str:
        sha = hashlib.sha256(data).hexdigest()
        await self._request(
            "PUT", f"/v1/datasets/{sha}", params={"kind": kind}, content=data, timeout=120.0
        )
        return sha

    async def run(
        self, *, exec_id: str, code: str, dataset_id: str, sheet: str | None, timeout_s: int
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"exec_id": exec_id, "code": code, "dataset_id": dataset_id}
        if sheet:
            body["sheet"] = sheet
        body["timeout_s"] = timeout_s
        response = await self._request(
            "POST", "/v1/runs", json=body, timeout=timeout_s + self._margin
        )
        return dict(response.json())

    async def delete(self, exec_id: str) -> None:
        await self._request("DELETE", f"/v1/runs/{exec_id}", timeout=10.0)

    async def artifact(self, exec_id: str, name: str) -> bytes:
        return (await self._request("GET", f"/v1/runs/{exec_id}/artifacts/{name}")).content
