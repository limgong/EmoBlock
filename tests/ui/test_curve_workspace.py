"""Mapped layout checks; these exercise shared widgets, not physical input."""
import unittest
import copy
from types import SimpleNamespace
from unittest.mock import patch
import curve_project
import curve_workflow
from test_curve_ui import MappedUIFixture, FakeController, fixture


class WorkspaceLayoutTests(MappedUIFixture):
    def test_native_creation_views_share_commands_and_hide_inactive_controls(self):
        controller=curve_workflow.Controller(fixture())
        self.app.controller=controller;self.app._switched();self.root.update()
        page=self.app.page;before=controller.state()['project']
        for advanced in (True,False,True,False):
            self.click_at(page.advanced_button)
            self.assertEqual(self.app.advanced,advanced)
            current=page.creation_views[advanced];other=page.creation_views[not advanced]
            self.assertIs(page.creation_row,current['creation_row'])
            self.assertIs(page.creation_row.master,page.stage_area if advanced else page.right)
            self.assertTrue(page.creation_row.winfo_ismapped());self.assertFalse(other['creation_row'].winfo_ismapped())
            self.assertIs(self.app.recommendation.calculate_button,page.final_button)
            for name in ('plus_button','minus_button','final_button'):
                self.assertEqual(current[name].instate(['disabled']),other[name].instate(['disabled']))
                self.assertFalse(set(other[name].state())&{'active','hover','pressed'})
            for view in page.creation_views.values():
                self.assertEqual(str(view['grid_entry'].cget('textvariable')),str(page.grid_count))
            if advanced:page.secondary_tools.reveal(page.plus_button);self.root.update()
            self.click_at(page.plus_button)
            self.assertEqual(controller.state()['project']['grid_count'],before['grid_count']+1)
            controller.undo();self.app.refresh();self.root.update()
            self.assertEqual(controller.state()['project'],before)
        self.assertEqual(self.app.player.calls,[])

    def click_at(self, widget, x=None, y=None):
        self.root.update()
        x=widget.winfo_width()//2 if x is None else int(x)
        y=widget.winfo_height()//2 if y is None else int(y)
        rootx=widget.winfo_rootx()+x;rooty=widget.winfo_rooty()+y
        self.assertIs(self.root.winfo_containing(rootx,rooty),widget)
        for event in ('<Enter>','<Motion>','<ButtonPress-1>','<ButtonRelease-1>'):
            widget.event_generate(event,x=x,y=y,rootx=rootx,rooty=rooty)
        self.root.update()

    def test_advanced_selected_actual_gap_keeps_canvas_and_scroll_reaches_tools(self):
        controller=curve_workflow.Controller(fixture())
        controller.edit('place',material_id='block',start_tick=0)
        self.app.controller=controller;self.app._switched();self.root.update()
        before=copy.deepcopy(controller.state());calls=list(self.app.player.calls)
        self.root.geometry('1020x700');self.root.update()
        self.click_at(self.app.page.advanced_button)
        self.click_at(self.app.page.timeline.mode_buttons['gaps'])
        gap=self.app.completion.gaps[0];timeline=self.app.page.timeline;canvas=timeline.canvas
        total=float(canvas.cget('scrollregion').split()[2])
        canvas.xview_moveto(max(0,gap['start_tick']*timeline.scale/total-.15));self.root.update()
        a,t,b,d=timeline.gap_boxes[gap['id']]
        left=max(a,canvas.canvasx(0)+12);right=min(b,canvas.canvasx(canvas.winfo_width())-12)
        self.assertGreater(right,left)
        self.click_at(canvas,(left+right)/2-canvas.canvasx(0),(t+d)/2)
        self.assertEqual(self.app.completion.selected_gap_id,gap['id'])
        state=(self.app.selected_target,self.app.selected_source_id,self.app.source_filter_id,
               self.app.playing_target,copy.deepcopy(self.app.combo_inputs))
        for theme in ('light','dark'):
            self.app.theme.set(theme);self.app.refresh()
            for size in ('1020x700','1280x800','1440x900'):
                self.root.geometry(size)
                for collapsed in (False,True):
                    with self.subTest(theme=theme,size=size,collapsed=collapsed):
                        self.app.source_user_collapsed=collapsed;self.app.layout_sources();self.root.update()
                        self.assertTrue(self.app.advanced);self.assertTrue(self.app.page.gap_panel.winfo_ismapped())
                        self.assertGreaterEqual(canvas.winfo_height(),320)
                        tools=self.app.page.secondary_tools
                        self.assertLess(tools.canvas.winfo_height(),tools.content.winfo_height())
                        # First and last native controls receive focus through the
                        # real clipped viewport. No invocation changes music here.
                        for widget in (self.app.page.plus_button,timeline.stage_selector,
                                       self.app.completion.start_button):
                            widget.focus_force();self.root.update()
                            self.assertGreaterEqual(widget.winfo_rooty(),tools.canvas.winfo_rooty())
                            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                                 tools.canvas.winfo_rooty()+tools.canvas.winfo_height())
                            self.assertIs(self.root.winfo_containing(widget.winfo_rootx()+widget.winfo_width()//2,
                                                                   widget.winfo_rooty()+widget.winfo_height()//2),widget)
                        tools.canvas.yview_moveto(0);self.root.update();first=tools.canvas.yview()
                        event=SimpleNamespace(x_root=tools.canvas.winfo_rootx()+2,y_root=tools.canvas.winfo_rooty()+2,delta=-120)
                        self.assertEqual(self.app.wheel(event),'break');self.root.update()
                        self.assertGreater(tools.canvas.yview()[0],first[0])
                        tools.canvas.yview_moveto(1);self.root.update()
                        self.assertAlmostEqual(tools.canvas.yview()[1],1,places=2)
                        for widget in (self.app.play_button,self.app.stop_button,self.app.page.gap_panel.winfo_children()[1]):
                            self.assertTrue(widget.winfo_ismapped());self.assertGreaterEqual(widget.winfo_height(),44)
                            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),self.root.winfo_rooty()+self.root.winfo_height())
                        canvas.focus_force();self.root.update()
                        self.assertGreaterEqual(canvas.winfo_height(),320)
                        self.assertEqual(before,controller.state());self.assertEqual(calls,self.app.player.calls)
                        self.assertEqual(state,(self.app.selected_target,self.app.selected_source_id,self.app.source_filter_id,
                                                self.app.playing_target,self.app.combo_inputs))

    def test_advanced_collapse_expand_restores_view_and_length_actions_one_undo(self):
        controller=curve_workflow.Controller(fixture())
        controller.edit('place',material_id='block',start_tick=0)
        self.app.controller=controller;self.app._switched();self.root.geometry('1020x700');self.root.update()
        timeline=self.app.page.timeline
        self.click_at(self.app.page.advanced_button)
        self.app.completion.select_gap(self.app.completion.gaps[0]['id'])
        before=copy.deepcopy(controller.state());gap_id=self.app.completion.selected_gap_id
        timeline.canvas.xview_moveto(.3);self.root.update();scroll=timeline.canvas.xview()
        self.app.page.cards.expanded.add('phrase');self.app.refresh();self.root.update()
        selected=self.app.selected_target;playing=self.app.playing_target;calls=list(self.app.player.calls)
        tools=self.app.page.secondary_tools;tools.canvas.yview_moveto(1);self.root.update()
        secondary_scroll=tools.canvas.yview()
        self.app.toggle_advanced();self.root.update();self.app.toggle_advanced();self.root.update()
        self.assertEqual(secondary_scroll,tools.canvas.yview())
        for _ in range(2):
            tools=self.app.page.secondary_tools
            tools.reveal(self.app.page.advanced_button);self.root.update()
            self.click_at(self.app.page.advanced_button)
            self.assertFalse(self.app.advanced)
            self.assertEqual(str(self.app.page.creation_row.pack_info()['in']),str(self.app.page.right))
            self.click_at(self.app.page.advanced_button)
            self.assertTrue(self.app.advanced)
            self.assertEqual(str(self.app.page.creation_row.pack_info()['in']),str(tools.content))
            self.assertEqual(before,controller.state());self.assertEqual(gap_id,self.app.completion.selected_gap_id)
            self.assertEqual(selected,self.app.selected_target);self.assertEqual(playing,self.app.playing_target)
            self.assertEqual(calls,self.app.player.calls);self.assertIn('phrase',self.app.page.cards.expanded)
            self.assertEqual(scroll,timeline.canvas.xview())
        tools.reveal(self.app.page.plus_button);self.root.update()
        self.click_at(self.app.page.plus_button)
        self.assertEqual(controller.state()['project']['grid_count'],before['project']['grid_count']+1)
        self.assertTrue(controller.undo());self.app.refresh();self.root.update()
        self.assertEqual(controller.state()['project'],before['project'])
        self.assertEqual(playing,self.app.playing_target);self.assertEqual(calls,self.app.player.calls)

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
