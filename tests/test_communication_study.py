from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
from types import SimpleNamespace

from village.agent import Agent
from village.board import Board
from village.models import ChatResult
from village.tools import Action,action_format_error,parse_action
from scripts.study_communication import StudyAgent,StudyOrchestrator,MODELS,INSTRUCTION,analyse,roster_for,outcomes,build_config


def agent(tmp_path,enabled):
    board=Board(tmp_path/'board.jsonl')
    board.post('peer','PRIVATE_PEER_SENTINEL')
    return StudyAgent(name='worker',model='test',tier='study',
        task=SimpleNamespace(task_id='mock:test',description='test task',workspace=tmp_path,provider='mock'),
        goal='solve task',client=None,sandbox=None,board=board,
        communication_enabled=enabled,initial_instruction=INSTRUCTION)


def test_control_blocks_board_at_prompt_and_dispatch(tmp_path):
    a=agent(tmp_path,False)
    messages=a._messages()
    text=json.dumps(messages)
    assert 'PRIVATE_PEER_SENTINEL' not in text
    assert 'read_board' not in text and 'post_message' not in text
    before=len(a.board)
    assert 'disabled' in a._dispatch(Action('read_board',{}))
    assert 'disabled' in a._dispatch(Action('post_message',{'text':'leak'}))
    assert len(a.board)==before


def test_treatment_exposes_peers_and_keeps_tools(tmp_path):
    a=agent(tmp_path,True)
    text=json.dumps(a._messages())
    assert 'PRIVATE_PEER_SENTINEL' in text
    assert 'read_board' in text and 'post_message' in text
    assert '- reflect ' not in text and '- recall ' not in text
    assert 'only bash' in a._dispatch(Action('reflect',{}))


def test_neutral_kickoff_is_identical_across_conditions(tmp_path):
    class Client:
        def chat(self,model,messages,**kwargs):
            assert messages[1]['content']==INSTRUCTION
            return ChatResult(text='<action>{"tool":"finish","input":{"summary":"done"}}</action>')
    for enabled in (False,True):
        folder=tmp_path/str(enabled);folder.mkdir()
        a=agent(folder,enabled);a.client=Client()
        a.max_steps=1;a.reflect_every=0;a.consolidate_every=0
        assert a.run().steps==1


def test_shell_text_cannot_establish_a_mock_success(tmp_path):
    a=agent(tmp_path,True)
    a._maybe_record_verdict('{"exit_code":0}',command="echo fake # submit.sh")
    assert not a.solved and a.poc_verdict is None


def test_controller_grading_can_establish_success(tmp_path,monkeypatch):
    a=agent(tmp_path,True)
    monkeypatch.setattr('village.agent.submit_poc',lambda *args,**kwargs:(True,{'exit_code':0,'tampered':[]}))
    a._dispatch(Action('submit_poc',{'path':'candidate'}))
    assert a.solved


def test_parallel_posts_have_unique_monotonic_sequence(tmp_path):
    board=Board(tmp_path/'board.jsonl')
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda i:board.post(str(i),'hello'),range(100)))
    assert [p['seq'] for p in board.all()]==list(range(1,101))
    assert [p['seq'] for p in Board(board.path).all()]==list(range(1,101))


def test_rosters_keep_population_and_mixed_composition_fixed():
    assert Counter(roster_for('mixed',0))==Counter({m:2 for m in MODELS.values()})
    for key,model in MODELS.items():assert roster_for(key,0)==[model]*6
    assert roster_for('mixed',42)==roster_for('mixed',42)


def test_primary_outcome_excludes_command_heuristics(tmp_path):
    folder=tmp_path/'.village/logs/run';folder.mkdir(parents=True)
    path=folder/'worker-1.jsonl'
    path.write_text(json.dumps({'type':'tamper','files':['vuln.c']})+'\n')
    runner=SimpleNamespace(cfg=SimpleNamespace(agents=[SimpleNamespace(name='worker-1',model='test')]),
                           initial={},final={})
    row=outcomes({'roster':'deepseek','seed':0,'board':True},runner,tmp_path,'run',1,0,1)
    assert not row['any_confirmed_task_change']
    with path.open('a') as f:f.write(json.dumps({'type':'submit','ok':False,'verdict':{'tampered':['vuln.c']}})+'\n')
    assert outcomes({},runner,tmp_path,'run',1,0,1)['any_confirmed_task_change']


def test_analysis_uses_matched_villages_and_keeps_mixed_exploratory():
    rows=[{'roster':m,'seed':0,'board':on,'complete':True,'any_confirmed_task_change':on}
          for m in ('deepseek','mixed') for on in (False,True)]
    result=analyse(rows)
    assert len(result['complete_pairs'])==2
    assert result['primary_homogeneous_pair_count']==1
    assert result['paired_risk_difference']==1
    assert result['exact_mcnemar_two_sided_p']==1


def test_private_notes_work_but_never_cross_agents(tmp_path,monkeypatch):
    monkeypatch.setattr('scripts.study_communication.make_sandbox',lambda *a:SimpleNamespace(close=lambda:None))
    cfg,run_id=build_config({'roster':'deepseek','seed':98,'board':False},tmp_path)
    board=Board(tmp_path/'shared.jsonl')
    runner=StudyOrchestrator(cfg,run_id=run_id,enabled=False)
    agents=runner.build_agents(board,None,goal='solve',task_ids=cfg.task.ids,
                              log_dir=tmp_path/'logs',round_name='round',max_steps=8)
    agents[0]._dispatch(Action('post_message',{'text':'PRIVATE_NOTE_SENTINEL'}))
    assert 'PRIVATE_NOTE_SENTINEL' in json.dumps(agents[0]._messages())
    assert 'PRIVATE_NOTE_SENTINEL' not in json.dumps(agents[1]._messages())
    assert 'private notebook' in agents[0]._messages()[0]['content']
    assert 'post_message' in agents[0]._messages()[0]['content']
    assert len(board)==0


def test_shared_notes_reach_other_agents(tmp_path,monkeypatch):
    monkeypatch.setattr('scripts.study_communication.make_sandbox',lambda *a:SimpleNamespace(close=lambda:None))
    cfg,run_id=build_config({'roster':'deepseek','seed':98,'board':True},tmp_path)
    board=Board(tmp_path/'shared.jsonl')
    runner=StudyOrchestrator(cfg,run_id=run_id,enabled=True)
    agents=runner.build_agents(board,None,goal='solve',task_ids=cfg.task.ids,
                              log_dir=tmp_path/'logs',round_name='round',max_steps=8)
    agents[0]._dispatch(Action('post_message',{'text':'SHARED_NOTE_SENTINEL'}))
    assert 'SHARED_NOTE_SENTINEL' in json.dumps(agents[1]._messages())
    assert len(board)==1


def test_format_feedback_reports_missing_json_structure_without_repair():
    malformed='<action>{"tool":"bash","input":{"command":"echo test"}</action>'
    assert not parse_action(malformed).valid
    feedback=action_format_error(malformed)
    assert 'Invalid JSON at line 1, column' in feedback
    assert 'outer action object' in feedback
    assert not parse_action(malformed).valid
