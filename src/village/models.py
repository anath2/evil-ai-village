"""Provider-neutral text inference with shared usage and budget accounting."""

from __future__ import annotations

import math
import os
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
    reported_cost: float | None = None


class InferenceClient:
    """Shared text inference interface, accounting, and HTTP retry handling."""

    provider = "openrouter"
    cost_available = True
    cost_unit = "usd"

    def __init__(self, timeout: float = 180.0, max_retries: int = 3, budget_usd: float = 0.0,
                 transport: httpx.BaseTransport | None = None):
        self.timeout = timeout
        if max_retries < 1:
            raise ValueError("max_retries must allow at least one attempt")
        self.max_retries = max_retries
        self.budget_usd = float(budget_usd or 0.0)
        if not math.isfinite(self.budget_usd) or self.budget_usd < 0:
            raise ValueError("Budget must be a finite nonnegative number")
        self._cost_error = None
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._cost_lock = threading.Lock()
        self.total_cost_usd = 0.0
        self.total_reported_cost = 0.0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def _account_usage(self, data: dict, token_fields: tuple[str, str]):
        usage = data.get("usage") if isinstance(data, dict) else None
        usage = usage if isinstance(usage, dict) else {}

        def tokens(field):
            try:
                return max(0, int(usage.get(field) or 0))
            except (ValueError, TypeError, OverflowError):
                return 0

        pt, ct = (tokens(field) for field in token_fields)
        value = usage.get("cost")
        try:
            cost = float(value) if value is not None and not isinstance(value, bool) else None
        except (ValueError, TypeError, OverflowError):
            cost = None
        if cost is not None and (not math.isfinite(cost) or cost < 0):
            cost = None
        with self._cost_lock:
            self.total_prompt_tokens += pt
            self.total_completion_tokens += ct
            if cost is None:
                self.cost_available = False
                self._cost_error = (
                    f"{self.provider} usage.cost is missing or invalid; "
                    "stopping because the USD budget cannot be tracked"
                )
            else:
                self.total_reported_cost += cost
                if self.cost_unit == "usd":
                    self.total_cost_usd += cost
            error = self._cost_error if self.budget_usd else None
        if error:
            raise BudgetExceeded(error)
        return pt, ct, cost

    def _check_budget(self) -> None:
        with self._cost_lock:
            if self.budget_usd and self._cost_error:
                raise BudgetExceeded(self._cost_error)
            if self.budget_usd and self.total_cost_usd >= self.budget_usd:
                raise BudgetExceeded(
                    f"budget cap ${self.budget_usd:.6f} reached (spent ${self.total_cost_usd:.6f})"
                )

    @property
    def budget_exhausted(self) -> bool:
        with self._cost_lock:
            return bool(self.budget_usd and (
                self._cost_error or self.total_cost_usd >= self.budget_usd))

    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stop: list[str] | None = None,
    ) -> ChatResult:
        payload = self._payload(model, messages, temperature, max_tokens, stop)
        self._check_budget()
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            self._check_budget()
            try:
                resp = self._client.post(self._url(), headers=self._headers(), json=payload)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"{self.provider} HTTP {exc.response.status_code} for {model}") from None
                last_err = exc
            except httpx.TransportError as exc:
                last_err = exc
            else:
                try:
                    data = resp.json()
                except ValueError:
                    # A response with unreadable usage must not bypass a budget.
                    self._account_usage({}, ("prompt_tokens", "completion_tokens"))
                    raise RuntimeError(f"{self.provider} returned invalid JSON for {model}") from None
                return self._parse(model, data)
            if attempt + 1 < self.max_retries:
                time.sleep(2**attempt)
        raise RuntimeError(f"{self.provider} request failed for {model}: {type(last_err).__name__}")

    def _url(self):
        raise NotImplementedError

    def _headers(self):
        raise NotImplementedError

    def _payload(self, model, messages, temperature, max_tokens, stop):
        raise NotImplementedError

    def close(self) -> None:
        self._client.close()


class OpenRouterClient(InferenceClient):
    """Existing OpenRouter chat-completions contract."""

    def _url(self):
        base = openrouter_base_url().rstrip("/")
        return f"{base}/chat/completions"

    def _headers(self):
        return openrouter_headers()

    def _payload(self, model, messages, temperature, max_tokens, stop):
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop

        return payload

    def _parse(self, model: str, data: dict) -> ChatResult:
        pt, ct, cost = self._account_usage(data, ("prompt_tokens", "completion_tokens"))
        if not isinstance(data, dict):
            raise RuntimeError(f"OpenRouter returned an invalid response for {model}")
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"No choices returned by {model}")
        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()
        # Some reasoning models put output in `reasoning` and leave content empty.
        if not text and message.get("reasoning"):
            text = str(message["reasoning"]).strip()
        return ChatResult(
            text=text, prompt_tokens=pt, completion_tokens=ct,
            cost_usd=cost if cost is not None else 0.0, raw=data, reported_cost=cost,
        )


class AdaptionClient(InferenceClient):
    """Adaption Responses API, normalized to the village's text contract."""

    provider = "adaption"
    cost_available = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cost_unit = os.environ.get("ADAPTION_COST_UNIT", "unverified").strip().lower()
        self.cost_available = self.cost_unit == "usd"
        if self.budget_usd and self.cost_unit != "usd":
            self.close()
            raise ValueError("Adaption USD budgets require ADAPTION_COST_UNIT=usd after confirming usage.cost units with your provider")

    def _url(self):
        base = os.environ.get("ADAPTION_BASE_URL", "https://api.prod.adaptionlabs.ai/api/v1")
        return f"{base.rstrip('/')}/responses"

    def _headers(self):
        key = os.environ.get("ADAPTION_API_KEY", "")
        if not key or key.endswith("REPLACE_ME"):
            raise ValueError("Set ADAPTION_API_KEY in .env")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if org := os.environ.get("ADAPTION_ORGANIZATION_ID"):
            headers["X-Organization-Id"] = org
        return headers

    def _payload(self, model, messages, temperature, max_tokens, stop):
        if stop:
            raise ValueError("Adaption does not document stop sequences")
        return {"model": model, "input": messages, "temperature": temperature,
                "max_output_tokens": max_tokens, "stream": False, "store": False,
                "agentic_memory": False, "tools": [], "tool_choice": "none"}

    def _parse(self, model, data):
        # Incomplete/failed generations can still consume tokens and money.
        pt, ct, cost = self._account_usage(data, ("input_tokens", "output_tokens"))
        if not isinstance(data, dict):
            raise RuntimeError(f"Adaption returned an invalid response for {model}")
        if data.get("error") or data.get("status") != "completed":
            raise RuntimeError(
                f"Adaption response did not complete for {model}: "
                f"status={data.get('status')}, "
                f"reason={(data.get('incomplete_details') or {}).get('reason', 'unknown')}"
            )
        text = "".join(
            part.get("text", "")
            for item in data.get("output", []) if item.get("type") == "message"
            for part in item.get("content", []) if part.get("type") == "output_text"
        ).strip()
        if not text:
            raise RuntimeError(f"Adaption returned no reply text for {model}")
        return ChatResult(text=text, prompt_tokens=pt, completion_tokens=ct,
                          cost_usd=cost if self.cost_unit == "usd" and cost is not None else 0.0,
                          raw=data, reported_cost=cost)


def create_client(*, budget_usd=0.0, **kwargs) -> InferenceClient:
    provider = os.environ.get("INFERENCE_PROVIDER", "openrouter").lower().strip()
    clients = {"openrouter": OpenRouterClient, "adaption": AdaptionClient}
    if provider not in clients:
        raise ValueError(f"Unknown INFERENCE_PROVIDER: {provider}")
    return clients[provider](budget_usd=budget_usd, **kwargs)
