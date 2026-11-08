#!/usr/bin/env python3
"""Live Docker checks without inference or model-generated commands."""
import json
import subprocess
import tempfile
import shlex
import os
from pathlib import Path

from village.config import SandboxSettings
from village.cybergym import _prepare_mock, submit_poc
from village.sandbox import DockerSandbox


def main():
    with tempfile.TemporaryDirectory(prefix='village-isolation-') as directory:
        root = Path(directory)
        workspace = root / 'agent'
        workspace.mkdir()
        canary = root / 'host-only'
        canary.write_text('host canary')
        _prepare_mock('mock:1', workspace)
        sandbox = DockerSandbox.create(workspace, SandboxSettings(bash_timeout=30))
        try:
            info = json.loads(subprocess.check_output(['docker', 'inspect', sandbox.container]))[0]
            assert info['HostConfig']['NetworkMode'] == 'none'
            assert info['HostConfig']['ReadonlyRootfs']
            assert info['Config']['User'] == f'{os.getuid()}:{os.getgid()}'
            assert info['HostConfig']['CapDrop'] == ['ALL']
            assert 'no-new-privileges' in info['HostConfig']['SecurityOpt']
            assert len(info['Mounts']) == 1
            assert info['Mounts'][0]['Source'] == str(workspace)
            checks = {
                'host files hidden': f'test ! -e {shlex.quote(str(canary))} && test ! -e {shlex.quote(str(Path.home() / ".ssh"))} && test ! -e {shlex.quote(str(Path(__file__).resolve().parents[1] / ".env"))}',
                'effective seccomp and privilege restrictions': "grep -Eq '^Seccomp:[[:space:]]+2$' /proc/self/status && grep -Eq '^NoNewPrivs:[[:space:]]+1$' /proc/self/status",
                'Docker socket hidden': 'test ! -S /var/run/docker.sock',
                'credentials absent': 'test -z "$ADAPTION_API_KEY$OPENROUTER_API_KEY"',
                'system writes blocked': '! touch /etc/village-test 2>/dev/null',
                'workspace writable': 'printf AAAAAAAAAAAAAAAA > poc',
                'network blocked': "python3 -c \"import socket; s=socket.socket(); s.settimeout(2); assert s.connect_ex(('1.1.1.1',443)) != 0\"",
            }
            for name, command in checks.items():
                result = sandbox.run(command)
                assert result.exit_code == 0, (name, result.output)
                print('PASS', name)
            solved, verdict = submit_poc(workspace, 'poc', sandbox=sandbox)
            assert solved, verdict
            sandbox.run('printf AAAA > small')
            solved, verdict = submit_poc(workspace, 'small', sandbox=sandbox)
            assert not solved and verdict['exit_code'] == 1, verdict
            print('PASS real compilation and positive/negative grading inside container')
            # A timed-out CLI must not leave its command running in the daemon.
            sandbox.timeout = 1
            result = sandbox.run('sleep 30 & wait')
            assert result.exit_code == 124
            result = subprocess.run(['docker', 'inspect', sandbox.container], capture_output=True)
            assert result.returncode != 0
            print('PASS timeout removes container and child processes')
        finally:
            sandbox.close()
        noisy = DockerSandbox.create(workspace, SandboxSettings(max_output_chars=1024))
        try:
            result = noisy.run('yes output')
            assert result.exit_code == 125 and len(result.stdout.encode()) <= 1024
            assert subprocess.run(['docker', 'inspect', noisy.container], capture_output=True).returncode != 0
            print('PASS output limit bounds harness capture and removes container')
        finally:
            noisy.close()
    print('PASS test containers removed')


if __name__ == '__main__':
    main()
