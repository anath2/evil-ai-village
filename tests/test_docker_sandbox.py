import subprocess
from pathlib import Path

import pytest

from village.config import SandboxSettings
from village.cybergym import _prepare_mock, submit_poc
from village.sandbox import DockerSandbox, ExecResult, make_sandbox


def test_docker_creation_boundary(monkeypatch, tmp_path):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr('village.sandbox.subprocess.run', run)
    sandbox = DockerSandbox.create(tmp_path, SandboxSettings())
    args = calls[0]
    for value in ['none', '--read-only', '--cap-drop', 'ALL',
                  'no-new-privileges', '--pids-limit', '--memory', '--cpus', '--user']:
        assert value in args
    assert args.count('--mount') == 1
    assert f'type=bind,src={tmp_path},dst=/workspace' in args
    assert not any('API_KEY' in str(value) or 'docker.sock' in str(value) for value in args)
    sandbox.close()
    assert calls[-1] == ['docker', 'rm', '--force', sandbox.container]


def test_verifier_uses_sandbox(monkeypatch, tmp_path):
    _prepare_mock('mock:1', tmp_path)
    class Sandbox:
        def run(self, command):
            assert command == "bash submit.sh 'poc; touch escaped'"
            return ExecResult(command, 0, '{"exit_code":0}', '')
    def forbidden(*args, **kwargs):
        raise AssertionError('Host subprocess must not execute grading')
    monkeypatch.setattr('village.cybergym.subprocess.run', forbidden)
    solved, verdict = submit_poc(tmp_path, 'poc; touch escaped', sandbox=Sandbox())
    assert solved and verdict['exit_code'] == 0


def test_unknown_sandbox_fails_closed(tmp_path):
    with pytest.raises(ValueError, match='Unknown sandbox'):
        make_sandbox('dockre', tmp_path, SandboxSettings())


def test_memory_cannot_follow_host_symlink(tmp_path):
    from village.memory import MemoryStore
    victim = tmp_path / 'outside'
    victim.write_text('preserve')
    memory = tmp_path / '.memory.jsonl'
    memory.symlink_to(victim)
    with pytest.raises(OSError):
        MemoryStore().save(memory)
    with pytest.raises(OSError):
        MemoryStore.load(memory)
    assert victim.read_text() == 'preserve'


def test_timeout_removes_container_and_prevents_reuse(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[1] == 'exec':
            raise subprocess.TimeoutExpired(args, 1)
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr('village.sandbox.subprocess.run', run)
    def timeout(*args):
        calls.append(['docker', 'exec'])
        raise subprocess.TimeoutExpired('docker exec', 1)
    monkeypatch.setattr('village.sandbox._capture_docker', timeout)
    sandbox = DockerSandbox('test-container', timeout=1)
    assert sandbox.run('sleep 30').exit_code == 124
    assert calls[-1] == ['docker', 'rm', '--force', 'test-container']
    with pytest.raises(RuntimeError, match='closed'):
        sandbox.run('echo unsafe reuse')
    sandbox.close()  # idempotent after timeout
    assert len(calls) == 2


def test_task_reuse_cannot_write_through_host_symlink(tmp_path):
    victim = tmp_path / 'outside'
    victim.write_text('preserve')
    workspace = tmp_path / 'agent'
    workspace.mkdir()
    (workspace / 'vuln.c').symlink_to(victim)
    with pytest.raises(ValueError, match='regular unlinked'):
        _prepare_mock('mock:1', workspace)
    assert victim.read_text() == 'preserve'


def test_partial_container_startup_is_cleaned_up(monkeypatch, tmp_path):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[1] == 'run':
            raise subprocess.CalledProcessError(125, args)
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr('village.sandbox.subprocess.run', run)
    with pytest.raises(subprocess.CalledProcessError):
        DockerSandbox.create(tmp_path, SandboxSettings())
    assert calls[-1][1:3] == ['rm', '--force']
    assert calls[-1][-1] == calls[0][calls[0].index('--name') + 1]
