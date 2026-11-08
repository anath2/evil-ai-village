"""Config loading: YAML + environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:  # optional
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


@dataclass
class GoalRound:
    """One goal period in a village rotation.

    Agents keep the same workspace (and thus memory + identity) across rounds;
    only the goal and assigned tasks change.
    """

    name: str = "round"
    goal: str = ""
    tasks: list[str] = field(default_factory=list)
    max_steps: int | None = None


@dataclass
class VillageSettings:
    name: str = "evil-ai-village"
    id: str = ""  # stable village id; workspace + memory persist under it
    goal: str = ""
    max_steps: int = 60
    consolidate_every: int = 15
    reflect_every: int = 3
    history_window: int = 30
    time_budget_seconds: int = 0
    budget_usd: float = 0.0  # 0 = unlimited


@dataclass
class BoardSettings:
    path: str = ".village/board.jsonl"
    read_limit: int = 25


@dataclass
class SandboxSettings:
    kind: str = "docker"  # docker | local (explicit unisolated development)
    workspace_root: str = ".village/workspaces"
    bash_timeout: int = 120
    max_output_chars: int = 8000
    docker_image: str = "evil-ai-village/agent:latest"


@dataclass
class TaskSettings:
    provider: str = "mock"  # mock | cybergym
    data_dir: str = "./cybergym_data/data"
    server: str = "http://127.0.0.1:8666"
    difficulty: str = "level1"
    mask_map: str = "./mask_map.json"
    ids: list[str] = field(default_factory=lambda: ["mock:1"])


@dataclass
class AgentSpec:
    name: str
    model: str
    tier: str = "mid"
    task: str | None = None


@dataclass
class SweepArm:
    name: str
    agents: list[AgentSpec] = field(default_factory=list)


@dataclass
class SweepSettings:
    budget_usd: float = 0.0
    arms: list[SweepArm] = field(default_factory=list)


@dataclass
class Config:
    village: VillageSettings
    board: BoardSettings
    sandbox: SandboxSettings
    task: TaskSettings
    agents: list[AgentSpec]
    goals: list[GoalRound] = field(default_factory=list)
    sweep: SweepSettings = field(default_factory=SweepSettings)
    root: Path = field(default_factory=Path.cwd)

    @property
    def village_id(self) -> str:
        return self.village.id or self.village.name or "village"

    def abspath(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (self.root / path)


def _section(cls, data: dict | None):
    data = data or {}
    known = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in data.items() if k in known})


def load_config(path: str | os.PathLike) -> Config:
    if load_dotenv is not None:
        load_dotenv()
    path = Path(path).expanduser().resolve()
    raw = yaml.safe_load(path.read_text())
    root = path.parent.parent if path.parent.name == "configs" else path.parent
    goals = [
        _section(GoalRound, g) for g in (raw.get("village") or {}).get("goals", [])
    ]
    sweep_raw = raw.get("sweep") or {}
    sweep = SweepSettings(
        budget_usd=float(sweep_raw.get("budget_usd") or 0.0),
        arms=[
            SweepArm(
                name=a.get("name", f"arm{i}"),
                agents=[_section(AgentSpec, s) for s in a.get("agents", [])],
            )
            for i, a in enumerate(sweep_raw.get("arms", []))
        ],
    )
    return Config(
        village=_section(VillageSettings, raw.get("village")),
        board=_section(BoardSettings, raw.get("board")),
        sandbox=_section(SandboxSettings, raw.get("sandbox")),
        task=_section(TaskSettings, raw.get("task")),
        agents=[_section(AgentSpec, a) for a in raw.get("agents", [])],
        goals=goals,
        sweep=sweep,
        root=root,
    )


def openrouter_headers() -> dict:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or key.endswith("REPLACE_ME"):
        raise SystemExit(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": os.environ.get(
            "OPENROUTER_REFERER", "https://github.com/ajitnath/evil-ai-village"
        ),
        "X-Title": os.environ.get("OPENROUTER_TITLE", "evil-ai-village"),
        "Content-Type": "application/json",
    }


def openrouter_base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
