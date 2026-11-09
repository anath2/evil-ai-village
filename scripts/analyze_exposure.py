#!/usr/bin/env python3
"""Exposure vs adoption report for a village run (see docs/experiments/exposure-norms.md).

    python scripts/analyze_exposure.py --run reports/experiment-2026-11-09
    python scripts/analyze_exposure.py --board B.jsonl --logs LOGDIR [--metrics M.json]

Prints the pilot gates and, per pattern, how often agents used it after having
read it versus without having read it. Offline; no inference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from village.exposure import (
    FEATURES, dose_response, exposure_table, gate_metrics, load_agents, load_board,
)


def resolve(args) -> tuple[Path, Path, Path | None]:
    if args.run:
        run = Path(args.run)
        logs = sorted((run / "logs").glob("*/"))
        if not logs:
            raise SystemExit(f"no logs under {run / 'logs'}")
        return run / "board.jsonl", logs[0], run / "metrics.json"
    if not (args.board and args.logs):
        raise SystemExit("give --run, or both --board and --logs")
    return Path(args.board), Path(args.logs), Path(args.metrics) if args.metrics else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", help="a reports/<run> directory (board.jsonl, logs/, metrics.json)")
    p.add_argument("--board")
    p.add_argument("--logs")
    p.add_argument("--metrics")
    p.add_argument("--first-post-only", action="store_true", help="one post per agent")
    p.add_argument("--json", action="store_true", help="print machine-readable output")
    args = p.parse_args()

    board_path, log_dir, metrics_path = resolve(args)
    board = load_board(board_path)
    agents = load_agents(log_dir)
    metrics = json.loads(metrics_path.read_text()) if metrics_path and metrics_path.exists() else None

    result = {
        "gates": gate_metrics(agents, metrics),
        "exposure": exposure_table(board, agents, first_post_only=args.first_post_only),
        "dose_response": {f: dose_response(board, agents, f) for f in ("signal_prefix", "next_line")},
    }
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    g = result["gates"]
    print(f"agents {g['agents']}, posters {g['posters']}")
    print(f"read before first post: {g['read_before_first_post']}/{g['posters']} "
          f"({g['read_before_first_post_rate']:.0%})   valid action rate {g['valid_action_rate']:.0%}   "
          f"429 share {g['rate_limit_share']:.1%}")
    print(f"\n{'pattern':16} {'exposed':>14} {'unexposed':>14}  one-sided Fisher p")
    for name in FEATURES:
        r = result["exposure"][name]
        e = f"{r['exposed_used']}/{r['exposed_n']}"
        u = f"{r['unexposed_used']}/{r['unexposed_n']}"
        print(f"{name:16} {e:>14} {u:>14}  {r['p_one_sided']:.3g}")
    for feat, buckets in result["dose_response"].items():
        cells = "  ".join(f"{k}: {v['used']}/{v['n']}" for k, v in buckets.items())
        print(f"\ndose-response {feat} (earlier posts with it seen -> used/posts)\n  {cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
