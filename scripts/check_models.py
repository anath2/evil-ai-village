#!/usr/bin/env python3
"""Verify that the configured inference models respond.

    python scripts/check_models.py [configs/village.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from village.config import load_config  # noqa: E402
from village.models import BudgetExceeded, create_client  # noqa: E402


def main(config_path: str = "configs/village.yaml", budget_usd: float | None = None) -> int:
    cfg = load_config(config_path)
    client = create_client(budget_usd=cfg.village.budget_usd if budget_usd is None else budget_usd)
    failures = 0
    try:
        for spec in cfg.agents:
            try:
                res = client.chat(
                    spec.model,
                    [{"role": "user", "content": "Reply with the single word: ready"}],
                    temperature=0.0,
                    max_tokens=1024,
                )
                print(f"Usage: input={res.prompt_tokens} output={res.completion_tokens} reported_cost={res.reported_cost}")
                print(f"OK   {spec.name:8s} {spec.model:38s} -> {res.text[:40]!r}")
            except BudgetExceeded as exc:
                failures += len(cfg.agents) - cfg.agents.index(spec)
                print(f"STOP budget: {exc}")
                break
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {spec.name:8s} {spec.model:38s} -> {exc}")
    finally:
        client.close()
    print(f"\n{len(cfg.agents) - failures}/{len(cfg.agents)} models responded")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "configs/village.yaml"))
