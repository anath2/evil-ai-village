#!/usr/bin/env python3
"""CLI entrypoint for the Evil AI Village.

Usage:
    python run.py run                 # run the village (default)
    python run.py board               # print the shared board
    python run.py tasks               # materialize task workspaces only
    python run.py check-models        # verify OpenRouter access per model
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent / "src"))

from village.config import load_config  # noqa: E402
from village.orchestrator import Orchestrator  # noqa: E402


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if getattr(args, "budget", None) is not None:
        cfg.village.budget_usd = args.budget
    Orchestrator(cfg).run()
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    from village.sweep import run_sweep

    cfg = load_config(args.config)
    run_sweep(cfg, getattr(args, "budget", None))
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    from village.board import Board
    from village.cybergym import prepare_task
    from village.models import OpenRouterClient

    cfg = load_config(args.config)
    orch = Orchestrator(cfg)
    board = Board(cfg.abspath(cfg.board.path))
    for i, spec in enumerate(cfg.agents):
        task_id = orch._assign_task(spec, i)
        info = prepare_task(cfg, task_id, orch.workspaces / spec.name)
        print(f"{spec.name:8s} task={info.task_id:16s} -> {info.workspace}")
    return 0


def cmd_board(args: argparse.Namespace) -> int:
    from village.board import Board, format_board

    cfg = load_config(args.config)
    board = Board(cfg.abspath(cfg.board.path))
    print(format_board(board.all()))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from village.analyze import analyze_run, write_outputs

    cfg = load_config(args.config)
    analysis = analyze_run(cfg, args.run, getattr(args, "round", None))
    graph_path, report_path = write_outputs(analysis, Path(analysis["log_dir"]))
    print(report_path.read_text())
    print(f"\nwrote {graph_path}\nwrote {report_path}")
    return 0


def cmd_check_models(args: argparse.Namespace) -> int:
    from scripts.check_models import main as check_main

    return check_main(args.config)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evil AI Village")
    p.add_argument("--config", default="configs/village.yaml", help="path to village config")
    p.add_argument("--budget", type=float, default=None, help="USD spend cap (overrides config)")
    # Allow --config/--budget both before AND after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS)
    common.add_argument("--budget", type=float, default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="command")
    sub.add_parser("run", parents=[common], help="run the village")
    sub.add_parser("sweep", parents=[common], help="run a capability-mix sweep")
    sub.add_parser("board", parents=[common], help="print the shared board")
    sub.add_parser("tasks", parents=[common], help="materialize task workspaces only")
    sub.add_parser("check-models", parents=[common], help="verify OpenRouter model access")
    analyze = sub.add_parser("analyze", parents=[common], help="generate the social report for a run")
    analyze.add_argument("--run", default=None, help="run id (default: latest)")
    analyze.add_argument("--round", default=None, help="round name (default: latest)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"
    return {
        "run": cmd_run,
        "sweep": cmd_sweep,
        "board": cmd_board,
        "tasks": cmd_tasks,
        "check-models": cmd_check_models,
        "analyze": cmd_analyze,
    }[command](args)


if __name__ == "__main__":
    raise SystemExit(main())
