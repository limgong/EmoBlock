"""Version binding, per-format availability and export-only state changes."""
import copy
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from unified_ui import UnifiedApp
from legacy_story_fixture import restore_legacy
from export_files import FORMATS


class ExportUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.root=tk.Tk();self.root.withdraw();self.app=UnifiedApp(self.root);restore_legacy(self.app);self.page=self.app.story_page
        self.sources={}
        for index in (1,2):
            folder=self.folder/str(index);folder.mkdir()
            for kind,(_,name,_) in FORMATS.items():
                path=folder/name;path.write_bytes(f'version {index} {kind}'.encode());self.sources[index,kind]=path
            self.app.results.append(dict(mode='测试成品',story_fingerprint=self.app.story_fingerprint(self.page.snapshot()),
                report=dict(output_directory=str(folder),duration_seconds=8,bars=4)))
        self.app.refresh_results();self.root.update_idletasks();self.app.saved_signature=self.app.project_signature()

    def tearDown(self):
        self.page.preview_planner.close();self.root.after_cancel(self.app.timer);self.root.destroy();self.temp.cleanup()

    def state(self):
        a=self.app
        return (a.project_signature(),a.dirty,copy.deepcopy(self.page.history),
            a.result_list.curselection(),a.playing_path,a.play_position,a.edit_status_label.cget('text'),self.page.generation_state)

    def test_versions_formats_and_changed_edits_export_exact_snapshot_without_state_changes(self):
        a=self.app;p=self.page
        p.bpm.set(str(int(float(p.bpm.get()))+1));a.update_edit_status()
        self.assertIn('尚未生成',a.edit_status_label.cget('text'))
        for index in (1,2):
            a.select_history(index-1)
            for kind,(label,_,_) in FORMATS.items():
                before=self.state();target=self.folder/f'中文 export V{index}.{kind}'
                with patch('unified_ui.filedialog.asksaveasfilename',return_value=str(target)) as dialog:a.export_result(kind)
                self.assertEqual(target.read_bytes(),self.sources[index,kind].read_bytes());self.assertEqual(self.state(),before)
                self.assertIn(f'V{index:02}',dialog.call_args.kwargs['title']);self.assertIn(label,dialog.call_args.kwargs['title'])
                self.assertEqual(dialog.call_args.kwargs['initialfile'],f'EmoBlocks-V{index:02}.{kind}')
                self.assertIn(f'V{index:02}',a.export_outcome);self.assertIn(str(target),a.export_outcome)
                with patch('ui_platform.open_folder') as opened:a.open_export_folder(a.last_export_path)
                opened.assert_called_once_with(target.resolve().parent)

    def test_cancel_is_silent_and_preserves_state_and_existing_feedback(self):
        a=self.app;a.export_outcome='previous feedback';a.export_status.configure(text='previous feedback')
        a.playing_path='active audio';a.play_position=3.5
        before=self.state();files={p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        with patch('unified_ui.filedialog.asksaveasfilename',return_value=''),patch.object(a,'tell') as tell:a.export_result('wav')
        tell.assert_not_called();self.assertEqual(a.export_outcome,'previous feedback');self.assertEqual(self.state(),before)
        self.assertEqual(files,{p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file()})

    def test_missing_format_and_disappearance_during_dialog_keep_history(self):
        a=self.app;self.sources[2,'wav'].unlink();a.update_result_controls()
        self.assertTrue(a.export_buttons['wav'].instate(['disabled']))
        self.assertTrue(a.export_buttons['mid'].instate(['!disabled']));self.assertTrue(a.export_buttons['mmp'].instate(['!disabled']))
        target=self.folder/'old.mid';target.write_bytes(b'old')
        def dialog(**_):self.sources[2,'mid'].unlink();return str(target)
        before=self.state()
        with patch('unified_ui.filedialog.asksaveasfilename',side_effect=dialog):a.export_result('mid')
        self.assertEqual(target.read_bytes(),b'old');self.assertEqual(self.state(),before)
        self.assertIn('V02 · MIDI 导出失败',a.export_outcome);self.assertTrue(a.export_buttons['mid'].instate(['disabled']))

    def test_nested_dialog_selection_cannot_change_bound_export_or_success_identity(self):
        a=self.app;a.select_history(0);target=self.folder/'bound.wav'
        def dialog(**_):
            a.result_list.selection_clear(0,'end');a.result_list.selection_set(1)
            a.export_result('mid')  # Reentrant command while native dialog pumps events.
            return str(target)
        with patch('unified_ui.filedialog.asksaveasfilename',side_effect=dialog) as dialog_mock:a.export_result('wav')
        self.assertEqual(dialog_mock.call_count,1);self.assertEqual(target.read_bytes(),self.sources[1,'wav'].read_bytes())
        self.assertIn('V01 · WAV 已导出',a.export_outcome);self.assertEqual(a.result_list.curselection(),(1,))

    def test_write_failure_preserves_state_and_prior_destination(self):
        a=self.app;target=self.folder/'existing.wav';target.write_bytes(b'old');before=self.state()
        with patch('unified_ui.filedialog.asksaveasfilename',return_value=str(target)),patch('export_files.os.replace',side_effect=PermissionError('denied')):
            a.export_result('wav')
        self.assertEqual(target.read_bytes(),b'old');self.assertEqual(self.state(),before)
        self.assertIn('可写目录',a.export_outcome);self.assertIsNone(a.last_export_path);self.assertFalse(a.exporting)

    def test_cannot_overwrite_other_version_metadata(self):
        a=self.app;target=self.folder/'1'/'report.json';target.write_bytes(b'original report')
        before=self.state()
        with patch('unified_ui.filedialog.asksaveasfilename',return_value=str(target)):a.export_result('wav')
        self.assertEqual(target.read_bytes(),b'original report');self.assertEqual(self.state(),before)
        self.assertIn('目标是生成源文件',a.export_outcome)
