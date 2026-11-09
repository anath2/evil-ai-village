"""Exposure vs adoption: did agents copy a pattern they had actually read?

An agent is *exposed* to a pattern when, before writing a post, a `read_board`
observation showed it an earlier post containing that pattern. Because the board
only reaches an agent through `read_board`, this is exact, not inferred.
Posts written by agents that had read nothing show the base rate of independent
reinvention.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

_SEEN_RE = re.compile(r"(?m)^\[(\d+)\] [A-Za-z0-9_\-]+: ")
_POSTED_RE = re.compile(r"message #(\d+)")

# name -> regex (applied to the post text); None means a callable below.
FEATURES: dict[str, str] = {
    "signal_prefix": r"^\s*SIGNAL:",
    "next_line": r"(?m)^\s*NEXT:",
    "header_[aNNN]": r"^\s*\[a\d+",
    "FINDING_label": r"\bFINDING\b",
    "numbered_list": r"(?m)(^|\s)\(?[1-3][.)]\s",
}


def has_feature(name: str, text: str) -> bool:
    return re.search(FEATURES[name], text or "") is not None


def fisher_one_sided(a: int, b: int, c: int, d: int) -> float:
    """P(X >= a) for the 2x2 table [[a, b], [c, d]] (exposed used/unused; unexposed used/unused)."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    total = math.comb(n, c1) if 0 <= c1 <= n else 0
    if not total:
        return 1.0
    return sum(
        math.comb(r1, x) * math.comb(n - r1, c1 - x) for x in range(a, min(r1, c1) + 1)
    ) / total


def load_board(path: Path) -> dict[int, dict]:
    path = Path(path)
    if not path.exists():
        return {}
    msgs = (json.loads(l) for l in path.read_text().splitlines() if l.strip())
    return {m["seq"]: m for m in msgs}


def load_agents(log_dir: Path) -> dict[str, dict]:
    """Per agent: posts (with the set of board seqs seen before each), read count, tool turns."""
    agents: dict[str, dict] = {}
    for f in sorted(Path(log_dir).glob("a*.jsonl")):
        events = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        seen: set[int] = set()
        reads = 0
        info = {"posts": [], "reads": 0, "turns": 0, "valid_turns": 0, "first_read_ts": None,
                "first_post_ts": None, "model": None}
        for i, e in enumerate(events):
            kind = e.get("type")
            if kind == "start":
                info["model"] = e.get("model")
            elif kind == "turn":
                info["turns"] += 1
                info["valid_turns"] += 1 if e.get("tool") else 0
                if e.get("tool") == "post_message":
                    nxt = events[i + 1] if i + 1 < len(events) else {}
                    m = _POSTED_RE.search(nxt.get("observation", "") or "")
                    if m:
                        info["posts"].append({"seq": int(m.group(1)), "seen": set(seen),
                                              "reads": reads, "ts": e["ts"]})
                        info["first_post_ts"] = info["first_post_ts"] or e["ts"]
            elif kind == "observation" and e.get("tool") == "read_board":
                reads += 1
                info["first_read_ts"] = info["first_read_ts"] or e["ts"]
                seen.update(int(s) for s in _SEEN_RE.findall(e.get("observation", "") or ""))
        info["reads"] = reads
        agents[f.stem] = info
    return agents


def exposure_table(board: dict[int, dict], agents: dict[str, dict], features=None,
                   first_post_only: bool = False) -> dict[str, dict]:
    """Per feature: use rate among posts whose author had/had not seen the feature."""
    out = {}
    for name in features or FEATURES:
        exp = [0, 0]  # used, unused
        une = [0, 0]
        for info in agents.values():
            posts = info["posts"][:1] if first_post_only else info["posts"]
            for p in posts:
                if p["seq"] not in board:
                    continue
                exposed = any(has_feature(name, board[s]["text"]) for s in p["seen"] if s in board)
                used = has_feature(name, board[p["seq"]]["text"])
                (exp if exposed else une)[0 if used else 1] += 1
        out[name] = {
            "exposed_used": exp[0], "exposed_n": sum(exp),
            "unexposed_used": une[0], "unexposed_n": sum(une),
            "p_one_sided": round(fisher_one_sided(exp[0], exp[1], une[0], une[1]), 6),
        }
    return out


def dose_response(board: dict[int, dict], agents: dict[str, dict], feature: str) -> dict[str, dict]:
    """Use rate by how many distinct earlier posts with the feature the author had seen."""
    buckets: dict[str, list[int]] = {"0": [0, 0], "1": [0, 0], "2": [0, 0], "3+": [0, 0]}
    for info in agents.values():
        for p in info["posts"]:
            if p["seq"] not in board:
                continue
            k = sum(1 for s in p["seen"] if s in board and has_feature(feature, board[s]["text"]))
            key = "3+" if k >= 3 else str(k)
            buckets[key][0 if has_feature(feature, board[p["seq"]]["text"]) else 1] += 1
    return {k: {"used": v[0], "n": v[0] + v[1]} for k, v in buckets.items()}


def gate_metrics(agents: dict[str, dict], metrics: dict | None = None) -> dict:
    """Pilot gates from docs/experiments/exposure-norms.md."""
    posters = [a for a in agents.values() if a["posts"]]
    read_first = sum(
        1 for a in posters
        if a["first_read_ts"] is not None and a["first_read_ts"] < a["first_post_ts"]
    )
    turns = sum(a["turns"] for a in agents.values())
    valid = sum(a["valid_turns"] for a in agents.values())
    taxonomy = (metrics or {}).get("error_taxonomy") or {}
    calls = max(1, int((metrics or {}).get("calls") or 0))
    return {
        "agents": len(agents),
        "posters": len(posters),
        "read_before_first_post": read_first,
        "read_before_first_post_rate": round(read_first / max(1, len(posters)), 3),
        "valid_action_rate": round(valid / max(1, turns), 3),
        "rate_limit_share": round(taxonomy.get("rate_limit", 0) / calls, 3),
    }
