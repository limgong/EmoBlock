"""Mapped native UI acceptance for the processing dock and scene geometry."""
import copy
import tkinter as tk
import time
from types import SimpleNamespace
from unittest.mock import patch
import curve_workflow
from curve_raster import pixels
from curve_visuals import source_badge
from curve_dialogs import confirm_combination
from curve_icons import icon_image
from test_curve_ui import MappedUIFixture,fixture


class ProcessingDockTests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.errors=[]
        self.root.report_callback_exception=lambda *error:self.errors.append(error)
        self.addCleanup(lambda:self.assertEqual(self.errors,[]))
        self.controller=curve_workflow.Controller(fixture())
        self.app.controller=self.controller;self.app._switched()
        self.root.geometry('1020x700');self.root.update()

    def test_original_badge_multiple_sources_and_generated_children(self):
        project=fixture();block=copy.deepcopy(project['materials'][-1])
        self.assertEqual(source_badge(block,project),'原素材·原料1')
        second=copy.deepcopy(project['sources'][0]);second['id']='second-source'
        project['sources'].append(second);block['provenance']['source_id']=second['id']
        self.assertEqual(source_badge(block,project),'原素材·原料2')
        block['generation']={'method':'variant'}
        self.assertEqual(source_badge(block,project),'')
        child=project['materials'][1]
        self.assertEqual(source_badge(child,project),'原素材·原料1')
        project['materials'][0]['generation']={'method':'answer'}
        self.assertEqual(source_badge(child,project),'')
        block['generation']=None;block['provenance']={}
        self.assertEqual(source_badge(block,project),'')
        self.assertIn('missing.mid',self.app.page.cards.describe(self.app.resolve('material','block')))
        row=self.app.page.cards.rows['block'];content=row.winfo_children()[0]
        labels=[w.itemcget(i,'text') for w in content.winfo_children() if isinstance(w,tk.Canvas)
                for i in w.find_withtag('card-type')]
        self.assertTrue(any('原素材·原料1' in label for label in labels))

    def test_single_dock_preserves_scene_scale_and_clips_native_canvas(self):
        self.app.edit('place',material_id='block',start_tick=0)
        ident=self.controller.state()['project']['placements'][0]['id']
        self.app.select_target('placement',ident)
        before=self.controller.state();timeline=self.app.page.timeline
        for theme in ('light','dark'):
            self.app.theme.set(theme)
            for size in ('1020x700','1280x800','1440x900'):
                self.root.geometry(size)
                for collapsed in (False,True):
                    self.app.source_user_collapsed=collapsed;self.app.layout_sources()
                    self.app.drawer_mode=None;self.app.details_expanded=False;self.app.advanced=False
                    self.app.refresh();self.root.update()
                    scene=timeline.scene_height;curve_y=timeline.y(.25)
                    self.assertGreaterEqual(timeline.canvas.winfo_height(),pixels(self.root,320))
                    self.assertGreaterEqual(scene,pixels(self.root,400))
                    for mode in ('details','advanced','plan'):
                        self.app.toggle_drawer(mode);self.root.update()
                        self.assertEqual(timeline.scene_height,scene)
                        self.assertEqual(timeline.y(.25),curve_y)
                        self.assertGreaterEqual(timeline.canvas.winfo_height(),pixels(self.root,240))
                        tools=self.app.page.secondary_tools
                        self.assertLessEqual(tools.winfo_height(),pixels(self.root,220))
                        self.assertEqual(bool(self.app.detail_row.winfo_ismapped()),mode=='details')
                        if tools.winfo_height()>4:
                            x=tools.winfo_rootx()+20;y=tools.winfo_rooty()+10
                            self.assertFalse(timeline.contains_root(x,y))
                            self.assertIsNot(self.root.winfo_containing(x,y),timeline.canvas)
                        self.assertTrue(self.app.stop_button.winfo_ismapped())
                        self.app.toggle_drawer(mode);self.root.update()
                        self.assertIsNone(self.app.drawer_mode)
                        self.assertEqual(timeline.scene_height,scene)
                    self.assertEqual(before,self.controller.state())

    def test_drawer_switch_and_escape_do_not_change_play_or_project(self):
        self.app.audition_target('material','block');self.finish_jobs()
        before=copy.deepcopy((self.controller.state(),self.app.playing_target,self.app.player.calls))
        for mode in ('plan','details','advanced','details'):
            self.app.toggle_drawer(mode);self.root.update()
            self.assertEqual(self.app.details_expanded,mode=='details')
            self.assertEqual(self.app.advanced,mode=='advanced')
        self.app.cancel_interaction(SimpleNamespace());self.root.update()
        self.assertIsNone(self.app.drawer_mode)
        self.assertEqual(before,(self.controller.state(),self.app.playing_target,self.app.player.calls))

    def test_scrolled_root_point_and_control_point_use_scene_height(self):
        timeline=self.app.page.timeline
        self.app.toggle_drawer('advanced');self.root.update()
        timeline.canvas.xview_moveto(.3);timeline.canvas.yview_moveto(1);self.root.update()
        x=timeline.x(7680);y=timeline.y(.1)
        event=self.event(timeline.canvas,x-timeline.canvas.canvasx(0),y-timeline.canvas.canvasy(0))
        point=timeline.root_point(event.x_root,event.y_root)
        self.assertAlmostEqual(point['tick'],7680,delta=15)
        self.assertAlmostEqual(point['level'],.1,delta=.004)
        timeline.set_mode('points');self.root.update()
        timeline.canvas.event_generate('<ButtonPress-1>',x=event.x,y=event.y)
        timeline.canvas.event_generate('<ButtonRelease-1>',x=event.x,y=event.y);self.root.update()
        self.assertTrue(any(abs(p['tick']-7680)<15 and abs(p['level']-.1)<.004
                            for p in self.controller.state()['project']['intensity_points']))

    def test_wheel_shift_and_diagonal_touchpad_route_both_axes(self):
        timeline=self.app.page.timeline;c=timeline.canvas
        self.app.toggle_drawer('advanced');self.root.update()
        c.xview_moveto(.1);c.yview_moveto(0);self.root.update()
        x=c.xview()[0];y=c.yview()[0]
        event=self.event(c,100,100)
        self.assertEqual(self.app.wheel(event),'break')
        self.assertEqual(c.xview()[0],x);self.assertGreater(c.yview()[0],y)
        event.state=1
        self.app.wheel(event);self.assertGreater(c.xview()[0],x)
        c.xview_moveto(.1);c.yview_moveto(.1);self.root.update()
        before=(c.xview()[0],c.yview()[0])
        with patch('curve_ui.touchpad_deltas',return_value=(-12,-12)):
            self.assertEqual(self.app.touchpad(event),'break')
        self.assertGreater(c.xview()[0],before[0]);self.assertGreater(c.yview()[0],before[1])

    def test_drag_body_anchor_placeholder_cancel_and_single_undo(self):
        self.app.edit('place',material_id='block',start_tick=1920)
        timeline=self.app.page.timeline;timeline.set_mode('arrange');self.root.update()
        placement=self.controller.state()['project']['placements'][0]
        a,t,b,d=timeline.boxes[placement['id']]
        start=self.event(timeline.canvas,a+20,t+15)
        before=self.controller.state()['project']
        timeline.press(start);offset=copy.deepcopy(timeline.drag)
        end=SimpleNamespace(x_root=start.x_root+int(1920*timeline.scale),y_root=start.y_root+10)
        timeline.motion(end);self.root.update()
        ghost=self.app.drag_ghost
        self.assertTrue(timeline.canvas.find_withtag('drag-origin'))
        self.assertAlmostEqual(ghost.winfo_rootx(),end.x_root-offset['offset'],delta=1)
        self.assertAlmostEqual(ghost.winfo_rooty(),end.y_root-offset['offset_y'],delta=1)
        self.assertAlmostEqual(ghost.winfo_width(),placement['length_ticks']*timeline.scale,delta=1)
        self.assertEqual(before,self.controller.state()['project'])
        self.app.cancel_interaction(SimpleNamespace());self.root.update()
        self.assertFalse(ghost.winfo_ismapped());self.assertEqual(before,self.controller.state()['project'])
        # A valid release moves exactly once; vertical pointer displacement never edits intensity.
        timeline.press(start);timeline.motion(end);timeline.release(end);self.root.update()
        moved=self.controller.state()['project']
        self.assertEqual(moved['placements'][0]['start_tick'],3840)
        self.assertEqual(moved['intensity_points'],before['intensity_points'])
        self.app.undo();self.assertEqual(before,self.controller.state()['project'])

    def test_edge_scroll_moves_both_axes_and_cancel_retires_timer(self):
        timeline=self.app.page.timeline;c=timeline.canvas
        self.app.toggle_drawer('advanced');self.root.update()
        c.xview_moveto(.2);c.yview_moveto(.1);self.root.update()
        before=(c.xview()[0],c.yview()[0])
        timeline.edge_pointer=(c.winfo_rootx()+c.winfo_width()-1,c.winfo_rooty()+c.winfo_height()-1)
        timeline._edge_step()
        self.assertGreater(c.xview()[0],before[0]);self.assertGreater(c.yview()[0],before[1])
        self.assertIsNotNone(timeline.edge_timer)
        timer=timeline.edge_timer;timeline.cancel()
        self.assertNotIn(timer,self.root.tk.call('after','info'))

    def test_themed_combination_modal_cancel_close_and_accept(self):
        before=self.controller.state()
        for theme,action in (('light','escape'),('dark','close'),('dark','accept')):
            self.app.theme.set(theme)
            def operate():
                window=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='组合积木')
                self.assertEqual(window.cget('bg'),self.app.theme.colors['panel'])
                self.assertIs(window.grab_current(),window)
                body=window.winfo_children()[0];row=body.winfo_children()[-1]
                if action=='accept':row.winfo_children()[-1].invoke()
                elif action=='close':window.tk.call(window.protocol('WM_DELETE_WINDOW'))
                else:window.event_generate('<Escape>')
            self.root.after(80,operate)
            self.assertEqual(confirm_combination(self.app,'A1+A2',8),action=='accept')
            self.assertIsNone(self.root.grab_current())
            self.assertEqual(before,self.controller.state())

    def test_clear_semantic_icons_are_distinct_and_palette_is_blue_white(self):
        self.assertEqual(self.app.theme.colors['accent'],'#2563eb')
        self.assertEqual(self.app.theme.colors['panel'],'#ffffff')
        for first,second in (('play','generate'),('stop','cancel'),('details','advanced')):
            a=icon_image(self.root,first,'#000000','#ffffff')
            b=icon_image(self.root,second,'#000000','#ffffff')
            self.assertNotEqual(a.tk.call(str(a),'data'),b.tk.call(str(b),'data'))
        for button in (self.app.detail_button,self.app.plan_button,self.app.page.advanced_button,self.app.play_button):
            self.assertGreaterEqual(button.winfo_height(),pixels(self.root,44))

    def test_canvas_motion_cannot_replace_selected_details(self):
        self.app.edit('place',material_id='block',start_tick=0)
        ident=self.controller.state()['project']['placements'][0]['id']
        self.app.select_target('placement',ident)
        self.app.show_detail('所选积木的持久情绪详情');self.root.update()
        timeline=self.app.page.timeline
        timeline.hover(self.event(timeline.canvas,timeline.x(0),timeline.y(.25)))
        self.assertEqual(self.app.detail_text.get(),'所选积木的持久情绪详情')

    def test_native_escape_cancels_drag_before_closing_drawer(self):
        self.app.edit('place',material_id='block',start_tick=1920)
        timeline=self.app.page.timeline;timeline.set_mode('arrange');self.root.update()
        placement=self.controller.state()['project']['placements'][0]
        a,t,b,d=timeline.boxes[placement['id']]
        start=self.event(timeline.canvas,a+20,t+15)
        before=self.controller.state()['project']
        timeline.press(start)
        timeline.motion(SimpleNamespace(x_root=start.x_root+35,y_root=start.y_root))
        timeline.canvas.focus_force();self.root.update()
        timeline.canvas.event_generate('<Escape>');self.root.update()
        self.assertIsNone(timeline.drag);self.assertFalse(self.app.drag_ghost.winfo_ismapped())
        self.assertEqual(before,self.controller.state()['project'])

    def test_opening_and_closing_plan_keeps_editing_tools_without_private_preview(self):
        before=self.controller.state()
        self.app.toggle_drawer('plan');self.root.update()
        self.assertIsNone(self.app.private_preview())
        self.assertTrue(self.app.page.timeline.tools.winfo_ismapped())
        self.app.toggle_drawer('plan');self.root.update()
        self.assertTrue(self.app.page.timeline.tools.winfo_ismapped())
        self.assertEqual(before,self.controller.state())

    def test_keyboard_hint_survives_mouse_leave_and_closes_after_focus_out(self):
        row=self.app.page.cards.rows['block'];title=row.winfo_children()[0].winfo_children()[0]
        before=self.controller.state();detail=self.app.detail_text.get()
        title.focus_force();self.root.update()
        tip=title.curve_tooltip
        title.event_generate('<Leave>');self.root.update()
        self.assertIs(self.root.focus_get(),title)
        deadline=time.monotonic()+2
        while tip.window is None and time.monotonic()<deadline:
            self.root.update();time.sleep(.005)
        self.assertIsNotNone(tip.window)
        self.assertEqual(self.app.detail_text.get(),detail)
        self.assertEqual(self.controller.state(),before)
        title.event_generate('<FocusOut>');self.root.update()
        self.assertIsNone(tip.window);self.assertIsNone(tip.timer)
