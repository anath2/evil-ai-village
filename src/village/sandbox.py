"""Command execution: explicit local development or managed offline Docker mock tasks."""

from __future__ import annotations

import subprocess
import base64
import selectors
import time
import os
import shlex
import uuid
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


class OutputLimitExceeded(RuntimeError):
    pass


def _capture_docker(args, timeout, limit):
    """Drain CLI output with a host-side bound, rather than buffering without limit."""
    output = bytearray()
    deadline = time.monotonic() + timeout
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(args, timeout)
                    if not selector.select(remaining):
                        raise subprocess.TimeoutExpired(args, timeout)
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > limit:
                        raise OutputLimitExceeded(output[:limit].decode(errors="replace"))
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            return code, output.decode(errors="replace")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


class DockerSandbox:
    def __init__(self, container: str, timeout: int = 120, max_output_chars: int = 8000):
        self.container = container
        self._closed = False
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def run(self, command: str, *, max_output_bytes: int | None = None) -> ExecResult:
        if self._closed:
            raise RuntimeError("Agent container is closed; start a new run")
        try:
            code, output = _capture_docker(
                ["docker", "exec", "--workdir", "/workspace", self.container, "bash", "-c", command],
                self.timeout, max(1, max_output_bytes or self.max_output_chars),
            )
            return ExecResult(command, code, output, "")
        except subprocess.TimeoutExpired:
            # Killing the CLI leaves exec processes alive in the daemon. Destroy
            # the whole agent container so descendants cannot outlive the timeout.
            self.close()
            return ExecResult(command, 124, "", f"timeout after {self.timeout}s; container removed")

        except OutputLimitExceeded as exc:
            self.close()
            return ExecResult(command, 125, str(exc), "output limit exceeded; container removed")

    @classmethod
    def create(cls, workspace: Path, settings):
        workspace = Path(workspace).resolve()
        if os.getuid() == 0:
            raise ValueError("Run the harness as a non-root user with Docker access")
        if not workspace.is_dir():
            raise ValueError("Agent workspace must already exist")
        name = f"village-{uuid.uuid4().hex[:12]}"
        cmd = ["docker", "run", "--detach", "--name", name,
               "--label", "evil-ai-village.managed=true",
               "--network", "none", "--read-only", "--init", "--log-driver", "none", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--pids-limit", "128",
               "--memory", "512m", "--memory-swap", "512m", "--cpus", "1",
               "--ulimit", "core=0",
               "--user", f"{os.getuid()}:{os.getgid()}",
               "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=128m,mode=1777",
               "--mount", f"type=bind,src={workspace},dst=/workspace",
               "--workdir", "/workspace", "--env", "HOME=/tmp",
               settings.docker_image, "sleep", "infinity"]
        sandbox = cls(name, settings.bash_timeout, settings.max_output_chars)
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except BaseException:
            # docker run may have created a container before failing or timing out.
            sandbox.close()
            raise
        return sandbox

    def close(self):
        if not self._closed:
            result = subprocess.run(["docker", "rm", "--force", self.container],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode and "No such container" not in result.stderr:
                raise RuntimeError(f"Could not remove agent container {self.container}: {result.stderr.strip()}")
            self._closed = True

    def write_file(self, relpath: str, content: str) -> Path:
        if self._closed:
            raise RuntimeError("Agent container is closed")
        parent = str(Path(relpath).parent)
        try:
            subprocess.run(
                ["docker", "exec", "-i", "--workdir", "/workspace", self.container,
                 "bash", "-c", f"mkdir -p -- {shlex.quote(parent)} && cat > {shlex.quote(relpath)}"],
                input=content, text=True, capture_output=True, check=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self.close()
            raise RuntimeError("File write timed out; agent container removed") from None
        return Path(relpath)

    def read_bytes(self, relpath: str, max_bytes: int = 1024 * 1024) -> bytes:
        # The trusted controller extracts a bounded artifact; no host path is opened.
        script = (
            "import base64,pathlib,sys; p=pathlib.Path(sys.argv[1]).resolve(); "
            "assert p.is_relative_to(pathlib.Path('/workspace')), 'PoC must be in workspace'; "
            "assert p.is_file(), 'PoC must be a regular file'; "
            "d=p.open('rb').read(int(sys.argv[2])+1); "
            "assert len(d)<=int(sys.argv[2]), 'PoC too large'; "
            "sys.stdout.buffer.write(base64.b64encode(d))"
        )
        result = self.run(
            f"python3 -c {shlex.quote(script)} {shlex.quote(relpath)} {int(max_bytes)}",
            max_output_bytes=((max_bytes + 2) // 3) * 4 + 4096,
        )
        if result.exit_code:
            raise ValueError("Could not read PoC artifact from agent container")
        return base64.b64decode(result.stdout, validate=True)

    def read_file(self, relpath: str, max_chars: int = 20000) -> str:
        result = self.run(f"head -c {int(max_chars)} -- {shlex.quote(relpath)}")
        return result.stdout


def make_sandbox(kind: str, workspace: Path, settings) -> LocalSandbox | DockerSandbox:
    if kind == "docker":
        return DockerSandbox.create(workspace, settings)
    if kind != "local":
        raise ValueError(f"Unknown sandbox kind: {kind}")
    return LocalSandbox(workspace, settings.bash_timeout, settings.max_output_chars)
