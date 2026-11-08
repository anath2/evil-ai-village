#!/usr/bin/env python3
"""Bounded paid mock-agent scaling trial; writes sanitized JSON and HTML results."""
import argparse
import html
import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from village.config import load_config
from village.models import create_client
from village.orchestrator import Orchestrator
import village.orchestrator as orchestration

ROOT = Path(__file__).resolve().parents[1]


class BatchedOrchestrator(Orchestrator):
    def _run_agents(self, agents):
        results = []
        for offset in range(0, len(agents), 8):
            results.extend(super()._run_agents(agents[offset:offset + 8]))
        return results


def write_report(output, report):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    rows = ''.join(
        '<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in (
            r.get('mode', 'mock task solving'), r['agents_requested'], r['agents_completed'], r['solved'],
            r['board_messages'],
            r['peak_concurrent_chat_calls'], r['chat_calls'], r['request_errors'],
            f"{r['seconds']:.1f}s", f"${r['cost_usd']:.6f}" if r['cost_available'] else 'unknown',
            r.get('error', 'completed'))) + '</tr>' for r in report['runs'])
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Village scaling trial</title><style>
body{font:16px system-ui;max-width:1100px;margin:48px auto;padding:0 24px;background:#111820;color:#e5edf5}
h1{font-size:40px;margin-bottom:8px}p{line-height:1.6;color:#bccbd8}table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:14px 10px;border-bottom:1px solid #354250}th{color:#86d5b1}
.scroll{overflow-x:auto}.tag{color:#86d5b1}footer{margin-top:32px;font-size:14px}</style>
<p class="tag">EVIL AI VILLAGE · MEASURED MOCK TRIAL</p><h1>More agents. Actual runs.</h1>
<p>Concurrent model agents, separate network-disabled Docker workspaces, a shared board,
and deterministic toy grading. These measurements show only the tested sizes and machine.</p>
<div class="scroll"><table><thead><tr><th>Mode</th><th>Requested</th><th>Completed</th><th>Solved</th><th>Board posts</th>
<th>Peak chat concurrency</th><th>Chat calls</th><th>Request errors</th><th>Wall time</th>
<th>Reported USD</th><th>Status</th></tr></thead><tbody>ROWS</tbody></table></div>
<p>Budgets are soft and can overshoot through concurrent in-flight requests. Chat calls
include failures; recorded costs cannot establish charges for requests whose responses were lost.
Model-reported API cost units are configured as USD for this account.</p>
<p>Runs above eight agents use sequential batches of at most eight, two turns each,
and board-focused instructions. Other tools remain available; zero solves is expected there.
Completed means the loop returned, including reaching its turn limit, rather than an explicit finish.
This is not evidence of 100 concurrent agents, useful cooperation, real vulnerability solving,
or a capability benchmark. Solved counts are harness verdicts on writable mock tasks.</p>
<footer>Generated: DATE · Source base: COMMIT · Raw measurements: results.json</footer></html>'''
    page = page.replace('ROWS', rows).replace('DATE', html.escape(report['started_utc']))
    page = page.replace('COMMIT', html.escape(report['source_commit']))
    (output / 'index.html').write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counts', type=int, nargs='+', default=[2, 4, 8])
    parser.add_argument('--budget-per-run', type=float, default=.10)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports' / 'mock-scale-2026-11-08')
    args = parser.parse_args()
    if not args.counts or any(n < 1 or n > 100 for n in args.counts):
        parser.error('Use between 1 and 100 agents per run (at most eight active)')
    if not 0 < args.budget_per_run <= .10 or len(args.counts) > 3:
        parser.error('At most three runs, each with a positive soft budget no larger than $0.10')
    subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], check=True,
                   capture_output=True, timeout=15)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(),
              'source_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
              'provider': None, 'model': 'deepseek-v4-flash',
              'soft_budget_per_run_usd': args.budget_per_run, 'runs': []}
    write_report(args.output, report)
    for count in args.counts:
        cfg = load_config(ROOT / 'configs/adaption-docker-smoke.yaml')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        cfg.village.name = f'scale-{count}-{stamp}'
        cfg.village.id = cfg.village.name
        cfg.village.budget_usd = args.budget_per_run
        cfg.village.time_budget_seconds = 90
        if count > 8:
            cfg.village.max_steps = 2
            cfg.village.goal = (
                'Throughput-only board trial: post one concise greeting to the shared '
                'board using post_message, then use finish. Do not run bash, solve '
                'the task, or submit a PoC. This measures orchestration, not solving.'
            )
        cfg.board.path = f'.village/{cfg.village.name}-board.jsonl'
        prototype = cfg.agents[0]
        cfg.agents = [type(prototype)(name=f'agent-{i+1:02}', model=prototype.model,
                     tier='trial', task=f'mock:{1+i%2}') for i in range(count)]
        metrics = {'active': 0, 'peak': 0, 'attempts': 0, 'errors': 0}
        lock = threading.Lock()

        def measured_client(**kwargs):
            client = create_client(timeout=30, max_retries=1, **kwargs)
            original = client.chat
            report['provider'] = client.provider

            def chat(*chat_args, **chat_kwargs):
                with lock:
                    metrics['active'] += 1
                    metrics['attempts'] += 1
                    metrics['peak'] = max(metrics['peak'], metrics['active'])
                try:
                    return original(*chat_args, **chat_kwargs)
                except Exception:
                    with lock:
                        metrics['errors'] += 1
                    raise
                finally:
                    with lock:
                        metrics['active'] -= 1
            client.chat = chat
            return client

        orchestration.create_client = measured_client
        runner = BatchedOrchestrator(cfg, run_id=cfg.village.name)
        started = time.monotonic()
        row = {'agents_requested': count, 'active_agent_limit': 8,
               'mode': 'board-focused throughput, two turns' if count > 8 else 'mock task solving'}
        results = []
        try:
            rounds = runner.run()
            results = [r for values in rounds.values() for r in values]
        except Exception as error:
            row['error'] = type(error).__name__
        finally:
            orchestration.create_client = create_client
        row.update(agents_completed=len(results), solved=sum(r.solved for r in results),
                   seconds=round(time.monotonic()-started, 3),
                   peak_concurrent_chat_calls=metrics['peak'], chat_calls=metrics['attempts'],
                   request_errors=metrics['errors'],
                   cost_usd=getattr(runner, 'total_cost_usd', 0),
                   cost_available=getattr(runner, 'cost_available', False),
                   board_messages=sum(1 for _ in cfg.abspath(cfg.board.path).open()) if cfg.abspath(cfg.board.path).exists() else 0,
                   agents=[{'name': r.name, 'solved': r.solved, 'steps': r.steps,
                            'budget_stopped': r.budget_stopped} for r in results])
        report['runs'].append(row)
        write_report(args.output, report)
        print('MEASUREMENT', json.dumps(row), flush=True)
        if row.get('error') or len(results) != count or not row['cost_available'] or sum(r.budget_stopped for r in results):
            print('Stopping before larger runs: incomplete run or budget/accounting limit.', flush=True)
            break
    print('Report:', args.output / 'index.html', flush=True)


if __name__ == '__main__':
    main()
