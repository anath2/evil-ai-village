"""Append-only shared message board (the 'society' substrate)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class Board:
    """Thread-safe, append-only JSONL board.

    The append-only property matters: in the 2026 incident agents tried to
    rewrite their own transcripts. We never mutate or delete lines.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._messages: list[dict] = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        self._messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    def post(self, author: str, text: str, *, kind: str = "chat", meta: dict | None = None) -> dict:
        with self._lock:
            msg = {
                "seq": len(self._messages) + 1,
                "ts": time.time(),
                "author": author,
                "kind": kind,
                "text": text,
            }
            if meta:
                msg["meta"] = meta
            with self.path.open("a") as fh:
                fh.write(json.dumps(msg) + "\n")
            self._messages.append(msg)
        return msg

    def recent(self, limit: int = 25, *, after_seq: int = 0) -> list[dict]:
        with self._lock:
            msgs = [m for m in self._messages if m["seq"] > after_seq]
        return msgs[-limit:]

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._messages)

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)


def format_board(messages: list[dict]) -> str:
    if not messages:
        return "(board is empty)"
    lines = []
    for m in messages:
        lines.append(f"[{m['seq']}] {m['author']}: {m['text']}")
    return "\n".join(lines)
