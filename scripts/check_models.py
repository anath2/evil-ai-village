#!/usr/bin/env python3
"""Verify that the configured OpenRouter models respond.

    python scripts/check_models.py [configs/village.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from village.config import load_config  # noqa: E402
from village.models import OpenRouterClient  # noqa: E402


def main(config_path: str = "configs/village.yaml") -> int:
    cfg = load_config(config_path)
    client = OpenRouterClient()
    failures = 0
    for spec in cfg.agents:
        try:
            res = client.chat(
                spec.model,
                [{"role": "user", "content": "Reply with the single word: ready"}],
                temperature=0.0,
                max_tokens=8,
            )
            print(f"OK   {spec.name:8s} {spec.model:38s} -> {res.text[:40]!r}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {spec.name:8s} {spec.model:38s} -> {exc}")
    client.close()
    print(f"\n{len(cfg.agents) - failures}/{len(cfg.agents)} models responded")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "configs/village.yaml"))
