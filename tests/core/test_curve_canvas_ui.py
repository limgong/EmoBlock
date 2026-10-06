"""Mapped integer coordinates, tick accuracy, scrolling, and atomic rejection."""
import copy
import tkinter as tk
from test_curve_ui import MappedUIFixture
from curve_canvas import snap_tick


class CurveCanvasTests(MappedUIFixture):
    def place(self, start=480):
        self.app.edit('place',material_id='block',start_tick=start)
        self.root.update()
        return self.controller.state()['project']['placements'][-1]['id']

    def test_exact_tick_render_and_half_up_snap(self):
        ident=self.place(1921)
        canvas=self.app.page.timeline
        self.assertIsInstance(canvas.canvas,tk.Canvas)
        self.assertAlmostEqual(canvas.boxes[ident][0],canvas.x(1921))
        self.assertEqual([snap_tick(t) for t in (239,240,719,720)],[0,480,480,960])
        a,t,b,d=canvas.boxes[ident]
        x=int(a-canvas.canvas.canvasx(0)+20);y=int((t+d)/2)
        event=self.event(canvas.canvas,x,y)
        before=copy.deepcopy(self.controller.state()['project'])
        canvas.press(event);canvas.release(event)
        self.assertEqual(before,self.controller.state()['project'])

    def test_mapped_move_after_horizontal_scroll_keeps_curve_and_neighbors(self):
        first=self.place(1920)
        second=self.place(5760)
        canvas=self.app.page.timeline
        canvas.canvas.xview_moveto(.14);self.root.update()
        before=self.controller.state()['project']
        a,t,b,d=canvas.boxes[first]
        x=int(a-canvas.canvas.canvasx(0)+30);y=int((t+d)/2)
        start=self.event(canvas.canvas,x,y)
        finish=self.event(canvas.canvas,x+int(480*canvas.scale),y+20)
        canvas.press(start);canvas.motion(finish);canvas.release(finish)
        after=self.controller.state()['project']
        self.assertEqual(next(p['start_tick'] for p in after['placements'] if p['id']==first),2400)
        self.assertEqual(next(p['start_tick'] for p in after['placements'] if p['id']==second),5760)
        self.assertEqual(before['intensity_points'],after['intensity_points'])

    def test_overlap_bounds_shrink_and_escape_are_atomic(self):
        ident=self.place(480);self.place(3840)
        before=self.controller.state()['project']
        self.assertFalse(self.app.edit('move',placement_id=ident,start_tick=3840))
        self.assertFalse(self.app.edit('move',placement_id=ident,start_tick=-480))
        self.assertFalse(self.app.edit('resize',grid_count=1))
        self.assertEqual(before,self.controller.state()['project'])
        canvas=self.app.page.timeline
        a,t,b,d=canvas.boxes[ident]
        start=self.event(canvas.canvas,int(a+20),int((t+d)/2))
        end=self.event(canvas.canvas,int(a+100),int((t+d)/2))
        canvas.press(start);canvas.motion(end)
        self.assertIsNotNone(canvas.preview)
        canvas.cancel();canvas.release(end)
        self.assertEqual(before,self.controller.state()['project'])

    def test_strength_is_display_only_and_delete_does_not_compact(self):
        first=self.place(480);second=self.place(3840)
        canvas=self.app.page.timeline
        before=self.controller.state()['project']
        empty=self.event(canvas.canvas,canvas.x(0),canvas.y(.8))
        canvas.press(empty);canvas.motion(self.event(canvas.canvas,100,70));canvas.release(empty)
        self.assertEqual(before,self.controller.state()['project'])
        canvas.selected_id=first;canvas.delete_selected()
        after=self.controller.state()['project']
        self.assertEqual(after['placements'][0]['id'],second)
        self.assertEqual(after['placements'][0]['start_tick'],3840)
        self.assertEqual(after['total_ticks'],before['total_ticks'])
