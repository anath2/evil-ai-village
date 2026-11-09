"""Publication boundary checks: raw evidence survives, credentials/symlinks do not."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_evidence_snapshot as snapshot


def test_snapshot_preserves_failed_evidence_without_credentials(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    run = repo / '.village/communication-study-failed/pilot'
    run.mkdir(parents=True)
    secret = 'example-sensitive-provider-value-123456789'
    (repo / '.env').write_text('ADAPTION_API_KEY=' + secret)
    (run / 'study.json').write_text(json.dumps({'status': 'failed', 'reply': secret}))
    outside = tmp_path / 'private.txt'
    outside.write_text('unrelated private material')
    (run / 'leak.txt').symlink_to(outside)
    (run / 'generated.bin').write_bytes(b'\x00\xff')
    source = run.parent / 'source'
    source.mkdir()
    (source / '.env').symlink_to(repo / '.env')
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **kw: 'abc123\n')
    output = tmp_path / 'out'
    manifest = snapshot.prepare(repo, output)
    saved = output / 'runs/communication-study-failed/pilot/study.json'
    assert json.loads(saved.read_text())['status'] == 'failed'
    assert secret not in saved.read_text()
    assert manifest['files'][0]['redactions'] == 1
    assert not any(p.is_symlink() for p in output.rglob('*'))
    assert not list(output.rglob('.env'))
    assert not list(output.rglob('*.bin'))
    assert not any('unrelated private material' in p.read_text() for p in output.rglob('*') if p.is_file())
