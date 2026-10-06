"""Project snapshots and transactional UI switching, using disposable files only."""
import copy
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import wave

import studio_model as model
from runtime_config import ASSETS
from unified_ui import UnifiedApp
from legacy_story_fixture import restore_legacy


class ProjectSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.root=tk.Tk();self.root.withdraw();self.app=UnifiedApp(self.root);restore_legacy(self.app);self.page=self.app.story_page
        self.root.update_idletasks();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.storage=patch.object(model.structure,'ROOT',self.folder);self.storage.start()

    def tearDown(self):
        self.storage.stop();self.page.preview_planner.close()
        self.root.after_cancel(self.app.timer);self.app.stop_playback();self.root.destroy();self.temp.cleanup()
        self.assertEqual(self.errors,[])

    def version(self):
        folder=self.folder/'render';folder.mkdir(exist_ok=True)
        with wave.open(str(folder/'preview.wav'),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\x01\x00'*8000)
        for name in ('composition.mid','composition.mmp'):(folder/name).write_text('test fixture')
        report=dict(output_directory=str(folder),bars=4,duration_seconds=8)
        self.app.add_result(report,'快速成品',story_project=self.page.snapshot());return folder

    def other_project(self):
        data=self.app.project_payload();data['settings']['story']['melody_only']=True
        return model.save_project(data['pool'],data['doc'],data['curve'],data['results'],data['settings'],path=self.folder/'other.json')

    def test_failed_switch_restores_expanded_failure_window(self):
        a=self.app;p=self.page;other=self.other_project()
        self.root.deiconify();self.root.update()
        p.generation_panel.pack(fill='x',before=p.footer)
        p.generation_failed('渲染阶段','保留原失败日志');p.toggle_generation_details();self.root.update()
        before=a.project_payload();history=copy.deepcopy(p.history);restore=p.restore
        def broken(story):
            restore(story);raise RuntimeError('injected restore failure')
        with patch.object(p,'restore',side_effect=broken):
            with self.assertRaises(ValueError):a.load_project(other)
        self.root.update()
        self.assertTrue(p.generation_window.winfo_ismapped())
        self.assertEqual(p.details_button.cget('text'),'收起详情')
        self.assertIn('保留原失败日志',p.generation_details.get('1.0','end'))
        self.assertEqual(a.project_payload(),before);self.assertEqual(p.history,history)
        p.details_button.invoke();self.root.update()
        self.assertEqual(p.generation_window.state(),'withdrawn')
        self.assertEqual(p.details_button.cget('text'),'展开详情')
        p.details_button.invoke();self.root.update()
        self.assertTrue(p.generation_window.winfo_ismapped())
        a.load_project(other);self.root.update()
        self.assertEqual(p.generation_window.state(),'withdrawn')

    def test_save_then_edit_and_undo_matches_persisted_content(self):
        a=self.app;p=self.page
        p.resize_timeline(1);self.assertTrue(a.dirty)
        generated=a.edit_status_label.cget('text');path=a.save_project()
        self.assertFalse(a.dirty);self.assertIn('已保存',a.save_status_label.cget('text'))
        self.assertEqual(a.edit_status_label.cget('text'),generated)
        p.resize_timeline(1);self.assertTrue(a.dirty);self.assertIn('未保存',a.save_status_label.cget('text'))
        p.undo();self.assertFalse(a.dirty);self.assertIn('已保存',a.save_status_label.cget('text'))
        self.assertEqual(json.loads(path.read_text()),a.project_payload())
        self.assertIn(path.name,a.save_location_text());self.assertIn(str(path),a.save_location_text())

    def test_selection_playback_scroll_and_generated_status_are_separate(self):
        a=self.app;p=self.page;self.version();a.save_project();signature=a.saved_signature
        a.show_result();a.select_history(0);p.select_source_card(p.project['sources'][0]['id'])
        p.line.xview_moveto(.5);a.play_position=3.;p.hover_region=1;p.draw()
        with patch.object(a.player,'play',return_value=1):a.play();a.stop_playback()
        self.assertFalse(a.dirty);self.assertEqual(signature,a.project_signature())
        a.add_result(copy.deepcopy(a.results[0]['report']),'快速成品',story_project=p.snapshot())
        self.assertTrue(a.dirty);self.assertIn('一致',a.edit_status_label.cget('text'))

    def test_each_save_is_new_and_old_file_unchanged(self):
        first=self.app.save_project();content=first.read_bytes();second=self.app.save_project()
        self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),content)
        self.assertEqual(json.loads(first.read_text()),json.loads(second.read_text()))

    def test_save_failure_preserves_editor_history_and_old_file(self):
        a=self.app;p=self.page;old=a.save_project();content=old.read_bytes();p.resize_timeline(1)
        data=a.project_payload();history=copy.deepcopy(p.history)
        with patch.object(model,'save_project',side_effect=PermissionError('test write denied')):
            with self.assertRaisesRegex(ValueError,'保存失败'):a.save_project()
        self.assertEqual(a.project_payload(),data);self.assertEqual(p.history,history)
        self.assertTrue(a.dirty);self.assertEqual(old.read_bytes(),content);self.assertEqual(a.saved_path,old)
        self.assertIn('保存失败',a.save_status_label.cget('text'))

    def test_cancel_open_preserves_playback_and_project(self):
        a=self.app;p=self.page;p.resize_timeline(1);data=a.project_payload();history=copy.deepcopy(p.history)
        a.playing_path='existing-playback';a.play_position=5
        with patch('project_session.filedialog.askopenfilename',return_value=''),patch.object(a,'stop_playback') as stop:
            a.open_project();stop.assert_not_called()
        self.assertEqual(a.project_payload(),data);self.assertEqual(p.history,history)
        self.assertEqual((a.playing_path,a.play_position),('existing-playback',5))

    def test_corrupt_or_unsupported_file_is_read_before_autosave(self):
        a=self.app;p=self.page;p.resize_timeline(1);data=a.project_payload();history=copy.deepcopy(p.history)
        for content in ('not json','{"schema":"unknown"}'):
            path=self.folder/'broken.json';path.write_text(content)
            with patch.object(a,'save_project') as save,patch.object(a,'stop_playback') as stop:
                with self.assertRaises((ValueError,KeyError)):a.load_project(path)
                save.assert_not_called();stop.assert_not_called()
            self.assertEqual(data,a.project_payload());self.assertEqual(history,p.history)

    def test_autosave_failure_blocks_open_new_and_close(self):
        a=self.app;p=self.page;other=self.other_project();p.resize_timeline(1)
        data=a.project_payload();history=copy.deepcopy(p.history)
        with patch.object(model,'save_project',side_effect=OSError('disk full')),patch.object(a,'stop_playback') as stop:
            for action in (a.new_project,lambda:a.load_project(other)):
                with self.assertRaisesRegex(ValueError,'保存失败'):action()
            a.close();stop.assert_not_called()
        self.assertTrue(self.root.winfo_exists());self.assertEqual(data,a.project_payload());self.assertEqual(history,p.history)

    def test_restore_failure_rolls_back_model_history_selection_and_playback(self):
        a=self.app;p=self.page;self.version();other=self.other_project();p.resize_timeline(1)
        data=a.project_payload();history=copy.deepcopy(p.history);original=p.restore
        a.playing_path='old-audio';a.play_position=2
        def broken(story):original(story);raise RuntimeError('injected restore failure')
        with patch.object(p,'restore',side_effect=broken),patch.object(a,'stop_playback') as stop:
            with self.assertRaisesRegex(ValueError,'恢复失败'):a.load_project(other)
            stop.assert_not_called()
        self.assertEqual(data,a.project_payload());self.assertEqual(history,p.history)
        self.assertEqual(a.result_list.curselection(),(0,));self.assertEqual((a.playing_path,a.play_position),('old-audio',2))
        self.assertFalse(a.switching_project)
        p.undo();self.assertNotEqual(p.history,history)

    def test_round_trip_preserves_sources_settings_metadata_and_saved_state(self):
        a=self.app;p=self.page;self.version();p.resize_timeline(1);p.melody_only.set(True)
        p.commit(p.snapshot(),'设置');a.seed.set('71');a.connections.set(False)
        saved=a.save_project();expected=a.project_payload()
        p.resize_timeline(1);a.load_project(saved)
        self.assertEqual(expected,a.project_payload());self.assertFalse(a.dirty)
        self.assertFalse(p.history.can_undo or p.history.can_redo);self.assertEqual(p.generation_state,'idle')
        self.assertIn('已保存',a.save_status_label.cget('text'))
        self.assertEqual(p.generation_detail,'');self.assertEqual(a.last_job_error,'')

    def test_missing_source_and_audio_keep_snapshots_and_mark_unavailable(self):
        a=self.app;p=self.page;folder=self.version()
        p.project['sources'][0]['source']['path']=str(self.folder/'missing.mid')
        a.source_path=str(self.folder/'missing-legacy.mid');a.track_var.set('1. prior track')
        saved=a.save_project();expected=a.project_payload();(folder/'preview.wav').unlink()
        a.load_project(saved)
        self.assertEqual(a.project_payload(),expected);self.assertFalse(a.dirty)
        self.assertIn('素材快照',a.notice.cget('text'));self.assertIn('音频不可用',a.selected_version_label.cget('text'))
        self.assertFalse(a.transport_play.enabled);self.assertTrue(a.export_buttons['wav'].instate(['disabled']))
        self.assertFalse(a.export_buttons['mid'].instate(['disabled']))
        self.assertTrue(p.project['sources'][0]['notes']);p.resize_timeline(1);self.assertTrue(a.dirty)

    def test_clean_new_project_does_not_claim_autosave(self):
        a=self.app
        with patch.object(a,'save_project') as save:a.new_project();save.assert_not_called()
        self.assertNotIn('自动保存',a.notice.cget('text'));self.assertIsNone(a.saved_path)
        self.assertIn('尚未保存',a.save_status_label.cget('text'))

    def test_open_then_clean_new_keeps_previous_snapshot_location(self):
        a=self.app;other=self.other_project();a.load_project(other)
        self.assertEqual(a.recent_snapshot_path,other.resolve())
        with patch.object(a,'save_project') as save:a.new_project();save.assert_not_called()
        self.assertIsNone(a.saved_path);self.assertEqual(a.recent_snapshot_path,other.resolve())
        self.assertFalse(a.save_location_button.instate(['disabled']))
        self.assertIn(str(other.resolve()),a.save_location_text());self.assertIn('当前新工程尚未保存',a.save_location_text())
        with patch('project_session.ui_platform.open_folder') as open_folder:
            a.open_saved_folder();open_folder.assert_called_once_with(other.resolve().parent)

    def test_restore_failure_rolls_back_track_options_and_selection(self):
        a=self.app;p=self.page;other=self.other_project()
        a.load_source(ASSETS/'EmoBlocks-Calm.mmp');a.save_project()
        values=[box.cget('values') for box in a.track_boxes];selected=a.track_var.get()
        payload=a.project_payload();original=p.restore
        def broken(story):original(story);raise RuntimeError('injected restore failure')
        with patch.object(p,'restore',side_effect=broken):
            with self.assertRaisesRegex(ValueError,'恢复失败'):a.load_project(other)
        self.assertEqual([box.cget('values') for box in a.track_boxes],values)
        self.assertEqual(a.track_var.get(),selected);self.assertEqual(a.project_payload(),payload)
        self.assertIn(selected,values[0])

    def test_busy_blocks_switch_save_and_close(self):
        a=self.app;data=a.project_payload();a.busy=True
        try:
            with patch.object(model,'load_project') as load,patch.object(model,'save_project') as save:
                for action in (a.new_project,a.save_project,lambda:a.load_project('unused')):
                    with self.assertRaises(ValueError):action()
                a.open_project();a.close();load.assert_not_called();save.assert_not_called()
            self.assertEqual(data,a.project_payload())
        finally:a.busy=False

    def test_failed_flush_removes_only_new_incomplete_snapshot(self):
        a=self.app;old=a.save_project();content=old.read_bytes();self.page.resize_timeline(1)
        with patch.object(model.os,'fsync',side_effect=OSError('write failed')):
            with self.assertRaisesRegex(ValueError,'保存失败'):a.save_project()
        self.assertEqual([p.resolve() for p in (self.folder/'projects').iterdir()],[old]);self.assertEqual(old.read_bytes(),content)
        self.assertTrue(a.dirty)

    def test_folder_action_routes_through_adapter(self):
        path=self.app.save_project()
        with patch('project_session.ui_platform.open_folder') as open_folder:
            self.app.open_saved_folder();open_folder.assert_called_once_with(path.parent)


if __name__=='__main__':unittest.main()
