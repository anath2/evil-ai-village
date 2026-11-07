"""OpenRouter chat client (text-only, OpenAI-compatible)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import httpx

from .config import openrouter_base_url, openrouter_headers


class BudgetExceeded(RuntimeError):
    """Raised when a run's USD spend cap has been reached."""


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    raw: dict | None = None


class OpenRouterClient:
    def __init__(self, timeout: float = 180.0, max_retries: int = 3, budget_usd: float = 0.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.budget_usd = float(budget_usd or 0.0)
        self._client = httpx.Client(timeout=timeout)
        self._cost_lock = threading.Lock()
        self.total_cost_usd = 0.0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def _check_budget(self) -> None:
        if self.budget_usd and self.total_cost_usd >= self.budget_usd:
            raise BudgetExceeded(
                f"budget cap ${self.budget_usd:.4f} reached (spent ${self.total_cost_usd:.4f})"
            )

    @property
    def budget_exhausted(self) -> bool:
        return bool(self.budget_usd) and self.total_cost_usd >= self.budget_usd

    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stop: list[str] | None = None,
    ) -> ChatResult:
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop

        self._check_budget()
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.post(
                    f"{openrouter_base_url()}/chat/completions",
                    headers=openrouter_headers(),
                    json=payload,
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                data = resp.json()
                return self._parse(model, data)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"OpenRouter call failed for {model}: {last_err}")

    def _parse(self, model: str, data: dict) -> ChatResult:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"No choices returned by {model}: {data}")
        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()
        # Some reasoning models put output in `reasoning` and leave content empty.
        if not text and message.get("reasoning"):
            text = str(message["reasoning"]).strip()
        usage = data.get("usage") or {}
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        cost = float(usage.get("cost") or 0.0)
        with self._cost_lock:
            self.total_cost_usd += cost
            self.total_prompt_tokens += pt
            self.total_completion_tokens += ct
        return ChatResult(text=text, prompt_tokens=pt, completion_tokens=ct, cost_usd=cost, raw=data)

    def close(self) -> None:
        self._client.close()
