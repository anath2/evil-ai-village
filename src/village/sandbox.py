"""Command execution sandboxes.

`local` runs commands with subprocess on the host — fine for mock development
only. `docker` execs into an isolated agent container and is what you should
use for any real CyberGym run (plus CyberGym's firewall/network isolation).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append("[stderr]\n" + self.stderr)
        return "\n".join(parts) if parts else "(no output)"

    def format(self, max_chars: int = 8000) -> str:
        body = self.output
        if len(body) > max_chars:
            body = body[:max_chars] + f"\n...(truncated {len(body) - max_chars} chars)"
        return f"$ {self.command}\n[exit {self.exit_code}]\n{body}"


class LocalSandbox:
    def __init__(self, workspace: Path, timeout: int = 120, max_output_chars: int = 8000):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def run(self, command: str) -> ExecResult:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return ExecResult(command, proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ExecResult(command, 124, exc.stdout or "", f"timeout after {self.timeout}s")

    def write_file(self, relpath: str, content: str) -> Path:
        p = self.workspace / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def read_file(self, relpath: str, max_chars: int = 20000) -> str:
        p = self.workspace / relpath
        if not p.exists():
            return f"(file not found: {relpath})"
        return p.read_text(errors="replace")[:max_chars]


class DockerSandbox:
    def __init__(self, container: str, timeout: int = 120, max_output_chars: int = 8000):
        self.container = container
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def run(self, command: str) -> ExecResult:
        try:
            proc = subprocess.run(
                ["docker", "exec", self.container, "bash", "-lc", command],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return ExecResult(command, proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ExecResult(command, 124, exc.stdout or "", f"timeout after {self.timeout}s")

    def write_file(self, relpath: str, content: str) -> Path:  # pragma: no cover
        subprocess.run(
            ["docker", "exec", "-i", self.container, "bash", "-lc", f"cat > {relpath}"],
            input=content,
            text=True,
            check=True,
        )
        return Path(relpath)

    def read_file(self, relpath: str, max_chars: int = 20000) -> str:  # pragma: no cover
        return self.run(f"head -c {max_chars} {relpath}").stdout


def make_sandbox(kind: str, workspace: Path, settings) -> LocalSandbox | DockerSandbox:
    if kind == "docker":
        return DockerSandbox(
            container=f"village-{workspace.name}",
            timeout=settings.bash_timeout,
            max_output_chars=settings.max_output_chars,
        )
    return LocalSandbox(
        workspace=workspace,
        timeout=settings.bash_timeout,
        max_output_chars=settings.max_output_chars,
    )
