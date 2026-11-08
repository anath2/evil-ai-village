#!/usr/bin/env python3
"""Run the pinned upstream verifier on loopback only; no agent shell executes here."""
import runpy
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    load_dotenv(ROOT / '.env')
    directory = ROOT / '.village' / 'cybergym-server'
    directory.mkdir(parents=True, exist_ok=True)
    sys.argv = ['cybergym.server', '--host', '127.0.0.1', '--port', '8666',
                '--log_dir', str(directory), '--db_path', str(directory / 'poc.db')]
    runpy.run_module('cybergym.server', run_name='__main__')
