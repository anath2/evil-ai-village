"""The handoff must reject unfinished integration before starting any work."""

from pathlib import Path

import pytest

from village.config import load_config
from village.mcp_server import build_server
from village.orchestrator import Orchestrator


@pytest.mark.parametrize("sandbox_kind", ["docker", "local"])
def test_unfinished_provider_stops_before_side_effects(monkeypatch, tmp_path, sandbox_kind):
    cfg = load_config(Path(__file__).resolve().parents[1] / "configs/cybergym.yaml")
    cfg.root = tmp_path
    cfg.sandbox.kind = sandbox_kind

    def forbidden(*args, **kwargs):
        pytest.fail("Unfinished integration must stop before doing work")

    for name in ("Board", "create_client", "prepare_task", "make_sandbox"):
        monkeypatch.setattr(f"village.orchestrator.{name}", forbidden)
    with pytest.raises(ValueError, match="mock tasks only"):
        Orchestrator(cfg).run()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("sandbox_kind", ["docker", "local"])
def test_unfinished_mcp_stops_before_side_effects(monkeypatch, tmp_path, sandbox_kind):
    def forbidden(*args, **kwargs):
        pytest.fail("Unfinished integration must stop before doing work")

    for name in ("Board", "make_sandbox"):
        monkeypatch.setattr(f"village.mcp_server.{name}", forbidden)
    with pytest.raises(ValueError, match="unfinished and disabled"):
        build_server(tmp_path / "workspace", tmp_path / "board.jsonl", "scout",
                     sandbox_kind=sandbox_kind, task_metadata=tmp_path / "metadata.json")
    assert list(tmp_path.iterdir()) == []
