#!/usr/bin/env python3
"""Bounded, inference-only, simultaneous all-model Adaption capacity probe."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from village.models import AdaptionClient, BudgetExceeded


def percentile(values, p):
    return sorted(values)[min(len(values)-1, math.ceil(p*len(values))-1)] if values else None


def summarize_wave(rows, seconds):
    groups = []
    for model in sorted({r['model'] for r in rows}):
        selected = [r for r in rows if r['model'] == model]
        latencies = [r['seconds'] for r in selected if r.get('issued')]
        groups.append({'model': model, 'attempts': len(selected),
                       'valid': sum(r['valid'] for r in selected),
                       'errors': dict(Counter(r['outcome'] for r in selected if not r['valid'])),
                       'p50_seconds': statistics.median(latencies) if latencies else None,
                       'p95_seconds': percentile(latencies, .95),
                       'valid_per_second': sum(r['valid'] for r in selected)/max(seconds, 1e-9)})
    # Recompute concurrency from recorded intervals; never equate thread count
    # with actual issued HTTP overlap. End events precede starts at equal times.
    events = sorted((t,delta,r['model']) for r in rows if r.get('issued')
                    for t,delta in ((r['start'],1),(r['end'],-1)))
    active = Counter(); peaks = Counter(); peak = 0; all_models_overlap = False
    for _, delta, model in events:
        active[model] += delta
        peaks[model] = max(peaks[model], active[model])
        peak = max(peak, sum(active.values()))
        all_models_overlap |= all(active[m] > 0 for m in {r['model'] for r in rows})
    return {'seconds': seconds, 'models': groups, 'issued_http_peak': peak,
            'issued_http_peak_by_model': dict(peaks),
            'all_models_overlapped': all_models_overlap,
            'valid': sum(r['valid'] for r in rows), 'attempts': len(rows),
            'valid_per_second': sum(r['valid'] for r in rows)/max(seconds, 1e-9)}


def run_wave(client, models, copies, trial, output_tokens=2048):
    jobs = [(model, i) for model in models for i in range(copies)]
    barrier = threading.Barrier(len(jobs), timeout=30)

    def request(job):
        model, index = job
        nonce = hashlib.sha256(f'{model}:{copies}:{trial}:{index}'.encode()).hexdigest()[:16]
        row = {'model': model, 'index': index, 'issued': False, 'valid': False,
               'outcome': 'not_issued', 'expected_token': nonce}
        prompt = ('This is a benign API transport test. Return only a JSON object '
                  'with exactly these fields: {"token":"'+nonce+'","ok":true}. '
                  'Do not use Markdown, tools or additional commentary.')
        payload = client._payload(model, [{'role':'user','content':prompt}], 0, output_tokens, None)
        try:
            barrier.wait()
            client._check_budget()
            row.update(issued=True, start=time.perf_counter())
            try:
                response = client._client.post(client._url(), headers=client._headers(), json=payload)
            finally:
                row['end'] = time.perf_counter()
                row['seconds'] = row['end']-row['start']
            row['http_status'] = response.status_code
            # Explicit allowlist: retain quota diagnostics, never auth/cookies
            # or arbitrary response headers. Raw provider bodies stay excluded.
            allowed = ('retry-after','x-ratelimit-limit-requests',
                       'x-ratelimit-remaining-requests','x-ratelimit-reset-requests',
                       'ratelimit-limit','ratelimit-remaining','ratelimit-reset')
            row['rate_limit_headers'] = {k:response.headers[k][:100] for k in allowed if k in response.headers}
            if response.status_code != 200:
                row['outcome'] = 'http_'+str(response.status_code)
                return row
            data = response.json()
            result = client._parse(model, data)
            row.update(cost_usd=result.cost_usd, input_tokens=result.prompt_tokens,
                       output_tokens=result.completion_tokens, truncated=result.truncated,
                       reply=result.text[:300])
            try:
                obj = json.loads(result.text)
                valid = (isinstance(obj,dict) and set(obj)=={'token','ok'}
                         and obj['token']==nonce and obj['ok'] is True)
            except ValueError:
                valid = False
            row['valid'] = valid and not result.truncated
            row['outcome'] = 'valid' if row['valid'] else 'truncated' if result.truncated else 'invalid_reply'
        except BudgetExceeded:
            row['outcome'] = 'budget_or_unknown_cost'
        except httpx.TimeoutException:
            row['outcome'] = 'timeout'
        except httpx.TransportError:
            row['outcome'] = 'transport_error'
        except Exception as exc:
            # Never write request headers, provider response bodies or exception text.
            row.update(outcome='response_error', error_type=type(exc).__name__)
        return row

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        rows = list(pool.map(request, jobs))
    return rows, summarize_wave(rows, time.perf_counter()-started)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--models', nargs='+', help='optional catalogue subset for isolated follow-up controls')
    p.add_argument('--levels', type=int, nargs='+', default=[1,2,4,8,16])
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--budget', type=float, default=.25)
    p.add_argument('--timeout', type=float, default=90)
    args = p.parse_args()
    if (not math.isfinite(args.budget) or args.budget <= 0 or
        not args.levels or any(n<1 or n>16 for n in args.levels) or
        args.levels != sorted(set(args.levels)) or not 1<=args.repeats<=3 or
        not math.isfinite(args.timeout) or args.timeout<=0):
        p.error('Use ascending unique levels in 1..16, 1..3 repeats, positive budget/timeout.')
    args.output.mkdir(parents=True, exist_ok=False)
    load_dotenv(ROOT/'.env')
    client = AdaptionClient(budget_usd=args.budget, timeout=args.timeout, max_retries=1, model_concurrency=0)
    report = {'protocol':'mixed-api-capacity-v1', 'status':'starting',
              'started_utc':datetime.now(timezone.utc).isoformat(),
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'model_client_sha256':hashlib.sha256((ROOT/'src/village/models.py').read_bytes()).hexdigest(),
              'levels':args.levels,'repeats':args.repeats,'soft_budget_usd':args.budget,
              'request_timeout_seconds':args.timeout,'max_output_tokens':2048,
              'retries':0,'model_semaphore':False,'waves':[],
              'interpretation':'Client-issued HTTP overlap, not proof of concurrent server-side GPU execution. Synthetic short-output workload; no behavioural generalisation claim.'}

    def save():
        report.update(cost_usd=client.total_cost_usd if client.cost_available else None,
                      input_tokens=client.total_prompt_tokens, output_tokens=client.total_completion_tokens)
        target=args.output/'report.json';temp=args.output/'report.tmp'
        temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(target)

    try:
        response=client._client.get(client._url().rsplit('/',1)[0]+'/models',headers=client._headers())
        response.raise_for_status()
        catalogue=sorted({m['id'] for m in response.json()['data']})
        if not catalogue or len(catalogue)>16:raise ValueError('Unexpected catalogue size')
        models=sorted(set(args.models)) if args.models else catalogue
        if not set(models)<=set(catalogue):raise ValueError('Requested model absent from catalogue')
        max_connections=len(models)*max(args.levels)
        client._client.close()
        client._client=httpx.Client(timeout=args.timeout, limits=httpx.Limits(
            max_connections=max_connections,max_keepalive_connections=max_connections))
        report.update(models=models, catalogue=catalogue, max_http_connections=max_connections, status='running')
        save()
        # Warmups also run across all models together, but are not pooled into
        # measured wave results. Responses have unique per-request nonces.
        schedule=[(1,-1)]+[(n,r) for n in args.levels for r in range(args.repeats)]
        for n,trial in schedule:
            rows,summary=run_wave(client,models,n,trial)
            report['waves'].append({'copies_per_model':n,'trial':trial,
                                    'warmup':trial==-1,'summary':summary,'requests':rows})
            save()
            print(json.dumps({'copies_per_model':n,'trial':trial,'valid':summary['valid'],
                              'attempts':len(rows),'http_peak':summary['issued_http_peak'],
                              'cost_usd':report['cost_usd']}),flush=True)
            if client.budget_exhausted or any(r['outcome'] in ('http_401','http_403','budget_or_unknown_cost') for r in rows):
                report.update(status='stopped',stop_reason='budget_or_authentication');break
            if trial>=0 and any(r['outcome']=='http_429' for r in rows):
                report.update(status='stopped',stop_reason='rate_limit; honor provider before escalating');break
            if trial>=0 and any(m['valid']/m['attempts']<.75 for m in summary['models']):
                report.update(status='stopped',stop_reason='validity_below_75_percent; diagnose before escalating');break
        else:report['status']='complete'
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error_type=type(exc).__name__)
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save();client.close()
    return 0 if report['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
