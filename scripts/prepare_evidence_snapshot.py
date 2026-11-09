#!/usr/bin/env python3
"""Prepare a reviewed, text-only mock-experiment snapshot; never upload or run agents."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

from dotenv import dotenv_values

from upload_to_hf import SECRET_PATTERNS


def prepare(repo: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    runtime = repo / '.village'
    sources: list[tuple[Path, Path]] = [(repo / 'reports', Path('reports'))]
    for pattern in ('communication-study-*', 'concurrency-*', 'stale-handoff-pilot*',
                    'stale-handoff-publication-draft', 'scale-500-*'):
        sources.extend((p, Path('runs') / p.name) for p in sorted(runtime.glob(pattern)) if p.is_dir())
    for p in sorted((runtime / 'logs').glob('scale-*')):
        sources.append((p, Path('early-mock/logs') / p.name))
    for p in sorted((runtime / 'workspaces').glob('scale-*')):
        sources.append((p, Path('early-mock/workspaces') / p.name))
    for pattern in ('scale-*-board.jsonl', 'latest-*.json', 'stale-handoff-diagnostic*.json',
                    'scale*trial.log', 'model-cost-smoke.json', 'gate_and_start_communication.py',
                    'diagnose_empty_responses.py'):
        sources.extend((p, Path('operations') / p.name) for p in sorted(runtime.glob(pattern)) if p.is_file())
    # The paused 500-agent harness wrote its evidence inside its frozen checkout.
    for p in sorted(runtime.glob('scale-500-*/source/.village')):
        sources.append((p, Path('runs') / p.parents[1].name / 'runtime'))

    configured = {**os.environ, **dotenv_values(repo / '.env')}
    secrets = [str(v).encode() for k, v in configured.items() if v and len(str(v)) >= 12
               and re.search(r'TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY', k, re.I)]
    files, omissions = [], []
    for source, destination in sources:
        for p in sorted(source.rglob('*')) if source.is_dir() else [source]:
            relative = p.relative_to(source) if source.is_dir() else Path()
            target = destination / relative
            if any(x in {'source', '__pycache__', '.git', '.venv'} for x in relative.parts):
                continue  # Frozen code is already preserved by its Git commit, not duplicated here.
            if p.is_dir() and not p.is_symlink():
                continue
            if p.is_symlink() or any(parent.is_symlink() for parent in p.parents if parent != repo.parent):
                omissions.append({'path': str(target), 'reason': 'symlink; never dereferenced'})
                continue
            if not p.is_file() or p.name == '.env' or p.name.endswith('.env') or p.suffix in {'.pyc', '.bin', '.gz'}:
                omissions.append({'path': str(target), 'reason': 'credential path, generated binary, or special file'})
                continue
            before = p.stat()
            content = p.read_bytes()
            after = p.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f'File changed during snapshot: {p.relative_to(repo)}')
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                omissions.append({'path': str(target), 'reason': 'non-UTF8 generated artifact'})
                continue
            if b'\0' in content:
                omissions.append({'path': str(target), 'reason': 'binary content'})
                continue
            redactions = 0
            for secret in secrets:
                redactions += content.count(secret)
                content = content.replace(secret, b'[REDACTED_CONFIGURED_CREDENTIAL]')
            text = content.decode('utf-8')
            for pattern, kind in SECRET_PATTERNS:
                text, n = pattern.subn('[REDACTED_CREDENTIAL]', text)
                redactions += n
            content = text.encode()
            dest = output / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            files.append({'path': target.as_posix(), 'bytes': len(content),
                          'sha256': hashlib.sha256(content).hexdigest(), 'redactions': redactions})
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
                'repository_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
                'files': files, 'omissions': omissions,
                'frozen_source_policy': 'Execution source commits/hashes are in run records; duplicate source checkouts omitted.',
                'scope': 'Local synthetic mock experiments only. Excludes CyberGym server, real-target/reference data, credentials, chat history and process memory.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(Path(__file__).resolve().parents[1], args.output.resolve())
    print(json.dumps({'files': len(result['files']), 'bytes': sum(f['bytes'] for f in result['files']),
                      'redactions': sum(f['redactions'] for f in result['files']), 'omissions': len(result['omissions'])}))
