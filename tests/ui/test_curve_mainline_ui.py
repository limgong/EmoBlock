"""Current UI acceptance: real mapped geometry, transactions and intent."""
import copy
from unittest.mock import patch
import tkinter as tk
import curve_workflow
from curve_raster import pixels
from test_curve_ui import MappedUIFixture, fixture

class MainlineUITests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.callback_errors=[]
        self.root.report_callback_exception=lambda *error:self.callback_errors.append(error)
        self.addCleanup(lambda:self.assertEqual(self.callback_errors,[]))

    def use_controller(self):
        self.controller=curve_workflow.Controller(fixture())
        self.app.controller=self.controller;self.app._switched();self.root.update()

    def click(self,widget):
        self.root.update()
        x,y=widget.winfo_width()//2,widget.winfo_height()//2
        self.assertIs(self.root.winfo_containing(widget.winfo_rootx()+x,widget.winfo_rooty()+y),widget)
        widget.event_generate('<ButtonPress-1>',x=x,y=y)
        widget.event_generate('<ButtonRelease-1>',x=x,y=y);self.root.update()

    def test_r8_selected_details_at_minimum_window_keep_canvas_and_native_owner(self):
        self.use_controller()
        self.app.edit('place',material_id='block',start_tick=0)
        ident=self.controller.state()['project']['placements'][0]['id']
        self.app.select_target('placement',ident)
        self.root.geometry(f'{pixels(self.root,1020)}x{pixels(self.root,700)}')
        self.app.source_user_collapsed=True
        before=self.controller.state()
        for theme in ('light','dark'):
            self.app.theme.set(theme);self.app.refresh();self.root.update()
            for expanded in (True,False):
                self.app.details_expanded=expanded
                self.app.show_detail('持久的情绪详情\n'*30);self.app.refresh();self.root.update()
                canvas=self.app.page.timeline.canvas
                self.assertGreaterEqual(canvas.winfo_height(),pixels(self.root,320))
                self.assertEqual(bool(self.app.detail_row.winfo_ismapped()),expanded)
                if expanded:
                    self.assertIs(self.app.detail_row.master,self.app.page.stage_area)
                    self.assertLessEqual(self.app.page.secondary_tools.winfo_height(),pixels(self.root,96))
                self.assertTrue(self.app.stop_button.winfo_ismapped())
                for button in (self.app.play_button,self.app.stop_button,self.app.cancel_button):
                    self.assertGreaterEqual(button.winfo_height(),pixels(self.root,44))
                    self.assertIs(self.root.winfo_containing(button.winfo_rootx()+button.winfo_width()//2,
                        button.winfo_rooty()+button.winfo_height()//2),button)
                self.assertIs(self.root.winfo_containing(canvas.winfo_rootx()+80,canvas.winfo_rooty()+80),canvas)
        self.assertEqual(before,self.controller.state())

    def test_primary_play_pause_controls_current_object_despite_selection_change(self):
        self.app.audition_target('material','block');self.finish_jobs()
        playing=copy.deepcopy(self.app.playing_target)
        self.app.select_target('material','child0')
        self.assertIs(self.app.play_button,self.app.pause_button)
        self.click(self.app.play_button);self.assertEqual(self.app.player.mode,'paused')
        self.assertEqual(self.app.playing_target,playing)
        self.assertEqual(self.app.play_button.icon,'play')
        self.click(self.app.play_button);self.assertEqual(self.app.player.mode,'playing')
        self.assertEqual(self.app.playing_target,playing)
        self.assertEqual(len(self.app.player.calls),1)
        self.app.audition_target('material','child0');self.finish_jobs()
        self.assertEqual(self.app.playing_target['target'],('material','child0'))
        self.assertEqual(len(self.app.player.calls),2)
        self.click(self.app.stop_button);self.assertIsNone(self.app.playing_target)

    def test_natural_end_replays_last_object_unless_selection_changed(self):
        self.app.prepare_target('material','block');self.finish_jobs()
        self.app.select_target('material','child0')
        self.app.play_target('material','block')
        self.app.player.mode='stopped';self.app.update_transport()
        self.click(self.app.play_button)
        self.assertEqual(self.app.playing_target['target'],('material','block'))
        self.assertEqual(len(self.app.player.calls),2)
        self.app.player.mode='stopped';self.app.select_target('material','extra0')
        self.click(self.app.play_button);self.finish_jobs()
        self.assertEqual(self.app.playing_target['target'],('material','extra0'))

    def test_sidebar_icon_toggle_preserves_selection_scroll_and_playback(self):
        self.app.select_target('material','block')
        self.app.audition_selected();self.finish_jobs()
        self.app.page.cards.canvas.yview_moveto(.3)
        before=self.controller.state();target=self.app.selected_target;playing=copy.deepcopy(self.app.playing_target)
        position=self.app.page.cards.canvas.yview()[0]
        self.assertEqual(self.app.collapse_button.icon,'sidebar')
        for _ in range(2):self.click(self.app.collapse_button)
        self.assertEqual(before,self.controller.state());self.assertEqual(target,self.app.selected_target)
        self.assertEqual(playing,self.app.playing_target)
        self.assertAlmostEqual(position,self.app.page.cards.canvas.yview()[0],places=3)
        self.assertFalse(self.app.page.derive_row.winfo_ismapped())
        self.assertFalse(self.app.page.combo_panel.winfo_ismapped())

    def test_right_click_and_keyboard_menu_capture_actual_block_and_do_not_audition(self):
        cards=self.app.page.cards;row=cards.rows['block']
        before=self.controller.state()
        with patch.object(tk.Menu,'tk_popup'):
            row.event_generate('<Button-3>',x=8,y=8);self.root.update()
        self.assertEqual(self.app.selected_target,('material','block'))
        self.assertEqual(before,self.controller.state());self.assertFalse(self.app.player.calls)
        submenu=self.root.nametowidget(cards.context.entrycget(0,'menu'))
        self.app.select_target('material','child0')
        with patch.object(self.app,'derive_selected') as derive:
            submenu.invoke(0)
            derive.assert_called_once_with('block','variant')
        with patch.object(tk.Menu,'tk_popup'):
            row=cards.rows['block'];row.focus_force();self.root.update()
            row.event_generate('<Shift-F10>');self.root.update()
        self.assertFalse(self.app.player.calls)

    def test_arrange_gap_selection_scope_and_blank_are_explicit_and_reversible(self):
        self.use_controller()
        self.app.edit('place',material_id='block',start_tick=1920)
        timeline=self.app.page.timeline;timeline.set_mode('arrange');self.root.update()
        gap=self.app.completion.gaps[0]
        a,t,b,d=timeline.gap_boxes[gap['id']]
        self.click_gap(timeline,(a+b)/2,(t+d)/2)
        self.assertEqual(self.app.completion.selected_gap_id,gap['id'])
        self.assertIn('当前空缺',self.app.page.gap_label.cget('text'))
        before=self.controller.state()['project']
        self.app.mark_selected_blank();self.root.update()
        self.assertTrue(self.controller.state()['project']['blank_regions'])
        self.assertFalse(self.app.player.calls)
        self.app.undo();self.assertEqual(before,self.controller.state()['project'])
        self.app.completion.select_gap(None);self.root.update()
        self.assertIn('全部空缺',timeline.all_gaps_button.cget('text'))

    def click_gap(self,timeline,x,y):
        canvas=timeline.canvas;x=int(x-canvas.canvasx(0));y=int(y)
        canvas.event_generate('<ButtonPress-1>',x=x,y=y)
        canvas.event_generate('<ButtonRelease-1>',x=x,y=y);self.root.update()
