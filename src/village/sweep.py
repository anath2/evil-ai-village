"""M4: capability-mix sweep.

Run the same goal across multiple model rosters ("arms") under a shared USD
budget cap, then compare capability vs collaboration. Each arm gets its own
board + village workspace so results don't contaminate.

    python run.py sweep --config configs/sweep.yaml --budget 1.0
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .analyze import analyze_run
from .config import Config
from .orchestrator import Orchestrator


def _arm_row(name: str, run_id: str, analysis: dict) -> dict:
    summary = analysis.get("summary", {})
    agents = summary.get("agents", [])
    influence = analysis.get("influence", {}) or {}
    top_free = max(influence.items(), key=lambda kv: kv[1]["free_ride_index"], default=(None, {}))
    top_lead = max(influence.items(), key=lambda kv: kv[1]["leadership"], default=(None, {}))
    deception_hits = sum(
        len(v) for v in (analysis.get("deception", {}) or {}).get("lexicon_hits", {}).values()
    )
    return {
        "arm": name,
        "run_id": run_id,
        "agents": len(agents),
        "solved": summary.get("solved", 0),
        "cost_usd": round(sum((a.get("cost_usd") or 0.0) for a in agents), 4),
        "board_messages": analysis.get("board_messages", 0),
        "coalitions": analysis.get("coalitions", {}).get("coalitions", []),
        "top_free_rider": top_free[0] if top_free[1] else None,
        "most_influential": top_lead[0] if top_lead[1] else None,
        "deception_hits": deception_hits,
        "forged_verdicts": len((analysis.get("deception", {}) or {}).get("forged_verdicts", [])),
        "budget_stopped": summary.get("budget_stopped", 0),
    }


def run_sweep(cfg: Config, budget_usd: float | None = None) -> list[dict]:
    arms = cfg.sweep.arms
    if not arms:
        raise SystemExit("no sweep arms configured (add a `sweep.arms` section)")
    total_budget = (
        budget_usd
        if budget_usd is not None
        else (cfg.sweep.budget_usd or cfg.village.budget_usd)
    )
    per_arm = round(total_budget / len(arms), 6) if total_budget else 0.0
    print(
        f"[sweep] {len(arms)} arms · total budget ${total_budget:.2f} · per arm ${per_arm:.2f}"
    )

    board_dir = Path(cfg.board.path).parent
    rows: list[dict] = []
    for arm in arms:
        arm_cfg = copy.deepcopy(cfg)
        arm_cfg.agents = arm.agents
        arm_cfg.goals = []  # single-goal comparison
        arm_cfg.village.id = f"{cfg.village_id}-{arm.name}"
        arm_cfg.village.budget_usd = per_arm
        arm_cfg.board.path = str(board_dir / f"board-{arm.name}.jsonl")

        print(f"\n########## SWEEP ARM: {arm.name} ({len(arm.agents)} agents) ##########")
        orch = Orchestrator(arm_cfg)
        orch.run()
        analysis = analyze_run(arm_cfg, orch.run_id)
        rows.append(_arm_row(arm.name, orch.run_id, analysis))

    _write_reports(cfg, rows, total_budget, per_arm)
    return rows


def _write_reports(cfg: Config, rows: list[dict], total_budget: float, per_arm: float) -> None:
    out_dir = cfg.abspath(".village") / "sweep"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sweep_summary.json").write_text(
        json.dumps({"total_budget_usd": total_budget, "per_arm_usd": per_arm, "arms": rows}, indent=2)
    )

    lines = [
        "# Capability-mix sweep",
        "",
        f"- total budget: **${total_budget:.2f}** · per arm: **${per_arm:.2f}**",
        f"- arms: **{len(rows)}**",
        "",
        "| arm | agents | solved | cost | msgs | coalitions | most influential | top free-rider | deception |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        coal = "; ".join(",".join(c) for c in r["coalitions"]) or "-"
        lines.append(
            f"| {r['arm']} | {r['agents']} | {r['solved']} | ${r['cost_usd']} | {r['board_messages']} "
            f"| {coal} | {r['most_influential'] or '-'} | {r['top_free_rider'] or '-'} | {r['deception_hits']} |"
        )
    total_spent = round(sum(r["cost_usd"] for r in rows), 4)
    lines += ["", f"**total spent: ${total_spent:.4f}** / cap ${total_budget:.2f}"]
    report = "\n".join(lines)
    (out_dir / "sweep_report.md").write_text(report)
    print(f"\n[sweep] wrote {out_dir / 'sweep_report.md'}")
    print(report)
