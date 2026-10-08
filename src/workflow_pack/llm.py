"""The only place that talks to a language model.

`OpenRouterClient` uses the OpenAI-compatible SDK pointed at OpenRouter.
`FakeClient` (in fake_llm.py) has the same `chat()` method and never touches the network;
tests and `--dry-run` use it.
"""

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from workflow_pack.common import now_iso
from workflow_pack.config import Settings


@dataclass
class LLMReply:
    text: str
    model: str
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class TransientLLMError(Exception):
    """A failure worth retrying (timeout, rate limit, 5xx)."""


class BudgetExceeded(Exception):
    pass


class LLMClient(Protocol):
    def chat(self, task: str, model_role: str, system: str, user: str, item_id: str) -> LLMReply: ...


def with_retries(call: Callable[[], LLMReply], max_tries: int = 3, base_delay: float = 1.0, sleep=time.sleep):
    """Retry transient errors with exponential backoff: wait 1s, then 2s (then give up)."""
    for attempt in range(1, max_tries + 1):
        try:
            return call()
        except TransientLLMError:
            if attempt == max_tries:
                raise
            sleep(base_delay * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def write_trace(trace_path: Path | None, record: dict) -> None:
    if trace_path is None:
        return
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class OpenRouterClient:
    def __init__(self, settings: Settings, trace_path: Path | None = None, max_cost_usd: float | None = None):
        if not settings.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to Portfolio Projects/.env (never commit it).")
        from openai import OpenAI  # imported here so tests never need network libraries configured

        self.settings = settings
        # The SDK's own retries are off: retries happen in with_retries() so they are visible and logged.
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, max_retries=0, timeout=60)
        self.trace_path = trace_path
        self.max_cost_usd = max_cost_usd or float(os.getenv("MAX_COST_PER_RUN_USD", "3"))
        self.total_cost_usd = 0.0

    def chat(self, task: str, model_role: str, system: str, user: str, item_id: str) -> LLMReply:
        if self.total_cost_usd >= self.max_cost_usd:
            raise BudgetExceeded(f"run cost reached US${self.total_cost_usd:.2f}; stopping as agreed in AGENTS.md")
        model = self.settings.model_for(model_role)
        reply = with_retries(lambda: self._call_once(task, model, system, user, item_id))
        self.total_cost_usd += reply.cost_usd
        return reply

    def _call_once(self, task: str, model: str, system: str, user: str, item_id: str) -> LLMReply:
        import openai

        started = time.perf_counter()
        trace = {"timestamp": now_iso(), "task": task, "item_id": item_id, "model": model}
        try:
            response = self.client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                extra_body={"usage": {"include": True}},  # OpenRouter adds the cost to `usage`
            )
        except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError) as e:
            write_trace(self.trace_path, {**trace, "outcome": f"retryable_error: {type(e).__name__}"})
            raise TransientLLMError(str(e)) from e
        usage = response.usage
        reply = LLMReply(
            text=response.choices[0].message.content or "",
            model=response.model or model,
            latency_s=round(time.perf_counter() - started, 3),
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cost_usd=float(getattr(usage, "cost", 0) or 0),
        )
        write_trace(self.trace_path, {**trace, **asdict(reply), "outcome": "ok"})
        return reply


def make_client(dry_run: bool, settings: Settings, trace_path: Path | None = None) -> LLMClient:
    if dry_run:
        from workflow_pack.fake_llm import FakeClient

        return FakeClient(trace_path=trace_path)
    return OpenRouterClient(settings, trace_path=trace_path)
