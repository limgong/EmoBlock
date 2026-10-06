"""Generation lifecycle through the real queue, worker and Tk controls; render faults are simulated."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import wave

import story_engine
from unified_ui import UnifiedApp
from legacy_story_fixture import restore_legacy


class GenerationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.app=UnifiedApp(self.root);restore_legacy(self.app)
        self.tk_errors=[];self.root.report_callback_exception=lambda *error:self.tk_errors.append(error)
        self.page=self.app.story_page;self.root.update_idletasks()
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.gates=[];self.calls=[];self.main=threading.get_ident()

    def tearDown(self):
        for gate in self.gates:gate.set()
        self.wait(lambda:not self.app.busy)
        self.page.preview_planner.close();self.root.after_cancel(self.app.timer)
        self.app.stop_playback();self.root.destroy();self.temp.cleanup()
        self.assertEqual(self.tk_errors,[])

    def wait(self,predicate):
        until=time.monotonic()+5
        while not predicate():
            if time.monotonic()>until:self.fail('job did not settle')
            self.root.update();time.sleep(.005)
        self.root.update_idletasks()

    def result(self,project):
        folder=self.folder/str(len(list(self.folder.iterdir())));folder.mkdir()
        planned=story_engine.plan(project)
        report=dict(status='complete',output_directory=str(folder),bars=project['duration']*project['bpm']/240,
                    duration_seconds=project['duration'])
        for name,data in (('story.json',project),('story-plan.json',planned),('report.json',report)):
            (folder/name).write_text(json.dumps(data))
        for name in ('composition.mid','composition.mmp'):(folder/name).write_bytes(b'fixture')
        with wave.open(str(folder/'preview.wav'),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\x01\x00'*8000)
        return planned,report

    def worker(self,project,progress):
        self.calls.append(copy.deepcopy(project));progress('测试后端：连续渲染整首音乐')
        return self.result(project)

    def blocked_worker(self,project,progress):
        self.calls.append(copy.deepcopy(project));progress('测试后端：连续渲染整首音乐')
        self.gates[-1].wait(5)
        return self.result(project)

    def test_duplicate_clicks_progress_main_thread_and_single_version(self):
        gate=threading.Event();self.gates.append(gate)
        p=self.page;a=self.app;p.resize_timeline(1);history=copy.deepcopy(p.history)
        seen=[];original=p.generation_progress
        def progress(text):seen.append((threading.get_ident(),text));original(text)
        with patch('story_ui.engine.generate',side_effect=self.blocked_worker),patch.object(p,'generation_progress',side_effect=progress),patch.object(a.player,'play') as play:
            p.generate();ident=a.active_job['id'];p.generate();p.generate_button.invoke()
            self.assertTrue(a.busy);self.assertIn('生成中',p.generation_status.get())
            self.wait(lambda:any('测试后端' in stage for _,stage in seen))
            self.assertIn('测试后端',p.generation_status.get());self.assertEqual(len(self.calls),1)
            self.assertTrue(all(owner==self.main for owner,_ in seen))
            self.assertTrue(p.undo_button.instate(['disabled']));self.assertFalse(a.stop_button.instate(['disabled']))
            with patch.object(a.player,'close') as stop:a.stop_button.invoke();stop.assert_called_once()
            before=copy.deepcopy(p.project)
            a.edit_shortcut(SimpleNamespace(widget=p.line,state=0,keysym='z'))
            p.press(SimpleNamespace(x=p.px(4),y=60));self.assertIsNone(p.drag)
            p.draw_source_cards();self.assertTrue(all(b.instate(['disabled']) for b in p.card_role_buttons.values()))
            self.assertEqual(p.project,before)
            gate.set();self.wait(lambda:not a.busy)
            a.messages.put((ident,'done',self.result(before)))
            a.messages.put((ident,'progress','迟到提示'))
            self.root.after_cancel(a.timer);a.poll()
            self.assertEqual(len(a.results),1);self.assertEqual(p.generation_state,'success')
            self.assertIn('V01',p.generation_status.get());play.assert_not_called()
            self.assertEqual(history,p.history)
            self.assertFalse(p.undo_button.instate(['disabled']));self.assertTrue(p.redo_button.instate(['disabled']))
            self.assertIn('一致',a.edit_status_label.cget('text'))

    def test_backend_failure_preserves_old_files_history_and_retry_uses_new_snapshot(self):
        p=self.page;a=self.app
        _,old=self.result(p.snapshot());a.add_result(old,'快速成品',story_project=p.snapshot())
        original_files={f.name:f.read_bytes() for f in Path(old['output_directory']).iterdir()}
        p.resize_timeline(1);p.undo();history=copy.deepcopy(p.history);before=copy.deepcopy(p.project)
        def fail(project,progress):
            self.calls.append(copy.deepcopy(project));progress('连续渲染整首音乐')
            raise RuntimeError('renderer failed; log: /tmp/example-render.log')
        with patch('story_ui.engine.generate',side_effect=fail):
            p.generate();self.wait(lambda:not a.busy)
        self.assertEqual(p.generation_state,'failed');self.assertIn('连续渲染',p.generation_status.get())
        self.assertIn('/tmp/example-render.log',p.generation_detail)
        p.details_button.invoke();self.assertEqual(p.generation_details.winfo_manager(),'pack')
        self.assertEqual(len(a.results),1);self.assertEqual(p.project,before);self.assertEqual(p.history,history)
        self.assertTrue(p.undo_button.instate(['disabled']));self.assertFalse(p.redo_button.instate(['disabled']))
        self.assertFalse(a.export_buttons['wav'].instate(['disabled']))
        with patch.object(a.player,'play',return_value=1) as play:
            a.play();play.assert_called_once();a.stop_playback()
        target=self.folder/'export.wav'
        with patch('unified_ui.filedialog.asksaveasfilename',return_value=str(target)):a.export_result('wav')
        self.assertEqual(target.read_bytes(),original_files['preview.wav'])
        self.assertEqual(original_files,{f.name:f.read_bytes() for f in Path(old['output_directory']).iterdir()})
        p.bpm.set('96');current=p.snapshot()
        with patch('story_ui.engine.generate',side_effect=self.worker):
            p.retry_button.invoke();self.wait(lambda:not a.busy)
        self.assertEqual(self.calls[-1],current);self.assertNotEqual(self.calls[0]['bpm'],self.calls[-1]['bpm'])
        self.assertEqual(len(a.results),2);self.assertIn('V02',p.generation_status.get())
        self.assertIn('一致',a.edit_status_label.cget('text'));self.assertEqual(history,p.history)

    def test_result_callback_exception_rolls_back_and_unlocks(self):
        a=self.app;p=self.page;p.resize_timeline(1);before=copy.deepcopy(p.history)
        add=a.add_result
        def broken(*args,**kwargs):add(*args,**kwargs);raise RuntimeError('injected after history append')
        with patch('story_ui.engine.generate',side_effect=self.worker),patch.object(a,'add_result',side_effect=broken):
            p.generate();self.wait(lambda:not a.busy)
        self.assertEqual(a.results,[]);self.assertEqual(p.generation_state,'failed')
        self.assertIn('整理生成结果',p.generation_status.get());self.assertIn('injected',p.generation_detail)
        self.assertFalse(p.generate_button.instate(['disabled']));self.assertEqual(p.history,before)
        self.assertFalse(p.undo_button.instate(['disabled']));self.assertTrue(p.redo_button.instate(['disabled']))
        self.assertTrue(all(b.instate(['disabled']) for b in a.export_buttons.values()))
        with patch('story_ui.engine.generate',side_effect=self.worker):p.retry_button.invoke();self.wait(lambda:not a.busy)
        self.assertEqual(len(a.results),1)

    def test_missing_file_is_not_a_version(self):
        def broken(project,progress):
            result=self.result(project);(Path(result[1]['output_directory'])/'composition.mid').unlink();return result
        with patch('story_ui.engine.generate',side_effect=broken):self.page.generate();self.wait(lambda:not self.app.busy)
        self.assertEqual(self.app.results,[]);self.assertEqual(self.page.generation_state,'failed')
        self.assertIn('composition.mid',self.page.generation_detail)

    def test_truncated_wav_payload_is_not_a_version(self):
        for keep in (44,80):
            with self.subTest(bytes=keep):
                def broken(project,progress):
                    result=self.result(project);path=Path(result[1]['output_directory'])/'preview.wav'
                    path.write_bytes(path.read_bytes()[:keep]);return result
                with patch('story_ui.engine.generate',side_effect=broken):
                    self.page.generate();self.wait(lambda:not self.app.busy)
                self.assertEqual(self.app.results,[]);self.assertEqual(self.page.generation_state,'failed')
                self.assertIn('音频数据不完整',self.page.generation_detail)
                self.assertFalse(self.page.retry_button.instate(['disabled']))

    def test_old_messages_cannot_finish_or_overwrite_new_job(self):
        a=self.app;p=self.page
        with patch('story_ui.engine.generate',side_effect=RuntimeError('first fails')):
            p.generate();old=a.active_job['id'];self.wait(lambda:not a.busy)
        gate=threading.Event();self.gates.append(gate)
        with patch('story_ui.engine.generate',side_effect=self.blocked_worker):
            p.generate();new=a.active_job['id']
            a.messages.put((old,'progress','旧阶段'));a.messages.put((old,'error','旧失败'))
            a.messages.put((old,'done',self.result(p.snapshot())))
            self.root.after_cancel(a.timer);a.poll()
            self.assertTrue(a.busy);self.assertEqual(a.active_job['id'],new);self.assertEqual(a.results,[])
            self.assertNotIn('旧',p.generation_status.get());gate.set();self.wait(lambda:not a.busy)
            status=p.generation_status.get()
            a.messages.put((old,'error','旧失败'));self.root.after_cancel(a.timer);a.poll()
            self.assertEqual(status,p.generation_status.get());self.assertEqual(len(a.results),1)

    def test_generic_job_callback_failure_and_disabled_state_recovery(self):
        a=self.app;p=self.page
        p.redo_button.state(['disabled']);seen=[]
        def work():a.progress_message('素材准备阶段');return 'result'
        def done(result):seen.append((result,threading.get_ident()));raise RuntimeError('callback failure')
        self.assertTrue(a.job('准备素材',work,done));self.assertFalse(a.job('duplicate',work,done))
        self.wait(lambda:not a.busy)
        self.assertEqual(seen,[('result',self.main)]);self.assertIsNone(a.active_job)
        self.assertTrue(p.redo_button.instate(['disabled']));self.assertFalse(p.generate_button.instate(['disabled']))
        self.assertEqual(p.generation_state,'idle')
        self.assertIn('callback failure',a.notice.cget('text'))
        self.assertIn('callback failure',a.last_job_error)
        values=[];a.job('再次准备',lambda:7,values.append);self.wait(lambda:not a.busy);self.assertEqual(values,[7])

    def test_input_validation_failure_can_be_fixed_without_worker(self):
        p=self.page;p.bpm.set('invalid')
        with patch('story_ui.engine.generate') as work:
            p.generate();self.assertFalse(self.app.busy);work.assert_not_called()
        self.assertEqual(p.generation_state,'failed');self.assertIn('检查当前编辑',p.generation_status.get())
        p.bpm.set('100')
        with patch('story_ui.engine.generate',side_effect=self.worker):p.retry_button.invoke();self.wait(lambda:not self.app.busy)
        self.assertEqual(self.calls[0]['bpm'],100)

    def test_thread_start_failure_unlocks_and_keeps_retry(self):
        with patch('unified_ui.threading.Thread.start',side_effect=RuntimeError('cannot start thread')):
            self.page.generate()
        self.assertFalse(self.app.busy);self.assertEqual(self.page.generation_state,'failed')
        self.assertFalse(self.page.retry_button.instate(['disabled']))

    def test_source_audition_job_still_prepares_then_explicitly_plays(self):
        p=self.page;a=self.app
        _,report=self.result(p.snapshot());path=Path(report['output_directory'])/'preview.wav'
        rows=copy.deepcopy(p.source_block_rows)
        with patch('story_ui.block_audition.render_source',return_value=(path,rows)),patch.object(a.player,'play',return_value=1) as play:
            p.start_source_audio();self.wait(lambda:not a.busy)
            play.assert_called_once();self.assertEqual(a.playing_path,'source:'+str(path))
        self.assertEqual(a.results,[]);self.assertEqual(p.generation_state,'idle')

    def test_source_audition_failure_exposes_log_and_leaves_preparing_state(self):
        p=self.page;a=self.app
        for action in (p.start_source_audio,p.play_source_block):
            with self.subTest(action=action.__name__):
                p.input_blocks.selection_set('0')
                with patch('story_ui.block_audition.render_source',side_effect=RuntimeError('LMMS failure; /tmp/verifier-render.log')):
                    action();self.wait(lambda:not a.busy)
                p.sync_source_player()
                self.assertIn('未完成',p.source_time.get());self.assertNotEqual(p.source_time.get(),'准备试听…')
                self.assertIn('/tmp/verifier-render.log',a.notice.cget('text'))
                self.assertIn('RuntimeError',a.last_job_error);self.assertEqual(a.results,[])
        _,report=self.result(p.snapshot());path=Path(report['output_directory'])/'preview.wav'
        with patch('story_ui.block_audition.render_source',return_value=(path,p.source_block_rows)),patch.object(a.player,'play',return_value=1):
            p.start_source_audio();self.wait(lambda:not a.busy)
        self.assertEqual(p.source_error,'');self.assertEqual(a.last_job_error,'')

    def test_version_is_bound_to_clicked_snapshot_not_later_control_values(self):
        p=self.page;a=self.app;gate=threading.Event();self.gates.append(gate)
        clicked=p.snapshot()
        with patch('story_ui.engine.generate',side_effect=self.blocked_worker):
            p.generate();p.bpm.set('96')  # programmatic change, UI itself is locked
            gate.set();self.wait(lambda:not a.busy)
        self.assertEqual(self.calls[0],clicked)
        self.assertEqual(a.results[0]['story_fingerprint'],a.story_fingerprint(clicked))
        self.assertEqual(p.bpm.get(),'96');self.assertIn('尚未生成',a.edit_status_label.cget('text'))


if __name__=='__main__':unittest.main()
