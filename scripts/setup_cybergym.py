#!/usr/bin/env python3
"""Fetch one ARVO task and its two images; never download the full benchmark."""
import argparse
import os
import re
import secrets
import subprocess
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', default='arvo:1065')
    parser.add_argument('--skip-images', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'arvo:\d+', args.task):
        parser.error('This setup helper supports ARVO task IDs, e.g. arvo:1065')
    number = args.task.split(':')[1]
    target = ROOT / 'cybergym_data' / 'data' / 'arvo' / number
    target.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for name in ['repo-vul.tar.gz', 'description.txt', 'error.txt']:
            path = target / name
            if not path.exists():
                url = f'https://huggingface.co/datasets/sunblaze-ucb/cybergym/resolve/main/data/arvo/{number}/{name}'
                with client.stream('GET', url) as response:
                    response.raise_for_status()
                    temporary = path.with_suffix(path.suffix + '.part')
                    size = 0
                    with temporary.open('wb') as stream:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 256 * 1024**2:
                                raise ValueError('Task download exceeds the 256 MiB setup limit')
                            stream.write(chunk)
                    temporary.replace(path)
            print(name, path.stat().st_size, 'bytes', flush=True)
    env_path = ROOT / '.env'
    env_path.touch(mode=0o600, exist_ok=True)
    env_path.chmod(0o600)
    if not (os.environ.get('CYBERGYM_API_KEY') or dotenv_values(env_path).get('CYBERGYM_API_KEY')):
        set_key(str(env_path), 'CYBERGYM_API_KEY', secrets.token_urlsafe(32))
        print('Created a private verifier key in ignored .env (not printed).', flush=True)
    if not args.skip_images:
        for mode in ['vul', 'fix']:
            subprocess.run(['docker', 'pull', f'n132/arvo:{number}-{mode}'], check=True)
    print('Task ready. Start scripts/cybergym_server.py, then use configs/cybergym.yaml.')


if __name__ == '__main__':
    main()
