"""New control flows on mapped Tk; Facade/provider fixtures are explicitly fake."""
import copy
import threading
import unittest
from unittest.mock import patch
import test_curve_p7_ui as p7
import test_curve_ui as base
import curve_ui


class RecommendationControlTests(p7.RecommendationMappedTests):
    def click(self, widget):
        self.root.update()
        coords=dict(x=8,y=8,rootx=widget.winfo_rootx()+8,rooty=widget.winfo_rooty()+8)
        widget.event_generate('<ButtonPress-1>',**coords)
        widget.event_generate('<ButtonRelease-1>',**coords);self.root.update()

    def mode_fixture(self):
        self.rec.mode.set('情绪编配');self.rec.mode_changed()
        self.mode_gate=threading.Event()
        self.mode_outcome=dict(candidate_id='candidate-A',mode='arranged',final_score={},comparison_score={},
            assets={k:self.controller.asset('candidate-A',k,'arranged') for k in ('comparison','final')},error=None)

    def test_cold_mode_audition_binds_side_and_plays_only_after_ack(self):
        self.ready();self.select();self.mode_fixture();before=self.controller.state()['project']
        self.click(self.rec.comparison_button)
        self.assertTrue(self.app.jobs);self.assertEqual(self.app.player.calls,[])
        self.mode_gate.set();self.finish_jobs()
        self.assertEqual(self.app.playing_target['target'],('recommendation','candidate-A','arranged','comparison'))
        self.assertEqual(self.controller.assets_called[-1],('candidate-A','comparison','arranged'))
        self.assertEqual(before,self.controller.state()['project'])
        self.assertEqual(len(self.app.player.calls),1)

    def test_stop_and_changed_mode_do_not_autoplay_late_asset_pair(self):
        for action in ('stop','mode'):
            with self.subTest(action=action):
                self.rec.mode.set('中性单旋律');self.ready();self.select();self.mode_fixture()
                self.click(self.rec.final_button)
                if action=='stop':self.click(self.app.stop_button)
                else:self.rec.mode.set('中性单旋律');self.rec.mode_changed()
                self.mode_gate.set();self.finish_jobs()
                self.assertEqual(self.app.player.calls,[])
                self.assertEqual(self.controller.rec['candidates'][0]['modes']['arranged']['status'],'AUDITION_READY')

    def test_back_no_apply_advanced_preserves_preview_draft_selection_and_scroll(self):
        self.ready();self.select();self.root.update()
        self.app.combo_inputs=[copy.deepcopy(self.controller._project['materials'][0])]
        draft=copy.deepcopy(self.app.combo_inputs);preview=copy.deepcopy(self.rec.preview)
        self.app.page.timeline.canvas.xview_moveto(.2)
        scroll=self.app.page.timeline.canvas.xview()[0];before=self.music_state()
        self.app.show_curve_stage('Bridge');self.root.update()
        self.assertIsNone(self.rec.preview);self.assertEqual(self.app.combo_inputs,draft)
        self.app.show_curve_stage('完整建议');self.root.update()
        self.assertEqual(self.rec.preview,preview);self.assertEqual(self.app.combo_inputs,draft)
        self.assertAlmostEqual(self.app.page.timeline.canvas.xview()[0],scroll,places=2)
        self.click(self.rec.back_button)
        self.assertIsNone(self.rec.preview);self.assertEqual(before,self.music_state())
        self.assertFalse(self.rec.visible)
        self.assertEqual(self.app.workspace_stage,'编辑')
        self.assertTrue(self.app.page.timeline.tools.winfo_ismapped())
        self.rec.show()
        self.select();self.click(self.rec.confirm_button)
        calls=[c for c in self.controller.calls if c[0]=='apply-recommendation']
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][1][2],self.controller.confirmations[-1])
        self.assertFalse(self.rec.visible);self.assertTrue(self.app.page.timeline.tools.winfo_ismapped())
        self.assertTrue(self.app.editable);self.assertEqual(self.app.workspace_stage,'编辑')
        self.rec.show();self.select();self.root.update()
        self.assertIsNotNone(self.rec.preview);self.assertTrue(self.rec.panel.winfo_ismapped())
        # This fixture checks the exact once-only public transaction call.
        # Actual undo/save authentication is exercised by the real-Facade probe.

    def test_mapped_return_restores_selected_edit_actions_and_retains_candidates_cache(self):
        self.app.edit('resize',grid_count=8)
        self.ready();canvas=self.app.page.timeline
        self.app.combo_inputs=[copy.deepcopy(self.controller._project['materials'][0])]
        asset=dict(wav_path=str(self.wav),midi_path=str(self.wav),mmp_path=str(self.wav),
                   renderer_version=self.app.audition_profile(),body_seconds=1.,audio_seconds=1.)
        self.app._cache_asset('retained-audition',asset)
        self.app.start_playback(asset,('fixture','playing'),'已明确试听对象')
        for mode in ('arrange','points','trace'):
            for selected in ('placement','gap'):
                with self.subTest(mode=mode,selected=selected):
                    self.rec.show();self.rec.exit_preview();self.root.update()
                    self.click(canvas.mode_buttons[mode])
                    if selected=='placement':
                        self.app.completion.select_gap(None)
                        self.app.select_target('placement',self.controller._project['placements'][-1]['id'])
                    else:
                        self.assertTrue(self.app.completion.gaps)
                        self.app.completion.select_gap(self.app.completion.gaps[0]['id'])
                    self.app.refresh();self.root.update()
                    before=self.music_state();draft=copy.deepcopy(self.app.combo_inputs)
                    cache=copy.deepcopy(self.app.ready_assets)
                    cache_identity=copy.deepcopy(self.app.ready_file_digests)
                    self.rec.show();self.select();self.root.update()
                    candidates=copy.deepcopy(self.rec.state['candidates'])
                    self.assertFalse(canvas.tools.winfo_ismapped())
                    self.click(self.rec.back_button)

                    self.assertTrue(self.app.editable);self.assertFalse(self.rec.visible)
                    self.assertFalse(self.rec.panel.winfo_ismapped());self.assertIsNone(self.rec.preview)
                    self.assertEqual(canvas.mode,mode)
                    for name in ('arrange','points','trace'):
                        self.assertTrue(canvas.mode_buttons[name].winfo_ismapped())
                        self.assertFalse(canvas.mode_buttons[name].instate(['disabled']))
                    self.assertEqual(bool(self.app.page.emotion_panel.winfo_ismapped()),selected=='placement')
                    self.assertEqual(bool(self.app.page.gap_panel.winfo_ismapped()),selected=='gap')
                    self.assertEqual(before,self.music_state());self.assertEqual(draft,self.app.combo_inputs)
                    self.assertEqual(cache,self.app.ready_assets);self.assertEqual(candidates,self.rec.state['candidates'])
                    self.assertEqual(cache_identity,self.app.ready_file_digests)
                    self.assertEqual(self.rec.selected_id,candidates[0]['id'])
                    self.rec.show();self.select();self.root.update()
                    self.assertIsNotNone(self.rec.preview);self.assertTrue(self.rec.panel.winfo_ismapped())
                    self.assertFalse(canvas.tools.winfo_ismapped())
                    self.assertEqual(before,self.music_state())
                    self.click(self.rec.back_button)

    def test_mapped_failed_apply_preserves_readonly_review(self):
        self.ready();self.select();self.root.update()
        before=self.music_state();preview=copy.deepcopy(self.rec.preview)
        with patch.object(self.controller,'apply_recommendation',side_effect=ValueError('APPLY_REJECTED')):
            self.click(self.rec.confirm_button)
        self.assertTrue(self.rec.visible);self.assertTrue(self.rec.panel.winfo_ismapped())
        self.assertFalse(self.app.page.timeline.tools.winfo_ismapped());self.assertFalse(self.app.editable)
        self.assertEqual(self.rec.preview,preview);self.assertEqual(before,self.music_state())
        self.assertIn('APPLY_REJECTED',self.app.status_text.get())

    def test_review_minimum_canvas_and_readonly_controls_both_themes(self):
        self.ready();self.select()
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for size in ('1020x700','1280x800','1440x900'):
                self.root.geometry(size)
                for collapsed in (False,True):
                    self.app.source_user_collapsed=collapsed;self.app.layout_sources();self.root.update()
                    self.assertGreaterEqual(self.app.page.timeline.canvas.winfo_height(),320)
                    self.assertFalse(self.app.page.timeline.tools.winfo_ismapped())
                    self.app.toggle_details();self.root.update()
                    self.assertGreaterEqual(self.app.page.timeline.canvas.winfo_height(),320)
                    self.assertTrue(self.app.detail_label.winfo_ismapped())
                    self.app.toggle_details();self.root.update()
                    for button in (self.rec.confirm_button,self.rec.back_button,self.rec.final_button,self.app.stop_button):
                        self.assertTrue(button.winfo_ismapped());self.assertGreaterEqual(button.winfo_height(),44)
                        self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())

    def test_stale_suspended_preview_cannot_restore_foreign_selection(self):
        self.ready();self.select();self.app.page.timeline.selected_id='place:0'
        self.app.show_curve_stage('Bridge')
        self.controller.rec['status']='STALE'
        self.app.show_curve_stage('完整建议');self.root.update()
        self.assertIsNone(self.rec.preview)
        self.assertIsNone(self.app.page.timeline.selected_id)
        self.assertFalse(self.app.page.timeline.readonly)
        self.assertEqual(self.controller.state()['project'],self.app.page.timeline.project)


class SourceControlTests(base.MappedUIFixture):
    def test_handmade_note_origin_none_source_filter_and_clear_do_not_change_music(self):
        project=base.fixture()
        handmade=copy.deepcopy(project['materials'][-1]);handmade.update(id='hand',label='手工素材',provenance={})
        for note in handmade['notes']:note['origin']=None
        project['materials'].append(handmade)
        self.app.controller=base.FakeController(project);self.controller=self.app.controller;self.app.refresh()
        before=self.controller.state()
        self.app.page.source_list.selection_set(0)
        self.app.page.source_list.event_generate('<<ListboxSelect>>');self.root.update()
        self.assertNotIn('hand',{m['id'] for m in self.app.page.cards.materials})
        self.assertTrue(self.app.material_from_source(project['materials'][0],'source'))
        self.app.filter_source(None);self.root.update()
        self.assertIn('hand',{m['id'] for m in self.app.page.cards.materials})
        self.assertEqual(before,self.controller.state());self.assertEqual(self.app.player.calls,[])

    def test_arrange_click_cannot_edit_intensity_and_drop_changes_mode_only(self):
        canvas=self.app.page.timeline;canvas.set_mode('arrange');before=self.controller.state()['project']
        event=self.event(canvas.canvas,canvas.x(960),canvas.y(.7))
        canvas.canvas.event_generate('<ButtonPress-1>',x=event.x,y=event.y)
        canvas.canvas.event_generate('<ButtonRelease-1>',x=event.x,y=event.y);self.root.update()
        self.assertIsNone(canvas.intensity_draft);self.assertEqual(before,self.controller.state()['project'])
        canvas.set_mode('trace');row=self.app.page.cards.rows['block']
        self.app.begin_material_drag(self.event(row,18,20),self.app.resolve('material','block'),row)
        end=self.event(row,canvas.canvas.winfo_rootx()+canvas.x(480)+18-row.winfo_rootx(),canvas.canvas.winfo_rooty()+canvas.y(.4)-row.winfo_rooty())
        self.app.material_motion(end);self.app.material_release(end);self.root.update()
        self.assertEqual(canvas.mode,'arrange')
        self.assertEqual(self.controller.state()['project']['intensity_points'],before['intensity_points'])


def load_tests(loader, tests, pattern):
    suite=unittest.TestSuite()
    for cls in (RecommendationControlTests,SourceControlTests):
        for name in cls.__dict__:
            if name.startswith('test_'):suite.addTest(cls(name))
    return suite
