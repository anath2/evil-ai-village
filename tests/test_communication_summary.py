import json
from scripts.summarize_communication_study import summarize,write_outputs


def report():
    agent={'name':'worker-1','confirmed_task_change':False,'peer_exposed':True,
           'recorded_notes':2,'post_attempts':1,'submissions':0,'finish_actions':1,
           'sandbox_lost':False,'api_errors':0,'valid_turns':3,'model_turns':3,'truncated_replies':0}
    return {'protocol':'communication-impossibility-v4','pilot':False,'status':'complete',
            'source_commit':'test-commit','source_sha256':{},'models':{'deepseek':'test-model'},
            'settings':{},'schedule':[{'roster':'deepseek','seed':0,'board':True}],
            'started_utc':'2026-11-09T00:00:00+00:00','finished_utc':'2026-11-09T00:01:00+00:00',
            'cost_usd':.01,'http_attempts':4,'dispatches':[{'monotonic':0},{'monotonic':1.6}],
            'preparations':{'deepseek-0':[{'name':'worker-1','ok':True,'text':'PRIVATE_NOTE_SENTINEL'}]},
            'results':[{'roster':'deepseek','seed':0,'board':True,'complete':True,
                        'any_confirmed_task_change':False,'agents':[agent],
                        'verified_successes':0,'http_attempts':3,'seconds':10,'reported_cost_usd':.005}]}


def test_curated_summary_omits_note_text_and_does_not_count_initial_notes_as_followup():
    data=summarize(report())
    assert 'PRIVATE_NOTE_SENTINEL' not in json.dumps(data)
    assert data['villages'][0]['followup_notes']==1
    assert data['preparation_calls']==1
    cell=next(c for c in data['cells'] if c['roster']=='deepseek' and c['shared'])
    assert cell['change_risk_wilson95'][1]>.7
    assert data['analysis']['primary_homogeneous_pair_count']==0


def test_partial_study_is_labelled_and_unknown_cost_supported(tmp_path):
    r=report();r['status']='stopped';r['cost_usd']=None;r['schedule'].append({'roster':'qwen','seed':0,'board':True})
    data=write_outputs(r,tmp_path/'summary')
    assert data['missing_villages']==1
    text=(tmp_path/'summary/README.md').read_text()
    assert 'INCOMPLETE' in text and 'unknown' in text
    assert 'PRIVATE_NOTE_SENTINEL' not in (tmp_path/'summary/metrics.json').read_text()
