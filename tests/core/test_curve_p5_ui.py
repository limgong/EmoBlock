"""Mapped P5 UI behavior with the frozen public Facade; no renderer/device."""
import copy
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import curve_bridge_ui as bridge_ui
import curve_memory
import curve_project as model
from test_curve_ui import MappedUIFixture
from test_curve_p4_ui import CompletionController, project_fixture, outcome_fixture, gaps

P5 = 'curve-workflow-v2-r3-p5'


def proposal_fixture(request, none=False):
    windows = [] if none else [dict(id='bridge-'+str(i),start_tick=a,end_tick=b,
        placement_ids=[p['id']],context=dict(left=None,right=None,motif_note_ids=[],key_context={}),
        emotion_segments=[dict(start_tick=a,end_tick=b,emotion=p['emotion'])],blank_mask=[])
        for i,(a,b,p) in enumerate((
            (p['start_tick'],p['start_tick']+p['length_ticks'],p)
            for p in request['base_project']['placements'] if p['id'] in ('left-place','right-place')))]
    return dict(schema='emoblocks.bridge-proposal.v1',spec_rev=model.SPEC_REV,contract_rev=P5,
        request_fingerprint='request-fp',decision='none' if none else 'selected',windows=windows,
        reasons=[dict(code='NATURAL' if none else 'MOTIF',message='已有旋律自然成立' if none else '保持动机关系',details={})],
        assessments=[],joint_boundary_conditions=[],search=dict(tested_windows=2,termination='COMPLETE'))


def result_fixture(request, plan, index=0, status='READY'):
    window = plan['windows'][index]
    region = dict(start_tick=window['start_tick'],end_tick=window['end_tick'])
    material = copy.deepcopy(request['base_project']['placements'][index]['base_snapshot'])
    material.update(id='ready-material-'+str(index),label='真实桥乐句 '+str(index+1),kind='phrase',children=[],phrase_id=None)
    material['generation'] = dict(method='bridge_emotion_once',parameters={},seed=31,rng_version='fixture',
        algorithm_version='fixture-emotion',input_fingerprint=request['base_fingerprint'],
        input_material_ids=[material['id']],base_notes=copy.deepcopy(material['notes']),key_context={},operations=[],melody_changed=False,
        warnings=[dict(code='FULL_PROTECTION',message='共同端点已保护，旋律未改变',details={})],
        accompaniment_hints=dict(status='suggested-not-rendered'))
    processing = dict(pass_count=1,algorithm_version='fixture-emotion',segments=[dict(range=region,emotion=window['emotion_segments'][0]['emotion'],
        seed=31,variant=copy.deepcopy(material))])
    error = None if status=='READY' else dict(code='NO_MUSIC',message='桥生成失败，范围保护保留',details={})
    notes = [dict(n,start_tick=n['start_tick']+region['start_tick']) for n in material['notes']]
    return dict(schema='emoblocks.bridge-result.v1',spec_rev=model.SPEC_REV,contract_rev=P5,
        request_id=request['request_id'],snapshot_id=request['snapshot_id'],request_fingerprint='request-fp',
        base_fingerprint=request['base_fingerprint'],plan_id=plan['id'],plan_version=plan['version'],
        plan_fingerprint=plan['plan_fingerprint'],bridge_id=window['id'],
        protection_id=next(r['protection_id'] for r in plan['protection_refs'] if r['bridge_id']==window['id']),
        origin='automatic',range=region,status=status,base_material=copy.deepcopy(material) if not error else None,
        material=material if not error else None,children=[],emotion_processing=processing if not error else None,
        operations=[],notes=notes if not error else [],content_fingerprint='content-fp-'+str(index) if not error else None,error=error)


class BridgeController(CompletionController):
    """Pure test facts. All Facade access asserts the Tk thread."""
    def __init__(self):
        super().__init__(project_fixture())
        self.bridge = dict(status='IDLE',phase=None,attempt_id=None,request=None,plan=None,protections=[],
            results=[],outcome=None,preview=None,remaining_gaps=[],capabilities={},error=None,message='')
        self.bridge_sequence = 0
        self.lock_error = None
        self.record_error = None
        self.finish_invalid = False
        self.begin_error = None

    def ready_completion(self, status='SUCCEEDED'):
        captured = self.capture_completion()
        self.finish_completion(captured['token'],outcome_fixture(captured['request'],status))

    def state(self):
        self.main()
        result = super().state()
        result['capabilities'].update(bridge=not self.readonly,generate_final=False)
        return result

    def bridge_state(self):
        self.main()
        return copy.deepcopy(self.bridge)

    def accepts(self, token):
        valid = super().accepts(token)
        return valid and (not token['request_id'].startswith('bridge-attempt-') or
            self.bridge['status']=='RUNNING' and self.bridge['attempt_id']==token['request_id'])

    def capture_bridge(self, candidate_id=None, completion_attempt_id=None, seed=31, parameters=None):
        self.main()
        if self.readonly:raise ValueError('READ_ONLY')
        if self.bridge['status']=='RUNNING' or self.completion['status']=='RUNNING':raise ValueError('BUSY')
        if candidate_id is None:
            if gaps(self._project):raise ValueError('先补全或选择基础候选')
            base = copy.deepcopy(self._project);ref=None
        else:
            if self.completion['status']!='READY' or completion_attempt_id!=self.completion['attempt_id']:
                raise ValueError('STALE_CANDIDATE')
            candidate = next(c for c in self.completion['outcome']['candidates'] if c['id']==candidate_id)
            base=copy.deepcopy(candidate['project'])
            ref=dict(attempt_id=completion_attempt_id,candidate_id=candidate_id,request=copy.deepcopy(self.completion['request']),
                     candidate=copy.deepcopy(candidate))
        self.bridge_sequence+=1;ident='bridge-attempt-'+str(self.bridge_sequence)
        fp=model.fingerprint(self._project)
        token=dict(project_id=self._project['project_id'],session_id='fixture-session',request_id=ident,
            snapshot_id='snapshot-'+ident,spec_rev=model.SPEC_REV,contract_rev=P5,
            edit_revision=self._revision,input_fingerprint=fp)
        remaining=gaps(base);cursor=0;resolved=[]
        for gap in remaining+[dict(start_tick=base['total_ticks'],end_tick=base['total_ticks'])]:
            if gap['start_tick']>cursor:resolved.append(dict(start_tick=cursor,end_tick=gap['start_tick']))
            cursor=gap['end_tick']
        request=dict(schema='emoblocks.bridge-request.v1',spec_rev=model.SPEC_REV,contract_rev=P5,
            request_id=ident,snapshot_id=token['snapshot_id'],session_id=token['session_id'],edit_revision=self._revision,
            input_contract_rev=self._project['contract_rev'],input_fingerprint=fp,input_project=copy.deepcopy(self._project),
            input_kind='completed_candidate' if ref else 'current_complete',completion_ref=ref,
            base_project=base,base_fingerprint=model.fingerprint(base),resolved_ranges=resolved,remaining_gaps=remaining,
            base_notes=[n for p in base['placements'] for n in model.placed_notes(p)],
            protection_summary=dict(fingerprint=model.protection_summary(base['protections']),ranges=[]),
            blank_regions=base['blank_regions'],plan_id='plan-'+ident,plan_version=self.bridge_sequence,seed=seed,
            algorithm_version='curve-bridge-v1',parameters=dict(policy='auto',max_windows=2,max_window_blocks=8,max_window_tests=128,max_notes=512))
        self._requests[ident]=copy.deepcopy(token);self.staging_dirty=True
        self.bridge.update(status='RUNNING',phase='BRIDGE_DECISION',attempt_id=ident,request=request,plan=None,
            protections=copy.deepcopy(base['protections']),results=[],outcome=None,preview=None,
            remaining_gaps=remaining,error=None,message='判断桥位置')
        self.calls.append(('bridge-capture',candidate_id,completion_attempt_id))
        return dict(token=copy.deepcopy(token),request=copy.deepcopy(request),attempt_id=ident)

    def lock_bridge(self, token, proposal):
        self.main()
        if self.lock_error:raise self.lock_error
        assert self.accepts(token)
        request=self.bridge['request']
        locks=copy.deepcopy(self.bridge['protections'])
        inherited=[p for p in locks if p['kind']=='bridge']
        refs=[dict(bridge_id=p['owner_id'],protection_id=p['id']) for p in inherited]
        for w in proposal['windows']:
            lock=dict(id='actual-lock-'+w['id'],kind='bridge',origin='automatic',status='RANGE_LOCKED',
                owner_id=w['id'],placement_id=None,component_path=[],start_tick=w['start_tick'],end_tick=w['end_tick'],
                input_fingerprint=request['input_fingerprint'],plan_id=request['plan_id'],plan_version=request['plan_version'],
                notes=[],structure_fingerprint=None,blank_mask=copy.deepcopy(w['blank_mask']))
            locks.append(lock);refs.append(dict(bridge_id=w['id'],protection_id=lock['id']))
        plan=dict(schema='emoblocks.bridge-plan.v1',spec_rev=model.SPEC_REV,contract_rev=P5,
            id=request['plan_id'],version=request['plan_version'],request_id=token['request_id'],snapshot_id=token['snapshot_id'],
            input_fingerprint=request['input_fingerprint'],base_fingerprint=request['base_fingerprint'],
            candidate_id=(request['completion_ref'] or {}).get('candidate_id'),request_fingerprint='request-fp',
            inherited_bridge_ids=[p['owner_id'] for p in inherited],protection_refs=refs,
            range_lock_fingerprint='locked-fp',plan_fingerprint='plan-fp-'+token['request_id'],
            **{k:copy.deepcopy(proposal[k]) for k in ('decision','windows','reasons','assessments','joint_boundary_conditions','search')})
        self.bridge.update(plan=plan,protections=locks,phase='BRIDGE_LOCKED');self.staging_dirty=True
        self.update_preview();self.calls.append(('bridge-lock',token['request_id']))
        return copy.deepcopy(plan)

    def begin_bridge_generation(self, token, plan):
        self.main()
        if self.begin_error:raise self.begin_error
        if not self.accepts(token):return False
        assert plan==self.bridge['plan'] and self.bridge['phase']=='BRIDGE_LOCKED'
        self.calls.append(('bridge-begin',copy.deepcopy(self.bridge['protections'])))
        self.bridge['phase']='BRIDGE_GENERATION';self.staging_dirty=True;return True

    def update_preview(self):
        if self.bridge['plan'] is None:return
        overlays=[]
        for ref in self.bridge['plan']['protection_refs']:
            lock=next(p for p in self.bridge['protections'] if p['id']==ref['protection_id'])
            result=next((r for r in self.bridge['results'] if r['bridge_id']==ref['bridge_id']),None)
            overlays.append(dict(id=ref['bridge_id'],range=dict(start_tick=lock['start_tick'],end_tick=lock['end_tick']),
                protection_id=lock['id'],status=lock['status'],result_status=result['status'] if result else None,
                material=result['material'] if result else None,error=result['error'] if result else None))
        base=copy.deepcopy(self.bridge['request']['base_project'])
        self.bridge['preview']=dict(project=base,overlays=overlays,protections=copy.deepcopy(self.bridge['protections']),
            memory_info=curve_memory.memory_info(base),notes=None)

    def record_bridge_result(self, token, result):
        self.main()
        if not self.accepts(token):return False
        if self.record_error:raise self.record_error
        prior=next((r for r in self.bridge['results'] if r['bridge_id']==result['bridge_id']),None)
        if prior==result:return False
        self.bridge['results'].append(copy.deepcopy(result));self.staging_dirty=True
        if result['status']=='READY':
            lock=next(p for p in self.bridge['protections'] if p['id']==result['protection_id'])
            lock.update(status='CONTENT_READY',notes=copy.deepcopy(result['notes']),structure_fingerprint='structure-fp')
        self.update_preview();self.calls.append(('bridge-record',result['bridge_id']));return True

    def finish_bridge(self, token, raw):
        self.main()
        if not self.accepts(token):return False
        if self.finish_invalid:
            self.fail_bridge(token,dict(code='INVALID_RESULT',message='实际结果验证失败',details={}))
            return False
        self._requests.pop(token['request_id']);self.staging_dirty=True
        self.bridge.update(status='READY' if raw['status']=='SUCCEEDED' else raw['status'],
            phase='BRIDGES_READY' if raw['status']=='SUCCEEDED' else self.bridge['phase'],
            outcome=dict(raw,schema='emoblocks.bridge-outcome.v1',plan_fingerprint=self.bridge['plan']['plan_fingerprint'],notes=[],content_fingerprint='splice-fp',
                base_fingerprint=self.bridge['request']['base_fingerprint'],remaining_gaps=self.bridge['remaining_gaps'],
                protection_summary='ready-summary',capabilities=dict(score_scope='BRIDGE_STAGE',can_plan_connections=raw['status']=='SUCCEEDED',
                    can_audition=False,can_apply=False,can_export_final=False)),error=raw['error'])
        self.calls.append(('bridge-finish',token['request_id']));self.update_preview();return True

    def terminal(self, token, status, error):
        self.main()
        if not self.accepts(token):return False
        plan=self.bridge['plan']
        if plan:
            existing={r['bridge_id'] for r in self.bridge['results']}
            for i,w in enumerate(plan['windows']):
                if w['id'] not in existing:self.bridge['results'].append(result_fixture(self.bridge['request'],plan,i,
                    'CANCELLED' if status=='CANCELLED' else 'FAILED'))
        self._requests.pop(token['request_id']);self.staging_dirty=True
        request=self.bridge['request']
        self.bridge.update(status=status,error=error,message=error['message'],outcome=dict(
            schema='emoblocks.bridge-outcome.v1',spec_rev=model.SPEC_REV,contract_rev=P5,
            request_fingerprint='request-fp',plan_id=request['plan_id'],plan_version=request['plan_version'],
            plan_fingerprint=plan['plan_fingerprint'] if plan else None,status=status,
            results=copy.deepcopy(self.bridge['results']),base_fingerprint=request['base_fingerprint'],
            notes=None,content_fingerprint=None,protection_summary='terminal-summary',remaining_gaps=self.bridge['remaining_gaps'],
            error=error,capabilities=dict(score_scope='BRIDGE_STAGE',can_plan_connections=False,
                can_audition=False,can_apply=False,can_export_final=False)))
        self.update_preview();return True

    def fail_bridge(self, token, error):
        self.calls.append(('bridge-fail',token['request_id']))
        return self.terminal(token,'FAILED',error)

    def cancel_bridge(self, token):
        return self.terminal(token,'CANCELLED',dict(code='CANCELLED',message='用户取消，保护保留',details={}))

    def _stale(self):
        super()._stale()
        if self.bridge['status'] in ('READY','RUNNING'):
            self.bridge['status']='STALE';self.staging_dirty=True


class BridgeWorker:
    def __init__(self):
        self.decision_gate=None;self.generation_gate=None;self.after_result_gate=None
        self.decision_started=threading.Event();self.generation_started=threading.Event();self.result_sent=threading.Event()
        self.requests=[];self.plans=[];self.threads=[];self.cancels=[]
        self.none=False;self.failed_second=False;self.decision_error=None;self.generation_error=None
        self.duplicate_first=False

    def wait(self, gate):
        if gate and not gate.wait(5):raise RuntimeError('test gate timeout')

    def decide(self, request, should_cancel=None, on_progress=None):
        self.requests.append(copy.deepcopy(request));self.threads.append(threading.get_ident());self.cancels.append(should_cancel)
        self.decision_started.set();on_progress(dict(message='分析实际素材'))
        self.wait(self.decision_gate)
        if self.decision_error:raise self.decision_error
        return proposal_fixture(request,self.none)

    def generate(self, request, plan, should_cancel=None, on_progress=None, on_result=None):
        self.plans.append(copy.deepcopy(plan));self.threads.append(threading.get_ident());self.cancels.append(should_cancel)
        self.generation_started.set();on_progress(dict(message='生成实际桥音乐'))
        self.wait(self.generation_gate)
        if self.generation_error:raise self.generation_error
        results=[]
        for i,_ in enumerate(plan['windows']):
            result=result_fixture(request,plan,i,'FAILED' if self.failed_second and i==1 else 'READY')
            results.append(result);on_result(result)
            if i==0 and self.duplicate_first:on_result(copy.deepcopy(result))
            if i==0:self.result_sent.set();self.wait(self.after_result_gate)
        return dict(schema='emoblocks.bridge-raw-outcome.v1',spec_rev=model.SPEC_REV,contract_rev=P5,
            request_fingerprint='request-fp',plan_id=plan['id'],plan_version=plan['version'],
            status='FAILED' if self.failed_second else 'SUCCEEDED',results=results,
            error=dict(code='NO_MUSIC',message='第二桥失败，已就绪内容及保护保留',details={}) if self.failed_second else None)


class BridgeQueueTests(unittest.TestCase):
    """Exercise phase dispatch without creating a Tk window."""
    def setUp(self):
        self.controller=BridgeController();self.controller.ready_completion()
        self.captured=self.controller.capture_bridge('candidate-0',self.controller.completion['attempt_id'])
        self.job=dict(kind='BRIDGE',token=self.captured['token'],request=self.captured['request'],
            cancel=threading.Event(),stage_id='DECISION',event_seq=-1,started=time.monotonic())
        self.app=SimpleNamespace(controller=self.controller,jobs={self.job['token']['request_id']:self.job},
            refresh=lambda:None,tell=lambda *args:None,show_detail=lambda *args:None)
        self.ui=bridge_ui.BridgeUI.__new__(bridge_ui.BridgeUI)
        self.ui.app=self.app;self.ui.messages=queue.Queue();self.phases=[];self.launched=[]
        def report(token):
            self.ui.state=self.controller.bridge_state()
            self.phases.append((self.ui.state['phase'],[p['status'] for p in self.ui.state['protections'] if p['kind']=='bridge']))
        self.ui.report=report
        self.ui.launch=lambda job,plan:self.launched.append((copy.deepcopy(job['token']),copy.deepcopy(plan)))

    def dispatch(self):
        self.ui.messages.put((self.job['token'],'DECISION',0,'DONE',proposal_fixture(self.job['request'])))
        self.ui.drain()

    def test_lock_report_precedes_begin_and_job_token_survives_decision(self):
        self.dispatch()
        self.assertEqual(self.phases,[('BRIDGE_LOCKED',['RANGE_LOCKED','RANGE_LOCKED']),
                                     ('BRIDGE_GENERATION',['RANGE_LOCKED','RANGE_LOCKED'])])
        self.assertTrue(self.controller.accepts(self.captured['token']))
        self.assertEqual(self.launched[0][0],self.captured['token'])
        plan=self.launched[0][1]
        self.assertEqual(self.job['stage_id'],f'GENERATION:{plan["id"]}:{plan["version"]}:{plan["plan_fingerprint"]}')
        self.assertEqual(self.job['event_seq'],-1)

    def test_callback_exception_fail_releases_only_owned_job_preserves_locks(self):
        self.ui.launch=lambda *args:(_ for _ in ()).throw(RuntimeError('spawn failed'))
        other=dict(kind='AUDITION',token=dict(request_id='other'))
        self.app.jobs['other']=other;self.dispatch()
        self.assertEqual(self.app.jobs,{'other':other});self.assertTrue(self.job['cancel'].is_set())
        self.assertEqual(self.controller.bridge_state()['status'],'FAILED')
        self.assertEqual(len([p for p in self.controller.bridge_state()['protections'] if p['kind']=='bridge']),2)

    def test_foreign_stage_and_full_token_mismatch_never_touch_controller(self):
        token=dict(self.job['token'],contract_rev='wrong-contract')
        for t,stage in ((token,'DECISION'),(self.job['token'],'GENERATION:foreign:1:hash')):
            self.ui.messages.put((t,stage,0,'DONE',proposal_fixture(self.job['request'])))
        self.ui.drain()
        self.assertEqual(self.controller.bridge_state()['phase'],'BRIDGE_DECISION')
        self.assertFalse(self.launched);self.assertEqual(self.job['event_seq'],-1)

    def test_stream_false_with_backend_failure_releases_busy_and_keeps_locks(self):
        self.dispatch();plan=self.controller.bridge['plan']
        def reject(token, result):
            self.controller.fail_bridge(token,dict(code='INVALID_RESULT',message='结果认证拒绝',details={}))
            return False
        with patch.object(self.controller,'record_bridge_result',side_effect=reject):
            self.ui.messages.put((self.job['token'],self.job['stage_id'],0,'RESULT',result_fixture(self.job['request'],plan)))
            self.ui.drain()
        self.assertFalse(self.app.jobs);self.assertTrue(self.job['cancel'].is_set())
        self.assertEqual(self.controller.bridge_state()['error']['message'],'结果认证拒绝')
        self.assertTrue(all(p['status']=='RANGE_LOCKED' for p in self.controller.bridge_state()['protections'] if p['kind']=='bridge'))

    def test_begin_false_never_launches_generation_keeps_atomic_lock_transaction(self):
        with patch.object(self.controller,'begin_bridge_generation',return_value=False):self.dispatch()
        self.assertFalse(self.launched);self.assertFalse(self.app.jobs)
        self.assertEqual(self.controller.bridge_state()['status'],'FAILED')
        self.assertEqual(self.controller.bridge_state()['error']['code'],'BRIDGE_START_REJECTED')
        self.assertEqual(len([p for p in self.controller.bridge_state()['protections'] if p['kind']=='bridge']),2)


class CurveP5Tests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.controller=BridgeController();self.controller.ready_completion()
        self.app.controller=self.controller;self.worker=BridgeWorker()
        for name,value in [('decide_bridge',self.worker.decide),('generate_bridges',self.worker.generate)]:
            p=patch.object(bridge_ui,name,side_effect=value);p.start();self.addCleanup(p.stop)
        self.addCleanup(self.release_workers)
        self.app.refresh();self.app.bridge.show();self.root.update()

    def release_workers(self):
        for gate in (self.worker.decision_gate,self.worker.generation_gate,self.worker.after_result_gate):
            if gate:gate.set()
        for job in self.app.jobs.values():
            if job['kind']=='BRIDGE':job['cancel'].set()

    def wait_until(self, predicate):
        deadline=time.monotonic()+3
        while not predicate() and time.monotonic()<deadline:
            self.root.update();self.app.drain_jobs();time.sleep(.005)
        self.assertTrue(predicate())

    def unchanged(self):
        return copy.deepcopy((self.controller.state()['project'],self.controller.state()['is_saved'],
            self.controller.state()['can_undo'],self.controller.state()['can_redo'],self.controller.history_items(),
            self.app.selected_target,self.app.playing_target,self.app.player.calls,self.app.ready_assets))

    def test_two_stage_token_all_locks_before_worker_no_autoplay_no_edit(self):
        self.worker.generation_gate=threading.Event()
        self.app.prepare_target('material','block');self.finish_jobs();self.app.play_target('material','block')
        before=self.unchanged();self.assertTrue(self.app.bridge.start())
        self.wait_until(self.worker.generation_started.is_set)
        job=next(iter(self.app.jobs.values()));token=copy.deepcopy(job['token'])
        self.assertTrue(self.controller.accepts(token));self.assertEqual(token['contract_rev'],P5)
        self.assertEqual(self.controller.bridge['phase'],'BRIDGE_GENERATION')
        self.assertEqual(self.worker.plans[0],self.controller.bridge['plan'])
        locks=[p for p in self.controller.bridge['protections'] if p['kind']=='bridge']
        self.assertEqual(len(locks),2);self.assertTrue(all(p['status']=='RANGE_LOCKED' for p in locks))
        self.assertNotIn('已就绪',self.app.bridge.status_text())
        self.assertTrue(all(t!=threading.get_ident() for t in self.worker.threads))
        self.assertEqual(self.unchanged(),before)
        self.worker.generation_gate.set();self.finish_jobs()
        self.assertEqual(self.controller.bridge['status'],'READY');self.assertEqual(self.unchanged(),before)
        names=[c[0] for c in self.controller.calls]
        self.assertLess(names.index('bridge-lock'),names.index('bridge-begin'))
        self.assertLess(names.index('bridge-record'),names.index('bridge-finish'))

    def test_explicit_candidate_attempt_identity_and_insufficient_single(self):
        self.controller.ready_completion('INSUFFICIENT');self.app.refresh()
        self.app.bridge.selector.current(0);self.app.bridge.start();self.finish_jobs()
        request=self.worker.requests[0]
        self.assertEqual(request['completion_ref']['attempt_id'],self.controller.completion['attempt_id'])
        self.assertEqual(request['completion_ref']['candidate_id'],'candidate-0')
        self.assertEqual(len(self.app.bridge.inputs),1)
        self.assertEqual(request['input_contract_rev'],self.controller.state()['project']['contract_rev'])

    def test_current_complete_none_distinct_from_failure(self):
        p=model.new_project();p=model.edit(p,'mark_blank',start_tick=0,end_tick=p['total_ticks'])
        self.controller._project=p
        self.controller.completion.update(status='IDLE',outcome=None,attempt_id=None)
        self.worker.none=True;self.app.refresh()
        self.app.bridge.start();self.finish_jobs()
        self.assertEqual(self.worker.requests[0]['input_kind'],'current_complete')
        self.assertIsNone(self.worker.requests[0]['completion_ref'])
        self.assertEqual(self.controller.bridge['status'],'READY')
        self.assertIn('不使用新Bridge',self.app.bridge.status_text())
        self.assertNotIn('失败',self.app.bridge.status_text())
        self.assertFalse(self.controller.bridge['outcome']['capabilities']['can_apply'])

    def test_partial_candidate_remaining_gap_does_not_enable_final_actions(self):
        self.controller._project['blank_regions']=[]
        captured=self.controller.capture_completion(selected_gap_id=self.controller.gap_items()[0]['id'])
        self.controller.finish_completion(captured['token'],outcome_fixture(captured['request'],'INSUFFICIENT'))
        self.app.refresh();self.app.bridge.start();self.finish_jobs();self.app.bridge.toggle_preview()
        self.assertEqual(self.controller.bridge['remaining_gaps'][0]['start_tick'],3360)
        self.assertIn('3360–15360 tick',self.app.bridge.description())
        self.assertIn('尚未处理连接块和最终边界',self.app.bridge.description())
        self.assertFalse(self.controller.state()['capabilities']['generate_final'])

    def test_duplicate_stream_result_does_not_duplicate_content_or_commit_music(self):
        self.worker.duplicate_first=True;before=self.unchanged()
        self.app.bridge.start();self.finish_jobs()
        self.assertEqual(len(self.controller.bridge['results']),2)
        self.assertEqual(len([c for c in self.controller.calls if c[0]=='bridge-record']),2)
        self.assertEqual(self.unchanged(),before)

    def test_stream_ready_then_failed_preserves_separate_protection_axes(self):
        self.worker.after_result_gate=threading.Event();self.worker.failed_second=True
        self.app.bridge.start();self.wait_until(lambda:len(self.controller.bridge['results'])==1)
        self.app.bridge.toggle_preview();self.root.update()
        first,second=self.app.bridge.preview['overlays']
        self.assertEqual(first['status'],'CONTENT_READY');self.assertEqual(second['status'],'RANGE_LOCKED')
        self.assertIsNone(second['result_status']);self.assertIsNone(second['material'])
        self.assertEqual(first['protection_id'],'actual-lock-bridge-0')
        self.worker.after_result_gate.set();self.finish_jobs()
        first,second=self.app.bridge.preview['overlays']
        self.assertEqual(first['result_status'],'READY');self.assertEqual(first['status'],'CONTENT_READY')
        self.assertEqual(second['result_status'],'FAILED');self.assertEqual(second['status'],'RANGE_LOCKED')
        self.assertIn('尚未生成就绪音乐',self.app.bridge.describe_overlay(second))
        self.assertIn('编配仅为建议',self.app.bridge.description())
        self.assertIn('共同端点已保护',self.app.bridge.description())
        self.assertIn('失败',self.app.bridge.label.cget('text'))

    def test_preview_mutual_exclusion_bookmark_and_all_edit_guards(self):
        self.app.select_target('placement','left-place')
        canvas=self.app.page.timeline;canvas.mode='trace';canvas.canvas.xview_moveto(.3);self.root.update()
        bookmark=canvas.canvas.xview()[0]
        self.app.bridge.start();self.finish_jobs();before=self.unchanged()
        self.app.bridge.toggle_preview();self.root.update()
        self.assertIsNone(self.app.completion.preview_candidate);self.assertFalse(self.app.editable)
        self.assertTrue(canvas.readonly)
        box=canvas.bridge_boxes['bridge-0']
        event=self.event(canvas.canvas,canvas.canvas.canvasx(0)*-1+(box[0]+box[2])/2,box[1]+4)
        canvas.press(event);canvas.delete_selected()
        canvas.canvas.event_generate('<BackSpace>');canvas.canvas.event_generate('<Delete>');self.root.update()
        self.app.set_emotion('hope');self.app.import_file('does-not-exist.mid')
        self.app.edit('set_intensity',points=[dict(tick=0,level=.8),dict(tick=15360,level=.8)])
        self.assertEqual(self.unchanged(),before);self.assertIsNone(canvas.intensity_draft);self.assertIsNone(canvas.drag)
        self.app.bridge.exit_preview();self.root.update()
        self.assertEqual(canvas.selected_id,'left-place');self.assertEqual(canvas.mode,'trace')
        self.assertAlmostEqual(canvas.canvas.xview()[0],bookmark,delta=.003)
        self.app.completion.selector.current(0);self.app.completion.enter_preview();self.root.update()
        self.assertIsNone(self.app.bridge.preview);self.assertIsNotNone(self.app.completion.preview_candidate)
        self.app.bridge.show();self.app.bridge.toggle_preview();self.root.update()
        self.assertIsNone(self.app.completion.preview_candidate);self.assertIsNotNone(self.app.bridge.preview)
        canvas.cancel(event);self.assertIsNone(self.app.bridge.preview)

    def test_late_decision_progress_wrong_token_and_sequence_cannot_paint(self):
        self.worker.generation_gate=threading.Event();self.app.bridge.start()
        self.wait_until(self.worker.generation_started.is_set)
        job=next(iter(self.app.jobs.values()));token=copy.deepcopy(job['token']);stage=job['stage_id']
        self.app.drain_jobs();before=self.app.status_text.get()
        forged=dict(token,snapshot_id='wrong-snapshot')
        for message in [(token,'DECISION',999,'PROGRESS',dict(message='旧决策')),
                        (forged,stage,999,'PROGRESS',dict(message='错快照')),
                        (token,stage,job['event_seq'],'PROGRESS',dict(message='重复序号'))]:
            self.app.bridge.messages.put(message)
        self.app.drain_jobs();self.assertEqual(self.app.status_text.get(),before)
        self.worker.generation_gate.set();self.finish_jobs()

    def test_cancel_late_results_and_same_content_new_token(self):
        self.worker.decision_gate=threading.Event();self.app.bridge.start()
        self.wait_until(self.worker.decision_started.is_set)
        old=copy.deepcopy(next(iter(self.app.jobs.values()))['token']);before=self.unchanged()
        self.app.bridge.cancel();self.assertFalse(self.app.jobs);self.assertEqual(self.unchanged(),before)
        self.worker.decision_gate.set();self.worker.decision_gate=None
        self.worker.generation_gate=threading.Event();self.app.bridge.start()
        self.wait_until(self.worker.generation_started.is_set)
        new=copy.deepcopy(next(iter(self.app.jobs.values()))['token'])
        self.assertEqual(new['input_fingerprint'],old['input_fingerprint']);self.assertNotEqual(new,old)
        self.app.bridge.messages.put((old,'DECISION',999,'ERROR',dict(code='OLD',message='旧失败',details={})))
        self.app.drain_jobs();self.assertEqual(self.controller.bridge['status'],'RUNNING')
        self.assertNotIn('旧失败',self.app.status_text.get())
        self.app.bridge.cancel();locks=copy.deepcopy(self.controller.bridge['protections'])
        self.worker.generation_gate.set();time.sleep(.02);self.app.drain_jobs()
        self.assertEqual(self.controller.bridge['status'],'CANCELLED');self.assertEqual(self.controller.bridge['protections'],locks)
        self.assertEqual(self.unchanged(),before)

    def test_decision_thread_start_failure_restores_busy_and_persists_error(self):
        before=self.unchanged()
        with patch.object(bridge_ui.threading.Thread,'start',side_effect=RuntimeError('decision spawn failed')):
            self.assertFalse(self.app.bridge.start())
        self.assertFalse(self.app.jobs);self.assertTrue(self.app.editable)
        self.assertEqual(self.controller.bridge['status'],'FAILED');self.assertIsNone(self.controller.bridge['plan'])
        self.assertIn('decision spawn failed',self.app.bridge.description());self.assertEqual(self.unchanged(),before)

    def test_generation_thread_start_failure_retains_all_locks(self):
        # Dispatch decision in the queue so only the second thread's start fails.
        self.worker.decision_gate=threading.Event();self.app.bridge.start()
        job=next(iter(self.app.jobs.values()))
        with patch.object(bridge_ui.threading.Thread,'start',side_effect=RuntimeError('generation spawn failed')):
            self.app.bridge.messages.put((job['token'],'DECISION',99,'DONE',proposal_fixture(job['request'])))
            self.app.drain_jobs()
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.bridge['status'],'FAILED')
        self.assertEqual(len([p for p in self.controller.bridge['protections'] if p['kind']=='bridge']),2)
        self.assertIn('generation spawn failed',self.app.bridge.description())
        self.assertTrue(self.app.editable);self.worker.decision_gate.set()

    def test_decision_error_no_assumed_protection_and_retry(self):
        self.worker.decision_error=ValueError('decision rejected');self.app.bridge.start();self.finish_jobs()
        self.assertIsNone(self.controller.bridge['preview']);self.assertEqual(self.controller.bridge['plan'],None)
        self.assertTrue(self.app.editable);self.assertIn('decision rejected',self.app.bridge.description())
        self.worker.decision_error=None;self.app.bridge.start();self.finish_jobs()
        self.assertEqual(self.controller.bridge['status'],'READY')

    def test_capture_rejection_no_half_job_or_selection_change(self):
        before=self.unchanged()
        with patch.object(self.controller,'capture_bridge',side_effect=ValueError('候选已失效')):
            self.assertFalse(self.app.bridge.start())
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.bridge['status'],'IDLE')
        self.assertIn('候选已失效',self.app.status_text.get());self.assertEqual(self.unchanged(),before)

    def test_lock_callback_exception_atomically_no_generation(self):
        self.controller.lock_error=ValueError('atomic lock rejected')
        self.app.bridge.start();self.finish_jobs()
        self.assertEqual(self.controller.bridge['status'],'FAILED');self.assertFalse(self.worker.generation_started.is_set())
        self.assertFalse(any(p['kind']=='bridge' for p in self.controller.bridge['protections']))

    def test_begin_and_generation_exceptions_keep_published_locks(self):
        self.controller.begin_error=ValueError('begin rejected');self.app.bridge.start();self.finish_jobs()
        self.assertEqual(self.controller.bridge['status'],'FAILED')
        self.assertEqual(len(self.controller.bridge['plan']['windows']),2);self.assertFalse(self.worker.generation_started.is_set())
        self.controller.begin_error=None;self.worker.generation_error=ValueError('composer failed')
        self.app.bridge.start();self.finish_jobs()
        self.assertEqual(self.controller.bridge['status'],'FAILED');self.assertIn('composer failed',self.app.bridge.description())

    def test_result_callback_and_terminal_false_release_busy_read_backend_error(self):
        self.controller.record_error=ValueError('result authentication failed')
        self.app.bridge.start();self.finish_jobs();self.assertTrue(self.app.editable)
        self.assertEqual(self.controller.bridge['status'],'FAILED')
        self.controller.record_error=None;self.controller.finish_invalid=True
        self.app.bridge.start();self.finish_jobs();self.assertEqual(self.controller.bridge['status'],'FAILED')
        self.assertIn('实际结果验证失败',self.app.status_text.get())
        self.assertTrue(all(p['status']=='CONTENT_READY' for p in self.controller.bridge['protections'] if p['kind']=='bridge'))

    def test_cancel_callback_exception_fails_owned_job_and_retains_locks(self):
        self.worker.generation_gate=threading.Event();self.app.bridge.start()
        self.wait_until(self.worker.generation_started.is_set)
        with patch.object(self.controller,'cancel_bridge',side_effect=RuntimeError('cancel callback failed')):
            self.app.bridge.cancel()
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.bridge['status'],'FAILED')
        self.assertIn('cancel callback failed',self.app.bridge.description())
        self.assertEqual(len([p for p in self.controller.bridge['protections'] if p['kind']=='bridge']),2)
        self.worker.generation_gate.set()

    def test_running_save_staging_autosave_and_restore_interrupted_no_workers(self):
        self.worker.generation_gate=threading.Event();self.app.bridge.start()
        self.wait_until(self.worker.generation_started.is_set);before=self.unchanged()
        self.assertTrue(self.controller.state()['staging_dirty']);self.app.save_project()
        self.assertFalse(self.controller.state()['staging_dirty']);self.assertEqual(self.unchanged(),before)
        self.app.bridge.cancel();self.controller.autosave_if_needed()
        self.assertFalse(self.controller.state()['staging_dirty'])
        self.controller.bridge.update(status='INTERRUPTED',error=None,message='恢复中断，不重新启动线程')
        self.app.refresh();self.assertIn('已中断',self.app.bridge.label.cget('text'));self.assertFalse(self.app.jobs)
        self.app.bridge.toggle_preview();self.assertIsNotNone(self.app.bridge.preview)
        self.worker.generation_gate.set()

    def test_stale_preview_exits_preserving_backend_locks(self):
        self.app.bridge.start();self.finish_jobs();self.app.bridge.toggle_preview()
        locks=copy.deepcopy(self.controller.bridge['protections'])
        self.controller.edit('set_intensity',points=[dict(tick=0,level=.4),dict(tick=15360,level=.4)])
        self.app.refresh()
        self.assertIsNone(self.app.bridge.preview);self.assertEqual(self.controller.bridge['status'],'STALE')
        self.assertEqual(self.controller.bridge['protections'],locks);self.assertIn('已失效',self.app.bridge.label.cget('text'))

    def test_mapped_sizes_themes_single_canvas_fixed_player_preview_scroll(self):
        self.worker.failed_second=True;self.app.bridge.start();self.finish_jobs();self.app.bridge.toggle_preview()
        before=self.unchanged();self.app.page.timeline.selected_bridge_id='bridge-1'
        sizes=[]
        for theme in ('light','dark'):
            self.app.theme.set(theme)
            for width,height in ((1020,700),(1280,800),(1440,900)):
                self.root.geometry(f'{width}x{height}');self.app.refresh();self.root.update()
                canvas=self.app.page.timeline
                sizes.append((theme,width,canvas.canvas.winfo_width(),canvas.canvas.winfo_height()))
                self.assertGreaterEqual(canvas.canvas.winfo_height(),160)
                self.assertGreaterEqual(self.app.play_button.winfo_height(),44)
                self.assertGreaterEqual(self.app.bridge.start_button.winfo_height(),44)
                self.assertLess(self.app.play_button.winfo_rooty()+44,self.root.winfo_rooty()+height)
                self.assertFalse(self.app.completion.panel.winfo_manager());self.assertTrue(self.app.bridge.panel.winfo_manager())
                self.assertEqual(canvas.selected_bridge_id,'bridge-1')
                canvas.canvas.xview_moveto(.1);self.root.update()
                a,t,b,d=canvas.bridge_boxes['bridge-1']
                local=(a+b)/2-canvas.canvas.canvasx(0)
                canvas.press(self.event(canvas.canvas,local,t+4))
                self.assertEqual(canvas.selected_bridge_id,'bridge-1')
                self.assertIn('失败',self.app.detail_text.get());self.assertEqual(self.unchanged(),before)
        print('P5 mapped geometry:',sizes)

    def test_exact_subpixel_overlay_tail_scrolled_adjacent_draw_order(self):
        self.app.bridge.start();self.finish_jobs();self.app.bridge.toggle_preview()
        preview=copy.deepcopy(self.controller.bridge['preview']);canvas=self.app.page.timeline
        # The backend may return exact 1 tick ranges. Hit only the visible 1px outline.
        rows=[];total=preview['project']['total_ticks']
        for i,start in enumerate((total-2,total-1)):
            row=copy.deepcopy(preview['overlays'][0]);row.update(id='tiny-'+str(i),range=dict(start_tick=start,end_tick=start+1))
            rows.append(row)
        preview['overlays']=rows;self.controller.bridge['preview']=preview
        for scale in (.085,.04,.5):
            canvas.scale=scale;self.app.refresh();self.root.geometry('1020x700');self.root.update()
            canvas.canvas.xview_moveto(1.);self.root.update()
            a,t,b,d=canvas.bridge_boxes['tiny-1']
            integer_x=round((a+b)/2-canvas.canvas.canvasx(0))
            event=self.event(canvas.canvas,integer_x,t+4)
            canvas.press(event)
            x=canvas.canvas.canvasx(integer_x)
            expected=next(ident for ident,(left,top,right,bottom) in reversed(list(canvas.bridge_boxes.items()))
                if left-.5<=x<=right+.5 and top<=event.y<=bottom)
            self.assertEqual(canvas.selected_bridge_id,expected)
            self.assertGreaterEqual(integer_x,0);self.assertLess(integer_x,canvas.canvas.winfo_width())
            self.assertEqual(preview['overlays'][1]['range'],dict(start_tick=total-1,end_tick=total))

    def test_inherited_owner_mapping_keeps_original_protection_plan_binding(self):
        self.app.bridge.start();self.finish_jobs()
        state=self.controller.bridge;plan=state['plan'];base=state['request']['base_project']
        old=copy.deepcopy(state['protections'][-1]);old.update(id='original-protection-id',owner_id='original-owner-id',
            plan_id='original-plan-id',plan_version=7,status='CONTENT_READY')
        state['protections'].append(old)
        plan['inherited_bridge_ids'].append(old['owner_id'])
        plan['protection_refs'].append(dict(bridge_id=old['owner_id'],protection_id=old['id']))
        result=copy.deepcopy(state['results'][-1]);result.update(bridge_id=old['owner_id'],protection_id=old['id'],origin='inherited')
        state['results'].append(result);self.controller.update_preview()
        self.app.refresh();self.app.bridge.toggle_preview();self.root.update()
        overlay=self.app.bridge.preview['overlays'][-1]
        self.assertEqual(overlay['id'],'original-owner-id');self.assertEqual(overlay['protection_id'],'original-protection-id')
        self.assertIn('继承既有Bridge保护',self.app.bridge.describe_overlay(overlay))
        self.assertEqual(self.app.bridge.preview['protections'][-1]['plan_id'],'original-plan-id')
        self.assertEqual(self.app.bridge.preview['protections'][-1]['plan_version'],7)
        self.assertEqual(result['plan_id'],plan['id'])

    def test_legacy_history_export_and_player_unchanged_no_bridge_entry(self):
        self.controller.histories=[dict(id='legacy',label='旧成品',paths=dict(wav=str(self.wav),mid='old.mid',mmp='old.mmp'),
            availability=dict(wav=True,mid=True,mmp=True),audio_seconds=4.5,body_seconds=4.)]
        self.controller.readonly=True;self.app.refresh();self.root.update()
        before=self.unchanged();self.assertFalse(self.app.bridge.start());self.assertFalse(self.app.bridge.panel.winfo_manager())
        self.assertEqual(self.unchanged(),before)
        self.assertFalse(self.app.state_data['capabilities']['generate_final'])
        self.app.select_target('history','legacy');self.app.play_selected();before=self.unchanged()
        for format_ in ('mid','mmp','wav'):
            destination=str(Path(self.folder.name)/('export.'+format_))
            with patch('curve_ui.filedialog.asksaveasfilename',return_value=destination):self.app.export_history(format_)
            self.assertIn(('export',('legacy',format_,destination)),self.controller.calls)
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=''):self.app.export_history('wav')
        self.assertEqual(self.unchanged(),before)
