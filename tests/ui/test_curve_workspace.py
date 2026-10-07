"""Mapped layout checks; these exercise shared widgets, not physical input."""
import unittest
import copy
from unittest.mock import patch
import curve_project
import curve_workflow
from test_curve_ui import MappedUIFixture, FakeController, fixture


class WorkspaceLayoutTests(MappedUIFixture):
    def test_real_selected_placement_and_gap_keep_minimum_canvas_and_direct_memory_errors(self):
        for memory in ('BOUND','PENDING_GAP','PRESERVE_BLANK'):
            controller=curve_workflow.Controller(fixture())
            controller.edit('place',material_id='block',start_tick=0)
            if memory=='BOUND':
                controller.edit('set_intensity',points=[dict(tick=0,level=.2),dict(tick=120,level=.9),dict(tick=15360,level=.2)])
            else:
                controller.edit('set_intensity',points=[dict(tick=0,level=.2),dict(tick=15360,level=.9)])
                if memory=='PRESERVE_BLANK':controller.edit('mark_blank',start_tick=14880,end_tick=15360,reason='test explicit blank')
            self.app.controller=controller;self.app._switched();self.root.update()
            self.assertEqual(controller.state()['memory_info']['state'],memory)
            before=copy.deepcopy(controller.state())
            placement=before['project']['placements'][0]['id']
            gap=self.app.completion.gaps[0]
            for selection in ('placement','gap'):
                self.app.page.timeline.set_mode('arrange' if selection=='placement' else 'gaps')
                if selection=='placement':self.app.select_target('placement',placement)
                else:self.app.completion.select_gap(gap['id'])
                for theme in ('light','dark'):
                    self.app.theme.set(theme);self.app.refresh()
                    self.root.geometry('1020x700')
                    for collapsed in (False,True):
                        self.app.source_user_collapsed=collapsed;self.app.layout_sources();self.root.update()
                        self.assertGreaterEqual(self.app.page.timeline.canvas.winfo_height(),320)
                        for button in (list(self.app.page.emotion_buttons.values()) if selection=='placement' else self.app.page.gap_panel.winfo_children()[1:]):
                            self.assertTrue(button.winfo_ismapped())
                            self.assertGreaterEqual(button.winfo_width(),44);self.assertGreaterEqual(button.winfo_height(),44)
                            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
                        self.assertEqual(bool(self.app.page.memory_label.winfo_ismapped()),memory!='BOUND')
                        if memory=='BOUND':self.assertTrue(self.app.page.timeline.canvas.find_withtag('memory-label'))
                        self.app.tell('受控错误：已有保护仍保留',True);self.root.update()
                        self.assertTrue(self.app.status_label.winfo_ismapped())
                        self.assertIn('已有保护',self.app.status_label.cget('text'))
                        self.assertGreaterEqual(self.app.page.timeline.canvas.winfo_height(),320)
                        self.assertTrue(self.app.stop_button.winfo_ismapped());self.assertGreaterEqual(self.app.stop_button.winfo_height(),44)
                        self.app.tell(self.app.workspace_hint())
            self.assertEqual(before,controller.state())

    def test_empty_workspace_only_import_and_no_recommendation_capture(self):
        self.app.controller=curve_workflow.Controller();self.app._switched();self.root.update()
        before=self.app.controller.state()
        with patch.object(self.app.controller,'capture_recommendations') as capture:
            self.assertFalse(self.app.generate_recommendations())
            self.assertFalse(self.app.recommendation.start())
            self.assertFalse(self.app.recommendation.start(automatic=True))
            capture.assert_not_called()
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for size in ('1020x700','1280x800','1440x900'):
                self.root.geometry(size);self.root.update()
                page=self.app.page
                self.assertTrue(page.timeline.empty_import.winfo_ismapped())
                self.assertTrue(page.empty_workspace.winfo_ismapped())
                self.assertFalse(page.timeline.tools.winfo_ismapped())
                self.assertFalse(page.derive_button.winfo_ismapped())
                self.assertFalse(page.final_button.winfo_ismapped())
                self.assertFalse(page.grid_entry.winfo_ismapped())
                self.assertFalse(page.memory_label.winfo_ismapped())
                self.assertTrue(page.final_button.instate(['disabled']))
                self.assertFalse(self.app.jobs)
        self.assertEqual(before,self.app.controller.state())

    def test_snapshot_without_source_restores_creation_tools_and_truthful_hint(self):
        project=curve_project.new_project()
        material=copy.deepcopy(fixture()['materials'][-1])
        material.update(id='handmade-snapshot',provenance={},phrase_id=None)
        for note in material['notes']:note.update(origin=None,lineage=[],slice=None)
        project['materials']=[material];curve_project.validate(project)
        self.app.controller=FakeController(project);self.app._switched();self.root.update()
        before=self.app.controller.state()
        self.assertFalse(self.app.page.empty_workspace.winfo_ismapped())
        self.assertFalse(self.app.page.timeline.empty_import.winfo_ismapped())
        self.assertTrue(self.app.page.timeline.tools.winfo_ismapped())
        self.assertTrue(self.app.page.derive_button.winfo_ismapped())
        self.assertFalse(self.app.page.derive_button.instate(['disabled']))
        self.assertTrue(self.app.has_generation_input())
        self.assertNotIn('导入旋律，开始创作',self.app.status_label.cget('text'))
        self.assertIn('素材',self.app.status_label.cget('text'))
        self.assertEqual(before,self.app.controller.state())

    def test_two_themes_sizes_source_visibility_and_player_column(self):
        before=self.controller.state()['project']
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for width,height in ((1020,700),(1280,800),(1440,900)):
                self.root.geometry(f'{width}x{height}')
                for collapsed in (False,True):
                    self.app.source_user_collapsed=collapsed;self.app.layout_sources();self.root.update()
                    canvas=self.app.page.timeline.canvas
                    self.assertGreaterEqual(canvas.winfo_height(),320)
                    self.assertEqual(bool(self.app.page.source_panel.winfo_ismapped()),not collapsed)
                    self.assertEqual(self.app.page.middle.winfo_width(),252)
                    for widget in (self.app.play_button,self.app.stop_button,self.app.pause_button):
                        self.assertTrue(widget.winfo_ismapped())
                        self.assertGreaterEqual(widget.winfo_height(),44)
                        self.assertGreaterEqual(widget.winfo_rootx(),self.app.page.right.winfo_rootx())
                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),self.root.winfo_rootx()+width)
                    self.assertEqual(before,self.controller.state()['project'])

    def test_card_geometry_notes_and_real_focus_tooltip(self):
        cards=self.app.page.cards;card=cards.rows['phrase']
        self.assertEqual(card.winfo_height(),96)
        content=card.winfo_children()[0]
        thumbnails=[w for w in content.winfo_children() if w.winfo_class()=='Canvas' and getattr(w,'material_thumbnail',False)]
        self.assertTrue(thumbnails[0].find_all())
        title=content.winfo_children()[0]
        tip=title.curve_tooltip
        title.focus_force();self.root.update();tip.show();self.root.update()
        self.assertTrue(tip.window.winfo_ismapped())
        self.assertIn('完整乐句',tip.window.winfo_children()[0].cget('text'))
        tip.hide();self.root.update();self.assertIsNone(tip.window)

    def test_source_threshold_respects_explicit_choice_and_merged_action_is_single(self):
        self.assertIs(self.app.prepare_button,self.app.play_button)
        before=self.controller.state()['project']
        for width,collapsed in ((1150,True),(1179,True),(1180,False)):
            self.app.source_user_collapsed=None;self.root.geometry(f'{width}x700');self.root.update()
            self.assertEqual(bool(self.app.page.source_panel.winfo_ismapped()),not collapsed)
        self.app.source_user_collapsed=False;self.root.geometry('1020x700');self.root.update()
        self.assertTrue(self.app.page.source_panel.winfo_ismapped())
        self.assertEqual(before,self.controller.state()['project'])
