"""P6 UI behavior using injected frozen Facade facts; real integration is separate."""
import copy
from pathlib import Path
import queue
import tempfile
import threading
import time
import tkinter as tk  # Exclude mapped tests from scripts/test.py --backend-only.
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import curve_connection_ui as connection_ui
import curve_memory
import curve_project as model
import curve_ui
import curve_bridges
import curve_connections
import curve_workflow
from test_curve_ui import MappedUIFixture
from test_curve_p5_ui import BridgeController, result_fixture
from test_curve_bridge_music import fixture as music_fixture

P6 = 'curve-workflow-v2-r3-p6'


def capabilities(ready=False):
    return dict(score_scope='CONNECTION_STAGE',can_plan_boundaries=ready,can_apply=False,can_audition=False,can_export_final=False)


def empty_state():
    return dict(status='IDLE',phase=None,attempt_id=None,request=None,plan=None,protections=[],results=[],
                outcome=None,preview=None,remaining_gaps=[],capabilities=capabilities(),error=None,message='连接尚未计算。')


def proposal(request, none_reason=None):
    layout=request['actual_layout'];notes=layout['notes'];windows=[]
    if none_reason is None:
        for i,(a,b) in enumerate(((1920,3840),(3840,5760))):
            original=[n for n in notes if a<=n['start_tick']<b]
            left=next((n for n in reversed(notes) if n['start_tick']+n['duration_tick']<=1920),None)
            right=next((n for n in notes if n['start_tick']>=5760),None)
            windows.append(dict(id='connection-'+str(i),start_tick=a,end_tick=b,technique='diatonic_guide',
                context=dict(left=copy.deepcopy(left),right=copy.deepcopy(right),motif_note_ids=[original[0]['id']]),
                original_notes=copy.deepcopy(original),reasons=[dict(code='MOTIF',message='使用实际桥端点和动机',details={})],
                key_context=dict(tonic=0,mode='major',confidence=1.,method='fixture'),parameters=dict(target_ticks=b-a,unit_ticks=10)))
    joints=[] if not windows else [dict(id='joint',left_connection_id=windows[0]['id'],right_connection_id=windows[1]['id'],
        tick=3840,relation='shared-arrival',left_endpoint=dict(pitch=60,start_tick=3720,duration_tick=120),
        right_endpoint=dict(pitch=60,start_tick=3840,duration_tick=120))]
    return dict(schema='emoblocks.connection-proposal.v1',spec_rev=model.SPEC_REV,contract_rev=P6,
        request_fingerprint=model.digest('emoblocks.connection-request.v1',request),decision='none' if none_reason else 'selected',
        none_reason=none_reason,windows=windows,reasons=[dict(code=none_reason or 'MOTIF',message='自然保留' if none_reason=='NOT_NEEDED'
            else '两侧没有合法连接空间' if none_reason else '已有音乐需要动机发展',details={})],assessments=[],
        joint_boundary_conditions=joints,search=dict(tested_windows=2,termination='EXHAUSTED'))


def connection_result(request, plan, index=0, status='READY'):
    w=plan['windows'][index];region=dict(start_tick=w['start_tick'],end_tick=w['end_tick'])
    parent=next(n for n in request['actual_layout']['notes'] if n['id']==w['context']['motif_note_ids'][0])
    ref=curve_connections.parent_ref(request,parent['id'])
    notes=[];operations=[]
    if status=='READY':
        for j,(tick,pitch) in enumerate(((region['start_tick'],64 if index==0 else 60),(region['end_tick']-120,60))):
            note=dict(copy.deepcopy(parent),id=w['id']+':new:'+str(j),pitch=pitch,start_tick=tick,duration_tick=120,
                lineage=list(dict.fromkeys(parent['lineage']+[parent['id']])),slice=None)
            notes.append(note);operations.append(dict(operation='connection-motif-cell',input_note_id=parent['id'],output_note_id=note['id'],
                rule=w['technique'],from_pitch=parent['pitch'],to_pitch=pitch,start_tick=tick,duration_tick=120,parent_ref=copy.deepcopy(ref)))
    generation=None if status!='READY' else curve_connections.generation_data(request,plan,w,operations)
    return dict(**curve_connections.result_header(request,plan,w['id']),
        status=status,notes=notes,operations=operations,generation=generation,
        content_fingerprint=curve_connections.content_fingerprint(region,notes) if notes else None,
        error=None if status=='READY' else dict(code=status,message='连接失败，原桥保护保留' if status=='FAILED' else '连接已取消',details={}))


class ConnectionController(BridgeController):
    """Only public APIs used by UI; this fixture does not certify music gates."""
    def __init__(self):
        super().__init__()
        self._project=music_fixture(4);self._saved=model.fingerprint(self._project)
        self.parents={};self.connection=empty_state();self.connection_sequence=0
        self.plan_error=None;self.begin_error=None;self.record_error=None;self.record_invalid=False
        self.finish_error=None;self.finish_invalid=False
        self.ready_parent('父A实际桥理由')

    def ready_parent(self, message):
        captured=self.capture_bridge();r=captured['request']
        place=r['base_project']['placements'][0]
        p=dict(schema='emoblocks.bridge-proposal.v1',spec_rev=model.SPEC_REV,contract_rev='curve-workflow-v2-r3-p5',
            request_fingerprint='request-fp',decision='selected',windows=[dict(id='bridge-0',start_tick=0,end_tick=1920,
                placement_ids=[place['id']],context=dict(left=None,right=None,motif_note_ids=[],key_context={}),
                emotion_segments=[dict(start_tick=0,end_tick=1920,emotion='calm')],blank_mask=[])],
            reasons=[dict(code='PARENT',message=message,details={})],assessments=[],joint_boundary_conditions=[],
            search=dict(tested_windows=1,termination='EXHAUSTED'))
        plan=self.lock_bridge(captured['token'],p);self.begin_bridge_generation(captured['token'],plan)
        row=result_fixture(r,plan);self.record_bridge_result(captured['token'],row)
        raw=dict(schema='emoblocks.bridge-raw-outcome.v1',spec_rev=model.SPEC_REV,contract_rev='curve-workflow-v2-r3-p5',
            request_fingerprint='request-fp',plan_id=plan['id'],plan_version=plan['version'],status='SUCCEEDED',results=[row],error=None)
        self.finish_bridge(captured['token'],raw)
        actual=[n for p in r['base_project']['placements'][1:] for n in model.placed_notes(p)]+row['notes']
        self.bridge['outcome']['notes']=sorted(actual,key=lambda n:(n['start_tick'],n['pitch'],n['duration_tick'],n['id']))
        self.bridge['capabilities']=copy.deepcopy(self.bridge['outcome']['capabilities'])
        self.bridge['preview']['notes']=copy.deepcopy(self.bridge['outcome']['notes'])
        self.parents[self.bridge['attempt_id']]=copy.deepcopy(self.bridge)
        return self.bridge['attempt_id']

    def state(self):
        result=super().state();result['capabilities']['connection']=not self.readonly;return result

    def connection_state(self):
        self.main();return copy.deepcopy(self.connection)

    def accepts(self, token):
        valid=super().accepts(token)
        return valid and (not token['request_id'].startswith('connection-attempt-') or
            self.connection['status']=='RUNNING' and self.connection['attempt_id']==token['request_id'])

    def capture_connection(self, bridge_attempt_id=None, seed=41, parameters=None):
        self.main()
        if self.readonly:raise ValueError('READ_ONLY')
        if self.connection['status']=='RUNNING':raise ValueError('BUSY')
        parent=self.parents[bridge_attempt_id or self.bridge['attempt_id']]
        if parent['status']!='READY':raise ValueError('BRIDGE_NOT_READY')
        self.connection_sequence+=1;ident='connection-attempt-'+str(self.connection_sequence)
        fp=model.fingerprint(self._project)
        token=dict(project_id=self._project['project_id'],session_id='fixture-session',request_id=ident,snapshot_id='snapshot-'+ident,
            spec_rev=model.SPEC_REV,contract_rev=P6,edit_revision=self._revision,input_fingerprint=fp)
        ref={k:copy.deepcopy(parent[k]) for k in ('attempt_id','request','plan','protections','results','outcome')}
        layout=dict(total_ticks=self._project['total_ticks'],bpm=self._project['bpm'],notes=copy.deepcopy(parent['outcome']['notes']),
            base_project=copy.deepcopy(parent['request']['base_project']),bridge_overlays=copy.deepcopy(parent['preview']['overlays']),
            protections=copy.deepcopy(parent['protections']),blank_regions=copy.deepcopy(parent['request']['blank_regions']),remaining_gaps=[])
        request=dict(schema='emoblocks.connection-request.v1',spec_rev=model.SPEC_REV,contract_rev=P6,
            request_id=ident,snapshot_id=token['snapshot_id'],session_id=token['session_id'],edit_revision=self._revision,
            input_contract_rev=self._project['contract_rev'],input_fingerprint=fp,input_project=copy.deepcopy(self._project),
            bridge_ref=ref,actual_layout=layout,layout_fingerprint=model.digest('emoblocks.connection-layout.v1',layout),
            protection_summary=dict(fingerprint=model.protection_summary(layout['protections']),ranges=[dict(start_tick=0,end_tick=1920)]),
            plan_id='connection-plan-'+str(self.connection_sequence),plan_version=self.connection_sequence,seed=seed,
            algorithm_version='curve-connection-v1',parameters=dict(policy='auto',max_windows=3,max_window_tests=128,
                max_window_ticks=3840,min_window_ticks=240,max_notes=512))
        self._requests[ident]=copy.deepcopy(token);self.staging_dirty=True
        self.connection=dict(empty_state(),status='RUNNING',phase='CONNECTION_PLANNING',attempt_id=ident,request=request,
            protections=copy.deepcopy(layout['protections']),message='分析实际就绪桥')
        self.calls.append(('connection-capture',bridge_attempt_id))
        return dict(status='STARTED',token=copy.deepcopy(token),request=copy.deepcopy(request),attempt_id=ident)

    def plan_connection(self, token, proposed):
        self.main()
        if self.plan_error:raise self.plan_error
        assert self.accepts(token)
        request=self.connection['request'];parent=request['bridge_ref']['plan']
        plan=dict(schema='emoblocks.connection-plan.v1',spec_rev=model.SPEC_REV,contract_rev=P6,id=request['plan_id'],
            version=request['plan_version'],request_id=token['request_id'],snapshot_id=token['snapshot_id'],
            request_fingerprint=proposed['request_fingerprint'],bridge_plan_id=parent['id'],bridge_plan_version=parent['version'],
            bridge_plan_fingerprint=parent['plan_fingerprint'],layout_fingerprint=request['layout_fingerprint'],
            protection_summary_fingerprint=request['protection_summary']['fingerprint'],
            **{k:copy.deepcopy(proposed[k]) for k in ('decision','none_reason','windows','reasons','assessments','joint_boundary_conditions','search')})
        plan['plan_fingerprint']=model.digest('emoblocks.connection-plan.v1',plan)
        self.connection.update(plan=plan,phase='CONNECTION_PLANNED');self.staging_dirty=True;self.update_connection_preview()
        self.calls.append(('connection-plan',token['request_id']));return copy.deepcopy(plan)

    def begin_connection_generation(self, token, plan):
        self.main()
        if self.begin_error:raise self.begin_error
        if not self.accepts(token):return False
        assert plan==self.connection['plan'] and self.connection['phase']=='CONNECTION_PLANNED'
        self.connection['phase']='CONNECTION_GENERATION';self.staging_dirty=True
        self.calls.append(('connection-begin',token['request_id']));return True

    def update_connection_preview(self):
        state=self.connection
        if state['plan'] is None:return
        request=state['request'];parent=request['bridge_ref'];overlays=[]
        for w in state['plan']['windows']:
            row=next((r for r in state['results'] if r['connection_id']==w['id']),None)
            ready=row is not None and row['status']=='READY'
            overlays.append(dict(id=w['id'],range=dict(start_tick=w['start_tick'],end_tick=w['end_tick']),
                status='CONTENT_READY' if ready else 'ALLOCATED',result_status=row['status'] if row else None,
                notes=copy.deepcopy(row['notes']) if ready else [],reasons=copy.deepcopy(w['reasons']),error=row['error'] if row else None))
        state['preview']=dict(project=copy.deepcopy(parent['request']['base_project']),overlays=copy.deepcopy(request['actual_layout']['bridge_overlays']),
            protections=copy.deepcopy(parent['protections']),memory_info=curve_memory.memory_info(parent['request']['base_project']),
            notes=copy.deepcopy(state['outcome']['notes'] if state['status']=='READY' else parent['outcome']['notes']),connection_overlays=overlays)

    def record_connection_result(self, token, result):
        self.main()
        if not self.accepts(token):return False
        if self.record_error:raise self.record_error
        if self.record_invalid:
            self.fail_connection(token,dict(code='INVALID_RESULT',message='连接认证失败',details={}));return False
        prior=next((r for r in self.connection['results'] if r['connection_id']==result['connection_id']),None)
        if prior==result:return False
        if prior:
            self.fail_connection(token,dict(code='DUPLICATE_CONFLICT',message='冲突重复结果',details={}));return False
        self.connection['results'].append(copy.deepcopy(result));self.staging_dirty=True;self.update_connection_preview()
        self.calls.append(('connection-record',result['connection_id']))
        if result['status']!='READY':self.terminate_connection(token,result['status'],result['error'])
        return True

    def outcome(self, status, error=None):
        state=self.connection;r=state['request'];plan=state['plan'];notes=None
        if status=='SUCCEEDED':
            notes=[n for n in r['actual_layout']['notes'] if not any(w['start_tick']<=n['start_tick']<w['end_tick'] for w in plan['windows'])]
            notes+= [n for row in state['results'] for n in row['notes']]
            notes=sorted(notes,key=lambda n:(n['start_tick'],n['pitch'],n['duration_tick'],n['id']))
        return dict(schema='emoblocks.connection-outcome.v1',spec_rev=model.SPEC_REV,contract_rev=P6,
            request_fingerprint=model.digest('emoblocks.connection-request.v1',r),plan_id=r['plan_id'],plan_version=r['plan_version'],
            plan_fingerprint=plan['plan_fingerprint'] if plan else None,status=status,results=copy.deepcopy(state['results']),
            notes=notes,content_fingerprint=model.digest('emoblocks.connection-splice.v1',dict(total_ticks=r['actual_layout']['total_ticks'],notes=notes)) if notes is not None else None,
            layout_fingerprint=r['layout_fingerprint'],protection_summary=r['protection_summary']['fingerprint'],remaining_gaps=[],
            error=error,capabilities=capabilities(status=='SUCCEEDED'))

    def finish_connection(self, token, raw):
        self.main()
        if self.finish_error:raise self.finish_error
        if not self.accepts(token):return False
        if self.finish_invalid:
            self.fail_connection(token,dict(code='INVALID_OUTCOME',message='连接终态验证失败',details={}));return False
        assert raw['results']==self.connection['results']
        self.connection.update(status='READY' if raw['status']=='SUCCEEDED' else raw['status'],error=raw['error'],
            phase='CONNECTIONS_READY' if raw['status']=='SUCCEEDED' else self.connection['phase'])
        self.connection['outcome']=self.outcome(raw['status'],raw['error']);self.connection['capabilities']=self.connection['outcome']['capabilities']
        self._requests.pop(token['request_id']);self.staging_dirty=True;self.update_connection_preview()
        self.calls.append(('connection-finish',token['request_id']));return True

    def terminate_connection(self, token, status, error):
        self.main()
        if not self.accepts(token):return False
        state=self.connection;plan=state['plan']
        if plan:
            existing={r['connection_id'] for r in state['results']}
            state['results'] += [connection_result(state['request'],plan,i,status) for i,w in enumerate(plan['windows']) if w['id'] not in existing]
        state.update(status=status,error=copy.deepcopy(error),message=error['message'],capabilities=capabilities())
        state['outcome']=self.outcome(status,error);self._requests.pop(token['request_id']);self.staging_dirty=True
        self.update_connection_preview();return True

    def fail_connection(self, token, error):
        self.calls.append(('connection-fail',token['request_id']));return self.terminate_connection(token,'FAILED',error)

    def cancel_connection(self, token):
        return self.terminate_connection(token,'CANCELLED',dict(code='CANCELLED',message='用户取消连接，桥保护保留',details={}))

    def _stale(self):
        super()._stale()
        if self.connection['status'] in ('RUNNING','READY'):
            self.connection['status']='STALE';self.connection['capabilities']=capabilities();self.staging_dirty=True


class ConnectionWorker:
    def __init__(self):
        self.planning_gate=None;self.generation_gate=None;self.after_result_gate=None
        self.planning_started=threading.Event();self.generation_started=threading.Event();self.finished=threading.Event()
        self.requests=[];self.plans=[];self.layouts=[];self.threads=[];self.cancels=[]
        self.none_reason=None;self.failed_second=False;self.duplicate_first=False
        self.planning_error=None;self.generation_error=None

    def wait(self, gate):
        if gate and not gate.wait(5):raise RuntimeError('test timing gate timeout')

    def plan(self, request, should_cancel=None, on_progress=None):
        self.requests.append(copy.deepcopy(request));self.threads.append(threading.get_ident());self.cancels.append(should_cancel)
        self.planning_started.set();on_progress('分析真实桥后的端点');self.wait(self.planning_gate)
        if self.planning_error:raise self.planning_error
        return proposal(request,self.none_reason)

    def generate(self, request, plan, actual_layout, should_cancel=None, on_progress=None, on_result=None):
        self.plans.append(copy.deepcopy(plan));self.layouts.append(copy.deepcopy(actual_layout));self.threads.append(threading.get_ident());self.cancels.append(should_cancel)
        self.generation_started.set();on_progress('生成连接乐句');self.wait(self.generation_gate)
        try:
            if self.generation_error:raise self.generation_error
            rows=[]
            for i,_ in enumerate(plan['windows']):
                row=connection_result(request,plan,i,'FAILED' if self.failed_second and i==1 else 'READY')
                rows.append(row);on_result(row)
                if i==0:
                    if self.duplicate_first:on_result(copy.deepcopy(row))
                    self.wait(self.after_result_gate)
            return dict(schema='emoblocks.connection-raw-outcome.v1',spec_rev=model.SPEC_REV,contract_rev=P6,
                request_fingerprint=plan['request_fingerprint'],plan_id=plan['id'],plan_version=plan['version'],
                status='FAILED' if self.failed_second else 'SUCCEEDED',results=rows,
                error=dict(code='COMPOSE_FAILED',message='第二连接失败，成功片段及桥锁保留',details={}) if self.failed_second else None)
        finally:self.finished.set()


class ConnectionQueueTests(unittest.TestCase):
    """Headless main-thread dispatch; no Tk window is constructed."""
    def setUp(self):
        self.controller=ConnectionController()
        captured=self.controller.capture_connection()
        self.job=dict(kind='CONNECTION',token=captured['token'],request=captured['request'],cancel=threading.Event(),
                      stage_id='PLANNING',event_seq=-1,started=time.monotonic())
        self.ui=connection_ui.ConnectionUI.__new__(connection_ui.ConnectionUI)
        self.ui.app=SimpleNamespace(controller=self.controller,jobs={captured['token']['request_id']:self.job})
        self.ui.messages=queue.Queue();self.phases=[];self.launched=[]
        def report(token):
            self.ui.state=self.controller.connection_state();self.phases.append(self.ui.state['phase'])
        self.ui.report=report;self.ui.launch=lambda job,plan:self.launched.append((copy.deepcopy(job['token']),copy.deepcopy(plan)))

    def dispatch(self):
        self.ui.messages.put((self.job['token'],'PLANNING',0,'DONE',proposal(self.job['request'])))
        self.ui.drain()

    def test_plan_published_before_begin_same_token_and_precise_layout(self):
        before=self.controller.state()['project'];self.dispatch()
        self.assertEqual(self.phases,['CONNECTION_PLANNED','CONNECTION_GENERATION'])
        self.assertTrue(self.controller.accepts(self.job['token']))
        plan=self.launched[0][1]
        self.assertEqual(self.job['stage_id'],f'GENERATION:{plan["id"]}:{plan["version"]}:{plan["plan_fingerprint"]}')
        self.assertEqual(self.controller.state()['project'],before)
        self.assertEqual(self.controller.connection['protections'],self.job['request']['bridge_ref']['protections'])

    def test_generation_start_exception_removes_only_own_job_keeps_parent_locks(self):
        self.ui.app.jobs['other']=dict(kind='AUDITION')
        self.ui.launch=lambda *args:(_ for _ in ()).throw(RuntimeError('generation spawn failed'))
        self.dispatch()
        self.assertEqual(set(self.ui.app.jobs),{'other'});self.assertTrue(self.job['cancel'].is_set())
        self.assertEqual(self.controller.connection['status'],'FAILED')
        self.assertEqual(self.controller.connection['protections'],self.job['request']['bridge_ref']['protections'])

    def test_token_stage_and_plan_fingerprint_mismatch_are_ignored(self):
        self.dispatch();stage=self.job['stage_id'];token=self.job['token']
        for t,s in ((dict(token,snapshot_id='wrong'),'PLANNING'),(token,'PLANNING'),(token,stage+'wrong-hash')):
            self.ui.messages.put((t,s,99,'ERROR',dict(code='OLD',message='foreign callback',details={})))
        self.ui.drain();self.assertEqual(self.controller.connection['status'],'RUNNING')
        self.assertEqual(self.job['event_seq'],-1)

    def test_duplicate_false_stays_running_invalid_false_reads_failed(self):
        self.dispatch();plan=self.controller.connection['plan'];row=connection_result(self.job['request'],plan)
        for seq in (0,1):
            self.ui.messages.put((self.job['token'],self.job['stage_id'],seq,'RESULT',row));self.ui.drain()
        self.assertEqual(len(self.controller.connection['results']),1);self.assertEqual(self.controller.connection['status'],'RUNNING')
        self.controller.record_invalid=True
        self.ui.app.refresh=lambda:None
        self.ui.messages.put((self.job['token'],self.job['stage_id'],2,'RESULT',connection_result(self.job['request'],plan,1)))
        self.ui.drain();self.assertFalse(self.ui.app.jobs);self.assertEqual(self.controller.connection['status'],'FAILED')
        self.assertEqual(self.controller.connection['results'][0],row)

    def test_begin_false_fails_and_does_not_start_worker(self):
        with patch.object(self.controller,'begin_connection_generation',return_value=False):self.dispatch()
        self.assertFalse(self.launched);self.assertFalse(self.ui.app.jobs)
        self.assertEqual(self.controller.connection['error']['code'],'CONNECTION_START_REJECTED')

    def test_first_failed_stream_row_terminates_and_keeps_prior_ready(self):
        self.dispatch();plan=self.controller.connection['plan']
        ready=connection_result(self.job['request'],plan)
        failed=connection_result(self.job['request'],plan,1,'FAILED')
        for seq,row in enumerate((ready,failed)):
            self.ui.messages.put((self.job['token'],self.job['stage_id'],seq,'RESULT',row));self.ui.drain()
        self.assertFalse(self.ui.app.jobs);self.assertTrue(self.job['cancel'].is_set())
        self.assertEqual(self.controller.connection['results'],[ready,failed])
        self.assertEqual(self.controller.connection['status'],'FAILED')


class ConnectionFacadeQueueTests(unittest.TestCase):
    """Real Facade/Store dispatch without Tk, renderer or P6 music substitution claims."""
    def setUp(self):
        self.controller=curve_workflow.Controller(music_fixture(4,rough=False))
        parent=self.controller.capture_bridge(parameters=dict(policy='none'))
        r,t=parent['request'],parent['token']
        plan=self.controller.lock_bridge(t,curve_bridges.decide_bridge(r))
        self.assertTrue(self.controller.begin_bridge_generation(t,plan))
        self.assertTrue(self.controller.finish_bridge(t,curve_bridges.generate_bridges(r,plan)))
        self.captured=self.controller.capture_connection(parameters=dict(policy='none'))
        self.token,self.request=self.captured['token'],self.captured['request']
        self.job=dict(kind='CONNECTION',token=self.token,request=self.request,cancel=threading.Event(),
                      stage_id='PLANNING',event_seq=-1,started=time.monotonic())
        self.ui=connection_ui.ConnectionUI.__new__(connection_ui.ConnectionUI)
        self.ui.app=SimpleNamespace(controller=self.controller,jobs={self.token['request_id']:self.job})
        self.ui.messages=queue.Queue();self.launched=[]
        self.ui.report=lambda _:setattr(self.ui,'state',self.controller.connection_state())
        self.ui.launch=lambda job,plan:self.launched.append(copy.deepcopy(plan))

    def dispatch_plan(self):
        # Authenticated explicit-preserve proposal. Actual P6 provider is tested separately.
        value=dict(schema='emoblocks.connection-proposal.v1',spec_rev=model.SPEC_REV,contract_rev=P6,
            request_fingerprint=curve_connections.request_fingerprint(self.request),decision='none',none_reason='NOT_NEEDED',
            windows=[],reasons=[dict(code='EXPLICIT_PRESERVE',message='用户明确保留实际音乐。',details={})],
            assessments=[],joint_boundary_conditions=[],search=dict(tested_windows=0,termination='EXHAUSTED'))
        self.ui.messages.put((self.token,'PLANNING',0,'DONE',value));self.ui.drain()

    def test_real_none_finish_has_no_music_undo_saved_or_history_change(self):
        before=self.controller.state();history=self.controller.history_items();self.dispatch_plan()
        self.assertTrue(self.controller.accepts(self.token));self.assertEqual(len(self.launched),1)
        raw=curve_connections.raw_outcome(self.request,self.launched[0],[])
        self.ui.messages.put((self.token,self.job['stage_id'],0,'DONE',raw));self.ui.drain()
        after=self.controller.state();state=self.controller.connection_state()
        for field in ('project','is_saved','can_undo','can_redo'):self.assertEqual(after[field],before[field])
        self.assertEqual(self.controller.history_items(),history);self.assertTrue(after['staging_dirty'])
        self.assertEqual(state['status'],'READY');self.assertEqual(state['plan']['none_reason'],'NOT_NEEDED')
        self.assertEqual(state['outcome']['notes'],self.request['actual_layout']['notes']);self.assertFalse(self.ui.app.jobs)
        self.assertFalse(state['capabilities']['can_audition']);self.assertFalse(state['capabilities']['can_apply'])

    def test_save_running_pure_restore_interrupted_rejects_original_token(self):
        self.dispatch_plan();before=self.controller.project
        with tempfile.TemporaryDirectory() as folder:
            path=self.controller.save_snapshot(Path(folder)/'connection.json')
            restored=curve_workflow.Controller()
            with patch.object(curve_bridges,'decide_bridge',side_effect=AssertionError('restore planned bridges')), \
                 patch.object(curve_connections,'plan_connection_blocks',side_effect=AssertionError('restore planned connections')), \
                 patch.object(curve_connections,'generate_connection_blocks',side_effect=AssertionError('restore generated connections')), \
                 patch.object(curve_memory,'recompute',side_effect=AssertionError('restore recomputed memory')), \
                 patch.object(threading.Thread,'start',side_effect=AssertionError('restore started thread')):
                restored.load(path)
            state=restored.connection_state()
            self.assertEqual(state['status'],'INTERRUPTED');self.assertEqual(state['phase'],'CONNECTION_GENERATION')
            self.assertEqual(state['request'],self.request);self.assertEqual(restored.project,before)
            self.assertTrue(restored.state()['is_saved']);self.assertTrue(restored.state()['staging_dirty'])
            self.assertFalse(restored.finish_connection(self.token,curve_connections.raw_outcome(self.request,self.launched[0],[])))
            self.assertEqual(restored.connection_state(),state)

    def test_actual_invalid_plan_callback_exits_busy_and_retries_next_version(self):
        bad=proposal(self.request);bad['request_fingerprint']='wrong-input'
        self.ui.messages.put((self.token,'PLANNING',0,'DONE',bad));self.ui.drain()
        state=self.controller.connection_state()
        self.assertEqual(state['status'],'FAILED');self.assertTrue(state['error']['message'])
        self.assertFalse(self.ui.app.jobs);self.assertFalse(self.controller.accepts(self.token))
        self.assertEqual(state['protections'],self.request['bridge_ref']['protections'])
        retry=self.controller.capture_connection(parameters=dict(policy='none'))
        self.assertEqual(retry['request']['plan_version'],self.request['plan_version']+1)
        self.assertFalse(self.controller.fail_connection(self.token,dict(code='LATE',message='迟到错误',details={})))
        self.assertEqual(self.controller.connection_state()['attempt_id'],retry['attempt_id'])

    def test_lazy_provider_uses_actual_public_module_signatures(self):
        cancel=lambda:False;progress=lambda _:None;result=lambda _:None
        with patch.object(curve_connections,'plan_connection_blocks',return_value='plan') as plan:
            self.assertEqual(connection_ui.plan_connection_blocks(self.request,cancel,progress),'plan')
            plan.assert_called_once_with(self.request,should_cancel=cancel,on_progress=progress)
        with patch.object(curve_connections,'generate_connection_blocks',return_value='raw') as generate:
            self.assertEqual(connection_ui.generate_connection_blocks(self.request,{},self.request['actual_layout'],cancel,progress,result),'raw')
            generate.assert_called_once_with(self.request,{},self.request['actual_layout'],should_cancel=cancel,on_progress=progress,on_result=result)


class CurveP6Tests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.controller=ConnectionController();self.app.controller=self.controller;self.worker=ConnectionWorker()
        for name,value in (('plan_connection_blocks',self.worker.plan),('generate_connection_blocks',self.worker.generate)):
            p=patch.object(connection_ui,name,side_effect=value);p.start();self.addCleanup(p.stop)
        self.addCleanup(self.release_workers)
        self.app.refresh();self.app.connection.show();self.root.update()

    def release_workers(self):
        for gate in (self.worker.planning_gate,self.worker.generation_gate,self.worker.after_result_gate):
            if gate:gate.set()
        for job in self.app.jobs.values():
            if job['kind']=='CONNECTION':job['cancel'].set()

    def wait_until(self, predicate):
        deadline=time.monotonic()+4
        while not predicate() and time.monotonic()<deadline:
            self.root.update();self.app.drain_jobs();time.sleep(.005)
        self.assertTrue(predicate())

    def unchanged(self):
        state=self.controller.state()
        return copy.deepcopy((state['project'],state['is_saved'],state['can_undo'],state['can_redo'],self.controller.history_items(),
            self.app.selected_target,self.app.playing_target,self.app.player.calls,self.app.player.status(),self.app.ready_assets))

    def run_connection(self):
        self.assertTrue(self.app.connection.start());self.finish_jobs()
        self.assertEqual(self.controller.connection['status'],'READY')

    def test_two_stages_same_token_no_music_edit_no_autoplay(self):
        self.app.prepare_target('material','material:0');self.finish_jobs();self.app.play_target('material','material:0')
        before=self.unchanged();self.worker.generation_gate=threading.Event();self.app.connection.start()
        self.wait_until(self.worker.generation_started.is_set)
        token=next(iter(self.app.jobs.values()))['token']
        self.assertEqual(token['contract_rev'],P6);self.assertTrue(self.controller.accepts(token))
        self.assertEqual(self.controller.connection['phase'],'CONNECTION_GENERATION')
        self.assertEqual(self.worker.layouts[0],self.worker.requests[0]['actual_layout'])
        self.assertEqual(self.controller.connection['protections'],self.worker.requests[0]['bridge_ref']['protections'])
        self.assertEqual(self.unchanged(),before);self.assertTrue(all(t!=threading.get_ident() for t in self.worker.threads))
        self.worker.generation_gate.set();self.finish_jobs();self.assertEqual(self.unchanged(),before)
        names=[c[0] for c in self.controller.calls]
        self.assertLess(names.index('connection-plan'),names.index('connection-begin'));self.assertLess(names.index('connection-record'),names.index('connection-finish'))

    def test_none_not_needed_and_no_legal_window_are_not_failure(self):
        before=self.unchanged()
        for reason,label in (('NOT_NEEDED','明确保留音乐'),('NO_LEGAL_WINDOW','没有合法连接范围')):
            self.worker.none_reason=reason;self.run_connection()
            self.assertIn(label,self.app.connection.status_text());self.assertNotIn('失败',self.app.connection.status_text())
            self.app.connection.toggle_preview();self.assertEqual(self.app.connection.preview['connection_overlays'],[])
            self.assertEqual(self.unchanged(),before);self.app.connection.exit_preview()
            self.assertFalse(self.controller.connection['capabilities']['can_apply'])
        self.assertIn('不可完整试听',self.app.connection.description())

    def test_partial_ready_then_failure_keeps_parent_locks_and_p5_music(self):
        self.worker.after_result_gate=threading.Event();self.worker.failed_second=True
        self.app.connection.start();self.wait_until(lambda:len(self.controller.connection['results'])==1)
        self.app.connection.toggle_preview();self.root.update()
        first,second=self.app.connection.preview['connection_overlays']
        self.assertEqual(first['status'],'CONTENT_READY');self.assertEqual(second['status'],'ALLOCATED')
        self.assertIsNone(second['result_status']);self.assertEqual(second['notes'],[])
        expected=self.controller.connection['request']['bridge_ref']['outcome']['notes']
        self.assertEqual(self.app.connection.preview['notes'],expected)
        self.worker.after_result_gate.set();self.finish_jobs()
        self.assertEqual(self.controller.connection['status'],'FAILED')
        self.assertEqual([o['result_status'] for o in self.app.connection.preview['connection_overlays']],['READY','FAILED'])
        self.assertEqual(self.app.connection.preview['notes'],expected)
        self.assertIn('尚无就绪音乐',self.app.connection.describe_overlay(self.app.connection.preview['connection_overlays'][1]))
        self.assertIn('不是Bridge保护锁',self.app.connection.description())

    def test_parent_a_preview_does_not_use_current_bridge_b_reasons(self):
        a=self.controller.bridge['attempt_id'];self.controller.ready_parent('父B不同的桥理由');self.app.refresh()
        self.assertTrue(self.app.connection.start(bridge_attempt_id=a));self.finish_jobs();self.app.connection.toggle_preview();self.root.update()
        self.assertEqual(self.app.connection.state['request']['bridge_ref']['attempt_id'],a)
        canvas=self.app.page.timeline;a,t,b,d=canvas.bridge_boxes['bridge-0']
        canvas.press(self.event(canvas.canvas,(a+b)/2-canvas.canvas.canvasx(0),t+4))
        self.assertIn('父A实际桥理由',self.app.detail_text.get());self.assertNotIn('父B不同',self.app.detail_text.get())
        self.assertIn('父A实际桥理由',self.app.connection.description())

    def test_readonly_backspace_delete_points_emotion_import_drop_and_bookmark(self):
        self.app.select_target('placement','place:2');canvas=self.app.page.timeline
        canvas.mode='trace';canvas.canvas.xview_moveto(.2);self.root.update();scroll=canvas.canvas.xview()[0]
        self.run_connection();before=self.unchanged();self.app.connection.toggle_preview();self.root.update()
        a,t,b,d=canvas.connection_boxes['connection-0']
        canvas.press(self.event(canvas.canvas,(a+b)/2-canvas.canvas.canvasx(0),t+4));self.assertEqual(canvas.selected_connection_id,'connection-0')
        # Canvas focus may not have settled after mapping. Consume each
        # synthetic key in this preview, before restoring the editable bookmark.
        canvas.canvas.focus_force();self.root.update()
        self.assertEqual(self.root.focus_get(),canvas.canvas)
        received=[];tag='P6ReadonlyKeys'+str(id(canvas));tags=canvas.canvas.bindtags()
        canvas.canvas.bindtags((tag,)+tags)
        for key in ('<BackSpace>','<Delete>'):
            self.root.bind_class(tag,key,lambda e:received.append((e.keysym,canvas.readonly,self.app.editable)))
        def remove_key_observer():
            canvas.canvas.bindtags(tags)
            for key in ('<BackSpace>','<Delete>'):self.root.unbind_class(tag,key)
        self.addCleanup(remove_key_observer)
        for key in ('<BackSpace>','<Delete>'):
            canvas.canvas.event_generate(key,when='tail');self.root.update()
        self.assertEqual([key for key,_,_ in received],['BackSpace','Delete'])
        self.assertTrue(all(readonly and not editable for _,readonly,editable in received))
        canvas.set_mode('trace');self.app.set_emotion('hope');self.app.import_file('blocked.mid')
        material=self.app.resolve('material','material:0')
        selected=self.app.selected_target
        self.app.begin_material_drag(self.event(self.app.page.cards.canvas,20,20),material,self.app.page.cards.canvas)
        self.assertIsNone(self.app.material_drag);self.assertIsNone(canvas.intensity_draft);self.assertIsNone(canvas.drag)
        self.assertEqual(self.app.selected_target,('material',material['id']))
        self.app.selected_target=selected
        self.assertEqual(self.unchanged(),before)

        self.app.connection.exit_preview();self.root.update()
        self.assertEqual(canvas.selected_id,'place:2');self.assertEqual(canvas.mode,'trace');self.assertAlmostEqual(canvas.canvas.xview()[0],scroll,delta=.003)

    def test_p4_p5_p6_mutually_exclusive_views_and_single_panel(self):
        self.run_connection();self.app.connection.toggle_preview();self.root.update()
        self.app.bridge.show();self.app.bridge.toggle_preview();self.root.update()
        self.assertIsNone(self.app.connection.preview);self.assertIsNotNone(self.app.bridge.preview)
        self.app.connection.show();self.app.connection.toggle_preview();self.root.update()
        self.assertIsNone(self.app.bridge.preview);self.assertIsNone(self.app.completion.preview_candidate)
        self.assertFalse(self.app.bridge.panel.winfo_manager());self.assertFalse(self.app.completion.panel.winfo_manager())
        self.app.show_curve_stage('补全');self.root.update()
        self.assertIsNone(self.app.connection.preview);self.assertFalse(self.app.connection.panel.winfo_manager())

    def test_cancel_and_late_same_content_new_request_cannot_overwrite(self):
        self.worker.generation_gate=threading.Event();self.app.connection.start();self.wait_until(self.worker.generation_started.is_set)
        old=copy.deepcopy(next(iter(self.app.jobs.values()))['token']);before=self.unchanged();locks=copy.deepcopy(self.controller.connection['protections'])
        self.app.connection.cancel();self.assertEqual(self.controller.connection['status'],'CANCELLED');self.assertEqual(self.unchanged(),before)
        self.worker.generation_gate.set();self.wait_until(self.worker.finished.is_set);self.app.drain_jobs()
        self.assertEqual(self.controller.connection['status'],'CANCELLED');self.assertEqual(self.controller.connection['protections'],locks)
        self.worker.generation_gate=None;self.run_connection();final=copy.deepcopy(self.controller.connection)
        self.app.connection.messages.put((old,'PLANNING',999,'ERROR',dict(code='LATE',message='old error',details={})))
        self.app.drain_jobs();self.assertEqual(self.controller.connection,final);self.assertEqual(self.unchanged(),before)

    def test_duplicate_result_false_does_not_fail_and_out_of_order_is_ignored(self):
        self.worker.duplicate_first=True;self.worker.after_result_gate=threading.Event()
        self.app.connection.start();self.wait_until(lambda:len(self.controller.connection['results'])==1)
        job=next(iter(self.app.jobs.values()));self.app.drain_jobs();before=self.app.status_text.get()
        for token,stage,seq in ((job['token'],'PLANNING',999),(dict(job['token'],contract_rev='wrong'),job['stage_id'],999),
                                (job['token'],job['stage_id'],job['event_seq'])):
            self.app.connection.messages.put((token,stage,seq,'PROGRESS','old planning'))
        self.app.drain_jobs();self.assertEqual(self.app.status_text.get(),before)
        self.assertEqual(self.controller.connection['status'],'RUNNING')
        self.worker.after_result_gate.set();self.finish_jobs();self.assertEqual(self.controller.connection['status'],'READY')

    def test_thread_start_fault_before_plan_and_after_plan_recovers_busy(self):
        before=self.unchanged()
        with patch.object(connection_ui.threading.Thread,'start',side_effect=RuntimeError('planning spawn failed')):
            self.assertFalse(self.app.connection.start())
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.connection['status'],'FAILED');self.assertIsNone(self.controller.connection['plan'])
        self.worker.planning_gate=threading.Event();self.app.connection.start();job=next(iter(self.app.jobs.values()))
        with patch.object(connection_ui.threading.Thread,'start',side_effect=RuntimeError('generation spawn failed')):
            self.app.connection.messages.put((job['token'],'PLANNING',99,'DONE',proposal(job['request'])));self.app.drain_jobs()
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.connection['status'],'FAILED');self.assertIsNotNone(self.controller.connection['plan'])
        self.assertIn('generation spawn failed',self.app.connection.description());self.assertEqual(self.unchanged(),before)
        self.worker.planning_gate.set()

    def test_plan_begin_record_finish_and_worker_exceptions_persist_failure(self):
        for field in ('plan_error','begin_error','record_error','finish_error'):
            with self.subTest(field=field):
                setattr(self.controller,field,ValueError(field));self.app.connection.start();self.finish_jobs()
                self.assertEqual(self.controller.connection['status'],'FAILED');self.assertIn(field,self.app.connection.description())
                self.assertTrue(self.app.editable);setattr(self.controller,field,None)
        for field in ('planning_error','generation_error'):
            setattr(self.worker,field,ValueError(field));self.app.connection.start();self.finish_jobs()
            self.assertEqual(self.controller.connection['status'],'FAILED');self.assertIn(field,self.app.connection.description());setattr(self.worker,field,None)

    def test_invalid_false_shows_persistent_backend_error(self):
        for field,message in (('record_invalid','连接认证失败'),('finish_invalid','连接终态验证失败')):
            setattr(self.controller,field,True);self.app.connection.start();self.finish_jobs()
            self.assertEqual(self.controller.connection['status'],'FAILED');self.assertIn(message,self.app.status_text.get())
            self.assertFalse(self.app.jobs);setattr(self.controller,field,False)

    def test_running_save_and_interrupted_facts_stay_dirty_then_explicit_retry(self):
        self.worker.generation_gate=threading.Event();self.app.connection.start();self.wait_until(self.worker.generation_started.is_set)
        before=self.unchanged();self.assertTrue(self.controller.state()['staging_dirty']);self.assertTrue(self.app.save_project())
        self.assertFalse(self.controller.state()['staging_dirty']);self.assertEqual(self.unchanged(),before)
        self.app.connection.cancel();self.controller.connection.update(status='INTERRUPTED',outcome=None,error=None,message='恢复中断，请重试')
        self.controller.staging_dirty=True;self.app.refresh();self.assertIn('中断',self.app.connection.label.cget('text'))
        self.assertFalse(self.app.jobs);self.app.connection.toggle_preview();self.assertIsNotNone(self.app.connection.preview)
        self.worker.generation_gate.set()

    def test_stale_after_edit_and_undo_does_not_revive(self):
        self.run_connection();self.app.connection.toggle_preview();locks=copy.deepcopy(self.controller.connection['protections'])
        self.controller.edit('set_intensity',points=[dict(tick=0,level=.4),dict(tick=7680,level=.4)]);self.app.refresh()
        self.assertIsNone(self.app.connection.preview);self.assertEqual(self.controller.connection['status'],'STALE')
        self.app.undo();self.assertEqual(self.controller.connection['status'],'STALE')
        self.assertEqual(self.controller.connection['protections'],locks);self.assertFalse(self.controller.connection['capabilities']['can_plan_boundaries'])

    def test_historical_velocity_preview_keeps_actual_music_and_original_lock(self):
        a=self.controller.bridge['attempt_id'];parent=self.controller.parents[a]
        parent['protections'][0]['notes'][0]['velocity']=80
        for key in ('results','outcome'):
            values=parent['results'][0]['notes'] if key=='results' else parent['outcome']['notes']
            values[0]['velocity']=100
        parent['preview']['overlays'][0]['material']['notes'][0]['velocity']=80
        self.worker.none_reason='NOT_NEEDED';self.run_connection();self.app.connection.toggle_preview()
        self.assertEqual(self.app.connection.preview['notes'][0]['velocity'],100)
        self.assertEqual(self.app.connection.preview['protections'][0]['notes'][0]['velocity'],80)
        self.assertEqual(self.controller.state()['project'],self.worker.requests[0]['input_project'])

    def test_mapped_three_sizes_dual_theme_exact_hits_scroll_and_fixed_player(self):
        self.worker.failed_second=True;self.app.connection.start();self.finish_jobs();self.app.connection.toggle_preview()
        self.app.advanced=True;self.app.refresh()
        before=self.unchanged();sizes=[];canvas=self.app.page.timeline
        for theme in ('light','dark'):
            self.app.theme.set(theme)
            for width,height in ((1020,700),(1280,800),(1440,900)):
                self.root.geometry(f'{width}x{height}');self.app.refresh();self.root.update()
                sizes.append((theme,width,canvas.canvas.winfo_width(),canvas.canvas.winfo_height()))
                self.assertGreaterEqual(canvas.canvas.winfo_height(),160);self.assertGreaterEqual(self.app.play_button.winfo_height(),44)
                self.assertGreaterEqual(self.app.connection.start_button.winfo_height(),44)
                self.assertTrue(canvas.stage_selector.winfo_ismapped());self.assertFalse(self.app.bridge.panel.winfo_manager())
                self.assertGreaterEqual(canvas.stage_selector.winfo_width(),canvas.stage_selector.winfo_reqwidth())
                self.assertFalse(canvas.tools.winfo_ismapped())
                self.assertTrue(all(b.instate(['disabled']) for b in canvas.mode_buttons.values()))
                for button in (self.app.connection.back_button,self.app.connection.preview_button):
                    self.assertTrue(button.winfo_ismapped());self.assertGreaterEqual(button.winfo_height(),44)
                    self.assertGreaterEqual(button.winfo_width(),44)
                    self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+width)
                canvas.canvas.xview_moveto(.1);self.root.update();a,t,b,d=canvas.connection_boxes['connection-1']
                canvas.press(self.event(canvas.canvas,(a+b)/2-canvas.canvas.canvasx(0),t+4))
                self.assertEqual(canvas.selected_connection_id,'connection-1');self.assertIn('失败',self.app.detail_text.get())
                self.assertTrue(canvas.canvas.find_withtag('bridge-range'));self.assertTrue(canvas.canvas.find_withtag('memory-range'))
                self.assertEqual(self.unchanged(),before)
        print('P6 mapped geometry:',sizes)

    def test_subpixel_head_tail_and_adjacent_outline_hit_draw_order(self):
        self.run_connection();self.app.connection.toggle_preview();canvas=self.app.page.timeline
        view=copy.deepcopy(self.controller.connection['preview']);total=view['project']['total_ticks']
        view['overlays']=[];rows=[]
        for i,start in enumerate((1,2,total-2,total-1)):
            row=copy.deepcopy(view['connection_overlays'][1]);row.update(id='tiny-'+str(i),range=dict(start_tick=start,end_tick=start+1),
                status='ALLOCATED',notes=[],result_status=None)
            rows.append(row)
        view['connection_overlays']=rows;self.controller.connection['preview']=view
        template=self.controller.connection['plan']['windows'][0]
        self.controller.connection['plan']['windows']=[dict(copy.deepcopy(template),id=row['id'],
            start_tick=row['range']['start_tick'],end_tick=row['range']['end_tick'],reasons=copy.deepcopy(row['reasons'])) for row in rows]
        for scale in (.085,.04,.5):
            canvas.scale=scale;self.app.refresh();self.root.geometry('1020x700');self.root.update()
            for scroll,ident in ((0.,'tiny-1'),(1.,'tiny-3')):
                canvas.canvas.xview_moveto(scroll);self.root.update();a,t,b,d=canvas.connection_boxes[ident]
                x=round((a+b)/2-canvas.canvas.canvasx(0));event=self.event(canvas.canvas,x,t+4)
                self.assertGreaterEqual(x,0);self.assertLess(x,canvas.canvas.winfo_width())
                expected=canvas.hit_connection(canvas.canvas.canvasx(x),event.y)
                canvas.press(event);self.assertEqual(canvas.selected_connection_id,expected)
                self.assertIsNotNone(expected)

    def test_legacy_exports_player_and_cancel_keep_state(self):
        self.controller.readonly=True;self.controller.histories=[dict(id='legacy',label='历史成品',paths=dict(wav=str(self.wav),mid='old.mid',mmp='old.mmp'),
            availability=dict(wav=True,mid=True,mmp=True),audio_seconds=4.5,body_seconds=4.)]
        self.app.refresh();self.root.update();self.assertFalse(self.app.connection.start());self.assertFalse(self.app.connection.panel.winfo_manager())
        self.app.select_target('history','legacy');self.app.play_selected();before=self.unchanged()
        for format_ in ('wav','mid','mmp'):
            destination=str(Path(self.folder.name)/('export.'+format_))
            with patch('curve_ui.filedialog.asksaveasfilename',return_value=destination):self.app.export_history(format_)
            self.assertIn(('export',('legacy',format_,destination)),self.controller.calls)
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=''):self.app.export_history('wav')
        self.assertEqual(self.unchanged(),before)


class ConnectionFacadeMappedTests(MappedUIFixture):
    """Mapped real Facade + independently authenticated fault-path notes, not music acceptance."""
    def setUp(self):
        super().setUp()
        from test_curve_connections import ready_bridge, proposal as gate_proposal, result as gate_result
        from test_curve_bridges import complete
        self.controller=ready_bridge(complete(manual=True));self.app.controller=self.controller
        self.gate_result=gate_result;self.last_rows=[];self.fail_second=False
        def plan(request,should_cancel=None,on_progress=None):
            if on_progress:on_progress('真实事务夹具：只替换连接范围内音乐。')
            return gate_proposal(request,((1920,3840),(3840,5760)))
        def generate(request,plan,actual_layout,should_cancel=None,on_progress=None,on_result=None):
            self.assertEqual(actual_layout,request['actual_layout'])
            rows=[]
            for i,win in enumerate(plan['windows']):
                row=(curve_connections.failure_result(request,plan,win['id'],
                        dict(code='FAULT_PATH',message='独立认证第二窗失败，保留桥与第一窗。',details={}))
                     if self.fail_second and i==1 else gate_result(request,plan,i))
                rows.append(row)
                if on_result:on_result(row)
            self.last_rows=copy.deepcopy(rows)
            return curve_connections.raw_outcome(request,plan,rows,'FAILED' if self.fail_second else 'SUCCEEDED',
                rows[-1]['error'] if self.fail_second else None)
        for name,value in (('plan_connection_blocks',plan),('generate_connection_blocks',generate)):
            patcher=patch.object(connection_ui,name,side_effect=value);patcher.start();self.addCleanup(patcher.stop)
        self.app.refresh();self.app.connection.show();self.root.update()

    def test_actual_facade_preview_selection_memory_locks_and_save_isolation(self):
        self.app.select_target('placement','use1');before=self.controller.state();playing=self.app.playing_target
        self.app.connection.start();self.finish_jobs();state=self.controller.connection_state()
        self.assertEqual(state['status'],'READY');self.assertEqual(state['results'],self.last_rows)
        self.app.connection.toggle_preview();self.root.update();canvas=self.app.page.timeline
        self.assertFalse(self.app.editable);self.assertEqual(self.app.private_preview()['memory_info'],state['preview']['memory_info'])
        self.app.page.memory_label.event_generate('<Button-1>',x=4,y=4)
        self.assertIn('候选记忆',self.app.detail_text.get());self.assertIn('已保护',self.app.detail_text.get())
        self.assertTrue(canvas.canvas.find_withtag('memory-range'));self.assertTrue(canvas.canvas.find_withtag('bridge-range'))
        self.assertTrue(canvas.canvas.find_withtag('connection-range'));self.assertTrue(canvas.canvas.find_withtag('connection-note'))
        canvas.delete_selected();self.app.set_emotion('hope')
        after=self.controller.state()
        for field in ('project','is_saved','can_undo','can_redo'):self.assertEqual(after[field],before[field])
        self.assertEqual(self.app.selected_target,('placement','use1'));self.assertEqual(self.app.playing_target,playing)
        self.assertEqual(self.app.player.calls,[])
        with tempfile.TemporaryDirectory() as folder:
            self.controller.save_snapshot(Path(folder)/'actual-facade.json')
            self.assertFalse(self.controller.state()['staging_dirty'])
        self.app.connection.exit_preview();self.root.update();self.assertEqual(canvas.selected_id,'use1')

    def test_actual_failed_stream_preserves_ready_and_parent_before_done(self):
        self.fail_second=True;before=self.controller.project;parent=self.controller.bridge_state()
        self.app.connection.start();self.finish_jobs();state=self.controller.connection_state()
        self.assertEqual(state['status'],'FAILED');self.assertEqual([r['status'] for r in state['results']],['READY','FAILED'])
        self.assertEqual(state['protections'],parent['protections']);self.assertEqual(state['preview']['notes'],parent['outcome']['notes'])
        self.assertEqual(self.controller.project,before);self.assertIn('独立认证第二窗失败',self.app.status_text.get())
        self.app.connection.toggle_preview();self.root.update();canvas=self.app.page.timeline
        a,t,b,d=canvas.connection_boxes['connection-1']
        canvas.press(self.event(canvas.canvas,(a+b)/2-canvas.canvas.canvasx(0),t+4))
        self.assertIn('FAULT_PATH',self.app.detail_text.get());self.assertFalse(self.app.jobs)
