"""Associative (episodic) memory for village agents.

Borrowed from Concordia's design: memories are stored with embeddings and
retrieved by semantic similarity, rather than carried as one flat string. This
gives agents *episodic recall* while keeping a persistent, compact memory.

The default `HashingEmbedder` is dependency-free and deterministic (stable
across processes), which makes retrieval reproducible and testable. Swap in a
real embedder (sentence-transformers, an embeddings API) by passing any
`Callable[[str], Sequence[float]]`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _stable_hash(token: str) -> int:
    # Python's built-in hash() is salted per process; use md5 for cross-run stability.
    return int(hashlib.md5(token.encode()).hexdigest(), 16)


class HashingEmbedder:
    """Feature-hashing bag-of-words embedder. Deterministic, no dependencies."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def __call__(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN_RE.findall((text or "").lower()):
            vec[_stable_hash(token) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class MemoryEntry:
    text: str
    kind: str = "note"
    ts: float = field(default_factory=time.time)
    embedding: list[float] = field(default_factory=list, repr=False)

    def to_json(self) -> dict:
        return {"text": self.text, "kind": self.kind, "ts": self.ts}


class MemoryStore:
    def __init__(self, embedder: Callable[[str], list[float]] | None = None):
        self.embedder = embedder or HashingEmbedder()
        self.entries: list[MemoryEntry] = []

    def add(self, text: str, *, kind: str = "note") -> MemoryEntry:
        entry = MemoryEntry(text=text.strip(), kind=kind, embedding=self.embedder(text))
        self.entries.append(entry)
        return entry

    def search(self, query: str, k: int = 5) -> list[MemoryEntry]:
        if not self.entries:
            return []
        q = self.embedder(query)
        scored = [(cosine(q, e.embedding), e) for e in self.entries]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [e for score, e in scored[:k] if score > 0]

    def reflection_texts(self) -> list[str]:
        return [e.text for e in self.entries if e.kind == "reflection"]

    def render(self, query: str, *, relevant: int = 5, recent: int = 5) -> str:
        """Render a compact memory block for the prompt."""
        blocks = []
        reflections = self.reflection_texts()
        if reflections:
            blocks.append("## Self-reflection\n" + "\n".join(f"- {r}" for r in reflections[-3:]))

        hits = self.search(query, k=relevant)
        if hits:
            blocks.append(
                "## Relevant memories\n"
                + "\n".join(f"- ({e.kind}) {e.text}" for e in hits)
            )

        if recent:
            tail = [e for e in self.entries[-recent:]]
            if tail:
                blocks.append(
                    "## Recent memories\n"
                    + "\n".join(f"- ({e.kind}) {e.text}" for e in tail)
                )
        return "\n\n".join(blocks) if blocks else "(empty — this is the start of your run)"

    # ---- persistence ----
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            os.close(fd)
            raise ValueError("Memory must be a regular file with one link")
        os.ftruncate(fd, 0)
        with os.fdopen(fd, "w") as fh:
            for e in self.entries:
                fh.write(json.dumps(e.to_json()) + "\n")

    @classmethod
    def load(cls, path: Path, embedder: Callable[[str], list[float]] | None = None) -> "MemoryStore":
        store = cls(embedder=embedder)
        path = Path(path)
        if not path.exists():
            return store
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("Memory must be a regular file")
        with os.fdopen(fd) as fh:
            lines = fh.read().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            store.add(obj.get("text", ""), kind=obj.get("kind", "note"))
        return store

    def __len__(self) -> int:
        return len(self.entries)
