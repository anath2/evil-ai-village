import json
import re
import threading

import httpx
import pytest

from scripts.probe_concurrency import run_wave, summarize_wave
from village.models import AdaptionClient


def make_client(monkeypatch, handler):
    monkeypatch.setenv('ADAPTION_API_KEY','test-only-not-a-real-key')
    monkeypatch.setenv('ADAPTION_COST_UNIT','usd')
    return AdaptionClient(budget_usd=.01,max_retries=1,model_concurrency=0,
                          transport=httpx.MockTransport(handler))


def test_multiple_requests_for_each_model_really_overlap(monkeypatch):
    barrier=threading.Barrier(4,timeout=5)
    def handler(request):
        prompt=json.loads(request.content)['input'][0]['content']
        obj=json.loads(re.search(r'(\{"token":"[a-f0-9]+","ok":true\})',prompt).group(1))
        barrier.wait()
        return httpx.Response(200,json={'status':'completed','usage':{
            'input_tokens':40,'output_tokens':15,'cost':.000001},'output':[{
                'type':'message','content':[{'type':'output_text','text':json.dumps(obj)}]}]})
    client=make_client(monkeypatch,handler)
    try:
        rows,summary=run_wave(client,['a','b'],2,0)
        assert len(rows)==4 and summary['valid']==4
        assert summary['issued_http_peak']==4
        assert summary['issued_http_peak_by_model']=={'a':2,'b':2}
        assert summary['all_models_overlapped']
        assert len({r['expected_token'] for r in rows})==4
        assert client.total_cost_usd==pytest.approx(.000004)
    finally:client.close()


def test_http_failures_are_not_hidden_as_retry_success(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(429,json={'error':'do-not-log-this-body'},
                              headers={'Retry-After':'60','Set-Cookie':'do-not-log-this-cookie'})
    client=make_client(monkeypatch,handler)
    try:
        rows,summary=run_wave(client,['a','b'],2,0)
        assert len(calls)==4 and summary['valid']==0
        assert all(r['outcome']=='http_429' for r in rows)
        assert 'do-not-log-this-body' not in json.dumps(rows)
        assert 'do-not-log-this-cookie' not in json.dumps(rows)
        assert all(r['rate_limit_headers']=={'retry-after':'60'} for r in rows)
    finally:client.close()


def test_threads_are_not_counted_as_overlapping_http_calls():
    rows=[{'model':'a','issued':True,'start':0,'end':1,'seconds':1,'valid':True,'outcome':'valid'},
          {'model':'b','issued':True,'start':1,'end':2,'seconds':1,'valid':False,'outcome':'timeout'}]
    summary=summarize_wave(rows,2)
    assert summary['issued_http_peak']==1
    assert not summary['all_models_overlapped']
    assert summary['valid_per_second']==.5
    assert summary['models'][1]['p95_seconds']==1
