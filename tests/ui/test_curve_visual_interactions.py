"""Mapped shared visuals and frozen playback captures; no device/render calls."""
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import curve_project
import curve_workflow
from curve_visuals import stable_number,material_type,note_segments
from curve_playback_ui import same_card
from curve_player_ui import navigate,waveform
from test_curve_ui import MappedUIFixture,fixture


class VisualInteractionTests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.native_scaling=float(self.root.tk.call('tk','scaling'))

    def tearDown(self):
        # Aqua shares scaling across interpreters: restore while Tk still exists,
        # including assertion failures, then perform the standard live teardown.
        try:self.root.tk.call('tk','scaling',self.native_scaling)
        finally:super().tearDown()

    def click(self,widget):
        self.root.update()
        widget.event_generate('<ButtonPress-1>',x=widget.winfo_width()//2,y=widget.winfo_height()//2)
        widget.event_generate('<ButtonRelease-1>',x=widget.winfo_width()//2,y=widget.winfo_height()//2)
        self.root.update()

    def test_native_scaling_125_and_mac_keep_critical_targets_and_scroll_hit(self):
        from curve_raster import pixels
        native=float(self.root.tk.call('tk','scaling'))
        before=copy.deepcopy(self.controller.state())
        for scaling in (1.25,native):
            self.root.tk.call('tk','scaling',scaling)
            for theme in ('light','dark'):
                self.app.theme.set(theme);self.app.refresh();self.root.update()
                self.assertGreaterEqual(pixels(self.root,44),44)
                self.assertGreaterEqual(self.app.play_button.winfo_height(),44)
                self.assertGreaterEqual(self.app.theme_button.winfo_height(),44)
                self.assertGreaterEqual(self.app.page.cards.scrollbar.winfo_width(),12)
        self.root.tk.call('tk','scaling',native)
        self.assertEqual(before,self.controller.state())

    def test_larger_scaling_phrase_controls_and_virtual_last_row_are_contained(self):
        import curve_ui,ui_platform
        from test_curve_ui import FakeController
        self.app.close()
        self.root=ui_platform.create_root();self.root.tk.call('tk','scaling',2.)
        self.controller=FakeController(fixture(200))
        self.app=curve_ui.CurveApplication(self.root,self.controller)
        self.root.geometry('1440x900');self.root.update()
        cards=self.app.page.cards;row=cards.rows['phrase']
        self.assertEqual(row.winfo_height(),cards.CARD_HEIGHT)
        self.assertGreaterEqual(cards.CARD_HEIGHT,144)
        content=row.winfo_children()[0];controls=[w for w in content.winfo_children() if w.winfo_class()=='Frame'][0]
        for button in controls.winfo_children():
            self.assertGreaterEqual(button.winfo_height(),66)
            self.assertLessEqual(button.winfo_y()+button.winfo_height(),content.winfo_height())
        cards.canvas.yview_moveto(1.);self.root.update()
        self.assertIn('extra199',cards.rows)
        last=cards.rows['extra199'];self.assertEqual(last.winfo_height(),cards.CARD_HEIGHT)
        hit=cards.at_root(last.winfo_rootx()+5,last.winfo_rooty()+last.winfo_height()-12)
        self.assertEqual(hit[0],'extra199')
        self.assertLess(len(cards.rows),20)

    def test_icon_focus_keyboard_and_scaled_hit_do_not_select_or_play(self):
        before=copy.deepcopy(self.controller.state());calls=list(self.app.player.calls)
        for theme in ('light','dark'):
            self.app.theme.set(theme);self.app.refresh();self.root.update()
            widget=self.app.theme_button
            self.assertGreaterEqual(widget.winfo_height(),44)
            widget.focus_force();self.root.update()
            self.assertTrue(widget.instate(['focus']))
            self.assertEqual(widget.cget('text'),'深色')
            self.assertTrue(hasattr(widget,'curve_tooltip'))
        old=self.app.theme.name
        self.app.theme_button.event_generate('<Return>');self.root.update()
        self.assertNotEqual(old,self.app.theme.name)
        self.assertEqual(before,self.controller.state());self.assertEqual(calls,self.app.player.calls)

    def test_repeated_hint_reuses_one_tip_and_latest_focus_detail_then_cleans_up(self):
        import tkinter as tk
        from curve_theme import hint
        content=self.app.page.cards.rows['phrase'].winfo_children()[0]
        controls=next(w for w in content.winfo_children() if w.winfo_class()=='Frame')
        button=controls.winfo_children()[0]
        tip=button.curve_tooltip
        bindings={event:button.bind(event) for event in ('<Enter>','<FocusIn>','<Motion>','<Destroy>')}
        persistent=self.app.detail_text.get()
        before=copy.deepcopy(self.controller.state());playing=copy.deepcopy(self.app.playing_target)
        details=[]
        hint(button,lambda:'完整新说明',details.append)
        hint(button,lambda:'最终完整说明',details.append)
        self.assertIs(button.curve_tooltip,tip)
        self.assertEqual(bindings,{event:button.bind(event) for event in bindings})
        button.focus_force();self.root.update()
        self.assertEqual(details,[])
        self.assertEqual(self.app.detail_text.get(),persistent)
        tip.show();self.root.update()
        windows=[w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel)]
        self.assertEqual(windows,[tip.window])
        self.assertEqual(tip.window.winfo_children()[0].cget('text'),'最终完整说明')
        tip.schedule();self.assertIsNotNone(tip.timer)
        pending=tip.timer
        button.destroy();self.root.update()
        self.assertNotIn(pending,self.root.tk.call('after','info'))
        self.assertEqual([w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel)],[])
        self.assertIsNone(tip.timer);self.assertIsNone(tip.window)
        self.assertEqual(self.controller.state(),before)
        self.assertEqual(self.app.playing_target,playing)
        self.assertEqual(details,[])

    def test_exact_note_clipping_rests_single_pitch_and_identity_label(self):
        notes=copy.deepcopy(self.controller._project['materials'][0]['notes'])
        before=copy.deepcopy(notes)
        lines=note_segments((10,20,100,45),notes,1920,1920,3)
        self.assertTrue(lines)
        for a,y,b,_,ident in lines:
            self.assertGreaterEqual(a,11.5);self.assertLessEqual(b,98.5)
            self.assertGreaterEqual(y,21.5);self.assertLessEqual(y,43.5)
        self.assertEqual(notes,before)
        lines=note_segments((0,0,100,20),[notes[0]],0,4080)
        self.assertEqual(lines[0][1],10)
        material=copy.deepcopy(self.controller._project['materials'][0])
        material['label']='名称含数字 999 FULL';self.assertNotIn(material['label'],stable_number(material))
        original=stable_number(material);material['label']='重命名';self.assertEqual(original,stable_number(material))
        material['label']='重命名 · M27';self.assertEqual(stable_number(material),'M27')
        material['generation']={'method':'bridge_phrase'};self.assertEqual(material_type(material),'bridge')
        material['kind']='combination';self.assertEqual(material_type(material),'combination')

    def test_nodes_only_intensity_modes_and_canvas_notes_within_block(self):
        self.app.controller=curve_workflow.Controller(fixture());self.app._switched();self.root.update()
        self.controller=self.app.controller
        self.app.edit('place',material_id='block',start_tick=1920)
        timeline=self.app.page.timeline;c=timeline.canvas;before=copy.deepcopy(self.controller.state())
        for mode in ('arrange','points','trace','arrange'):
            self.click(timeline.mode_buttons[mode]);self.root.update()
            self.assertEqual(bool(c.find_withtag('control-point')),mode in ('points','trace'))
            box=next(iter(timeline.boxes.values()))
            for item in c.find_withtag('placement-note'):
                x,y,z,_=c.coords(item)
                self.assertGreaterEqual(x,box[0]);self.assertLessEqual(z,box[2])
                self.assertGreaterEqual(y,box[1]+30);self.assertLessEqual(y,box[3]-5)
        self.assertEqual(before,self.controller.state())

    def test_one_bar_buttons_use_atomic_refusal_and_one_undo(self):
        controller=curve_workflow.Controller(fixture());self.app.controller=controller;self.app._switched();self.root.update()
        before=controller.state();self.click(self.app.page.plus_button)
        self.assertEqual(controller.state()['project']['grid_count'],before['project']['grid_count']+1)
        controller.undo();self.app.refresh();self.assertEqual(controller.state()['project'],before['project'])
        controller.edit('place',material_id='block',start_tick=13440);self.app.refresh()
        before=controller.state();self.click(self.app.page.minus_button)
        self.assertEqual(before,controller.state());self.assertTrue(self.app.status_error)
        self.assertTrue(self.app.page.plus_button.winfo_ismapped());self.assertFalse(self.app.page.grid_entry.winfo_class()=='TSpinbox')

    def test_detached_drag_gate_ghost_cancel_and_formal_late_refusal(self):
        controller=curve_workflow.Controller(fixture());self.app.controller=controller;self.app._switched();self.root.update()
        cards=self.app.page.cards;material=self.app.resolve('material','block');row=cards.rows['block']
        before=controller.state();start=self.event(row,8,12)
        self.app.begin_material_drag(start,material,row)
        c=self.app.page.timeline.canvas
        point=SimpleNamespace(x_root=c.winfo_rootx()+int(self.app.page.timeline.x(0))+8,y_root=c.winfo_rooty()+130)
        self.app.material_motion(point);self.root.update()
        self.assertTrue(self.app.drag_ghost.winfo_ismapped());self.assertTrue(self.app.page.timeline.preview_state['allowed'])
        self.assertEqual(before,controller.state())
        self.app.cancel_interaction();self.root.update()
        self.assertFalse(self.app.drag_ghost.winfo_ismapped());self.assertIsNone(self.app.page.timeline.preview)
        self.assertEqual(before,controller.state())
        # The preview cannot grant a later commit after another real edit.
        self.assertTrue(self.app.ghost().check('place',material_id='block',start_tick=0)['allowed'])
        controller.edit('place',material_id='block',start_tick=0);self.app.refresh()
        before=controller.state();self.assertFalse(self.app.edit('place',material_id='block',start_tick=0))
        self.assertEqual(before,controller.state())

    def test_transient_scroll_near_drag_idle_keeps_geometry_and_cleans_timer(self):
        cards=self.app.page.cards;bar=cards.scrollbar
        bar.set(0,.2);self.root.update();width=bar.winfo_width()
        bar.hide();self.assertFalse(bar.visible)
        e=SimpleNamespace(x_root=bar.winfo_rootx()+2,y_root=cards.canvas.winfo_rooty()+30)
        bar.near(e);self.assertTrue(bar.visible)
        old=cards.canvas.yview()[0]
        bar.press(SimpleNamespace(x=6,y=10));self.assertTrue(bar.dragging)
        bar.motion(SimpleNamespace(x=6,y=bar.winfo_height()-20));self.root.update()
        self.assertGreaterEqual(cards.canvas.yview()[0],old)
        bar.hide();self.assertTrue(bar.visible)
        bar.release();bar.blur();bar.hide();self.assertFalse(bar.visible)
        self.root.update();self.assertEqual(width,bar.winfo_width());self.assertGreaterEqual(width,12)
        self.assertGreaterEqual(bar.thumb[1],24)
        bar.destroy();self.assertIsNone(bar.timer)

    def test_scrollbar_hide_focus_drag_real_timer_and_destroy_keep_timer_ownership(self):
        bar=self.app.page.cards.scrollbar;before=copy.deepcopy(self.controller.state())
        playing=copy.deepcopy(self.app.playing_target);calls=list(self.app.player.calls)
        registered=set();real_after=bar.after
        def record(ms,func=None,*args):
            ident=real_after(ms,func,*args)
            if func is not None:registered.add(ident)
            return ident
        def pending():return registered.intersection(self.root.tk.call('after','info'))
        with patch.object(bar,'after',side_effect=record):
            bar.reveal();first=bar.timer
            self.assertIn(first,pending())
            bar.hide()
            self.assertIsNone(bar.timer);self.assertFalse(bar.visible)
            self.assertNotIn(first,pending())
            bar.focus_force();self.root.update();self.assertTrue(bar.focused)
            for _ in range(3):
                previous=bar.timer;bar.hide()
                self.assertTrue(bar.visible);self.assertIsNotNone(bar.timer)
                self.assertNotIn(previous,pending());self.assertEqual(pending(),{bar.timer})
            self.app.theme_button.focus_force();self.root.update();bar.hide()
            self.assertFalse(bar.focused);self.assertFalse(pending())
            bar.press(self.event(bar,bar.winfo_width()//2,10));self.root.update()
            self.assertTrue(bar.dragging)
            for _ in range(3):
                previous=bar.timer;bar.hide()
                self.assertTrue(bar.visible);self.assertNotIn(previous,pending())
                self.assertEqual(pending(),{bar.timer})
            bar.release();self.app.theme_button.focus_force();self.root.update();bar.hide()
            self.assertFalse(bar.dragging);self.assertFalse(bar.focused);self.assertFalse(pending())
            # Exercise the actual 900ms Tcl callback, not a shortened/mocked timer.
            bar.leave();timer=bar.timer
            self.assertIn(timer,pending())
            deadline=time.monotonic()+2
            while bar.timer is not None and time.monotonic()<deadline:
                self.root.update();time.sleep(.01)
            self.assertIsNone(bar.timer);self.assertFalse(bar.visible);self.assertFalse(pending())
            bar.focus();bar.hide();self.assertEqual(pending(),{bar.timer})
            bar.destroy()
            self.assertIsNone(bar.timer);self.assertFalse(pending())
        self.assertEqual(before,self.controller.state());self.assertEqual(playing,self.app.playing_target)
        self.assertEqual(calls,self.app.player.calls)

    def test_neutral_capture_bpm_navigation_hash_and_modified_same_id(self):
        self.app.prepare_target('material','block');self.finish_jobs();self.app.play_target('material','block')
        playing=copy.deepcopy(self.app.playing_target);context=playing['context'];before=self.controller.state()
        self.assertEqual(context['bpm'],120);self.assertTrue(context['segments'])
        self.assertTrue(same_card(playing,self.app.resolve('material','block')))
        changed=copy.deepcopy(self.app.resolve('material','block'));changed['notes'][0]['pitch']+=1
        self.assertFalse(same_card(playing,changed))
        self.app.select_target('material','phrase');self.assertEqual(playing,self.app.playing_target)
        self.assertTrue(navigate(self.app,0));self.assertEqual(before,self.controller.state())
        # Mechanical content rejection happens before another player call.
        calls=len(self.app.player.calls);self.wav.write_bytes(self.wav.read_bytes()+b'changed')
        self.app.seek_value.set(.2)
        with self.assertRaises(ValueError):self.app.seek_release()
        self.assertEqual(calls,len(self.app.player.calls));self.assertEqual(before,self.controller.state())

    def test_actual_pcm_waveform_no_autoplay_and_detached_worker(self):
        values,duration=waveform(self.wav)
        self.assertTrue(values);self.assertEqual(max(values),0);self.assertGreater(duration,0)
        self.app.prepare_target('material','block');self.finish_jobs();self.app.play_target('material','block')
        before=self.controller.state();calls=list(self.app.player.calls)
        deadline=time.monotonic()+2
        while self.app.waveform.pending and time.monotonic()<deadline:
            self.root.update();self.app.waveform.drain();time.sleep(.01)
        self.assertFalse(self.app.waveform.pending)
        self.assertTrue(self.app.waveform.find_withtag('pcm-wave'))
        self.assertEqual(before,self.controller.state());self.assertEqual(calls,self.app.player.calls)
        self.app.stop();self.root.update();self.assertFalse(self.app.waveform.find_withtag('pcm-wave'))
        self.assertTrue(self.app.block_selector.instate(['disabled']))
