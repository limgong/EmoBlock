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
    def click(self,widget):
        self.root.update()
        widget.event_generate('<ButtonPress-1>',x=widget.winfo_width()//2,y=widget.winfo_height()//2)
        widget.event_generate('<ButtonRelease-1>',x=widget.winfo_width()//2,y=widget.winfo_height()//2)
        self.root.update()

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
        bar.press(SimpleNamespace(x=6,y=10));self.assertTrue(bar.dragging)
        bar.hide();self.assertTrue(bar.visible)
        bar.release();bar.blur();bar.hide();self.assertFalse(bar.visible)
        self.root.update();self.assertEqual(width,bar.winfo_width());self.assertGreaterEqual(width,12)
        self.assertGreaterEqual(bar.thumb[1],24)
        bar.destroy();self.assertIsNone(bar.timer)

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
