#!/usr/bin/env python3
"""Prompt privately for an Adaption key and update the project-local .env."""
from getpass import getpass
from pathlib import Path

from dotenv import set_key


def main():
    env_path = Path(__file__).resolve().parents[1] / '.env'
    print('Adaption inference setup')
    print('Paste your API key below. Input is hidden; press Enter to save.')
    key = getpass('Adaption API key: ').strip()
    if not key or any(char.isspace() for char in key):
        raise SystemExit('No valid key entered. Nothing changed.')
    env_path.touch(mode=0o600, exist_ok=True)
    env_path.chmod(0o600)
    set_key(str(env_path), 'ADAPTION_API_KEY', key)
    set_key(str(env_path), 'INFERENCE_PROVIDER', 'adaption')
    print('Saved to the project .env. Adaption is selected.')
    print('To check inference (no agent shell commands):')
    print(f'cd {env_path.parent}')
    print(' .venv/bin/python run.py check-models --config configs/adaption.yaml')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('\nCancelled.')
