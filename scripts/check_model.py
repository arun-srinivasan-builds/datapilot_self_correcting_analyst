"""M2 step 0: minimal live compatibility check for the configured model.

Makes a handful of minimal calls, writes docs/evidence/m2/model-check.md (no secrets) and exits
non-zero if the model is unavailable or incompatible. It never substitutes another model.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datapilot.config import get_settings  # noqa: E402

log = logging.getLogger("check_model")
BASE = "https://api.openai.com/v1"
REPORT = ROOT / "docs" / "evidence" / "m2" / "model-check.md"
KEY_LIKE = re.compile(r"sk-[A-Za-z0-9_\-*\.]+")


def redact(text: str, key: str) -> str:
    if key:
        text = text.replace(key, "[REDACTED]")
    return KEY_LIKE.sub("[REDACTED]", text)[:600]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("autogen_core").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    if not settings.has_api_key:
        log.error("OPENAI_API_KEY is missing or still the placeholder. Set it in .env. Stopping.")
        return 2
    key = settings.openai_api_key.get_secret_value()
    model = settings.openai_model
    headers = {"Authorization": f"Bearer {key}"}
    rows: list[tuple[str, str, str]] = []
    ok = True

    def record(name: str, passed: bool, detail: str, *, required: bool = True) -> None:
        nonlocal ok
        ok = ok and (passed or not required)
        label = "PASS" if passed else ("FAIL" if required else "UNSUPPORTED (informational)")
        rows.append((name, label, redact(detail, key)))
        log.info("%s: %s", name, label)

    with httpx.Client(timeout=60, headers=headers) as http:
        r = http.get(f"{BASE}/models/{model}")
        record("models.retrieve", r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}")
        if r.status_code != 200:
            return write(rows, model, False)

        def chat(**extra: object) -> httpx.Response:
            body = {"model": model, "messages": [{"role": "user", "content": "Reply with: ok"}]}
            return http.post(f"{BASE}/chat/completions", json={**body, **extra})

        r = chat(max_completion_tokens=256)
        passed = r.status_code == 200
        detail = f"HTTP {r.status_code}"
        if passed:
            data = r.json()
            choice = data["choices"][0]
            detail += (
                f"; text={bool(choice['message'].get('content'))}"
                f"; finish={choice.get('finish_reason')}; usage={data.get('usage')}"
            )
        else:
            detail += " " + r.text
        record("chat.completions (max_completion_tokens)", passed, detail)
        for name, extra in (
            ("param: max_tokens", {"max_tokens": 64}),
            ("param: temperature=0", {"temperature": 0, "max_completion_tokens": 256}),
            ("param: seed", {"seed": 7, "max_completion_tokens": 256}),
        ):
            r = chat(**extra)
            record(
                name,
                r.status_code == 200,
                f"HTTP {r.status_code} " + (r.text[:300] if r.status_code != 200 else ""),
                required=False,
            )

    async def via_autogen() -> None:
        from autogen_core.models import UserMessage
        from autogen_ext.models.openai import OpenAIChatCompletionClient

        client = OpenAIChatCompletionClient(
            model=model,
            api_key=key,
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "unknown",
                "structured_output": True,
            },
        )
        try:
            res = await client.create([UserMessage(content="Reply with: ok", source="user")])
            record("autogen OpenAIChatCompletionClient", True, f"usage={res.usage}")
        finally:
            await client.close()

    try:
        asyncio.run(via_autogen())
    except Exception as exc:  # report, never substitute
        record("autogen OpenAIChatCompletionClient", False, f"{type(exc).__name__}: {exc}")
    return write(rows, model, ok)


def write(rows: list[tuple[str, str, str]], model: str, ok: bool) -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# gpt-6-luna compatibility check",
        "",
        f"- Model: `{model}`",
        f"- Run at: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"- Overall: **{'PASS' if ok else 'FAIL - stop and report; do not substitute'}**",
        "- Pricing: user-supplied; no price assumed.",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {n} | {s} | {d.replace('|', '/')} |" for n, s, d in rows]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("Report written to %s", REPORT)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
