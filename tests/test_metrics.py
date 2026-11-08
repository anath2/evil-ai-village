"""Reliability metric taxonomy tests — no network, no Docker.

    pytest -q tests/test_metrics.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from scale_society import _error_kind, _percentile, compute_metrics  # noqa: E402


def _write_log(log_dir: Path, agent: str, events: list[dict]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"{agent}.jsonl").open("w") as fh:
        for e in events:
            fh.write(json.dumps({"agent": agent, **e}) + "\n")


def test_error_kind_buckets() -> None:
    assert _error_kind("request failed: HTTPStatusError 429") == "rate_limit"
    assert _error_kind("ReadTimeout after 120s") == "timeout"
    assert _error_kind("ConnectError boom") == "connect"
    assert _error_kind("Adaption response did not complete: status=incomplete") == "incomplete"
    assert _error_kind("HTTP 401 for model") == "client_error"
    assert _error_kind("HTTP 503 for model") == "server_error"
    assert _error_kind("something weird") == "other"


def test_percentile_handles_empty_and_known_values() -> None:
    assert _percentile([], 0.5) is None
    assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0
    assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == 5.0


def test_compute_metrics_taxonomy(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    # a1: works, posts, finishes
    _write_log(log_dir, "a1", [
        {"type": "turn", "step": 1, "tool": "bash"},
        {"type": "turn", "step": 2, "tool": "post_message"},
        {"type": "end", "solved": False},
    ])
    # a2: two api errors, one abort, one sandbox loss, never finished
    _write_log(log_dir, "a2", [
        {"type": "turn", "step": 1, "tool": "bash"},
        {"type": "api_error", "error": "HTTPStatusError 429 too many"},
        {"type": "api_error", "error": "ReadTimeout after 120s"},
        {"type": "sandbox_lost", "reason": "timeout"},
        {"type": "abort", "reason": "sandbox_lost"},
    ])
    # a3: starved entirely (no turns)
    _write_log(log_dir, "a3", [{"type": "abort", "reason": "time budget exceeded"}])

    base = {
        "calls": 20, "peak": 4, "errors": 2, "retries": 3, "truncated": 1,
        "latencies": [1.0, 2.0, 3.0, 4.0, 40.0], "cost_usd": 0.5,
    }
    summary = {"board_messages": 9}
    social = {
        "coalitions": {"coalitions": [{"members": ["a1", "a2"]}], "isolates": ["a3"]},
        "influence": {"a1": {"posts": 2}, "a2": {"posts": 0}, "a3": {"posts": 0}},
    }

    m = compute_metrics(
        summary=summary, social=social, log_dir=log_dir, base=base,
        count=3, active=8, seconds=60.0, steps=2,
    )

    # Reliability
    assert m["completion_rate"] == round(1 / 3, 3)
    assert m["turn_yield"] == round(3 / 6, 3)  # 3 valid turns of 3 agents x 2 steps
    assert m["error_rate"] == round(2 / 20, 3)
    assert m["error_taxonomy"] == {"rate_limit": 1, "timeout": 1}
    assert m["retry_rate"] == round(3 / 20, 3)
    assert m["starvation_rate"] == round(1 / 3, 3)
    assert m["abort_reasons"] == {"sandbox_lost": 1, "time budget exceeded": 1}
    assert m["sandbox_lost"] == 1
    assert m["truncated_responses"] == 1

    # Throughput / cost
    assert m["latency_p50"] == 3.0
    assert m["latency_p95"] == 40.0
    assert m["throughput_agents_per_min"] == 1.0
    assert m["saturation"] == 0.5
    assert m["cost_per_agent"] == round(0.5 / 3, 6)
    assert m["cost_per_successful_turn"] == round(0.5 / 3, 6)  # 3 valid turns

    # Society
    assert m["participation_rate"] == round(1 / 3, 3)
    assert m["board_density"] == 3.0
    assert m["isolate_rate"] == round(1 / 3, 3)
    assert m["largest_coalition"] == 2
    assert m["agents_logged"] == 3
