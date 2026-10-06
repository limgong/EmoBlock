"""Automatic memory follows actual editing, undo, restore and theme switching."""
import copy
from pathlib import Path
import tempfile
import tkinter as tk
import wave
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import intensity_curve
import story_engine as engine
import ui_theme
import ui_platform
from unified_ui import UnifiedApp
from legacy_story_fixture import restore_legacy


class AutomaticMemoryUITests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.app=UnifiedApp(self.root);restore_legacy(self.app)
        self.root.update_idletasks();self.page=self.app.story_page

    def tearDown(self):
        self.page.preview_planner.close();self.root.after_cancel(self.app.timer);self.root.destroy()

    def test_theme_switch_roundtrip_preserves_project_history_and_selection(self):
        p=self.page;before=copy.deepcopy(p.project)
        p.select_palette('hope');p.selected_region=('curve',2)
        for name in ('light','dark','light','dark','light'):
            self.app.set_theme(name);self.root.update_idletasks()
            self.assertEqual(p.line.cget('background'),ui_theme.PALETTES[name]['panel'])
            self.assertEqual(p.canvas.cget('background'),ui_theme.PALETTES[name]['bg'])
            self.assertEqual(p.project,before);self.assertEqual(len(p.history),0)
            self.assertEqual(p.paint_emotion,'hope');self.assertEqual(p.selected_region,('curve',2))
        self.assertEqual(self.app.theme_choice.get(),'B · 浅色')

    def test_icon_button_shows_destination_theme_and_switches_without_editing(self):
        before=copy.deepcopy(self.page.project)
        self.assertEqual(self.app.theme_button.icon,'moon')
        self.app.theme_button.command()
        self.assertEqual(self.app.theme_button.icon,'sun')
        self.assertEqual(ui_theme.current,'dark')
        self.app.theme_button.command()
        self.assertEqual(self.app.theme_button.icon,'moon')
        self.assertEqual(self.page.project,before)

    def test_workspace_uses_fixed_panels_and_borderless_chrome(self):
        self.assertEqual(bool(self.root.overrideredirect()),not ui_platform.NATIVE_CHROME)
        self.assertFalse(self.page.canvas.winfo_manager())
        self.assertFalse(hasattr(self.app.rail_page,'canvas'))
        self.assertEqual(self.page.source_panel.winfo_manager(),'grid')
        self.assertEqual(self.page.editor_panel.winfo_manager(),'grid')
        self.assertEqual(self.app.logo.icon,'blocks')

    def test_source_paging_keeps_card_count_bounded_without_changing_project(self):
        project=self.page.snapshot()
        for i in range(7):
            source=copy.deepcopy(project['sources'][0]);source['id']=f'page-{i}';project['sources'].append(source)
        self.page.restore(project);before=copy.deepcopy(self.page.project)
        columns=getattr(self.page,'source_card_columns',3)
        first=set(self.page.card_play_buttons)
        self.page.page_sources(1)
        self.assertLessEqual(len(self.page.card_play_buttons),columns)
        self.assertNotEqual(set(self.page.card_play_buttons),first)
        self.assertEqual(self.page.project,before)

    def test_source_card_selection_does_not_start_audio(self):
        project=self.page.snapshot();other=copy.deepcopy(project['sources'][0]);other['id']='second-source';other['name']='第二段旋律'
        project['sources'].append(other);self.page.restore(project)
        with patch.object(self.page,'start_source_audio') as start,patch.object(self.page,'toggle_source_play') as toggle:
            self.page.select_source_card(other['id'])
            start.assert_not_called();toggle.assert_not_called()
            self.assertEqual(self.page.sources.selection(),(other['id'],))
            self.page.card_action(other['id'],'play');toggle.assert_called_once()

    def test_generated_version_and_unrendered_edit_are_distinct(self):
        report=dict(output_directory='missing-version',duration_seconds=10,bars=5)
        self.app.add_result(report,'快速成品',story_project=self.page.snapshot())
        self.assertIn('V01',self.app.selected_version_label.cget('text'))
        self.assertIn('首次生成',self.app.selected_version_label.cget('text'))
        self.assertIn('段旋律',self.app.selected_version_label.cget('text'))
        self.assertIn('一致',self.app.edit_status_label.cget('text'))
        self.page.resize_timeline(1)
        self.assertIn('尚未生成',self.app.edit_status_label.cget('text'))

    def test_legacy_quick_result_does_not_claim_story_editor_matches(self):
        report=dict(output_directory='legacy-quick',duration_seconds=10,bars=5)
        self.app.add_result(report,'快速成品')
        self.assertIn('尚未生成',self.app.edit_status_label.cget('text'))
        self.assertNotIn('story_fingerprint',self.app.results[0])

    def test_play_origin_names_source_and_generated_version(self):
        source=self.page.selected_source();self.page.source_audio=dict(id=source['id'],path='source-preview.wav')
        fake=Mock();fake.status.return_value=(1.,'paused')
        with patch.object(self.app,'player',fake):
            self.app.playing_path='source:source-preview.wav';self.app.update_play_origin()
            self.assertIn('已暂停：素材',self.app.play_origin_label.cget('text'))
            self.app.results=[dict(mode='快速成品',report=dict(output_directory='version-one',duration_seconds=10,bars=5))]
            self.app.playing_path='version-one';self.app.update_play_origin()
            self.assertIn('成品 V01',self.app.play_origin_label.cget('text'))

    def test_export_dialog_identifies_selected_version(self):
        with tempfile.TemporaryDirectory() as folder:
            with wave.open(str(Path(folder,'preview.wav')),'wb') as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(1000);output.writeframes(b'\0\0'*1000)
            self.app.results=[dict(mode='快速成品',report=dict(output_directory=folder,duration_seconds=10,bars=5))]
            self.app.refresh_results()
            with patch('unified_ui.filedialog.asksaveasfilename',return_value='') as dialog:
                self.app.export_result('wav')
            self.assertIn('V01',dialog.call_args.kwargs['title'])
            self.assertEqual(dialog.call_args.kwargs['initialfile'],'EmoBlocks-V01.wav')

    def test_scaled_timeline_maps_pointer_to_logical_intensity_height(self):
        self.page.timeline_scale=.65
        event=self.page.timeline_event(SimpleNamespace(x=50,y=93.6,x_root=50,y_root=93.6))
        self.assertAlmostEqual(event.y,144)
        self.assertEqual(event.x,50)

    def test_history_selection_and_keyboard_keep_real_report_identity(self):
        reports=[dict(duration_seconds=i+8,output_directory=f'absent-{i}',bars=4) for i in range(4)]
        self.app.results=[dict(mode='快速成品',report=r) for r in reports]
        self.app.refresh_results()
        self.assertIs(self.app.selected_report(),reports[-1])
        self.app.select_history(0)
        self.assertIs(self.app.selected_report(),reports[0])
        self.app.move_history(1)
        self.assertIs(self.app.selected_report(),reports[1])
        self.assertTrue(any(row[2]==1 for row in self.app.history_rows))
        self.assertEqual(self.app.waveform_values,[])

    def test_transport_pauses_and_resumes_selected_recording(self):
        self.app.results=[dict(mode='快速成品',report=dict(output_directory='selected',duration_seconds=10,bars=5))]
        self.app.refresh_results();self.app.playing_path='selected'
        fake=Mock(opened=True);fake.status.return_value=(2.,'playing')
        with patch.object(self.app,'player',fake):
            self.app.toggle_result_play();fake.pause.assert_called_once()
            self.assertEqual(self.app.transport_play.icon,'play')
            fake.status.return_value=(2.,'paused')
            self.app.toggle_result_play();fake.resume.assert_called_once()
            self.assertEqual(self.app.transport_play.icon,'pause')

    def test_history_scroll_reaches_oldest_without_changing_selected_audio(self):
        app=self.app
        reports=[dict(duration_seconds=8,output_directory=f'missing-{i}',bars=4) for i in range(8)]
        app.results=[dict(mode='快速成品',report=r) for r in reports];app.refresh_results()
        app.scroll_history(SimpleNamespace(delta=-120*20))
        self.assertEqual(app.history_rows[-1][2],0)
        self.assertLessEqual(app.history_rows[-1][1],app.history_extent()[0])
        self.assertIs(app.selected_report(),reports[-1])
        self.assertTrue(app.history_canvas.find_withtag('history-scrollbar'))
        app.hide_history_scroll()
        self.assertFalse(app.history_canvas.find_withtag('history-scrollbar'))
        app.choose_history(SimpleNamespace(x=40,y=70))
        self.assertIs(app.selected_report(),reports[0])
        app.select_history(7)
        self.assertEqual(app.history_offset,0)

    def test_history_thumb_drag_reaches_end(self):
        app=self.app
        app.results=[dict(mode='快速成品',report=dict(duration_seconds=8,output_directory=f'missing-{i}',bars=4)) for i in range(8)]
        app.refresh_results();app.reveal_history_scroll()
        app.history_drag=(0,0)
        app.drag_history(SimpleNamespace(y=1000))
        self.assertEqual(app.history_offset,app.history_extent()[2])
        app.release_history_scroll(SimpleNamespace())
        self.assertIsNone(app.history_drag)

    def test_drag_peak_moves_memory_and_undo_restores(self):
        p=self.page;before=engine.automatic_peak_anchor(p.project)
        index=2;_,x,y=p.intensity_handles[index]
        event=lambda yy:SimpleNamespace(x=x-p.line.canvasx(0),y=yy)
        p.press(event(y));p.motion(event(144));p.release(event(144))
        after=engine.automatic_peak_anchor(p.project)
        self.assertEqual(after['memory_time'],p.project['intensity_points'][index]['time'])
        self.assertEqual(after['level'],1)
        self.assertEqual(p.project['anchors'],[])
        p.undo();self.assertEqual(engine.automatic_peak_anchor(p.project),before)

    def test_source_audio_can_pause_without_any_generated_result(self):
        self.app.results=[];self.app.playing_path='source-preview.wav'
        fake=Mock(opened=True);fake.status.return_value=(1.,'playing')
        with patch.object(self.app,'player',fake),patch.object(self.app,'play') as play:
            self.app.toggle_result_play();fake.pause.assert_called_once()
            fake.status.return_value=(1.,'paused')
            self.app.toggle_result_play();fake.resume.assert_called_once()
            play.assert_not_called()

    def test_playback_marker_tracks_boundaries_without_changing_selection(self):
        app=self.app
        app.results=[dict(mode='快速成品',report=dict(output_directory='track',duration_seconds=40,bars=20))]
        app.refresh_results()
        app.audition_blocks=[dict(start_seconds=i,end_seconds=i+1,emotion='hope') for i in range(40)]
        app.result_block.configure(values=tuple(str(i) for i in range(40)));app.result_block.current(0)
        app.playing_path='track';app.play_position=20.;app.draw_result_tiles()
        self.assertEqual(app.visible_playback_block,20)
        self.assertGreater(app.audition_page,0)
        self.assertTrue(app.audition_tiles.find_withtag('playing-block'))
        self.assertEqual(app.result_block.current(),0)
        app.playing_path='source:another.wav';app.draw_result_tiles()
        self.assertIsNone(app.visible_playback_block)
        self.assertFalse(app.audition_tiles.find_withtag('playing-block'))

    def test_audition_tiles_select_correct_block_on_second_page(self):
        import ui_scale
        app=self.app
        app.audition_blocks=[dict(emotion='hope') for _ in range(40)]
        app.result_block.configure(values=tuple(str(i) for i in range(40)))
        app.result_block.current(0);app.audition_page=1;app.draw_result_tiles()
        x,y,right,bottom,index=app.audition_boxes[0]
        self.assertGreater(index,0)
        with patch.object(app,'play_result_block') as play:
            app.pick_result_tile(SimpleNamespace(x=(x+right)/2,y=(y+bottom)/2*ui_scale.factor))
            self.assertEqual(app.result_block.current(),index);play.assert_called_once()
        self.assertFalse(app.result_block.winfo_manager())

    def test_right_click_cannot_disable_or_create_memory(self):
        p=self.page;before=copy.deepcopy(p.project)
        for time in (0,8.5,17,26):
            p.context_click(SimpleNamespace(x=p.px(time)-p.line.canvasx(0),y=119))
        self.assertEqual(p.project,before);self.assertEqual(len(p.history),0)
        self.assertFalse(p.line.bind('<Double-Button-1>'))

    def test_restore_migrates_manual_markers_and_disabled_flag_without_losing_backup(self):
        p=self.page;legacy=copy.deepcopy(p.project)
        legacy['auto_peak_memory']=False
        legacy['anchors']=[dict(time=8,hold=2,emotion='crisis',level=.6)]
        original=copy.deepcopy(legacy)
        p.restore(legacy)
        self.assertEqual(legacy,original)
        self.assertEqual(p.project['legacy_memory_anchors'],original['anchors'])
        self.assertEqual(p.project['anchors'],[])
        self.assertTrue(p.project['auto_peak_memory'])
        self.assertIsNotNone(engine.automatic_peak_anchor(p.snapshot()))

    def test_tie_uses_earliest_peak_and_bpm_change_retains_auto(self):
        p=self.page;project=p.snapshot()
        for point in project['intensity_points']:point['level']=.8
        p.commit(project)
        self.assertEqual(engine.automatic_peak_anchor(p.project)['memory_time'],1)
        p.bpm.set('100');p.commit(p.snapshot())
        self.assertTrue(p.project['auto_peak_memory'])
        self.assertEqual(engine.automatic_peak_anchor(p.project)['memory_time'],1.2)

    def test_override_at_peak_does_not_remove_memory_or_mutate_saved_edits(self):
        p=self.page;project=p.snapshot()
        project['overrides']=[dict(start=14,end=20,emotion='hope',level=.2,end_level=.8)]
        p.commit(project);before=copy.deepcopy(p.project)
        plan=engine.plan(p.project)
        self.assertEqual(p.project,before)
        self.assertEqual(len(plan['anchors']),1)
        self.assertTrue(plan['anchors'][0]['auto_peak'])
        anchor=engine.automatic_peak_anchor(p.project)
        block=next(b for b in plan['blocks'] if b['start_seconds']==anchor['time'])
        self.assertTrue(block['pinned']);self.assertEqual(block['version'],'original')


if __name__=='__main__':unittest.main()
