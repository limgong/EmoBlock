"""Mapped P4 UI with a frozen public Facade fixture; no render or devices.

Candidate construction here is explicit test data, not a substitute completion
algorithm or a claim that the pending real provider passed integration.
"""
import copy
import math
from pathlib import Path
import threading
import time
from unittest.mock import patch

import tkinter as tk
import curve_project as model
import curve_memory
import curve_completion_ui as completion_ui
from test_curve_ui import FakeController, MappedUIFixture, fixture


def project_fixture():
    p = fixture(extra=12)
    material = copy.deepcopy(next(m for m in p['materials'] if m['id']=='block'))
    material.update(id='left', length_ticks=1200)
    p['materials'].append(material)
    p = model.edit(p,'place',material_id='left',start_tick=0,placement_id='left-place')
    p = model.edit(p,'place',material_id='block',start_tick=1440,placement_id='right-place')
    p = model.edit(p,'mark_blank',start_tick=3360,end_tick=p['total_ticks'])
    p = model.edit(p,'set_intensity',points=[dict(tick=0,level=.25),dict(tick=1250,level=.9),dict(tick=p['total_ticks'],level=.25)])
    return p


def gaps(p):
    fp = model.fingerprint(p)
    return [dict(r,id=model.digest('emoblocks.gap.v1',dict(input_fingerprint=fp,range=r))) for r in model.gaps(p)]


def outcome_fixture(request, status='SUCCEEDED'):
    candidates = []
    if status in ('SUCCEEDED','INSUFFICIENT'):
        for i in range(2 if status=='SUCCEEDED' else 1):
            p = copy.deepcopy(request['project'])
            added = []; materials = []
            for index,gap in enumerate(request['target_gaps']):
                material = dict(id=f'new-{i}-{index}',label='精确补全',kind='block',
                    length_ticks=gap['end_tick']-gap['start_tick'],
                    notes=[dict(id='new-note',pitch=60+i,start_tick=0,duration_tick=gap['end_tick']-gap['start_tick'],
                                velocity=80,origin=None,lineage=[],slice=None)],
                    provenance={},generation=None,phrase_id=None,children=[])
                p['materials'].append(material);materials.append(material)
                p = model.edit(p,'place',material_id=material['id'],start_tick=gap['start_tick'],placement_id=f'added-{i}-{index}')
                placement=p['placements'][-1];placement['emotion']='hope'
                variant=copy.deepcopy(material)
                variant.update(id='emotion-'+material['id'],generation=dict(melody_changed=False,
                    warnings=[dict(code='FULL_PROTECTION',message='全保护，旋律未改变',details={})],
                    accompaniment_hints=dict(status='suggested-not-rendered')))
                placement['emotion_variant']=variant
                added.append(placement['id'])
            # Backend service fixtures: the candidate's memory differs from the editor's pending gap.
            memory=curve_memory.expected_protection(p)
            p['protections']=[memory] if memory else []
            info=curve_memory.memory_info(p)
            remaining=gaps(p)
            notes=[n for placement in p['placements'] for n in model.placed_notes(placement)]
            fp=model.fingerprint(p)
            p['contract_rev']='curve-workflow-v2-r3-p4'
            candidates.append(dict(schema='emoblocks.completed-candidate.v1',spec_rev=model.SPEC_REV,
                contract_rev='curve-workflow-v2-r3-p4',id='candidate-'+str(i),snapshot_id=request['snapshot_id'],
                input_fingerprint=request['input_fingerprint'],request_fingerprint='request-fp',project=p,
                added_placement_ids=added,staged_materials=materials,notes=notes,
                target_resolution=[dict(gap_id=g['id'],start_tick=g['start_tick'],end_tick=g['end_tick'],complete=True,
                                        note_ids=[n['id'] for n in notes if n['id'].startswith('added-')]) for g in request['target_gaps']],
                remaining_gaps=remaining,base_write_ranges=[{k:g[k] for k in ('start_tick','end_tick')} for g in request['target_gaps']],
                emotion_arrangement=[dict(placement_id=ident,emotion='hope') for ident in added],memory_info=info,
                protection_summary=model.protection_summary(p['protections']),score=dict(total=.7),
                reasons=[dict(code='CONTEXT',message='基础旋律关系说明',details={})],provenance={},
                content_fingerprint=fp,music_fingerprint='music-'+str(i),
                capabilities=dict(score_scope='BASE_COMPLETION',target_complete=True,can_audition=False,can_apply=False,can_export_final=False)))
    return dict(schema='emoblocks.completion-outcome.v1',spec_rev=model.SPEC_REV,contract_rev='curve-workflow-v2-r3-p4',
        snapshot_id=request['snapshot_id'],input_fingerprint=request['input_fingerprint'],request_fingerprint='request-fp',
        status=status,candidates=candidates,differences=[],
        shortage_reasons=[dict(code='FINITE_POOL',message='有限备选池只得到一套',details={})] if status=='INSUFFICIENT' else [],
        unresolved_targets=[] if candidates else request['target_gaps'],
        search=dict(expansions=4,generated_notes=2,termination='EXHAUSTED',raw_termination='RAW_POOL_EXHAUSTED',rejections=[]),
        error=None)


class CompletionController(FakeController):
    def __init__(self, project):
        super().__init__(project)
        self.staging_dirty=False;self.sequence=0;self.attempts=[]
        self.completion=dict(status='IDLE',attempt_id=None,input_fingerprint=None,request=None,outcome=None,message='',error=None)
        self.finish_error=None;self.finish_false=False;self.fail_false=False

    def main(self):
        assert threading.get_ident()==self.main_thread

    def state(self):
        result=super().state()
        result['staging_dirty']=self.staging_dirty
        result['capabilities'].update(completion=not self.readonly,intensity_edit=not self.readonly,
                                      emotion=not self.readonly,memory=not self.readonly)
        result['memory_info']=None if self.readonly else curve_memory.memory_info(self._project)
        return result

    def gap_items(self):
        self.main();return [] if self.readonly else gaps(self._project)

    def completion_state(self):
        self.main();return copy.deepcopy(self.completion)

    def capture_completion(self, selected_gap_id=None, seed=31, budget=None):
        self.main()
        if self.readonly:raise ValueError('READ_ONLY')
        if self.completion['status']=='RUNNING':raise ValueError('DUPLICATE_REQUEST')
        targets=self.gap_items()
        if selected_gap_id is not None:
            targets=[g for g in targets if g['id']==selected_gap_id]
            if not targets:raise ValueError('STALE_GAP')
        self.sequence+=1;ident='completion-'+str(self.sequence);fp=model.fingerprint(self._project)
        request=dict(schema='emoblocks.completion-request.v1',spec_rev=model.SPEC_REV,contract_rev='curve-workflow-v2-r3-p4',
            input_contract_rev=self._project['contract_rev'],request_id=ident,snapshot_id='snapshot-'+ident,
            input_fingerprint=fp,project=copy.deepcopy(self._project),scope='selected' if selected_gap_id else 'all',
            target_gaps=targets,library_ids=sorted(m['id'] for m in self._project['materials']),contexts=[],
            protection_summary=dict(fingerprint=model.protection_summary(self._project['protections']),ranges=[]),
            blank_regions=copy.deepcopy(self._project['blank_regions']),seed=seed,algorithm_version='curve-completion-v1',
            budget=dict(max_expansions=256,beam_width=8,material_limit=24,max_new_notes=256,max_candidates=2))
        self.calls.append(('completion-capture',selected_gap_id))
        if not targets:
            outcome=outcome_fixture(request,'NOT_NEEDED')
            outcome['search'].update(expansions=0,generated_notes=0,termination='NO_TARGETS',raw_termination='NO_TARGETS')
            self.completion.update(status='NOT_NEEDED',outcome=outcome,message='没有待补全空缺。')
            return dict(token=None,request=request,attempt_id=None,immediate_outcome=outcome)
        token=dict(project_id=self._project['project_id'],session_id='fixture-session',request_id=ident,
            snapshot_id=request['snapshot_id'],spec_rev=model.SPEC_REV,contract_rev='curve-workflow-v2-r3-p4',
            edit_revision=self._revision,input_fingerprint=fp)
        self._requests[ident]=copy.deepcopy(token);self.attempts.append(ident);self.staging_dirty=True
        self.completion=dict(status='RUNNING',attempt_id=ident,input_fingerprint=fp,request=request,outcome=None,
                             message='补全计算中',error=None)
        return dict(token=copy.deepcopy(token),request=copy.deepcopy(request),attempt_id=ident,immediate_outcome=None)

    def accepts(self, token):
        self.main()
        valid=super().accepts(token)
        return valid and (not token['request_id'].startswith('completion-') or
                         (self.completion['status']=='RUNNING' and self.completion['attempt_id']==token['request_id']))

    def finish_completion(self, token, outcome):
        self.main()
        if self.finish_error:raise self.finish_error
        if not self.accepts(token):return False
        if self.finish_false:
            self.fail_completion(token,dict(code='INVALID_CANDIDATE',message='候选验证失败',details={}))
            return False
        self._requests.pop(token['request_id']);self.staging_dirty=True
        state=dict(SUCCEEDED='READY',INSUFFICIENT='READY',FAILED='FAILED',CANCELLED='CANCELLED')[outcome['status']]
        self.completion.update(status=state,outcome=copy.deepcopy(outcome),message='基础候选已暂存',error=outcome['error'])
        self.calls.append(('completion-finish',token['request_id']));return True

    def fail_completion(self, token, error):
        self.main()
        if self.fail_false or not self.accepts(token):return False
        self._requests.pop(token['request_id']);self.staging_dirty=True
        outcome=outcome_fixture(self.completion['request'],'FAILED');outcome['error']=error
        self.completion.update(status='FAILED',outcome=outcome,error=error,message=error['message'])
        self.calls.append(('completion-fail',token['request_id']));return True

    def cancel_completion(self, token):
        self.main()
        if not self.accepts(token):return False
        self._requests.pop(token['request_id']);self.staging_dirty=True
        outcome=outcome_fixture(self.completion['request'],'CANCELLED')
        self.completion.update(status='CANCELLED',outcome=outcome,message='已取消')
        return True

    def _stale(self):
        if self.completion['status'] in ('READY','RUNNING'):
            self.completion['status']='STALE';self.staging_dirty=True

    def _set(self, project):
        changed=super()._set(project)
        if changed:self._stale()
        return changed

    def undo(self):
        changed=super().undo()
        if changed:self._stale()
        return changed

    def redo(self):
        changed=super().redo()
        if changed:self._stale()
        return changed

    def save_snapshot(self, path=None):
        result=super().save_snapshot(path);self.staging_dirty=False;self.calls.append(('save-stage',self.completion['status']))
        return result

    def autosave_if_needed(self):
        self.main()
        if self.save_error:raise self.save_error
        if self.staging_dirty or not self.state()['is_saved']:
            self.calls.append(('autosave',None));return self.save_snapshot()


class CompletionWorker:
    def __init__(self):
        self.gate=None;self.started=threading.Event();self.finished=threading.Event()
        self.requests=[];self.cancels=[];self.threads=[];self.error=None;self.status='SUCCEEDED'

    def prepare(self, request, should_cancel=None, on_progress=None):
        self.requests.append(copy.deepcopy(request));self.cancels.append(should_cancel);self.threads.append(threading.get_ident())
        self.started.set()
        on_progress(dict(event_seq=0,phase='BASE_COMPLETION',message='搜索真实素材',expansions=1))
        if self.gate and not self.gate.wait(5):raise RuntimeError('test gate timeout')
        try:
            if self.error:raise self.error
            return outcome_fixture(request,self.status)
        finally:self.finished.set()


class CurveP4Tests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.controller=CompletionController(project_fixture());self.app.controller=self.controller
        self.real_prepare=completion_ui.prepare_completion
        self.worker=CompletionWorker()
        patcher=patch.object(completion_ui,'prepare_completion',side_effect=self.worker.prepare)
        patcher.start();self.addCleanup(patcher.stop)
        self.addCleanup(self.release_worker)
        self.app.refresh();self.root.update()

    def release_worker(self):
        if self.worker.gate:self.worker.gate.set()
        if self.worker.started.is_set():self.worker.finished.wait(5)

    def musical_state(self):
        state=self.controller.state()
        return copy.deepcopy((state['project'],state['is_saved'],state['can_undo'],state['can_redo'],
            self.controller.history_items(),self.app.selected_target,self.app.selected_history_id,
            self.app.playing_target,self.app.player.calls,self.app.player.status(),self.app.ready_assets))

    def run_completion(self):
        self.assertTrue(self.app.completion.start());self.finish_jobs()
        self.assertEqual(self.app.completion.state['status'],'READY')

    def preview(self, index=0):
        ui=self.app.completion
        ui.selector.current(index);ui.selector.event_generate('<<ComboboxSelected>>');self.root.update()
        self.assertTrue(ui.preview_candidate)

    def event_at(self,tick,level=.5):
        c=self.app.page.timeline
        return self.event(c.canvas,c.x(tick)-c.canvas.canvasx(0),c.y(level))

    def test_lazy_service_load_uses_frozen_callbacks(self):
        with patch.object(completion_ui.importlib,'import_module') as load:
            request={};cancel=lambda:False;progress=lambda event:None
            self.real_prepare(request,cancel,progress)
            load.assert_called_once_with('curve_candidates')
            load.return_value.prepare_completion.assert_called_once_with(request,should_cancel=cancel,on_progress=progress)

    def test_mapped_gap_mode_240ticks_does_not_edit_or_play(self):
        before=self.musical_state();c=self.app.page.timeline
        self.assertEqual([(g['start_tick'],g['end_tick']) for g in self.app.completion.gaps],[(1200,1440)])
        c.mode_buttons['gaps'].invoke();self.root.update()
        event=self.event_at(1320,.45)
        c.canvas.event_generate('<ButtonPress-1>',x=event.x,y=event.y)
        c.canvas.event_generate('<ButtonRelease-1>',x=event.x,y=event.y);self.root.update()
        self.assertEqual(self.app.completion.selected_gap_id,self.app.completion.gaps[0]['id'])
        self.assertEqual(self.musical_state(),before);self.assertIsNone(c.intensity_draft)
        self.run_completion()
        self.assertEqual(self.worker.requests[0]['scope'],'selected')
        self.assertEqual(self.worker.requests[0]['target_gaps'],self.app.completion.gaps)
        self.assertEqual(self.musical_state(),before)
        self.assertTrue(self.controller.state()['staging_dirty'])
        self.assertIn('已保存',self.app.save_label.cget('text'));self.assertIn('暂存未保存',self.app.save_label.cget('text'))
        self.assertTrue(self.controller.state()['is_saved']);self.assertIn('候选暂存未保存',self.app.saved_description)
        self.assertNotEqual(self.worker.threads[0],threading.get_ident())

    def test_default_all_and_clear_selected_gap(self):
        self.app.completion.select_gap(self.app.completion.gaps[0]['id'])
        self.app.page.timeline.all_gaps_button.invoke()
        self.run_completion()
        self.assertEqual(self.worker.requests[0]['scope'],'all')
        self.assertIsNone(self.app.completion.selected_gap_id)

    def test_existing_points_and_trace_modes_do_not_select_gap(self):
        c=self.app.page.timeline
        event=self.event_at(1320,.4)
        c.press(event)
        self.assertIsNotNone(c.intensity_draft);self.assertIsNone(self.app.completion.selected_gap_id)
        c.cancel();c.set_mode('trace');c.press(event)
        self.assertIsNotNone(c.intensity_draft);self.assertIsNone(self.app.completion.selected_gap_id)
        c.cancel()

    def test_subpixel_gap_integer_hit_scroll_resize_and_adjacent_music(self):
        p=project_fixture()
        p['placements'][1]['start_tick']=1201
        p['blank_regions'][0]['start_tick']=3121
        p['intensity_points']=[dict(tick=0,level=.25),dict(tick=p['total_ticks'],level=.25)]
        self.controller=CompletionController(p);self.app.controller=self.controller;self.app.refresh()
        c=self.app.page.timeline;c.set_mode('gaps')
        for geometry,scale in [('1020x700',.085),('1280x800',.15),('1440x900',.085)]:
            self.root.geometry(geometry);c.scale=scale;self.root.update();c.draw()
            c.canvas.xview_moveto(.03);self.root.update()
            gap=self.app.completion.gaps[0];a,t,b,d=c.gap_boxes[gap['id']]
            x=round((a+b)/2-c.canvas.canvasx(0));y=round(t+5)
            self.assertLess(b-a,1)
            c.canvas.event_generate('<ButtonPress-1>',x=x,y=y);c.canvas.event_generate('<ButtonRelease-1>',x=x,y=y)
            self.root.update();self.assertEqual(self.app.completion.selected_gap_id,gap['id'])
            selected=gap['id']
            # Music wins where its visible outline overlaps a gap stroke.
            music=c.project['placements'][1];center=c.y(c.level(music['start_tick']+music['length_ticks']/2))
            event=self.event(c.canvas,math.ceil(c.x(1201)-c.canvas.canvasx(0)),round(center))
            c.press(event);c.release(event)
            self.assertEqual(self.app.selected_target,('placement',music['id']))
            self.assertEqual(self.app.completion.selected_gap_id,selected)
        self.assertEqual(self.controller.state()['project'],p)
        self.run_completion();self.preview()
        added=c.project['placements'][-1]
        self.assertEqual(added['length_ticks'],1)
        center=c.y(c.level(added['start_tick']+.5))
        event=self.event(c.canvas,round(c.x(1200.5)-c.canvas.canvasx(0)),round(center))
        c.canvas.event_generate('<ButtonPress-1>',x=event.x,y=event.y)
        c.canvas.event_generate('<ButtonRelease-1>',x=event.x,y=event.y);self.root.update()
        self.assertEqual(c.selected_id,added['id'])
        self.assertEqual(self.controller.state()['project'],p)

    def test_preview_uses_own_memory_warns_and_restores_editor_and_player(self):
        self.app.select_target('material','block');self.app.prepare_selected();self.finish_jobs();self.app.play_selected()
        c=self.app.page.timeline;c.canvas.xview_moveto(.03);self.root.update()
        before=self.musical_state();scroll=c.canvas.xview()[0]
        self.assertEqual(self.controller.state()['memory_info']['state'],'PENDING_GAP')
        self.run_completion();self.preview()
        overlay=c.memory_overlay();self.assertEqual(overlay[0]['state'],'BOUND');self.assertIsNotNone(overlay[1])
        self.assertIn('memory-range',c.canvas.gettags(c.canvas.find_withtag('memory-range')[0]))
        self.assertIn('全保护，旋律未改变',self.app.detail_text.get())
        self.assertIn('编配仅为建议，尚未渲染',self.app.detail_text.get())
        self.assertIn('剩余空缺：无',self.app.detail_text.get())
        self.assertFalse(self.app.editable);self.assertTrue(c.readonly)
        placement=c.project['placements'][-1];self.assertEqual(placement['start_tick'],1200);self.assertEqual(placement['length_ticks'],240)
        event=self.event_at(1320,.8);c.press(event);c.motion(self.event_at(4000,.8));c.release(event);c.delete_selected()
        c.set_mode('trace');self.app.set_emotion('crisis');self.app.undo();self.app.redo()
        self.assertEqual(self.musical_state(),before)
        self.preview(1);self.assertEqual(self.musical_state(),before)
        c.canvas.xview_moveto(.3);self.app.completion.exit_button.invoke();self.root.update()
        self.assertFalse(c.readonly);self.assertEqual(c.project,self.controller.state()['project'])
        self.assertAlmostEqual(c.canvas.xview()[0],scroll,places=2);self.assertEqual(self.musical_state(),before)

    def test_mapped_escape_collapses_dock_without_changing_preview_edit_or_play(self):
        self.run_completion();before=self.musical_state();self.preview()
        canvas=self.app.page.timeline.canvas;canvas.focus_force();self.root.update()
        canvas.event_generate('<Escape>');self.root.update()
        self.assertIsNotNone(self.app.completion.preview_candidate)
        self.assertIsNone(self.app.drawer_mode)
        self.assertTrue(self.app.page.timeline.readonly)
        self.assertEqual(self.musical_state(),before)

    def test_theme_resize_preview_keeps_selection_and_usable_player(self):
        self.run_completion();self.preview();c=self.app.page.timeline
        ident=c.project['placements'][-1]['id'];c.selected_id=ident
        before=self.musical_state()
        for name,geometry in [('dark','1020x700'),('light','1280x800'),('dark','1440x900')]:
            self.app.theme.set(name);self.root.geometry(geometry);self.app.refresh();self.root.update()
            self.assertEqual(c.selected_id,ident);self.assertEqual(self.musical_state(),before)
            self.assertGreaterEqual(c.canvas.winfo_height(),160)
            self.assertGreaterEqual(self.app.play_button.winfo_height(),44)
            self.assertTrue(self.app.play_button.winfo_ismapped())
            for button in (self.app.completion.start_button,self.app.completion.cancel_button,self.app.completion.exit_button):
                if not button.winfo_ismapped():continue
                self.assertGreaterEqual(button.winfo_height(),44)
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
            if geometry=='1020x700':self.assertFalse(self.app.page.source_panel.winfo_ismapped())

    def test_cancel_late_duplicate_and_old_progress_do_not_replace_new_request(self):
        self.worker.gate=threading.Event();self.app.completion.start();self.assertTrue(self.worker.started.wait(1))
        old=copy.deepcopy(next(iter(self.app.jobs.values()))['token']);before=self.musical_state()
        event=next(iter(self.app.jobs.values()))['cancel']
        self.app.completion.cancel_button.invoke();self.assertTrue(event.is_set());self.assertTrue(self.worker.cancels[0]())
        self.worker.gate.set();self.assertTrue(self.worker.finished.wait(2))
        self.app.drain_jobs();self.assertEqual(self.app.completion.state['status'],'CANCELLED')
        self.assertEqual(self.musical_state(),before)
        self.worker.gate=threading.Event();self.worker.started.clear();self.worker.finished.clear()
        self.app.completion.start();self.assertTrue(self.worker.started.wait(1));self.app.drain_jobs()
        current=copy.deepcopy(next(iter(self.app.jobs.values()))['token'])
        self.assertEqual(old['input_fingerprint'],current['input_fingerprint'])
        status=self.app.status_text.get()
        for kind,value in [('PROGRESS',dict(event_seq=999,phase='BASE_COMPLETION',message='旧任务',expansions=999)),
                           ('DONE',outcome_fixture(self.worker.requests[0])),('ERROR',dict(code='ERROR',message='旧失败',details={}))]:
            self.app.completion.messages.put((old,kind,value))
        self.app.drain_jobs();self.assertEqual(self.app.status_text.get(),status)
        self.worker.gate.set();self.finish_jobs();completed=self.app.completion.state.copy()
        self.app.completion.messages.put((current,'DONE',outcome_fixture(self.worker.requests[-1])))
        self.app.drain_jobs();self.assertEqual(self.app.completion.state,completed)
        self.assertEqual(self.musical_state(),before)

    def test_progress_checks_full_token_sequence_and_phase(self):
        self.worker.gate=threading.Event();self.app.completion.start();self.assertTrue(self.worker.started.wait(1));self.app.drain_jobs()
        token=copy.deepcopy(next(iter(self.app.jobs.values()))['token'])
        def send(t,seq,message,phase='BASE_COMPLETION'):
            self.app.completion.messages.put((t,'PROGRESS',dict(event_seq=seq,phase=phase,message=message,expansions=2)))
            self.app.drain_jobs()
        send(token,2,'新进度');status=self.app.status_text.get()
        for seq in (1,2,True):send(token,seq,'乱序')
        altered=dict(token,snapshot_id='wrong');send(altered,3,'错误快照')
        send(token,3,'非P4','BRIDGE');self.assertEqual(self.app.status_text.get(),status)
        self.app.completion.cancel()
        send(token,4,'取消后');self.assertIn('已取消',self.app.status_text.get())

    def test_worker_and_mainthread_failures_release_busy_and_allow_retry(self):
        for error_at in ('worker','finish'):
            self.worker.error=RuntimeError('准备失败') if error_at=='worker' else None
            self.controller.finish_error=RuntimeError('回调失败') if error_at=='finish' else None
            before=self.musical_state();self.app.completion.start();self.finish_jobs()
            self.assertEqual(self.app.completion.state['status'],'FAILED');self.assertTrue(self.app.editable)
            self.assertIsNotNone(self.app.completion.state['error']);self.assertEqual(self.musical_state(),before)
        self.worker.error=None;self.controller.finish_error=None;self.run_completion()

    def test_thread_start_failure_persists_failure_releases_busy_and_allows_retry(self):
        before=self.musical_state()
        with patch.object(completion_ui.threading.Thread,'start',side_effect=RuntimeError('cannot start new thread')):
            self.assertFalse(self.app.completion.start())
        self.assertFalse(self.app.jobs);self.assertTrue(self.app.editable)
        self.assertEqual(self.app.completion.state['status'],'FAILED')
        self.assertIn('cannot start new thread',self.app.status_text.get());self.assertTrue(self.app.status_error)
        self.assertTrue(self.controller.staging_dirty);self.assertFalse(self.worker.requests)
        self.assertEqual(self.musical_state(),before)
        self.run_completion();self.assertEqual(self.musical_state(),before)

    def test_false_finish_reads_backend_failed_details_without_claiming_success(self):
        self.controller.finish_false=True
        before=self.musical_state();self.app.completion.start();self.finish_jobs()
        self.assertEqual(self.app.completion.state['status'],'FAILED')
        self.assertTrue(self.app.status_error);self.assertIn('候选验证失败',self.app.status_text.get())
        self.assertIn('INVALID_CANDIDATE',self.app.detail_text.get())
        self.assertTrue(self.app.editable);self.assertEqual(self.musical_state(),before)

    def test_false_fail_does_not_overwrite_newer_status(self):
        self.worker.gate=threading.Event();self.worker.error=RuntimeError('不属于当前任务')
        self.app.completion.start();self.assertTrue(self.worker.started.wait(1))
        self.controller.fail_false=True
        self.app.drain_jobs()
        self.app.tell('较新任务的消息')
        self.worker.gate.set();self.finish_jobs()
        self.assertEqual(self.app.status_text.get(),'较新任务的消息')

    def test_no_target_and_bad_selected_capture_have_no_attempt(self):
        p=project_fixture();p=model.edit(p,'mark_blank',start_tick=1200,end_tick=1440)
        self.controller=CompletionController(p);self.app.controller=self.controller;self.app.refresh()
        before=self.musical_state();self.app.completion.start();self.root.update()
        self.assertFalse(self.app.jobs);self.assertFalse(self.controller.attempts);self.assertFalse(self.worker.requests)
        self.assertFalse(self.controller.staging_dirty);self.assertEqual(self.musical_state(),before)
        self.assertEqual(self.app.completion.state['status'],'NOT_NEEDED')
        self.app.completion.selected_gap_id='stale'
        self.app.safe(self.app.completion.start)
        self.assertTrue(self.app.status_error);self.assertFalse(self.controller.attempts);self.assertEqual(self.musical_state(),before)

    def test_stale_after_edit_undo_and_interrupted_recovery_do_not_start_worker(self):
        self.run_completion();before=self.controller.state()['project']
        self.app.edit('set_melody_only',value=True);self.app.undo()
        self.assertEqual(self.controller.state()['project'],before)
        self.assertEqual(self.app.completion.state['status'],'STALE');self.assertTrue(self.app.completion.selector.instate(['disabled']))
        count=len(self.worker.requests)
        self.controller.completion.update(status='INTERRUPTED',outcome=None,message='保存的计算已中断')
        self.app.refresh();self.root.update()
        self.assertIn('已中断',self.app.completion.label.cget('text'));self.assertEqual(len(self.worker.requests),count)
        self.assertTrue(self.controller.state()['staging_dirty'])

    def test_staging_autosave_failure_blocks_switch_close_and_running_save_is_explicit(self):
        self.worker.gate=threading.Event();self.app.completion.start();self.assertTrue(self.worker.started.wait(1))
        self.assertFalse(self.app.close());self.assertFalse(self.app.new_project());self.assertFalse(self.app.open_project('legacy'))
        self.assertEqual(self.app.file_menu.entrycget('保存快照','state'),'normal')
        self.app.file_menu.invoke('保存快照')
        self.assertIn(('save-stage','RUNNING'),self.controller.calls)
        self.assertFalse(self.controller.staging_dirty)
        self.app.completion.cancel();self.assertTrue(self.controller.staging_dirty)
        self.controller.save_error=OSError('disk full');before=self.musical_state()
        self.assertFalse(self.app.close());self.app.safe(self.app.new_project);self.app.safe(lambda:self.app.open_project('legacy'))
        self.assertEqual(self.musical_state(),before);self.assertFalse(self.app.closed);self.assertTrue(self.root.winfo_exists())
        self.controller.save_error=None
        self.app.save_project();self.assertFalse(self.controller.staging_dirty)

    def test_insufficient_and_remaining_gaps_are_explicit(self):
        p=project_fixture();p=model.edit(p,'delete_blank',blank_id=p['blank_regions'][0]['id'])
        self.controller=CompletionController(p);self.app.controller=self.controller;self.app.refresh()
        self.app.completion.select_gap(self.app.completion.gaps[0]['id']);self.worker.status='INSUFFICIENT'
        self.run_completion();self.assertIn('方案不足',self.app.completion.label.cget('text'))
        self.preview();self.assertIn('3360–15360 tick',self.app.detail_text.get());self.assertIn('有限备选池',self.app.detail_text.get())
        self.assertEqual(self.app.completion.preview_candidate['capabilities']['can_apply'],False)
        self.assertIn('尚未处理bridge与连接',self.app.completion.label.cget('text'))

    def test_readonly_history_format_export_and_play_selection_survive(self):
        self.controller.readonly=True
        self.controller.histories=[dict(id='history',label='历史成品',paths=dict(wav=str(self.wav),mid='history.mid',mmp='history.mmp'),
            availability=dict(wav=True,mid=True,mmp=False),audio_seconds=4.5,body_seconds=4.)]
        self.app.refresh();self.root.update()
        before=self.musical_state();self.assertFalse(self.app.completion.start());self.assertFalse(self.app.completion.panel.winfo_ismapped())
        self.assertEqual(self.musical_state(),before)
        self.app.page.history_list.selection_set(0);self.app.history_selected()
        self.assertEqual(self.app.player.calls,[]);self.app.play_selected();self.assertEqual(self.app.playing_target['target'],('history','history'))
        playing=copy.deepcopy(self.app.playing_target)
        destination=Path(self.folder.name)/'history.mid'
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=str(destination)):
            self.app.export_history('mid')
        self.assertIn(('export',('history','mid',str(destination))),self.controller.calls)
        self.assertIn(str(destination),self.app.export_receipt.get('1.0','end'))
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=''):
            self.app.export_history('wav')
        self.assertEqual(self.app.playing_target,playing);self.assertEqual(len(self.app.player.calls),1)


class RealFacadeP4Tests(MappedUIFixture):
    """Real P4 Facade/gates/store; only the algorithm and audio are fixtures."""
    def setUp(self):
        super().setUp()
        import curve_workflow
        from test_curve_candidates import fixture as gate_fixture, material
        self.controller=gate_fixture()
        extra=material('different');extra['notes'][0]['pitch']=67
        self.controller.edit('add_material',material=extra)
        self.controller.edit('set_intensity',points=[dict(tick=0,level=.2),dict(tick=1320,level=.9),dict(tick=3840,level=.2)])
        self.initial_path=Path(self.folder.name)/'initial.json'
        self.controller.save_snapshot(self.initial_path)
        self.app.controller=self.controller;self.app.refresh();self.root.update()
        self.app.completion.select_gap(self.controller.gap_items()[0]['id'])
        self.curve_workflow=curve_workflow
        self.gate=threading.Event();self.gate.set();self.started=threading.Event();self.finished=threading.Event()
        self.algorithm_threads=[]
        self.addCleanup(self.release_algorithm)
        from types import SimpleNamespace
        patcher=patch.dict('sys.modules',curve_completion=SimpleNamespace(propose=self.propose))
        patcher.start();self.addCleanup(patcher.stop)

    def propose(self, request, should_cancel=None, on_progress=None):
        from test_curve_candidates import proposal, raw
        self.algorithm_threads.append(threading.get_ident());self.started.set()
        on_progress(dict(message='固定提案夹具',expansions=1))
        try:
            if not self.gate.wait(5):raise RuntimeError('fixture timeout')
            return raw([proposal(request,'A1',emotion='hope'),proposal(request,'different',emotion='hope')])
        finally:self.finished.set()

    def release_algorithm(self):
        self.gate.set()
        if self.started.is_set():self.finished.wait(5)

    def musical_state(self):
        state=self.controller.state()
        return copy.deepcopy((state['project'],state['is_saved'],state['can_undo'],state['can_redo'],
                              self.app.selected_target,self.app.playing_target,self.app.player.calls,self.app.player.status()))

    def test_actual_gate_memory_preview_and_saved_bundle_keep_edit_and_player(self):
        self.app.select_target('material','A1');self.app.prepare_selected();self.finish_jobs();self.app.play_selected()
        before=self.musical_state();self.app.completion.start();self.finish_jobs()
        self.assertEqual(self.app.completion.state['status'],'READY');self.assertEqual(len(self.app.completion.candidates),2)
        self.assertEqual(self.musical_state(),before);self.assertTrue(self.controller.state()['staging_dirty'])
        self.assertNotEqual(self.algorithm_threads[0],threading.get_ident())
        self.app.completion.selector.current(0);self.app.completion.enter_preview();self.root.update()
        info,lock=self.app.page.timeline.memory_overlay()
        self.assertEqual(info['state'],'BOUND');self.assertEqual((lock['start_tick'],lock['end_tick']),(1200,1440))
        self.assertIn('旋律未改变',self.app.detail_text.get());self.assertIn('编配仅为建议',self.app.detail_text.get())
        self.assertIn('3360–3840 tick',self.app.detail_text.get());self.assertEqual(self.musical_state(),before)
        self.app.completion.exit_preview();self.assertEqual(self.musical_state(),before)
        saved=Path(self.folder.name)/'ready.json';self.controller.save_snapshot(saved);self.app.refresh()
        reopened=self.curve_workflow.Controller();reopened.load(saved)
        self.assertEqual(reopened.project,self.controller.project);self.assertEqual(reopened.completion_state()['status'],'READY')
        self.assertFalse(self.controller.state()['staging_dirty'])

    def test_real_invalid_finish_false_is_visible_persistent_failure(self):
        before=self.musical_state()
        with patch.object(completion_ui,'prepare_completion',return_value={}):
            self.app.completion.start();self.finish_jobs()
        state=self.controller.completion_state()
        self.assertEqual(state['status'],'FAILED');self.assertIsNotNone(state['error'])
        self.assertTrue(self.app.status_error);self.assertIn(state['error']['message'],self.app.status_text.get())
        self.assertEqual(self.musical_state(),before);self.assertTrue(self.app.editable)
        saved=Path(self.folder.name)/'failed.json';self.controller.save_snapshot(saved)
        reopened=self.curve_workflow.Controller();reopened.load(saved)
        self.assertEqual(reopened.completion_state()['status'],'FAILED')

    def test_real_thread_start_failure_consumes_token_and_retry_succeeds(self):
        before=self.musical_state()
        with patch.object(completion_ui.threading.Thread,'start',side_effect=RuntimeError('thread start denied')):
            self.assertFalse(self.app.completion.start())
        self.assertFalse(self.app.jobs);self.assertEqual(self.controller.completion_state()['status'],'FAILED')
        self.assertTrue(self.app.editable);self.assertEqual(self.musical_state(),before)
        self.assertTrue(self.app.completion.start());self.finish_jobs()
        self.assertEqual(self.controller.completion_state()['status'],'READY');self.assertEqual(self.musical_state(),before)

    def test_real_running_save_cancel_and_reopen_are_interrupted_without_restart(self):
        self.gate.clear();self.app.completion.start();self.assertTrue(self.started.wait(1))
        before=self.musical_state();saved=Path(self.folder.name)/'running.json'
        self.controller.save_snapshot(saved);self.app.refresh()
        self.app.completion.cancel();self.assertEqual(self.controller.completion_state()['status'],'CANCELLED')
        self.assertTrue(self.controller.state()['staging_dirty']);self.assertEqual(self.musical_state(),before)
        self.gate.set();self.assertTrue(self.finished.wait(2));self.app.drain_jobs()
        self.assertEqual(self.controller.completion_state()['status'],'CANCELLED')
        count=len(self.algorithm_threads)
        self.app.open_project(saved);self.root.update()
        self.assertEqual(self.controller.completion_state()['status'],'INTERRUPTED')
        self.assertTrue(self.controller.state()['staging_dirty']);self.assertEqual(len(self.algorithm_threads),count)
        self.assertIn('已中断',self.app.completion.label.cget('text'))
