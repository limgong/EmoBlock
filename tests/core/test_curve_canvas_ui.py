"""Mapped integer coordinates, tick accuracy, scrolling, and atomic rejection."""
import copy
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import ui_platform
from test_curve_ui import MappedUIFixture
from curve_canvas import snap_tick


class CurveCanvasTests(MappedUIFixture):
    def place(self, start=480):
        self.app.edit('place',material_id='block',start_tick=start)
        self.root.update()
        return self.controller.state()['project']['placements'][-1]['id']

    def canvas_key(self, sequence):
        canvas = self.app.page.timeline.canvas
        canvas.focus_force()
        self.root.update()
        self.assertEqual(self.root.focus_get(), canvas)
        canvas.event_generate(sequence, state=0)
        canvas.event_generate(sequence.replace('<','<KeyRelease-'), state=0)
        self.root.update()

    def test_native_delete_keys_delete_selected_once_and_undo_restores_saved_content(self):
        first = self.place(480); second = self.place(3840)
        canvas = self.app.page.timeline
        before = copy.deepcopy(self.controller.state()['project'])
        import curve_project as model
        self.controller._saved = model.fingerprint(before)
        self.app.refresh()
        for sequence in ui_platform.DELETE_SHORTCUT_EVENTS:
            with self.subTest(sequence=sequence):
                self.root.update()  # Read settled mapped geometry after undo/selection layout changes.
                a,t,b,d = canvas.boxes[first]
                click = self.event(canvas.canvas, int(a+20), int((t+d)/2))
                self.assertTrue(canvas.contains_root(click.x_root,click.y_root))
                canvas.press(click); canvas.release(click)
                undo_count = len(self.controller._undo)
                self.canvas_key(sequence)
                after = self.controller.state()
                self.assertEqual([p['id'] for p in after['project']['placements']], [second])
                self.assertEqual(after['project']['placements'][0]['start_tick'], 3840)
                self.assertEqual(after['project']['intensity_points'], before['intensity_points'])
                self.assertEqual(after['project']['total_ticks'], before['total_ticks'])
                self.assertFalse(after['is_saved'])
                self.assertEqual(len(self.controller._undo), undo_count+1)
                self.app.undo()
                self.assertEqual(self.controller.state()['project'], before)
                self.assertTrue(self.controller.state()['is_saved'])

    def test_backspace_in_text_inputs_does_not_delete_selected_block(self):
        ident = self.place()
        self.app.page.timeline.selected_id = ident
        before = copy.deepcopy(self.controller.state())
        for widget_type in (tk.Entry, ttk.Entry, tk.Text):
            with self.subTest(widget=widget_type):
                widget = widget_type(self.root)
                widget.place(x=20,y=60,width=180,height=50)
                if isinstance(widget, tk.Text):
                    widget.insert('1.0', 'AB'); widget.mark_set('insert', '1.2')
                else:
                    widget.insert(0, 'AB'); widget.icursor('end')
                widget.focus_force(); self.root.update()
                self.assertTrue(widget.winfo_viewable())
                self.assertEqual(self.root.focus_get(), widget)
                # Some themes select the input on focus; test an explicit caret.
                if isinstance(widget, tk.Text):
                    widget.tag_remove('sel', '1.0', 'end'); widget.mark_set('insert', '1.2')
                else:
                    widget.selection_clear(); widget.icursor('end')
                widget.event_generate('<BackSpace>', state=0)
                widget.event_generate('<KeyRelease-BackSpace>', state=0)
                self.root.update()
                content = widget.get('1.0','end-1c') if isinstance(widget, tk.Text) else widget.get()
                self.assertEqual(content, 'A')
                self.assertEqual(self.controller.state(), before)
                widget.destroy()

    def test_delete_keys_keep_busy_and_readonly_projects_intact(self):
        ident = self.place()
        canvas = self.app.page.timeline
        canvas.selected_id = ident
        before = copy.deepcopy(self.controller.state())
        for sequence in ui_platform.DELETE_SHORTCUT_EVENTS:
            with self.subTest(sequence=sequence, mode='busy'):
                with patch.object(self.app, 'jobs', {'busy': {}}):
                    self.canvas_key(sequence)
                self.assertEqual(self.controller.state(), before)
            with self.subTest(sequence=sequence, mode='readonly-preview'):
                canvas.set_project(before['project'], readonly=True)
                self.canvas_key(sequence)
                self.assertEqual(self.controller.state(), before)
                canvas.set_project(before['project'])

    def test_delete_key_rejected_by_protection_preserves_project_and_history(self):
        ident = self.place()
        canvas = self.app.page.timeline
        canvas.selected_id = ident
        before = copy.deepcopy(self.controller.state())
        for sequence in ui_platform.DELETE_SHORTCUT_EVENTS:
            with self.subTest(sequence=sequence):
                with patch.object(self.controller, 'edit', side_effect=ValueError('保护范围不能删除')) as edit:
                    self.canvas_key(sequence)
                    edit.assert_called_once_with('delete', placement_id=ident)
                self.assertEqual(self.controller.state(), before)
                self.assertEqual(canvas.selected_id, ident)

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
