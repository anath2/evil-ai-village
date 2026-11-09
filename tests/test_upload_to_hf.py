"""Offline checks for scripts/upload_to_hf.py — no network, no HF token."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import upload_to_hf as hf  # noqa: E402


def _make_run(tmp_path: Path, secret: str | None = None) -> Path:
    run = tmp_path / "experiment-test"
    (run / "logs" / "run-1").mkdir(parents=True)
    (run / "README.md").write_text("# Test run\n\nAgents failed to solve the task.\n")
    (run / "metrics.json").write_text(json.dumps({"completion_rate": 1.0, "errors": 0}))
    (run / "board.jsonl").write_text(
        json.dumps({"agent": "a1", "text": "hello"}) + "\n"
    )
    (run / "logs" / "run-1" / "a1.jsonl").write_text('{"type": "end"}\n')
    if secret:
        (run / "leak.jsonl").write_text(f"key={secret}\n")
    return run


def test_collect_files_recurses_and_ignores(tmp_path):
    run = _make_run(tmp_path)
    files = hf.collect_files(run)
    names = {f.relative_to(run).as_posix() for f in files}
    assert "README.md" in names
    assert "metrics.json" in names
    assert "board.jsonl" in names
    assert "logs/run-1/a1.jsonl" in names  # nested logs included


def test_collect_files_include_exclude(tmp_path):
    run = _make_run(tmp_path)
    only_md = hf.collect_files(run, allow=["*.md"])
    assert all(f.suffix == ".md" for f in only_md)
    no_logs = hf.collect_files(run, ignore=["logs/"])
    assert not any("logs" in f.parts for f in no_logs)


def test_scan_secrets_detects_and_clean(tmp_path):
    clean = _make_run(tmp_path / "clean")
    assert hf.scan_secrets(hf.collect_files(clean), clean) == []

    dirty = _make_run(tmp_path / "dirty", secret="sk-or-v1-" + "a" * 40)
    hits = hf.scan_secrets(hf.collect_files(dirty), dirty)
    assert hits and hits[0]["kind"] == "OpenRouter key"


def test_build_card_embeds_metrics_and_summary(tmp_path):
    run = _make_run(tmp_path)
    card = hf.build_card("experiment-test", run, "user/evil-ai-village", None)
    assert card.startswith("---\n")
    assert "license: apache-2.0" in card
    assert "completion_rate" in card
    assert "Agents failed to solve" in card
    assert "experiments/experiment-test" in card


def test_dry_run_blocks_secret_and_returns_zero(tmp_path, capsys):
    run = _make_run(tmp_path, secret="hf_" + "b" * 30)
    rc = hf.main([str(run), "--repo-id", "user/evil-ai-village", "--dry-run"])
    out = capsys.readouterr()
    assert rc == 1  # blocked
    assert "REFUSING to upload" in out.err
    assert "HuggingFace token" in out.err


def test_dry_run_clean_prints_manifest(tmp_path, capsys):
    run = _make_run(tmp_path)
    rc = hf.main([str(run), "--repo-id", "user/evil-ai-village", "--dry-run"])
    out = capsys.readouterr()
    assert rc == 0
    assert "[dry-run]" in out.out
    assert "secret scan: clean" in out.out
    assert "board.jsonl" in out.out
