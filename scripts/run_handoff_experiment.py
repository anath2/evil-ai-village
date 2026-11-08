#!/usr/bin/env python3
"""Run a bounded stale-handoff pilot, or recompute its summary without inference."""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from village.handoff_experiment import ARMS, CASES, PROTOCOL, WORKERS, run_episode, summarize
from village.models import create_client


def write_summary(output: Path, manifest: dict, episodes: list[dict]) -> dict:
    summary = summarize(episodes)
    summary["scheduled_episodes"] = len(manifest["schedule"])
    summary["recorded_episodes"] = len(episodes)
    summary["missing_episodes"] = len(manifest["schedule"]) - len(episodes)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# Stale-handoff pilot", "",
             f"Protocol: `{manifest['protocol']}`. Model: `{manifest['model']}`. Provider: `{manifest['provider']}`.",
             f"Run status: **{manifest['status']}**. Recorded {len(episodes)}/{len(manifest['schedule'])} episodes.",
             "", "Each episode contains three dependent workers; worker reports are not independent trials.",
             "False success means claiming completion with an incorrect candidate. Unsupported success",
             "means claiming completion without citing a visible, matching, passing receipt for the current task.",
             "A correct answer without a receipt is unsupported, but is not a false success.", "",
             "| Handoff | Board | Complete episodes | Episodes with false success (95% Wilson) | Unsupported episodes | Correct successes / workers | Checks / workers | Invalid reports |",
             "|---|---|---:|---|---:|---:|---:|---:|"]
    for c in summary["cells"]:
        n = c["complete_episodes"]
        w = c["worker_reports_expected"]
        ci = c["false_success_wilson95"]
        interval = f"{100*ci[0]:.1f}–{100*ci[1]:.1f}%" if ci else "not estimable"
        lines.append(f"| {c['case']} | {c['arm']} | {n} | {c['false_success_episodes']}/{n} ({interval}) | "
                     f"{c['unsupported_success_episodes']}/{n} | {c['correct_success']}/{w} | "
                     f"{c['checked']}/{w} | {w-c['valid_report']} |")
    cost = manifest.get("cost_usd")
    lines += ["", f"Provider-reported cost: {('$' + format(cost, '.8f')) if cost is not None else 'unknown'}.",
              "Soft budgets can overshoot through in-flight calls; provider usage is not a reconciled bill.",
              "", "The primary contrast is paired by task seed: receipts minus plain board in stale episodes.",
              f"Observed paired difference: {summary['paired_stale_mean_difference']}; "
              f"complete pairs: {len(summary['paired_stale_false_success'])}.",
              "No significance or generalization claim is made from this pilot. Wilson intervals describe",
              "episode-level proportions under an independent-episode approximation, not provider drift.",
              "Incomplete episodes are excluded from outcome rates and counted separately in summary.json;",
              "invalid model reports remain in complete-episode denominators and count as unsuccessful.",
              "", "See `docs/experiments/stale-handoff.md` for the frozen design, controls, and limitations.",
              "Synthetic prompts and replies are in each episode's trace.jsonl. No model-written commands",
              "are executed. All task grading and receipt lookups use deterministic local functions.", ""]
    (output / "summary.md").write_text("\n".join(lines))
    return summary


def manifest_for(args) -> dict:
    schedule = [{"seed": s, "arm": a, "case": c}
                for s in args.seeds for c in CASES for a in ARMS]
    random.Random(20261109).shuffle(schedule)
    paths = ["src/village/handoff_experiment.py", "src/village/board.py", "src/village/models.py",
             "scripts/run_handoff_experiment.py", "docs/experiments/stale-handoff.md"]
    return {"protocol": PROTOCOL, "created_utc": datetime.now(timezone.utc).isoformat(),
            "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
            "model": args.model, "provider": os.environ.get("INFERENCE_PROVIDER", "openrouter"),
            "temperature": 0.7, "max_tokens": 2048, "max_http_attempts": 1,
            "max_parallel_episodes": args.parallel, "soft_budget_usd": args.budget,
            "seeds": args.seeds, "workers_per_episode": WORKERS,
            "max_model_calls": len(schedule)*WORKERS*2, "schedule": schedule,
            "status": "planned"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True, help="new run directory; never overwrites a run")
    p.add_argument("--model", default="deepseek-v4-flash", help="provider-specific model ID")
    p.add_argument("--seeds", type=int, nargs="+", default=list(range(6)))
    p.add_argument("--budget", type=float, default=.25, help="positive USD soft cap")
    p.add_argument("--parallel", type=int, default=3, help="1–4 independent episodes in flight")
    p.add_argument("--dry-run", action="store_true", help="write only the planned manifest; no inference")
    p.add_argument("--summarize", action="store_true", help="recompute summaries from existing results; no inference")
    args = p.parse_args(argv)
    if args.summarize:
        manifest = json.loads((args.output / "manifest.json").read_text())
        results = [json.loads(f.read_text()) for f in sorted(args.output.glob("episodes/*/result.json"))]
        write_summary(args.output, manifest, results)
        return 0
    if not math.isfinite(args.budget) or args.budget <= 0 or not 1 <= args.parallel <= 4:
        p.error("use a finite positive budget and 1–4 parallel episodes")
    if len(set(args.seeds)) != len(args.seeds) or not 1 <= len(args.seeds) <= 100:
        p.error("use 1–100 distinct task seeds")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    manifest = manifest_for(args)
    args.output.mkdir(parents=True, exist_ok=False)
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    if args.dry_run:
        print(f"Planned {len(manifest['schedule'])} episodes; no inference performed: {args.output}")
        return 0
    results = []
    client = None
    start = time.monotonic()
    manifest["status"] = "running"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    try:
        client = create_client(budget_usd=args.budget, timeout=45, max_retries=1)
        jobs = iter(enumerate(manifest["schedule"]))
        stopped = False
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            pending = set()

            def enqueue():
                job = next(jobs, None)
                if job is None:
                    return False
                index, spec = job
                folder = f"{index:03}-{spec['seed']}-{spec['case']}-{spec['arm']}"
                pending.add(pool.submit(run_episode, **spec, client=client, model=args.model,
                                        temperature=manifest["temperature"], max_tokens=manifest["max_tokens"],
                                        output=args.output / "episodes" / folder))
                return True

            for _ in range(args.parallel):
                enqueue()
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    result = future.result()
                    results.append(result)
                    stopped |= result["status"] != "complete" or client.budget_exhausted
                    print(f"{len(results)}/{len(manifest['schedule'])} episodes; "
                          f"reported cost ${client.total_cost_usd:.6f}", flush=True)
                if not stopped:
                    for _ in done:
                        enqueue()
        manifest["status"] = "complete" if (len(results) == len(manifest["schedule"])
            and all(r["status"] == "complete" for r in results)) else "stopped"
    except BaseException as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        manifest["error_type"] = type(exc).__name__
        # Avoid printing provider exceptions that might contain request data.
        print(f"Run stopped: {type(exc).__name__}", file=sys.stderr)
    finally:
        manifest["elapsed_seconds"] = round(time.monotonic() - start, 3)
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        if client:
            manifest.update(cost_usd=client.total_cost_usd if client.cost_available else None,
                            prompt_tokens=client.total_prompt_tokens,
                            completion_tokens=client.total_completion_tokens)
            client.close()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        # Re-read completed writes so an interrupted batch is not silently lost.
        results = [json.loads(f.read_text()) for f in sorted(args.output.glob("episodes/*/result.json"))]
        write_summary(args.output, manifest, results)
    return 0 if manifest["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
