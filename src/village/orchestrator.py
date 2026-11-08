"""Orchestrator: assemble a village and run its agents, optionally across rounds.

A village has a **stable workspace** (`village_id`) so agent memory and identity
persist across goal rotations; each round writes its own logs and summary.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import uuid
from pathlib import Path

from .agent import Agent, AgentResult
from .board import Board
from .config import Config, AgentSpec, GoalRound
from .cybergym import prepare_task
from .models import InferenceClient, create_client
from .sandbox import make_sandbox


class Orchestrator:
    def __init__(self, cfg: Config, *, run_id: str | None = None):
        self.cfg = cfg
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.logs_root = cfg.abspath(".village") / "logs" / self.run_id
        # Stable across rounds AND across separate `run.py run` invocations.
        self.workspaces = cfg.abspath(cfg.sandbox.workspace_root) / cfg.village_id

    # ---- planning ------------------------------------------------------
    def _rounds(self) -> list[GoalRound]:
        if self.cfg.goals:
            return self.cfg.goals
        return [
            GoalRound(
                name="round",
                goal=self.cfg.village.goal,
                tasks=list(self.cfg.task.ids),
                max_steps=self.cfg.village.max_steps,
            )
        ]

    def _task_for(self, spec: AgentSpec, index: int, task_ids: list[str]) -> str:
        # Explicit per-agent task wins only when it belongs to this round's set.
        if spec.task and spec.task in task_ids:
            return spec.task
        if task_ids:
            return task_ids[index % len(task_ids)]
        return spec.task or "mock:1"

    def build_agents(
        self,
        board: Board,
        client: InferenceClient,
        *,
        goal: str,
        task_ids: list[str],
        log_dir: Path,
        round_name: str,
        max_steps: int,
    ) -> list[Agent]:
        agents: list[Agent] = []
        for i, spec in enumerate(self.cfg.agents):
            task_id = self._task_for(spec, i, task_ids)
            workspace = self.workspaces / spec.name
            task = prepare_task(self.cfg, task_id, workspace)
            sandbox = make_sandbox(self.cfg.sandbox.kind, workspace, self.cfg.sandbox)
            agents.append(
                Agent(
                    name=spec.name,
                    model=spec.model,
                    tier=spec.tier,
                    task=task,
                    goal=goal,
                    round_name=round_name,
                    client=client,
                    sandbox=sandbox,
                    board=board,
                    max_steps=max_steps,
                    consolidate_every=self.cfg.village.consolidate_every,
                    reflect_every=self.cfg.village.reflect_every,
                    history_window=self.cfg.village.history_window,
                    time_budget_seconds=self.cfg.village.time_budget_seconds,
                    log_dir=log_dir,
                )
            )
        return agents

    # ---- execution -----------------------------------------------------
    def _run_agents(self, agents: list[Agent]) -> list[AgentResult]:
        results: list[AgentResult] = []
        with cf.ThreadPoolExecutor(max_workers=max(1, len(agents))) as pool:
            futures = {pool.submit(a.run): a for a in agents}
            for fut in cf.as_completed(futures):
                agent = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"[village:{self.run_id}] {agent.name} crashed: {exc}")
                    continue
                results.append(res)
                flag = "SOLVED" if res.solved else "no-solve"
                print(
                    f"[village:{self.run_id}] {res.name} finished ({flag}) "
                    f"steps={res.steps} cost={'$' + format(res.cost_usd, '.8f') if agent.client.cost_available else 'unknown'} mem={res.memories}"
                )
        return results

    def run(self) -> dict[str, list[AgentResult]]:
        board = Board(self.cfg.abspath(self.cfg.board.path))
        client = create_client(budget_usd=self.cfg.village.budget_usd)
        self.inference_provider = client.provider
        self.cost_available = client.cost_available
        rounds = self._rounds()
        multi = len(rounds) > 1
        all_results: dict[str, list[AgentResult]] = {}

        print(f"[village:{self.run_id}] village '{self.cfg.village_id}', {len(rounds)} round(s)")
        try:
            for i, rnd in enumerate(rounds):
                log_dir = (self.logs_root / rnd.name) if multi else self.logs_root
                max_steps = rnd.max_steps or self.cfg.village.max_steps
                task_ids = rnd.tasks or list(self.cfg.task.ids)
                print(f"\n[village:{self.run_id}] === round {i + 1}/{len(rounds)}: {rnd.name} ===")
                agents = self.build_agents(
                    board,
                    client,
                    goal=rnd.goal or self.cfg.village.goal,
                    task_ids=task_ids,
                    log_dir=log_dir,
                    round_name=rnd.name,
                    max_steps=max_steps,
                )
                for a in agents:
                    print(f"  - {a.name:8s} {a.tier:6s} {a.model:38s} task={a.task.task_id} mem={len(a.memory or [])}")
                results = self._run_agents(agents)
                all_results[rnd.name] = results
                self.cost_available = client.cost_available
                self.total_cost_usd = client.total_cost_usd
                self.total_reported_cost = getattr(client, "total_reported_cost", None)
                self.cost_unit = getattr(client, "cost_unit", "usd")
                self._write_round_summary(log_dir, rnd, results, board, task_ids)
        finally:
            cap = f" / cap ${client.budget_usd:.2f}" if client.budget_usd else ""
            hit = " [BUDGET CAP HIT]" if client.budget_exhausted else ""
            print(
                f"\n[village:{self.run_id}] total cost {'$' + format(client.total_cost_usd, '.8f') if client.cost_available else 'unknown'}{cap}{hit} "
                f"({client.total_prompt_tokens} prompt + {client.total_completion_tokens} completion tokens)"
            )
            self.cost_available = client.cost_available
            self.total_cost_usd = client.total_cost_usd
            self.total_reported_cost = getattr(client, "total_reported_cost", None)
            self.cost_unit = getattr(client, "cost_unit", "usd")
            if client.provider == "adaption":
                print(f"[village:{self.run_id}] provider-reported cost {client.total_reported_cost:.8f} ({client.cost_unit} units)")
            client.close()

        self._write_village_summary(all_results, board)
        return all_results

    # ---- outputs -------------------------------------------------------
    def _write_round_summary(
        self, log_dir: Path, rnd: GoalRound, results: list[AgentResult], board: Board, task_ids: list[str]
    ) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "run_id": self.run_id,
            "inference_provider": getattr(self, "inference_provider", "unknown"),
            "cost_available": getattr(self, "cost_available", False),
            "cost_unit": getattr(self, "cost_unit", "unverified"),
            "total_reported_cost": getattr(self, "total_reported_cost", None),
            "total_cost_usd": getattr(self, "total_cost_usd", None),
            "village_id": self.cfg.village_id,
            "round": rnd.name,
            "goal": rnd.goal or self.cfg.village.goal,
            "config_root": str(self.cfg.root),
            "board_path": str(self.cfg.abspath(self.cfg.board.path)),
            "workspace_root": str(self.workspaces),
            "task_ids": task_ids,
            "agents": [r.__dict__ for r in results],
            "board_messages": len(board),
            "solved": sum(1 for r in results if r.solved),
            "budget_usd": self.cfg.village.budget_usd,
            "budget_stopped": sum(1 for r in results if r.budget_stopped),
        }
        (log_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"[village:{self.run_id}] wrote {log_dir / 'summary.json'}")

    def _write_village_summary(self, all_results: dict[str, list[AgentResult]], board: Board) -> None:
        self.logs_root.mkdir(parents=True, exist_ok=True)
        summary = {
            "run_id": self.run_id,
            "inference_provider": getattr(self, "inference_provider", "unknown"),
            "cost_available": getattr(self, "cost_available", False),
            "cost_unit": getattr(self, "cost_unit", "unverified"),
            "total_reported_cost": getattr(self, "total_reported_cost", None),
            "total_cost_usd": getattr(self, "total_cost_usd", None),
            "village_id": self.cfg.village_id,
            "workspace_root": str(self.workspaces),
            "board_path": str(self.cfg.abspath(self.cfg.board.path)),
            "board_messages": len(board),
            "rounds": [
                {
                    "name": name,
                    "solved": sum(1 for r in results if r.solved),
                    "agents": len(results),
                    "cost_usd": round(sum(r.cost_usd for r in results), 4),
                    "memories": {r.name: r.memories for r in results},
                    "reflections": {r.name: r.reflections for r in results},
                }
                for name, results in all_results.items()
            ],
        }
        (self.logs_root / "village_summary.json").write_text(json.dumps(summary, indent=2))
        print(f"[village:{self.run_id}] wrote {self.logs_root / 'village_summary.json'}")
