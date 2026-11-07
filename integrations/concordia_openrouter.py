"""Concordia <-> OpenRouter adapter.

Concordia's LLM interface is tiny: implement `sample_text` and `sample_choice`.
OpenRouter is OpenAI-compatible, so we reuse the `openai` client with a custom
`base_url`. This is an OPTIONAL integration — install with:

    pip install "gdm-concordia[openai]"

It is intentionally not a core dependency of evil-ai-village.
"""

from __future__ import annotations

import os
import re
from collections.abc import Collection, Mapping, Sequence

from concordia.language_model import language_model


class OpenRouterLanguageModel(language_model.LanguageModel):
    """A Concordia LanguageModel backed by any OpenRouter model."""

    def __init__(
        self,
        model_name: str,
        *,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 180.0,
    ):
        from openai import OpenAI  # imported lazily; only needed for this adapter

        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        self._model_name = model_name
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            default_headers={
                "HTTP-Referer": os.environ.get(
                    "OPENROUTER_REFERER", "https://github.com/ajitnath/evil-ai-village"
                ),
                "X-Title": os.environ.get("OPENROUTER_TITLE", "evil-ai-village"),
            },
        )

    def sample_text(
        self,
        prompt: str,
        *,
        max_tokens: int = language_model.DEFAULT_MAX_TOKENS,
        terminators: Collection[str] = language_model.DEFAULT_TERMINATORS,
        temperature: float = language_model.DEFAULT_TEMPERATURE,
        top_p: float = language_model.DEFAULT_TOP_P,
        top_k: int = language_model.DEFAULT_TOP_K,
        timeout: float = language_model.DEFAULT_TIMEOUT_SECONDS,
        seed: int | None = None,
    ) -> str:
        del top_p, top_k, timeout  # not uniformly supported by all OpenRouter models
        messages = [
            {
                "role": "system",
                "content": (
                    "You always continue the user's input and never repeat what "
                    "the user already said."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        kwargs = {"model": self._model_name, "messages": messages, "max_tokens": max_tokens}
        # temperature/seed are unsupported by some reasoning models; try, then fall back.
        try:
            resp = self._client.chat.completions.create(temperature=temperature, **kwargs)
        except Exception:  # noqa: BLE001
            resp = self._client.chat.completions.create(**kwargs)
        text = (resp.choices[0].message.content or "").strip()
        for term in terminators:
            if term in text:
                text = text.split(term)[0]
        return text

    def sample_choice(
        self,
        prompt: str,
        responses: Sequence[str],
        *,
        seed: int | None = None,
    ) -> tuple[int, str, Mapping[str, object]]:
        del seed
        options = "\n".join(f"{i}. {r}" for i, r in enumerate(responses))
        query = (
            f"{prompt}\n\nChoose exactly one of the following options. "
            f"Reply with ONLY the option number.\n{options}\nAnswer:"
        )
        for _ in range(6):
            out = self.sample_text(query, max_tokens=16, temperature=0.0)
            m = re.search(r"\d+", out)
            if m:
                idx = int(m.group())
                if 0 <= idx < len(responses):
                    return idx, responses[idx], {"raw": out}
        return 0, responses[0], {"raw": "fallback", "reason": "unparseable choice"}

    def close(self) -> None:
        self._client.close()


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    model_name = sys.argv[1] if len(sys.argv) > 1 else "qwen/qwen3.5-9b"
    lm = OpenRouterLanguageModel(model_name)
    print("sample_text:", repr(lm.sample_text("Say the single word: ready", max_tokens=8)))
    i, r, info = lm.sample_choice(
        "Which is a security tool?",
        ["Stockfish", "gdb", "Photoshop"],
    )
    print("sample_choice:", i, repr(r), info)
    lm.close()
