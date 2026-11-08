"""Exercise the real adapters at the HTTP boundary; no paid calls or shell tools."""
import json

import httpx
import pytest

from village.models import AdaptionClient, OpenRouterClient, create_client


def test_openrouter_contract(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-or')
    def respond(request):
        assert request.url.path == '/api/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-or'
        payload = json.loads(request.content)
        assert payload['messages'] == [{'role': 'user', 'content': 'hello'}]
        assert payload['max_tokens'] == 20
        assert payload['stop'] == ['END']
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ready'}}],
            'usage': {'prompt_tokens': 3, 'completion_tokens': 1, 'cost': .001}})
    client = OpenRouterClient(transport=httpx.MockTransport(respond))
    try:
        result = client.chat('model', [{'role': 'user', 'content': 'hello'}], max_tokens=20, stop=['END'])
        assert result.text == 'ready'
        assert client.total_cost_usd == .001
    finally:
        client.close()


def test_adaption_contract(monkeypatch):
    monkeypatch.setenv('ADAPTION_API_KEY', 'test-adaption')
    monkeypatch.setenv('ADAPTION_ORGANIZATION_ID', 'org-test')
    def respond(request):
        assert request.url.path == '/api/v1/responses'
        assert request.headers['Authorization'] == 'Bearer test-adaption'
        assert request.headers['X-Organization-Id'] == 'org-test'
        payload = json.loads(request.content)
        assert payload['input'][0]['role'] == 'system'
        assert payload['max_output_tokens'] == 128
        assert payload['tools'] == [] and payload['tool_choice'] == 'none'
        assert payload['store'] is False and payload['agentic_memory'] is False
        assert 'messages' not in payload and 'max_tokens' not in payload
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'reasoning', 'summary': [{'text': 'private'}]},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': 'ready'}]}],
            'usage': {'input_tokens': 9, 'output_tokens': 2}})
    client = AdaptionClient(transport=httpx.MockTransport(respond))
    try:
        result = client.chat('qwen3.5-397b', [{'role': 'system', 'content': 'hello'}], max_tokens=128)
        assert result.text == 'ready'
        assert (result.prompt_tokens, result.completion_tokens) == (9, 2)
        assert client.total_prompt_tokens == 9
    finally:
        client.close()


@pytest.mark.parametrize('status', ['failed', 'incomplete', 'queued'])
def test_adaption_rejects_noncompleted(status):
    client = AdaptionClient()
    try:
        with pytest.raises(RuntimeError, match='did not complete'):
            client._parse('model', {'status': status})
        with pytest.raises(RuntimeError, match='no reply text'):
            client._parse('model', {'status': 'completed', 'output': []})
    finally:
        client.close()


def test_provider_selection_and_budget(monkeypatch):
    monkeypatch.delenv('INFERENCE_PROVIDER', raising=False)
    client = create_client()
    assert isinstance(client, OpenRouterClient)
    client.close()
    monkeypatch.delenv('ADAPTION_COST_UNIT', raising=False)
    monkeypatch.setenv('INFERENCE_PROVIDER', 'adaption')
    client = create_client()
    assert isinstance(client, AdaptionClient)
    client.close()
    with pytest.raises(ValueError, match='require ADAPTION_COST_UNIT'):
        create_client(budget_usd=1)
    monkeypatch.setenv('INFERENCE_PROVIDER', 'typo')
    with pytest.raises(ValueError, match='Unknown'):
        create_client()


def test_auth_error_is_not_retried_or_leaked(monkeypatch):
    monkeypatch.setenv('ADAPTION_API_KEY', 'test-secret')
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(401, json={'error': 'test-secret'})
    client = AdaptionClient(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RuntimeError, match='adaption HTTP 401') as error:
            client.chat('model', [])
        assert 'test-secret' not in str(error.value)
        assert len(calls) == 1
    finally:
        client.close()


def test_transient_retry(monkeypatch):
    monkeypatch.setenv('ADAPTION_API_KEY', 'test')
    monkeypatch.setattr('village.models.time.sleep', lambda _: None)
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': 'ready'}]}]})
    client = AdaptionClient(transport=httpx.MockTransport(respond))
    try:
        assert client.chat('model', []).text == 'ready'
        assert len(calls) == 2
    finally:
        client.close()


def adaption_response(cost=0.001, status='completed'):
    return {'status': status, 'usage': {'input_tokens': 5, 'output_tokens': 7, 'cost': cost},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'ready'}]}]}


def test_adaption_budget_stops_before_second_http_request(monkeypatch):
    from village.models import BudgetExceeded
    monkeypatch.setenv('ADAPTION_API_KEY', 'test')
    monkeypatch.setenv('ADAPTION_COST_UNIT', 'usd')
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=adaption_response(.002))
    client = AdaptionClient(budget_usd=.001, transport=httpx.MockTransport(respond))
    try:
        result = client.chat('model', [])
        assert result.cost_usd == result.reported_cost == .002
        assert client.total_cost_usd == .002
        assert client.budget_exhausted
        with pytest.raises(BudgetExceeded, match='budget cap'):
            client.chat('model', [])
        assert len(calls) == 1
    finally:
        client.close()


@pytest.mark.parametrize('cost', [None, -1, float('nan'), float('inf'), 'invalid', True])
def test_adaption_missing_or_invalid_cost_stops_budget(monkeypatch, cost):
    from village.models import BudgetExceeded
    monkeypatch.setenv('ADAPTION_COST_UNIT', 'usd')
    client = AdaptionClient(budget_usd=1)
    try:
        with pytest.raises(BudgetExceeded, match='missing or invalid'):
            client._parse('model', adaption_response(cost))
        assert client.budget_exhausted and not client.cost_available
        with pytest.raises(BudgetExceeded):
            client._check_budget()
    finally:
        client.close()


def test_adaption_counts_charged_incomplete_responses(monkeypatch):
    monkeypatch.setenv('ADAPTION_COST_UNIT', 'usd')
    client = AdaptionClient(budget_usd=.001)
    try:
        with pytest.raises(RuntimeError, match='did not complete'):
            client._parse('model', adaption_response(.002, status='incomplete'))
        assert client.total_cost_usd == .002 and client.budget_exhausted
        assert (client.total_prompt_tokens, client.total_completion_tokens) == (5, 7)
    finally:
        client.close()


def test_adaption_records_unverified_units_without_claiming_usd(monkeypatch):
    monkeypatch.delenv('ADAPTION_COST_UNIT', raising=False)
    client = AdaptionClient()
    try:
        result = client._parse('model', adaption_response(.001))
        assert result.reported_cost == client.total_reported_cost == .001
        assert result.cost_usd == client.total_cost_usd == 0
        assert not client.cost_available
    finally:
        client.close()


def test_adaption_zero_cost_is_valid(monkeypatch):
    monkeypatch.setenv('ADAPTION_COST_UNIT', 'usd')
    client = AdaptionClient(budget_usd=1)
    try:
        client._parse('model', adaption_response(0))
        assert client.cost_available and not client.budget_exhausted
    finally:
        client.close()


def test_concurrent_adaption_cost_accumulation(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv('ADAPTION_COST_UNIT', 'usd')
    client = AdaptionClient()
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: client._parse('model', adaption_response(.001)), range(100)))
        assert client.total_cost_usd == pytest.approx(.1)
        assert client.total_prompt_tokens == 500
    finally:
        client.close()


@pytest.mark.parametrize('provider', ['openrouter', 'adaption'])
def test_run_accounts_cost_and_stops_before_next_request(monkeypatch, tmp_path, provider):
    """Exercise factory -> agent -> budget stop -> saved summary, without shell actions."""
    from village.config import load_config
    from village.orchestrator import Orchestrator

    monkeypatch.setenv('INFERENCE_PROVIDER', provider)
    monkeypatch.setenv('ADAPTION_COST_UNIT', 'usd')
    monkeypatch.setenv('ADAPTION_API_KEY', 'test')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test')
    calls = []
    action = '<action>{"tool":"post_message","input":{"text":"hello"}}</action>'
    def respond(request):
        calls.append(request)
        if provider == 'adaption':
            data = adaption_response(.002)
            data['output'][0]['content'][0]['text'] = action
        else:
            data = {'choices': [{'message': {'content': action}}],
                    'usage': {'prompt_tokens': 5, 'completion_tokens': 7, 'cost': .002}}
        return httpx.Response(200, json=data)
    monkeypatch.setattr('village.orchestrator.create_client',
        lambda **kwargs: create_client(transport=httpx.MockTransport(respond), **kwargs))
    path = tmp_path / 'config.yaml'
    path.write_text('village: {name: test, max_steps: 3, budget_usd: 0.001}\n'
                    'sandbox: {kind: local}\nboard: {path: board.jsonl}\nagents: [{name: scout, model: model}]\n')
    orchestrator = Orchestrator(load_config(path), run_id='budget-check')
    results = orchestrator.run()['round']
    assert len(calls) == 1
    assert len(results) == 1 and results[0].budget_stopped
    summary = json.loads((tmp_path / '.village/logs/budget-check/summary.json').read_text())
    assert summary['budget_stopped'] == 1
    assert summary['total_cost_usd'] == .002 and summary['cost_available']
    assert summary['inference_provider'] == provider


@pytest.mark.parametrize('provider', ['openrouter', 'adaption'])
@pytest.mark.parametrize('body', [{'usage': []}, {'usage': {'input_tokens': [], 'cost': None}}, []])
def test_malformed_usage_cannot_bypass_budget(monkeypatch, provider, body):
    from village.models import BudgetExceeded
    monkeypatch.setenv('INFERENCE_PROVIDER', provider)
    monkeypatch.setenv('ADAPTION_COST_UNIT', 'usd')
    client = create_client(budget_usd=1)
    try:
        with pytest.raises(BudgetExceeded, match='missing or invalid'):
            client._parse('model', body)
        assert client.budget_exhausted
    finally:
        client.close()
