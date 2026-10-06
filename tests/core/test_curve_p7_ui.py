"""Mapped P7 Facade/ACK behavior. Fixture assets are not LMMS/audio evidence."""
import copy
from pathlib import Path
import threading
import time
import tkinter as tk
from unittest.mock import patch

import curve_project as model
import curve_memory
import curve_recommendation_ui as ui
from test_curve_ui import MappedUIFixture
from test_curve_p6_ui import ConnectionController

P7 = 'curve-workflow-v2-r3-p7'


def caps(ready=True, scope='FULL'):
    return dict(score_scope=scope,target_complete=True,can_preview=True,
        can_play_comparison=ready,can_play_final=ready,can_apply=ready,
        can_export_final=False,blocking_reasons=[])


def ref(ident):
    return dict(id=ident,version=1,fingerprint='fixture:'+ident)


class RecommendationController(ConnectionController):
    """Public, main-thread-only fixture; it intentionally does not certify music."""
    def __init__(self, wav):
        super().__init__()
        self.wav = wav
        self.rec_sequence = 0
        self.mode_sequence = 0
        self.audits = {}
        self.root_request = None
        self.mode_tokens = {}
        self.error_at = None
        self.rec = dict(status='IDLE',phase=None,attempt_id=None,candidates=[],error=None,message='',
            search=None,insufficient_reason=None,accepted_ref=None,
            capabilities=dict(can_calculate=True,can_cancel=False,can_auto_complete=True))
        self.accepted = None
        self.effective_protections = []
        self.confirmations = []
        self.assets_called = []
        self.prepared_modes = []
        self.receipts = {}
        self.source_facts = []

    def state(self):
        self.main()
        result = super().state()
        result['capabilities']['recommendation'] = not self.readonly
        return result

    def recommendation_state(self):
        self.main()
        return copy.deepcopy(self.rec)

    def effective_music(self):
        self.main()
        p = self._project
        return dict(project_id=p['project_id'],total_ticks=p['total_ticks'],bpm=p['bpm'],
            notes=[n for place in p['placements'] for n in model.placed_notes(place)],
            emitted_notes=[],segments=[],protections=copy.deepcopy(p['protections']+self.effective_protections),remaining_gaps=[],
            memory_info=curve_memory.memory_info(p),accepted_ref=self.rec['accepted_ref'],
            derived_layers_status='ACTIVE' if self.accepted else 'NONE')

    def history(self):
        self.main()
        return self.history_items()

    def accepted_state(self):
        self.main()
        return dict(status='ACTIVE' if self.accepted else 'NONE',candidate_ref=self.rec['accepted_ref'],
            score_ref=ref('score') if self.accepted else None,result_id='result' if self.accepted else None,
            mode='melody_only' if self.accepted else None,remaining_gaps=[],message='')

    def capture_recommendations(self, selected_gap_id=None, seed=31, parameters=None, mode=None):
        self.main()
        self.rec_sequence += 1
        ident = 'recommendation-'+str(self.rec_sequence)
        fp = model.fingerprint(self._project)
        token = dict(project_id=self._project['project_id'],session_id='fixture-session',request_id=ident,
            snapshot_id='snapshot-'+ident,spec_rev=model.SPEC_REV,contract_rev=P7,
            edit_revision=self._revision,input_fingerprint=fp)
        targets = self.gap_items()
        if selected_gap_id is not None:targets = [g for g in targets if g['id']==selected_gap_id]
        request = dict(schema='emoblocks.recommendation-request.v1',spec_rev=model.SPEC_REV,contract_rev=P7,
            token=copy.deepcopy(token),input_project=copy.deepcopy(self._project),input_contract_rev=self._project['contract_rev'],
            input_fingerprint=fp,scope='selected' if selected_gap_id else 'all' if targets else 'current_complete',
            target_gaps=targets,mode=mode,seed=seed,parameters=parameters or dict(completion_budget={},bridge_parameters={},
                connection_parameters={},boundary_parameters={},max_pipeline_candidates=4,max_recommendations=2),
            algorithm_version='fixture',request_fingerprint='request:'+ident)
        self._requests[ident] = copy.deepcopy(token)
        self.audits[ident] = dict(last_seq=-1,bundles=[],cancel=False,status='RUNNING')
        self.root_request = copy.deepcopy(request)
        self.rec.update(status='RUNNING',phase='BASE_COMPLETION',attempt_id=ident,candidates=[],error=None)
        self.rec['capabilities']['can_cancel'] = True
        self.staging_dirty = True
        self.calls.append(('recommendation-capture',selected_gap_id))
        return dict(token=token,request=request,attempt_id=ident,source_facts=copy.deepcopy(self.source_facts))

    def record_recommendation_progress(self, token, event):
        self.main()
        assert isinstance(event['seq'],int) and not isinstance(event['seq'],bool) and event['seq']>=1
        if self.error_at=='progress':raise ValueError('invalid progress callback')
        audit = self.audits[token['request_id']]
        accepted = event['seq']>audit['last_seq'] and token['session_id']=='fixture-session'
        if accepted:
            audit['last_seq'] = event['seq']
            audit['bundles'].append(copy.deepcopy(event['stage_bundle']))
            if self.rec['attempt_id']==token['request_id'] and self.rec['status']=='RUNNING' and not audit['cancel']:
                self.rec.update(phase=event['phase'],message=event['message'])
        self.calls.append(('progress',copy.deepcopy(event)))
        return dict(accepted=accepted,continue_processing=accepted and not audit['cancel']
            and audit['status']=='RUNNING' and self.rec['attempt_id']==token['request_id'])

    def finish_recommendations(self, token, outcome):
        self.main()
        if self.error_at=='finish':raise ValueError('invalid result callback')
        if self.rec['attempt_id']!=token['request_id'] or self.rec['status']!='RUNNING':return False
        audit = self.audits[token['request_id']]
        if self.error_at=='false_failed':
            self.rec.update(status='FAILED',error=dict(code='GATE',message='实际谱认证失败',details={}))
            audit['status']='FAILED'
            return False
        status = dict(SUCCEEDED='READY',INSUFFICIENT='READY',CANCELLED='CANCELLED',FAILED='FAILED')[outcome['status']]
        self.rec.update(status=status,phase='AUDITION_READY' if status=='READY' else None,
            candidates=copy.deepcopy(outcome['candidates']),error=outcome['error'],
            search=outcome['search'],insufficient_reason=outcome['insufficient_reason'])
        audit['status'] = status
        self._requests.pop(token['request_id'],None)
        return True

    def fail_recommendations(self, token, error, stage_bundle=None):
        self.main()
        self.calls.append(('fail',(copy.deepcopy(token),copy.deepcopy(error),copy.deepcopy(stage_bundle))))
        audit = self.audits[token['request_id']]
        if stage_bundle:audit['bundles'].append(copy.deepcopy(stage_bundle))
        if self.rec['attempt_id']!=token['request_id'] or self.rec['status']!='RUNNING':return False
        audit['status']='FAILED'
        self.rec.update(status='FAILED',error=copy.deepcopy(error))
        self._requests.pop(token['request_id'],None)
        return True

    def cancel_recommendations(self, token):
        self.main()
        self.audits[token['request_id']]['cancel'] = True
        if self.rec['attempt_id']!=token['request_id'] or self.rec['status']!='RUNNING':return False
        self.rec['phase']='CANCEL_REQUESTED'
        return True

    def asset(self, candidate_id, kind, mode):
        return dict(schema='emoblocks.final-asset.v1',spec_rev=model.SPEC_REV,contract_rev=P7,
            id=f'{candidate_id}:{mode}:{kind}',version=1,candidate_ref=ref(candidate_id),
            score_ref=ref(f'{candidate_id}:{mode}:{kind}'),kind=kind,mode=mode,renderer_version='fixture-only',
            files={ext:dict(path=str(self.wav),sha256='fixture-only',bytes=1) for ext in ('wav','mid','mmp')},
            body_ticks=self._project['total_ticks'],body_seconds=4.,audio_seconds=4.5,
            tail_policy='fixture-only',asset_fingerprint='fixture-only')

    def candidate_fixture(self, request, ident='candidate-A', scope='FULL'):
        p = copy.deepcopy(request['input_project'])
        bridge = copy.deepcopy(self.bridge['preview'])
        overlays = copy.deepcopy(bridge['overlays'])
        notes = copy.deepcopy(bridge['notes'])
        connection = dict(id='connect-A',range=dict(start_tick=1920,end_tick=3840),status='CONTENT_READY',
            result_status='READY',notes=copy.deepcopy(notes),reasons=[dict(code='MOTIF',message='候选A实际连接',details={})],error=None)
        preview = dict(project=p,notes=notes,protections=bridge['protections'],bridge_overlays=overlays,
            connection_overlays=[connection],boundary_overlays=[dict(id='bound-A',tick=3840,method='none',
                editable_ranges=[],operation_ids=[],performance_hint_ids=[],reasons=['实际保留'])],
            memory_info=curve_memory.memory_info(p))
        mode = request['mode']
        assets = {k:self.asset(ident,k,mode) for k in ('comparison','final')}
        mode_data = dict(status='AUDITION_READY',final_score_ref=assets['final']['score_ref'],
            comparison_score_ref=assets['comparison']['score_ref'],assets=assets,error=None,capabilities=caps(scope=scope))
        return dict(id=ident,version=1,title='建议 '+ident,scope=scope,remaining_gaps=[] if scope=='FULL' else [dict(start_tick=1,end_tick=2)],
            rank=1,reasons=['保持动机与桥保护'],score_ref=assets['final']['score_ref'],music_fingerprint='music:'+ident,
            assets=assets,capabilities=caps(scope=scope),preview=preview,modes={mode:mode_data})

    def outcome(self, request, status='SUCCEEDED', scope='FULL'):
        candidates = [self.candidate_fixture(request,scope=scope)] if status in ('SUCCEEDED','INSUFFICIENT') else []
        return dict(schema='emoblocks.recommendation-outcome.v1',spec_rev=model.SPEC_REV,contract_rev=P7,
            request_fingerprint=request['request_fingerprint'],status=status,candidates=candidates,facts=[],stage_bundle={},
            search=dict(tested_candidates=2,completed_candidates=len(candidates),duplicate_candidates=1,termination='COMPLETE'),
            insufficient_reason='实际音乐相同，只保留一套' if status=='INSUFFICIENT' else None,
            failures=[],error=None,outcome_fingerprint='fixture-only')

    def recommendation_asset(self, candidate_id, kind='final', mode=None):
        self.main()
        self.assets_called.append((candidate_id,kind,mode))
        candidate = next(c for c in self.rec['candidates'] if c['id']==candidate_id)
        asset = candidate['modes'][mode]['assets'][kind]
        if not self.wav.exists():raise ValueError('ASSET_MISSING')
        return copy.deepcopy(asset)

    def capture_recommendation_mode(self, candidate_id, mode):
        self.main()
        self.mode_sequence += 1
        token = dict(self.root_request['token'],request_id='mode-'+str(self.mode_sequence))
        self.mode_tokens[token['request_id']] = dict(token=copy.deepcopy(token),candidate_id=candidate_id,mode=mode)
        candidate = next(c for c in self.rec['candidates'] if c['id']==candidate_id)
        candidate['modes'][mode] = dict(status='RENDERING',final_score_ref=None,comparison_score_ref=None,
            assets=dict(comparison=None,final=None),error=None,capabilities=caps(False))
        self.prepared_modes.append((candidate_id,mode))
        return dict(token=token,request=copy.deepcopy(self.root_request),candidate_id=candidate_id,mode=mode,
                    source_facts=[])

    def finish_recommendation_mode(self, token, outcome):
        self.main()
        if self.error_at=='mode_finish':raise ValueError('invalid mode callback')
        job = self.mode_tokens.pop(token['request_id'],None)
        if not job:return False
        candidate = next(c for c in self.rec['candidates'] if c['id']==job['candidate_id'])
        candidate['modes'][job['mode']].update(status='AUDITION_READY',assets=copy.deepcopy(outcome['assets']),capabilities=caps())
        return True

    def fail_recommendation_mode(self, token, error):
        self.main()
        job = self.mode_tokens.pop(token['request_id'],None)
        if not job:return False
        candidate = next(c for c in self.rec['candidates'] if c['id']==job['candidate_id'])
        candidate['modes'][job['mode']].update(status='FAILED',error=copy.deepcopy(error))
        return True

    def cancel_recommendation_mode(self, token):
        self.main()
        job = self.mode_tokens.pop(token['request_id'],None)
        if not job:return False
        candidate = next(c for c in self.rec['candidates'] if c['id']==job['candidate_id'])
        candidate['modes'][job['mode']].update(status='MISSING',error=dict(code='CANCELLED',message='该模式已取消',details={}))
        return True

    def confirmation_ref(self, candidate_id, mode=None):
        self.main()
        value = dict(session_id='fixture-session',edit_revision=self._revision,input_fingerprint=model.fingerprint(self._project),
            candidate_ref=ref(candidate_id),mode=mode,final_score_ref=ref('final:'+mode),
            comparison_score_ref=ref('comparison:'+mode),asset_pair_fingerprint='pair:'+mode)
        self.confirmations.append(copy.deepcopy(value))
        return value

    def apply_recommendation(self, candidate_id, transaction_id=None, mode=None, confirmation_ref=None):
        self.main()
        assert confirmation_ref==self.confirmations[-1]
        assert confirmation_ref['mode']==mode
        self.calls.append(('apply-recommendation',(candidate_id,mode,copy.deepcopy(confirmation_ref))))
        receipt = dict(transaction_id='transaction:'+candidate_id,candidate_ref=ref(candidate_id),score_ref=ref('final:'+mode),
            input_snapshot_id=self.root_request['token']['snapshot_id'],pre_revision=self._revision,post_revision=self._revision+1,
            accepted_binding_fingerprint='binding',registered_source_ids=[],registered_material_ids=[],
            accepted_record_id='accepted',result_id='result')
        self._revision += 1
        self.accepted = candidate_id
        self.rec.update(status='APPLIED',accepted_ref=ref(candidate_id))
        return dict(changed=True,receipt=receipt)

    def history_asset(self, ident, mode=None):
        self.main()
        self.assets_called.append((ident,'history',mode))
        return self.asset(ident,'final',mode)

    def export_history(self, ident, format_, destination, mode=None):
        self.main()
        self.calls.append(('export',(ident,format_,destination,mode)))
        return Path(destination)


class RecommendationMappedTests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.controller = RecommendationController(self.wav)
        self.app.controller = self.controller
        self.app.refresh()
        self.rec = self.app.recommendation
        self.threads = []
        self.provider_error = None
        self.progress_phases = []
        self.responses = []
        self.progress_gate = None
        self.after_ack = threading.Event()
        self.mode_gate = None
        self.last_request = None
        self.last_source_facts = None
        for name, function in [('prepare_recommendations',self.prepare),('prepare_candidate_mode',self.prepare_mode)]:
            patcher = patch.object(ui,name,side_effect=function)
            patcher.start();self.addCleanup(patcher.stop)
        self.addCleanup(self.release_workers)

    def release_workers(self):
        if self.progress_gate:self.progress_gate.set()
        if self.mode_gate:self.mode_gate.set()
        self.rec.shutdown()

    def prepare(self, request, source_facts=None, should_cancel=None, on_progress=None):
        self.threads.append(threading.get_ident())
        self.last_request = copy.deepcopy(request)
        if self.progress_gate:self.progress_gate.wait(3)
        self.last_source_facts = copy.deepcopy(source_facts)
        for phase in self.progress_phases:
            reply = on_progress(dict(seq=0,phase=phase,message=phase,candidate_id='candidate-A',stage_bundle=dict(facts=[phase])))
            self.responses.append(reply)
            self.after_ack.set()
            if not reply['continue_processing']:break
        if self.provider_error:raise self.provider_error
        status = 'CANCELLED' if should_cancel() or any(not r['continue_processing'] for r in self.responses) else 'SUCCEEDED'
        # Construct data from request only; no Controller/Tk calls in the worker.
        return copy.deepcopy(self.prepared_outcome or dict(self.default_outcome,status=status,candidates=[] if status=='CANCELLED' else self.default_outcome['candidates']))

    def prepare_mode(self, request, candidate_id, mode, source_facts, should_cancel=None, on_progress=None):
        assert isinstance(source_facts,list)
        self.threads.append(threading.get_ident())
        if self.mode_gate:self.mode_gate.wait(3)
        if self.provider_error:raise self.provider_error
        return copy.deepcopy(self.mode_outcome)

    def start(self, automatic=False):
        self.prepared_outcome = None
        request = dict(input_project=copy.deepcopy(self.controller._project),mode=self.rec.mode_key(),request_fingerprint='fixture')
        self.default_outcome = self.controller.outcome(request)
        return self.rec.start(automatic=automatic)

    def ready(self, scope='FULL'):
        self.start()
        self.finish_jobs()
        if scope=='LOCAL':
            candidate = self.controller.rec['candidates'][0]
            candidate['scope']='LOCAL';candidate['remaining_gaps']=[dict(start_tick=1,end_tick=2)]
        self.app.refresh()

    def select(self):
        self.rec.selector.current(0)
        self.rec.select()

    def music_state(self):
        return copy.deepcopy((self.controller._project,self.controller._undo,self.controller._redo,self.controller._saved,
                              self.app.selected_target,self.app.playing_target,self.app.player.calls))

    def test_runtime_capture_closure_is_isolated_from_caller_and_controller_mutations(self):
        # Transport-only leaf fixture, not a claim of FinalScore/music authentication.
        original = [dict(id='accepted-score',kind='final_score',version=1,fingerprint='fixture-only',
            data=dict(notes=[dict(id='old-note',pitch=60,start_tick=1,duration_tick=240,velocity=80,
                origin=None,lineage=['parent'],slice=None)]),dependencies=[])]
        self.controller.source_facts = copy.deepcopy(original)
        captured_outputs = []
        capture = self.controller.capture_recommendations
        def record_capture(**kwargs):
            value = capture(**kwargs)
            captured_outputs.append(value)
            return value
        self.progress_gate = threading.Event()
        with patch.object(self.controller,'capture_recommendations',side_effect=record_capture):
            self.start()
        # Both returned DTO and subsequently mutable Controller data change before
        # the provider observes its own frozen copy. Neither may leak into the job.
        captured_outputs[0]['source_facts'][0]['data']['notes'][0]['pitch'] = 72
        captured_outputs[0]['source_facts'].append(dict(id='caller-added'))
        self.controller.source_facts[0]['data']['notes'][0]['lineage'].append('later-parent')
        self.controller.source_facts.clear()
        self.progress_gate.set();self.finish_jobs()
        self.assertEqual(self.last_source_facts,original)
        self.assertNotIn('source_facts',self.last_request)
        self.assertTrue(all(ident!=threading.get_ident() for ident in self.threads))

    def test_runtime_p7_input_forwards_captured_closure_and_keeps_music_header(self):
        self.controller.source_facts = [dict(id='old-score-ref',kind='final_score',version=1,
            fingerprint='fixture-only',data=dict(notes=[]),dependencies=[])]
        before=self.music_state()
        capture = self.controller.capture_recommendations
        def p7_capture(**kwargs):
            value = capture(**kwargs)
            # Public DTO fixture only: the local pre-p7 model is not changed or
            # bypassed. Real accepted-project/registry authentication is separate.
            value['request']['input_project']['contract_rev'] = P7
            value['request']['input_contract_rev'] = P7
            return value
        with patch.object(self.controller,'capture_recommendations',side_effect=p7_capture):
            self.start();self.finish_jobs()
        self.assertEqual(self.last_source_facts,self.controller.source_facts)
        self.assertEqual(self.last_request['input_project']['contract_rev'],P7)
        self.assertEqual(self.last_request['input_contract_rev'],P7)
        self.assertEqual(self.last_request['token']['contract_rev'],P7)
        self.assertEqual(before,self.music_state())

    def test_runtime_legacy_three_field_capture_passes_explicit_empty_closure(self):
        capture = self.controller.capture_recommendations
        def legacy_capture(**kwargs):
            value = capture(**kwargs)
            value.pop('source_facts')
            return value
        with patch.object(self.controller,'capture_recommendations',side_effect=legacy_capture):
            self.start();self.finish_jobs()
        self.assertEqual(self.last_source_facts,[])
        self.assertNotIn('source_facts',self.last_request)

    def test_runtime_closure_thread_start_failure_preserves_active_playback_and_music(self):
        self.controller.source_facts = [dict(id='prior-fact',data=dict(notes=[]))]
        self.app.start_playback(dict(wav_path=str(self.wav),body_seconds=4,audio_seconds=4.5),('material','old'),'原素材')
        before=self.music_state();status=self.app.player.status()
        with patch.object(ui.threading.Thread,'start',side_effect=RuntimeError('runtime thread start failed')):
            self.assertFalse(self.start())
        self.assertEqual(before,self.music_state())
        self.assertEqual(self.app.player.status(),status)
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.rec['status'],'FAILED')
        self.assertIn('runtime thread start failed',self.app.status_text.get())
        self.assertIsNone(self.last_source_facts)

    def deliver(self, job, seq, kind, payload, ack=None):
        envelope = dict(token=copy.deepcopy(job['token']),seq=seq,kind=kind,payload=copy.deepcopy(payload))
        self.rec.messages.put((envelope,ack))
        self.rec.drain()

    def test_completion_and_selection_never_steal_player_or_material(self):
        self.app.select_target('material',self.controller._project['materials'][0]['id'])
        self.app.start_playback(dict(wav_path=str(self.wav),body_seconds=4,audio_seconds=4.5),('material','old'),'原素材')
        before = self.music_state()
        self.ready();self.select()
        self.assertEqual(before,self.music_state())
        self.assertFalse(self.app.editable)
        self.assertTrue(all(t!=threading.get_ident() for t in self.threads))
        self.assertIsNone(self.rec.bookmark['selected'])

    def test_selected_all_and_current_complete_capture_exact_gap_identity(self):
        self.start();self.finish_jobs()
        self.assertEqual(self.last_request['scope'],'current_complete')
        self.assertEqual(self.last_request['target_gaps'],[])
        self.controller._project['placements'] = [self.controller._project['placements'][0],self.controller._project['placements'][2]]
        self.app.refresh()
        targets=self.controller.gap_items();self.assertEqual(len(targets),2)
        self.app.completion.select_gap(targets[0]['id'])
        before=self.music_state();self.start();self.finish_jobs()
        self.assertEqual(self.last_request['scope'],'selected')
        self.assertEqual(self.last_request['target_gaps'],[targets[0]])
        self.assertEqual(before,self.music_state())
        self.app.completion.select_gap(None);self.start();self.finish_jobs()
        self.assertEqual(self.last_request['scope'],'all')
        self.assertEqual(self.last_request['target_gaps'],targets)

    def test_same_display_title_never_confuses_candidate_identity(self):
        self.ready()
        first=self.controller.rec['candidates'][0]
        second=copy.deepcopy(first);second['id']='candidate-B';second['title']=first['title']
        self.controller.rec['candidates'].append(second);self.app.refresh()
        self.rec.selector.current(1);self.rec.selector.event_generate('<<ComboboxSelected>>');self.root.update()
        self.assertEqual(self.rec.selected_id,'candidate-B')
        self.app.refresh();self.assertEqual(self.rec.selector.current(),1)
        self.assertFalse(self.app.player.calls)

    def test_real_ack_precedes_next_stage_and_lock_status_does_not_mean_ready(self):
        self.progress_phases = ['BRIDGE_LOCKED','BRIDGE_GENERATION','CONNECTIONS','BOUNDARIES']
        self.start()
        deadline = time.monotonic()+3
        while self.rec.messages.empty() and time.monotonic()<deadline:time.sleep(.002)
        self.assertFalse(self.after_ack.is_set())
        self.assertFalse(self.controller.audits[self.controller.rec['attempt_id']]['bundles'])
        self.rec.drain();self.finish_jobs()
        self.assertTrue(all(r==dict(accepted=True,continue_processing=True) for r in self.responses))
        self.assertEqual([p for p in self.progress_phases],[c[1]['phase'] for c in self.controller.calls if c[0]=='progress'])
        self.assertNotIn('就绪',ui.PHASES['BRIDGE_LOCKED'])

    def test_cancel_keeps_running_token_until_lock_ack_and_terminal(self):
        self.progress_gate = threading.Event();self.progress_phases=['BRIDGE_LOCKED']
        self.start();job=self.rec.active_job();before=self.music_state()
        self.app.cancel_jobs()
        self.assertIs(self.app.jobs[job['token']['request_id']],job)
        self.assertEqual(self.controller.rec['phase'],'CANCEL_REQUESTED')
        self.progress_gate.set();self.finish_jobs()
        audit=self.controller.audits[job['token']['request_id']]
        self.assertEqual(audit['bundles'],[dict(facts=['BRIDGE_LOCKED'])])
        self.assertFalse(self.responses[0]['continue_processing'])
        self.assertEqual(self.controller.rec['status'],'CANCELLED')
        self.assertEqual(before,self.music_state())

    def test_late_lock_audit_does_not_replace_new_attempt(self):
        self.ready();old=next(iter(self.rec.runtimes.values()))
        self.progress_gate=threading.Event();self.start();new=self.rec.active_job()
        before=copy.deepcopy(self.controller.rec)
        ack=dict(event=threading.Event(),response=None)
        self.deliver(old,50,'progress',dict(seq=50,phase='BRIDGE_LOCKED',message='旧锁',candidate_id=None,stage_bundle=dict(facts=['late-lock'])),ack)
        self.assertTrue(ack['event'].is_set())
        self.assertFalse(ack['response']['continue_processing'])
        self.assertEqual(self.controller.rec,before)
        self.assertIs(self.app.jobs[new['token']['request_id']],new)
        self.deliver(old,51,'result',self.default_outcome)
        self.assertEqual(self.controller.rec,before)
        self.progress_gate.set();self.finish_jobs()

    def test_duplicate_and_out_of_order_envelopes_ack_without_failure(self):
        self.progress_gate=threading.Event();self.start();job=self.rec.active_job()
        event=dict(seq=10,phase='BRIDGE_LOCKED',message='真实锁',candidate_id=None,stage_bundle=dict(facts=['lock']))
        self.deliver(job,10,'progress',event)
        for seq in (10,9):
            ack=dict(event=threading.Event(),response=None)
            self.deliver(job,seq,'progress',dict(event,seq=seq),ack)
            self.assertTrue(ack['event'].is_set());self.assertFalse(ack['response']['accepted'])
        self.assertEqual(len(self.controller.audits[job['token']['request_id']]['bundles']),1)
        self.assertEqual(self.controller.rec['status'],'RUNNING')
        self.rec.cancel();self.progress_gate.set()
        self.deliver(job,11,'result',dict(self.default_outcome,status='CANCELLED',candidates=[]))
        self.finish_jobs()

    def test_provider_error_keeps_acknowledged_partial_facts(self):
        self.progress_phases=['BRIDGE_LOCKED','BRIDGE_GENERATION'];self.provider_error=RuntimeError('provider failed')
        self.start();self.finish_jobs()
        failure=next(c[1] for c in self.controller.calls if c[0]=='fail')
        self.assertEqual(failure[2],dict(facts=['BRIDGE_GENERATION']))
        self.assertEqual(self.controller.rec['status'],'FAILED')
        self.assertIn('provider failed',self.app.status_text.get())

    def test_thread_start_failure_leaves_no_busy_or_music_change(self):
        before=self.music_state()
        with patch.object(ui.threading.Thread,'start',side_effect=RuntimeError('thread start failed')):
            self.assertFalse(self.start())
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.rec['status'],'FAILED')
        self.assertEqual(before,self.music_state())

    def test_progress_callback_exception_ack_stops_worker_and_recovers(self):
        self.controller.error_at='progress';self.progress_phases=['BRIDGE_LOCKED']
        self.start();self.finish_jobs()
        self.assertFalse(self.responses[0]['continue_processing'])
        self.assertEqual(self.controller.rec['status'],'FAILED')

    def test_result_callback_exception_recovers_busy(self):
        self.controller.error_at='finish';self.start();self.finish_jobs()
        self.assertEqual(self.controller.rec['status'],'FAILED')
        self.assertIn('invalid result callback',self.app.status_text.get())

    def test_false_terminal_uses_persisted_failure_and_duplicate_not_new_fail(self):
        self.controller.error_at='false_failed';self.start();self.finish_jobs()
        self.assertIn('实际谱认证失败',self.app.status_text.get())
        job=next(iter(self.rec.runtimes.values()))
        self.deliver(job,50,'result',self.default_outcome)
        self.assertFalse([c for c in self.controller.calls if c[0]=='fail'])

    def test_explicit_play_authenticates_both_sides_without_changing_editor_selection(self):
        self.ready();self.select();selected=self.app.selected_target
        self.rec.play('comparison');self.rec.play('final')
        self.assertEqual(self.controller.assets_called,[('candidate-A','comparison','melody_only'),('candidate-A','final','melody_only')])
        self.assertEqual(self.app.playing_target['target'],('recommendation','candidate-A','melody_only','final'))
        self.assertEqual(self.app.selected_target,selected)
        self.assertEqual(len(self.app.player.calls),2)
        self.assertIn('实际音频',self.rec.description())

    def test_seek_reauthenticates_captured_side_and_mode_not_new_ui_preference(self):
        self.ready();self.select();self.rec.play('comparison')
        self.rec.mode.set(ui.MODES['arranged']);self.rec.mode_changed()
        self.app.seek_value.set(1.);self.app.seek_release()
        self.assertEqual(self.controller.assets_called[-1],('candidate-A','comparison','melody_only'))
        self.assertEqual(self.app.player.calls[-1][1],1.)
        self.wav.unlink();before=len(self.app.player.calls)
        with self.assertRaisesRegex(ValueError,'ASSET_MISSING'):self.app.seek_release()
        self.assertEqual(len(self.app.player.calls),before)

    def test_missing_file_fails_before_player_and_retry_is_only_mode(self):
        self.ready();self.select();self.wav.unlink()
        with self.assertRaisesRegex(ValueError,'ASSET_MISSING'):self.rec.play('final')
        self.assertFalse(self.app.player.calls)
        self.rec.mode.set(ui.MODES['arranged']);self.rec.mode_changed()
        before=self.music_state()
        self.mode_outcome=dict(candidate_id='candidate-A',mode='arranged',final_score={},comparison_score={},
            assets={kind:self.controller.asset('candidate-A',kind,'arranged') for kind in ('comparison','final')},error=None)
        self.rec.prepare_mode();self.finish_jobs()
        self.assertEqual(self.controller.rec_sequence,1)
        self.assertEqual(self.controller.prepared_modes,[('candidate-A','arranged')])
        self.assertEqual(before,self.music_state())

    def test_mode_change_does_not_write_music_or_play_and_mode_pair_confirm_ref(self):
        self.ready();self.select();before=self.music_state()
        self.rec.mode.set(ui.MODES['arranged']);self.rec.mode_changed()
        self.assertEqual(before,self.music_state())
        self.assertIn('MISSING',self.rec.description())
        self.assertTrue(self.rec.confirm_button.instate(['disabled']))
        self.mode_outcome=dict(candidate_id='candidate-A',mode='arranged',final_score={},comparison_score={},
            assets={kind:self.controller.asset('candidate-A',kind,'arranged') for kind in ('comparison','final')},error=None)
        self.rec.prepare_mode();self.finish_jobs();self.rec.confirm()
        self.assertEqual(self.controller.confirmations[-1]['mode'],'arranged')
        call=next(c[1] for c in self.controller.calls if c[0]=='apply-recommendation')
        self.assertEqual(call[2],self.controller.confirmations[-1])
        self.assertFalse(self.app.player.calls)

    def test_confirmation_authority_failure_keeps_preview_music_and_player(self):
        self.ready();self.select();before=self.music_state();preview=copy.deepcopy(self.rec.preview)
        with patch.object(self.controller,'confirmation_ref',side_effect=ValueError('ASSET_PAIR_STALE')):
            self.app.safe(self.rec.confirm)
        self.assertEqual(before,self.music_state());self.assertEqual(self.rec.preview,preview)
        self.assertIn('ASSET_PAIR_STALE',self.app.status_text.get())
        self.assertFalse([c for c in self.controller.calls if c[0]=='apply-recommendation'])

    def test_mode_provider_and_callback_failure_preserve_other_mode(self):
        for error_at in (None,'mode_finish'):
            with self.subTest(error_at=error_at):
                self.ready();self.select()
                old=copy.deepcopy(self.controller.rec['candidates'][0]['modes']['melody_only'])
                self.rec.mode.set(ui.MODES['arranged']);self.rec.mode_changed()
                self.provider_error=RuntimeError('mode failed') if error_at is None else None
                self.controller.error_at=error_at
                self.mode_outcome=dict(candidate_id='candidate-A',mode='arranged',assets={},error=None)
                self.rec.prepare_mode();self.finish_jobs()
                self.assertEqual(self.controller.rec['candidates'][0]['modes']['melody_only'],old)
                self.assertEqual(self.controller.rec['candidates'][0]['modes']['arranged']['status'],'FAILED')
                self.assertEqual(self.controller.rec['status'],'READY')
                self.provider_error=None;self.controller.error_at=None;self.rec.mode.set(ui.MODES['melody_only'])

    def test_mode_start_failure_and_cancel_late_result_keep_original_asset(self):
        self.ready();self.select();old=copy.deepcopy(self.controller.rec['candidates'][0]['modes']['melody_only'])
        self.rec.mode.set(ui.MODES['arranged'])
        with patch.object(ui.threading.Thread,'start',side_effect=RuntimeError('cannot start')):
            self.assertFalse(self.rec.prepare_mode())
        self.assertEqual(self.controller.rec['candidates'][0]['modes']['melody_only'],old)
        self.mode_gate=threading.Event()
        self.mode_outcome=dict(candidate_id='candidate-A',mode='arranged',assets={},error=None)
        self.rec.prepare_mode();job=self.rec.active_job();self.rec.cancel()
        self.assertFalse(self.app.jobs)
        self.mode_gate.set()
        deadline=time.monotonic()+2
        while self.rec.messages.empty() and time.monotonic()<deadline:time.sleep(.002)
        self.rec.drain()
        self.assertEqual(self.controller.rec['candidates'][0]['modes']['melody_only'],old)
        self.assertEqual(self.controller.rec['candidates'][0]['modes']['arranged']['status'],'MISSING')

    def test_automatic_uses_same_ref_highest_candidate_without_play_or_selection(self):
        selected=self.app.selected_target;self.start(automatic=True);self.finish_jobs()
        self.assertEqual(self.controller.accepted,'candidate-A')
        self.assertEqual(self.controller.rec['status'],'APPLIED')
        self.assertIsNone(self.rec.selected_id)
        self.assertEqual(selected,self.app.selected_target)
        self.assertFalse(self.app.player.calls)

    def test_cancelled_automatic_never_applies(self):
        self.progress_gate=threading.Event();self.start(automatic=True);self.rec.cancel()
        self.progress_gate.set();self.finish_jobs()
        self.assertIsNone(self.controller.accepted)
        self.assertFalse(self.controller.confirmations)

    def test_automatic_confirmation_save_failure_preserves_ready_candidate_and_reports(self):
        before=self.music_state()
        with patch.object(self.controller,'apply_recommendation',side_effect=OSError('snapshot save failed')):
            self.start(automatic=True);self.finish_jobs()
        self.assertEqual(self.controller.rec['status'],'READY')
        self.assertIn('自动确认失败',self.app.status_text.get())
        self.assertIn('snapshot save failed',self.app.status_text.get())
        self.assertEqual(before,self.music_state())
        self.assertFalse([c for c in self.controller.calls if c[0]=='fail'])

    def test_mode_failure_names_captured_mode_after_preference_changes(self):
        self.ready();self.select();self.rec.mode.set(ui.MODES['arranged'])
        self.mode_gate=threading.Event();self.provider_error=RuntimeError('render failed')
        self.rec.prepare_mode();self.rec.mode.set(ui.MODES['melody_only']);self.rec.mode_changed()
        self.mode_gate.set();self.finish_jobs()
        self.assertIn('情绪编配',self.app.status_text.get())
        self.assertIn('render failed',self.app.status_text.get())
        self.assertEqual(self.rec.mode_key(),'melody_only')

    def test_insufficient_and_interrupted_stale_show_real_state(self):
        self.ready();self.select()
        for status in ('INTERRUPTED','STALE','FAILED'):
            self.controller.rec.update(status=status,insufficient_reason='只有一套不同音乐',
                error=dict(code='TEST',message='真实失败原因',details={}) if status=='FAILED' else None)
            self.app.refresh()
            self.assertIn('只有一套不同音乐',self.rec.description())
            if status=='STALE':self.assertIsNone(self.rec.preview)
        self.assertIn('真实失败原因',self.rec.description())

    def test_preview_readonly_delete_intensity_emotion_import_and_restore_scroll(self):
        self.ready()
        canvas=self.app.page.timeline
        canvas.selected_id=self.controller._project['placements'][1]['id']
        canvas.canvas.xview_moveto(.25);self.root.update()
        selected,scroll=canvas.selected_id,canvas.canvas.xview()[0]
        before=self.music_state();self.select()
        self.assertEqual(self.rec.bookmark['selected'],selected)
        self.assertTrue(canvas.readonly)
        for key in ('<BackSpace>','<Delete>'):
            canvas.canvas.event_generate(key);self.root.update()
        canvas.press(self.event(canvas.canvas,60,150))
        canvas.release(self.event(canvas.canvas,90,140))
        self.app.set_emotion('hope');self.app.import_file('blocked.mid');self.app.drop_files(['blocked.mid'])
        self.assertEqual(before,self.music_state())
        self.rec.exit_preview();self.root.update()
        self.assertEqual(canvas.selected_id,selected)
        self.assertAlmostEqual(canvas.canvas.xview()[0],scroll,places=2)

    def test_own_boundary_bridge_connection_labels_and_scrolled_integer_hits(self):
        self.ready();self.select();canvas=self.app.page.timeline
        self.assertTrue(canvas.canvas.find_withtag('final-boundary'))
        self.assertTrue(canvas.canvas.find_withtag('bridge-range'))
        self.assertTrue(canvas.canvas.find_withtag('connection-range'))
        self.assertTrue(canvas.canvas.find_withtag('final-note'))
        self.controller.bridge['plan']['reasons']=[dict(code='OTHER',message='别的父桥，不可借用',details={})]
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for size in ('1020x700','1280x800','1440x900'):
                self.root.geometry(size);self.root.update()
                canvas.canvas.xview_moveto(.35);self.root.update()
                x=round(canvas.x(3840)-canvas.canvas.canvasx(0))
                canvas.press(self.event(canvas.canvas,x,90))
                self.assertIn('bound-A',self.app.detail_text.get())
                self.assertNotIn('别的父桥',self.app.detail_text.get())
                self.assertGreaterEqual(canvas.canvas.winfo_height(),160)
                for button in (self.rec.calculate_button,self.rec.auto_button,self.rec.cancel_button,
                               self.rec.confirm_button,self.rec.final_button,self.rec.comparison_button):
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreaterEqual(button.winfo_height(),44)
                    self.assertGreaterEqual(button.winfo_rootx(),self.app.page.middle.winfo_rootx())
                    self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.app.page.middle.winfo_rootx()+self.app.page.middle.winfo_width())
                    self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.app.play_button.winfo_rooty())

    def test_one_tick_tail_and_neighbor_preview_no_music_quantization(self):
        self.ready();self.select();canvas=self.app.page.timeline
        preview=self.controller.rec['candidates'][0]['preview']
        preview['bridge_overlays']=[];preview['connection_overlays']=[];preview['boundary_overlays']=[]
        project=preview['project'];p=project['placements'][0]
        p['start_tick']=1;p['length_ticks']=1
        nextp=copy.deepcopy(p);nextp.update(id='neighbor',start_tick=2)
        project['placements']=[p,nextp]
        self.app.refresh();self.root.update()
        for scale in (.085,.42):
            canvas.scale=scale;canvas.draw()
            a,t,b,d=canvas.boxes['neighbor'];integer=round(b)
            canvas.press(self.event(canvas.canvas,integer-canvas.canvas.canvasx(0),round((t+d)/2)+15))
            self.assertEqual(canvas.selected_id,'neighbor')
            self.assertEqual(project['placements'][0]['length_ticks'],1)

    def test_save_during_running_and_running_mode_is_allowed(self):
        self.progress_gate=threading.Event();self.start()
        self.assertIsNotNone(self.app.save_project())
        self.rec.cancel();self.progress_gate.set();self.finish_jobs()
        self.ready();self.select();self.rec.mode.set(ui.MODES['arranged'])
        self.mode_gate=threading.Event();self.mode_outcome=dict(candidate_id='candidate-A',mode='arranged',assets={},error=None)
        self.rec.prepare_mode()
        self.assertIsNotNone(self.app.save_project())
        self.rec.cancel();self.mode_gate.set()

    def test_local_history_never_exports_and_full_export_binds_version_mode(self):
        self.ready(scope='LOCAL');self.select()
        self.assertIn('不可正式整曲导出',self.rec.description())
        history=dict(id='accepted-history',label='接受历史',generated_at='fixture',version=3,scope='LOCAL',
            mode='melody_only',score_ref=ref('history-score'),modes={},availability=dict(wav=True,mid=True,mmp=True),application_status='HISTORICAL')
        self.controller.histories=[history];self.app.selected_history_id=history['id'];self.app.refresh()
        self.assertTrue(all(b.instate(['disabled']) for b in self.app.page.export_buttons.values()))
        with patch('curve_ui.filedialog.asksaveasfilename') as dialog:
            self.app.export_history('mid');dialog.assert_not_called()
        history['scope']='FULL';self.app.refresh();self.rec.mode.set(ui.MODES['arranged'])
        self.app.toggle_history();self.root.update()
        self.assertTrue(self.app.page.history_mode.winfo_ismapped())
        self.app.play_target('history',history['id'])
        self.assertEqual(self.controller.assets_called[-1],(history['id'],'history','arranged'))
        path=str(self.wav.parent/'selected.mid')
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=path):self.app.export_history('mid')
        self.assertEqual(self.controller.calls[-1],('export',(history['id'],'mid',path,'arranged')))
        self.assertIn('v3',self.app.export_receipt.get('1.0','end'))
        self.assertIn(path,self.app.export_receipt.get('1.0','end'))

    def test_native_export_cancel_keeps_selection_music_and_player(self):
        self.controller.histories=[dict(id='h',label='旧历史',paths={'wav':str(self.wav)},availability=dict(wav=True,mid=True,mmp=True),
            body_seconds=4.,audio_seconds=4.5)]
        self.app.selected_history_id='h';self.app.refresh();self.app.play_target('history','h')
        before=self.music_state()
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=''):self.app.export_history('mid')
        self.assertEqual(before,self.music_state())
        self.assertFalse([c for c in self.controller.calls if c[0]=='export'])

    def test_accepted_bridge_hit_and_delete_never_edit_underlying_place(self):
        self.ready();p=self.controller.bridge['protections'][0]
        self.controller.effective_protections=[copy.deepcopy(p)]
        self.controller.accepted='candidate-A';self.app.refresh();self.root.update()
        canvas=self.app.page.timeline
        ident=self.controller._project['placements'][0]['id'];canvas.selected_id=ident
        self.app.selected_target=('placement',ident)
        before=copy.deepcopy(self.controller.calls)
        a,t,b,d=next(iter(canvas.accepted_bridge_boxes.values()))
        x=round((a+b)/2-canvas.canvas.canvasx(0));y=round((t+d)/2)
        canvas.press(self.event(canvas.canvas,x,y));canvas.delete_selected()
        self.app.set_emotion('hope')
        self.assertEqual(before,self.controller.calls)
        self.assertIn('Bridge',self.app.detail_text.get())
        self.assertIsNone(canvas.drag)

    def test_accepted_bridge_frame_does_not_steal_control_point_priority(self):
        self.ready()
        self.controller.effective_protections=[copy.deepcopy(self.controller.bridge['protections'][0])]
        self.controller.accepted='candidate-A';self.app.refresh();self.root.update()
        canvas=self.app.page.timeline
        index,x,y=canvas.point_boxes[0]
        event=self.event(canvas.canvas,round(x-canvas.canvas.canvasx(0)),round(y))
        canvas.press(event)
        self.assertIsNotNone(canvas.intensity_draft)
        self.assertEqual(canvas.intensity_draft['index'],index)
        before=self.music_state();canvas.cancel()
        self.assertEqual(before,self.music_state())
        self.assertIsNone(canvas.drag)

    def test_pure_restored_interrupted_state_does_not_restart_worker_or_play(self):
        self.ready();before=self.music_state()
        self.controller.rec.update(status='INTERRUPTED',phase=None,message='运行中保存，重开已中断')
        with patch.object(ui.threading.Thread,'start',side_effect=AssertionError('pure restore starts no thread')):
            self.app.refresh();self.root.update()
        self.assertFalse(self.app.jobs)
        self.assertIn('中断',self.rec.description())
        self.assertEqual(before,self.music_state())

    def test_stage_switch_restores_bookmark_and_is_mutually_exclusive(self):
        self.ready();canvas=self.app.page.timeline;canvas.canvas.xview_moveto(.2)
        scroll=canvas.canvas.xview()[0];self.select()
        for stage in ('Bridge','连接','补全','完整建议'):
            self.app.show_curve_stage(stage);self.root.update()
            self.assertIsNone(self.rec.preview)
            self.assertAlmostEqual(canvas.canvas.xview()[0],scroll,places=2)
            self.assertEqual(self.rec.visible,stage=='完整建议')
