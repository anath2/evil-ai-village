#!/usr/bin/env python3
"""Verify real CyberGym grading without inference; reference fixtures never enter a model run."""
import argparse
import json
import tempfile
from pathlib import Path

from village.config import load_config
from village.cybergym import prepare_task, submit_poc
from village.sandbox import DockerSandbox

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(ROOT / 'configs/cybergym.yaml'))
    parser.add_argument('--reference-poc', type=Path, required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)
    cfg.village.id = 'cybergym-preflight'
    reference = args.reference_poc.read_bytes()
    with tempfile.TemporaryDirectory(prefix='cybergym-preflight-') as temp:
        workspace = Path(temp) / 'check'
        workspace.mkdir()
        task = prepare_task(cfg, cfg.task.ids[0], workspace)
        (workspace / 'reference.poc').write_bytes(reference)
        (workspace / 'negative.poc').write_bytes(b'')
        sandbox = DockerSandbox.create(workspace, cfg.sandbox)
        try:
            results = {}
            for filename, expected in [('reference.poc', True), ('negative.poc', False)]:
                solved, verdict = submit_poc(workspace, filename, sandbox=sandbox, task=task)
                results[filename] = verdict
                print(filename, json.dumps(verdict), flush=True)
                assert solved is expected, verdict
            output = ROOT / '.village' / 'cybergym-preflight.json'
            output.write_text(json.dumps(results, indent=2))
            print('PASS real vulnerable/fixed positive and negative grading; agents had no network')
        finally:
            sandbox.close()


if __name__ == '__main__':
    main()
