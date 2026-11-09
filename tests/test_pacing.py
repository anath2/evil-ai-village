"""Every retry must pass the same dispatch limiter as an initial HTTP request."""
import json
from concurrent.futures import ThreadPoolExecutor

import httpx

from village.models import OpenRouterClient
from village.pacing import RequestPacer


def test_retries_are_paced_and_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test')
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={'retry-after': '0'}, json={'error': 'busy'})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ok'}}],
                                        'usage': {'cost': 0, 'prompt_tokens': 1, 'completion_tokens': 1}})
    client = OpenRouterClient(transport=httpx.MockTransport(handler), max_retries=2)
    pacer = RequestPacer(.01, tmp_path / 'attempts.jsonl')
    client._client.event_hooks['request'].append(pacer)
    assert client.chat('test-model', [{'role': 'user', 'content': 'hi'}]).text == 'ok'
    rows = [json.loads(line) for line in pacer.path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[1]['monotonic'] - rows[0]['monotonic'] >= .009
    assert all(row['model'] == 'test-model' for row in rows)
    assert all('hi' not in row for row in rows)
    client.close()


def test_shared_pacer_serializes_threads(tmp_path):
    pacer = RequestPacer(.01, tmp_path / 'attempts.jsonl')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(pacer, [httpx.Request('POST', 'https://example.com', json={'model': 'test'}) for _ in range(4)]))
    rows = [json.loads(line) for line in pacer.path.read_text().splitlines()]
    assert len(rows) == 4
    assert min(b['monotonic'] - a['monotonic'] for a, b in zip(rows, rows[1:])) >= .009


def test_shuffled_roster_preserves_main_model_counts():
    from scripts.scale_society import build_config, roster_models
    from collections import Counter
    cfg = build_config(500, 'mock:impossible', 6, 10, 1800, 'test', roster_seed=20261109)
    assert Counter(a.model for a in cfg.agents) == Counter(m for m, _ in roster_models(500))
    assert len({a.model for a in cfg.agents[:28]}) == 4


def test_overlapping_calls_do_not_double_count_client_retries(monkeypatch):
    import threading
    from scripts import scale_society as scale
    entered = threading.Barrier(2)
    counted = threading.Barrier(2)
    guard = threading.Lock()
    class Client:
        retry_count = 0
        truncated_count = 0
        def chat(self):
            entered.wait()
            with guard:
                self.retry_count = 1
                self.truncated_count = 1
            counted.wait()
            return 'ok'
    client = Client()
    monkeypatch.setattr(scale, 'create_client', lambda **kw: client)
    metrics = dict(active=0, peak=0, calls=0, errors=0, retries=0, truncated=0, latencies=[])
    factory = scale.measured_client_factory(metrics, threading.Lock())
    measured = factory()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: measured.chat(), range(2))) == ['ok', 'ok']
    assert metrics['calls'] == 2
    assert metrics['retries'] == 1
    assert metrics['truncated'] == 1
