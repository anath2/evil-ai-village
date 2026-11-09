import json

from village.board import Board
from village.exposure import (
    dose_response, exposure_table, fisher_one_sided, gate_metrics, load_agents, load_board,
)
from village.prompts import build_kickoff, build_kickoff_read_first
from scripts.scale_society import SEED_POSTS, build_config, roster_models, seed_board


def test_read_first_kickoff_only_adds_the_read_step():
    default = build_kickoff("a001", "mock:impossible")
    read_first = build_kickoff_read_first("a001", "mock:impossible")
    assert "read_board" not in default
    assert "First call read_board" in read_first
    for shared in ("mock:impossible", "post a short introduction", "crashing PoC", "coordinate"):
        assert shared in default and shared in read_first


def test_seed_board_preloads_scripted_posts(tmp_path):
    path = tmp_path / "board.jsonl"
    seed_board(path)
    board = Board(path)  # a fresh Board (as the orchestrator creates) must see the seeds
    msgs = board.all()
    assert [m["author"] for m in msgs] == [f"seed{i}" for i in range(1, len(SEED_POSTS) + 1)]
    assert all(m["meta"] == {"seed": True} for m in msgs)
    assert all(m["text"].startswith("SIGNAL:") and "\nNEXT:" in m["text"] for m in msgs)
    assert board.post("a001", "hello")["seq"] == len(SEED_POSTS) + 1


def test_seed_posts_carry_no_task_forced_vocabulary_or_workaround_hints():
    text = " ".join(SEED_POSTS)
    for token in ("UNREACHABLE", "UNSOLVABLE", "IMPOSSIBLE", "/dev/", "fifo", "/proc"):
        assert token.lower() not in text.lower()


def test_single_model_roster_override():
    assert roster_models(3, "qwen3.5-397b") == [("qwen3.5-397b", "xlarge")] * 3
    cfg = build_config(4, "mock:impossible", 6, 1.0, 900, "t", model="qwen3.5-397b")
    assert {a.model for a in cfg.agents} == {"qwen3.5-397b"} and len(cfg.agents) == 4
    assert len({m for m, _ in roster_models(100)}) == 4  # default mixed roster unchanged


def _write_run(tmp_path):
    board = tmp_path / "board.jsonl"
    posts = [
        ("seed1", "SIGNAL: a\nNEXT: b"), ("seed2", "SIGNAL: c\nNEXT: d"),
        ("a001", "SIGNAL: mine\nNEXT: z"),   # read the seeds first, then copied
        ("a002", "hello"),                    # read nothing first
        ("a003", "SIGNAL: independent"),      # read nothing first, still used it
    ]
    board.write_text("".join(json.dumps({"seq": i, "ts": i, "author": a, "text": t}) + "\n"
                             for i, (a, t) in enumerate(posts, 1)))
    logs = tmp_path / "logs"
    logs.mkdir()

    def write(name, events):
        (logs / f"{name}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    write("a001", [
        {"type": "start", "ts": 1, "model": "m"},
        {"type": "turn", "ts": 2, "tool": "read_board", "step": 1},
        {"type": "observation", "ts": 3, "tool": "read_board",
         "observation": "[1] seed1: SIGNAL: a\nNEXT: b\n[2] seed2: SIGNAL: c\nNEXT: d"},
        {"type": "turn", "ts": 4, "tool": "post_message", "step": 2},
        {"type": "observation", "ts": 5, "tool": "post_message", "observation": "posted as message #3"},
    ])
    write("a002", [
        {"type": "start", "ts": 1, "model": "m"},
        {"type": "turn", "ts": 2, "tool": "post_message", "step": 1},
        {"type": "observation", "ts": 3, "tool": "post_message", "observation": "posted as message #4"},
        {"type": "turn", "ts": 4, "tool": "", "step": 2},
    ])
    write("a003", [
        {"type": "start", "ts": 1, "model": "m"},
        {"type": "turn", "ts": 2, "tool": "post_message", "step": 1},
        {"type": "observation", "ts": 3, "tool": "post_message", "observation": "posted as message #5"},
    ])
    return board, logs


def test_exposure_table_splits_by_what_was_actually_read(tmp_path):
    board_path, logs = _write_run(tmp_path)
    board, agents = load_board(board_path), load_agents(logs)
    assert agents["a001"]["posts"][0]["seen"] == {1, 2}
    assert agents["a002"]["posts"][0]["seen"] == set()
    r = exposure_table(board, agents)["signal_prefix"]
    assert (r["exposed_used"], r["exposed_n"]) == (1, 1)
    assert (r["unexposed_used"], r["unexposed_n"]) == (1, 2)
    assert dose_response(board, agents, "signal_prefix")["2"] == {"used": 1, "n": 1}


def test_gate_metrics_counts_read_first_and_valid_actions(tmp_path):
    board_path, logs = _write_run(tmp_path)
    g = gate_metrics(load_agents(logs), {"calls": 10, "error_taxonomy": {"rate_limit": 1}})
    assert g["posters"] == 3 and g["read_before_first_post"] == 1
    assert g["valid_action_rate"] == 0.8  # 4 of 5 turns had a parsed tool
    assert g["rate_limit_share"] == 0.1


def test_fisher_matches_known_value():
    assert abs(fisher_one_sided(3, 0, 0, 3) - 0.05) < 1e-9
    assert fisher_one_sided(0, 5, 0, 5) == 1.0
