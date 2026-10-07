"""Mapped layout checks; these exercise shared widgets, not physical input."""
import unittest
import copy
from unittest.mock import patch
import curve_project
import curve_workflow
from test_curve_ui import MappedUIFixture, FakeController, fixture


class WorkspaceLayoutTests(MappedUIFixture):
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
        thumbnails=[w for w in content.winfo_children() if w.winfo_class()=='Canvas']
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
