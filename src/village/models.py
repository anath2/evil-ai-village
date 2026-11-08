"""Provider-neutral text inference with shared usage and budget accounting."""

from __future__ import annotations

import math
import os
import random
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
    # True when the provider stopped early (e.g. max_output_tokens) and we
    # returned partial text rather than failing the whole turn.
    truncated: bool = False


class InferenceClient:
    """Shared text inference interface, accounting, and HTTP retry handling."""

    provider = "openrouter"
    cost_available = True
    cost_unit = "usd"

    RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(self, timeout: float = 180.0, max_retries: int = 3, budget_usd: float = 0.0,
                 transport: httpx.BaseTransport | None = None,
                 backoff_base: float = 1.0, backoff_cap: float = 30.0,
                 model_concurrency: int = 0):
        self.timeout = timeout
        if max_retries < 1:
            raise ValueError("max_retries must allow at least one attempt")
        self.max_retries = max_retries
        self.backoff_base = float(backoff_base)
        self.backoff_cap = float(backoff_cap)
        # Per-model in-flight cap. 0 = unlimited (one shared client).
        self.model_concurrency = max(0, int(model_concurrency or 0))
        self._model_locks: dict[str, threading.Semaphore] = {}
        self._model_lock_guard = threading.Lock()
        # Retry accounting for the reliability metrics (guarded by _cost_lock).
        self.retry_count = 0
        self.truncated_count = 0
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

    def _model_semaphore(self, model: str) -> threading.Semaphore | None:
        """Return the per-model semaphore, or None when no cap is configured."""
        if self.model_concurrency <= 0:
            return None
        with self._model_lock_guard:
            sem = self._model_locks.get(model)
            if sem is None:
                sem = threading.Semaphore(self.model_concurrency)
                self._model_locks[model] = sem
            return sem

    def _backoff_seconds(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped."""
        ceiling = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        return random.uniform(0.0, max(0.0, ceiling))

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        """Parse a Retry-After header in seconds, if present and sane."""
        raw = response.headers.get("retry-after") if response is not None else None
        if not raw:
            return None
        try:
            value = float(raw.strip())
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        return min(value, 120.0)

    def _count_retry(self) -> None:
        with self._cost_lock:
            self.retry_count += 1

    def _count_truncated(self) -> None:
        with self._cost_lock:
            self.truncated_count += 1

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
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> ChatResult:
        """One model call, throttled by the per-model in-flight cap."""
        sem = self._model_semaphore(model)
        if sem is None:
            return self._chat(model, messages, temperature=temperature,
                              max_tokens=max_tokens, stop=stop)
        with sem:
            return self._chat(model, messages, temperature=temperature,
                              max_tokens=max_tokens, stop=stop)

    def _chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
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
                status = exc.response.status_code
                if status not in self.RETRYABLE_STATUS:
                    # 4xx other than 429 is our bug (bad payload/key): fail fast.
                    raise RuntimeError(
                        f"{self.provider} HTTP {status} for {model}"
                    ) from None
                last_err = exc
                self._count_retry()
                if attempt + 1 < self.max_retries:
                    # 429 honors Retry-After; 5xx uses jittered backoff.
                    delay = self._retry_after_seconds(exc.response) \
                        if status == 429 else None
                    time.sleep(delay if delay is not None else self._backoff_seconds(attempt))
            except httpx.TransportError as exc:
                last_err = exc
                self._count_retry()
                if attempt + 1 < self.max_retries:
                    time.sleep(self._backoff_seconds(attempt))
            else:
                try:
                    data = resp.json()
                except ValueError:
                    # A response with unreadable usage must not bypass a budget.
                    self._account_usage({}, ("prompt_tokens", "completion_tokens"))
                    raise RuntimeError(f"{self.provider} returned invalid JSON for {model}") from None
                return self._parse(model, data)
        raise RuntimeError(
            f"{self.provider} request failed for {model} after {self.max_retries} attempts: "
            f"{type(last_err).__name__}: {last_err}"
        )

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

    @staticmethod
    def _extract_text(data: dict) -> str:
        return "".join(
            part.get("text", "")
            for item in data.get("output", []) if item.get("type") == "message"
            for part in item.get("content", []) if part.get("type") == "output_text"
        ).strip()

    def _parse(self, model, data):
        # Incomplete/failed generations can still consume tokens and money.
        pt, ct, cost = self._account_usage(data, ("input_tokens", "output_tokens"))
        if not isinstance(data, dict):
            raise RuntimeError(f"Adaption returned an invalid response for {model}")
        truncated = False
        if data.get("error") or data.get("status") != "completed":
            reason = (data.get("incomplete_details") or {}).get("reason", "unknown")
            # A reasoning model that hit the output cap still produced usable
            # partial text. Failing the turn wastes the tokens we already paid for.
            if not data.get("error") and reason == "max_output_tokens":
                text = self._extract_text(data)
                if text:
                    truncated = True
                    self._count_truncated()
                    return ChatResult(
                        text=text, prompt_tokens=pt, completion_tokens=ct,
                        cost_usd=cost if self.cost_unit == "usd" and cost is not None else 0.0,
                        raw=data, reported_cost=cost, truncated=True,
                    )
            raise RuntimeError(
                f"Adaption response did not complete for {model}: "
                f"status={data.get('status')}, reason={reason}"
            )
        text = self._extract_text(data)
        if not text:
            raise RuntimeError(f"Adaption returned no reply text for {model}")
        return ChatResult(text=text, prompt_tokens=pt, completion_tokens=ct,
                          cost_usd=cost if self.cost_unit == "usd" and cost is not None else 0.0,
                          raw=data, reported_cost=cost, truncated=truncated)


def create_client(*, budget_usd=0.0, **kwargs) -> InferenceClient:
    provider = os.environ.get("INFERENCE_PROVIDER", "openrouter").lower().strip()
    clients = {"openrouter": OpenRouterClient, "adaption": AdaptionClient}
    if provider not in clients:
        raise ValueError(f"Unknown INFERENCE_PROVIDER: {provider}")
    return clients[provider](budget_usd=budget_usd, **kwargs)
