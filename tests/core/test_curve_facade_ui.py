"""Actual P2 Facade + mapped Tk; device/renderer evidence is separate."""
import copy
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import curve_project as model
import curve_workflow as workflow
import curve_ui
from runtime_config import ASSETS
from test_curve_ui import FakePlayer, FakeDrop


class IntegratedFacadeUI(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.controller = workflow.Controller()
        with patch.object(curve_ui, 'WavePlayer', FakePlayer), patch.object(curve_ui, 'FileDrop', FakeDrop):
            self.app = curve_ui.CurveApplication(self.root, self.controller)
        self.root.update()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.app.closed = True
        self.root.after_cancel(self.app.timer)
        self.app.cancel_interaction()
        self.app.player.close()
        self.root.destroy()

    def settle(self):
        deadline = time.monotonic() + 5
        while self.app.jobs and time.monotonic() < deadline:
            self.root.update()
            self.app.drain_jobs()
            time.sleep(.005)
        self.assertFalse(self.app.jobs)
        self.root.update()

    def import_real(self):
        self.app.import_file(ASSETS / 'theme-c.mid')
        self.settle()
        self.assertEqual(len(self.controller.project['sources']), 1)
        return next(m for m in self.controller.project['materials'] if m['kind'] == 'block' and m['notes'])

    def test_real_protected_warning_survives_passive_card_events_and_theme_refresh(self):
        material = self.import_real()
        self.app.edit('place', material_id=material['id'], start_tick=0)
        ident = self.controller.project['placements'][0]['id']
        self.app.select_target('placement', ident)
        self.app.set_emotion('hope')
        self.controller.session.mark_saved()
        self.root.geometry('1020x700')
        self.root.update()
        before = copy.deepcopy(self.controller.state())
        selected = self.app.selected_target
        playing = copy.deepcopy(self.app.playing_target)
        for theme in ('light', 'dark'):
            self.app.theme.set(theme)
            self.app.refresh()
            self.root.update()
            self.app.set_emotion('hope')
            warning = self.app.detail_text.get()
            self.assertIn('尚未渲染', warning)
            row = next(iter(self.app.page.cards.rows.values()))
            title = row.winfo_children()[0].winfo_children()[0]
            x, y = title.winfo_width() // 2, title.winfo_height() // 2
            rx, ry = title.winfo_rootx() + x, title.winfo_rooty() + y
            self.assertIs(self.root.winfo_containing(rx, ry), title)
            for event in ('<Motion>', '<Enter>', '<FocusIn>'):
                if event == '<FocusIn>':
                    title.focus_force()
                else:
                    title.event_generate(event, x=x, y=y, rootx=rx, rooty=ry)
                self.root.update()
                self.assertEqual(self.app.detail_text.get(), warning, (theme, event))
            # Exercise the real delayed tooltip callback, with a bounded observation.
            observed = []
            observer = self.root.after(500, lambda: observed.append(True))
            deadline = time.monotonic() + 2
            try:
                while not observed and time.monotonic() < deadline:
                    self.root.update()
                self.assertTrue(observed)
                tip = title.curve_tooltip
                self.assertIsNotNone(tip.window)
                text = tip.text() if callable(tip.text) else tip.text
                self.assertEqual(tip.window.winfo_children()[0].cget('text'), text)
                self.assertEqual(self.app.detail_text.get(), warning)
            finally:
                if not observed:
                    self.root.after_cancel(observer)
                title.curve_tooltip.hide()
            for event in ('<Leave>', '<FocusOut>'):
                title.event_generate(event)
                self.root.update()
                self.assertEqual(self.app.detail_text.get(), warning)
            self.assertIsNone(title.curve_tooltip.timer)
            self.assertIsNone(title.curve_tooltip.window)
            self.assertEqual(self.controller.state(), before)
            self.assertEqual(self.app.selected_target, selected)
            self.assertEqual(self.app.playing_target, playing)
            self.assertEqual(self.app.player.calls, [])

    def test_real_keyboard_hint_preserves_warning_but_explicit_card_selection_updates_details(self):
        material = self.import_real()
        self.app.edit('place', material_id=material['id'], start_tick=0)
        ident = self.controller.project['placements'][0]['id']
        self.app.select_target('placement', ident)
        self.app.set_emotion('hope')
        self.controller.session.mark_saved()
        self.root.update()
        before = copy.deepcopy(self.controller.state())
        warning = self.app.detail_text.get()
        card_id, row = next(iter(self.app.page.cards.rows.items()))
        title = row.winfo_children()[0].winfo_children()[0]
        title.focus_force()
        self.root.update()
        self.assertIs(self.root.focus_get(), title)
        self.assertEqual(self.app.detail_text.get(), warning)
        title.event_generate('<Return>')
        self.root.update()
        self.assertEqual(self.app.selected_target, ('material', card_id))
        expected = self.app.page.cards.describe(self.app.resolve('material', card_id))
        self.assertEqual(self.app.detail_text.get(), expected)
        self.app.select_target('placement', ident)
        self.app.show_detail(warning)
        title = self.app.page.cards.rows[card_id].winfo_children()[0].winfo_children()[0]
        x, y = title.winfo_width() // 2, title.winfo_height() // 2
        rx, ry = title.winfo_rootx() + x, title.winfo_rooty() + y
        self.assertIs(self.root.winfo_containing(rx, ry), title)
        for event in ('<ButtonPress-1>', '<ButtonRelease-1>'):
            title.event_generate(event, x=x, y=y, rootx=rx, rooty=ry)
        self.root.update()
        self.assertEqual(self.app.selected_target, ('material', card_id))
        self.assertEqual(self.app.detail_text.get(), expected)
        self.assertEqual(self.controller.state(), before)
        self.assertIsNone(self.app.playing_target)
        self.assertEqual(self.app.player.calls, [])

    def test_real_import_derive_combo_and_save_reopen_without_implicit_play(self):
        material = self.import_real()
        self.app.select_target('material', material['id'])
        imported = self.controller.project
        self.assertEqual(self.app.player.calls, [])
        self.assertEqual(self.controller.project, imported)
        self.app.page.method.set('回答句')
        self.app.derive_selected()
        self.settle()
        # The import already contains this default answer and its children.
        self.assertEqual(self.controller.project, imported)
        self.assertIn('不同的新旋律', self.app.status_text.get())
        self.app.page.method.set('副旋律规则')
        self.app.derive_selected()
        self.settle()
        self.assertGreater(len(self.controller.project['materials']), len(imported['materials']))
        self.app.undo()
        self.assertEqual(self.controller.project, imported)
        self.app.add_combo(material, material['id'], 'right')
        self.app.cancel_combo()
        self.assertEqual(self.controller.project, imported)
        self.app.add_combo(material, material['id'], 'left')
        self.app.confirm_combo()
        self.settle()
        combo = self.controller.project['materials'][-1]
        self.assertEqual(combo['kind'], 'combination')
        self.assertEqual(combo['length_ticks'], 2 * material['length_ticks'])
        self.assertTrue(self.app.edit('place', material_id=combo['id'], start_tick=13))
        placed = self.controller.project
        self.assertEqual(placed['placements'][0]['start_tick'], 13)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.controller.save_snapshot(Path(tmp) / '中文 snapshot.json')
            reopened = workflow.Controller()
            reopened.load(path)
            self.assertEqual(reopened.project, placed)
            self.assertTrue(reopened.state()['is_saved'])
        self.assertEqual(self.app.player.calls, [])

    def test_cancel_then_late_result_cannot_add_material_or_change_playing(self):
        material = self.import_real()
        before = self.controller.project
        gate = threading.Event()
        original = workflow.prepare_generation
        def delayed(*args, **kwargs):
            gate.wait(3)
            return original(*args, **kwargs)
        self.app.select_target('material', material['id'])
        self.app.page.method.set('回答句')
        with patch.object(workflow, 'prepare_generation', delayed):
            self.app.derive_selected()
            self.assertTrue(self.app.jobs)
            self.app.cancel_jobs()
            gate.set()
            deadline = time.monotonic() + 3
            while self.app.messages.empty() and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.005)
            self.app.drain_jobs()
        self.assertEqual(self.controller.project, before)
        self.assertEqual(self.app.player.calls, [])
        self.assertFalse(self.app.jobs)

    def test_ui_preferences_keep_saved_fingerprint_and_history(self):
        self.import_real()
        self.controller.session.mark_saved()
        before = copy.deepcopy(self.controller.project)
        can_undo = self.controller.state()['can_undo']
        for size in ('1020x700', '1280x800', '1440x900'):
            self.root.geometry(size)
            self.app.theme.set('dark')
            self.app.refresh()
            self.root.update()
            self.app.theme.set('light')
            self.app.refresh()
            self.root.update()
        self.assertEqual(self.controller.project, before)
        self.assertTrue(self.controller.state()['is_saved'])
        self.assertEqual(self.controller.state()['can_undo'], can_undo)
        self.assertEqual(self.app.player.calls, [])

    def canvas_event(self, tick, level):
        timeline = self.app.page.timeline
        canvas = timeline.canvas
        x = round(timeline.x(tick) - canvas.canvasx(0))
        y = round(timeline.y(level) - canvas.canvasy(0))
        return SimpleNamespace(x=x, y=y, x_root=canvas.winfo_rootx()+x,
                               y_root=canvas.winfo_rooty()+y)

    def test_real_trace_service_release_once_undo_and_escape_atomic(self):
        self.import_real()
        self.controller.session.mark_saved()
        original = copy.deepcopy(self.controller.project)
        timeline = self.app.page.timeline
        timeline.set_mode('trace')
        first = self.canvas_event(480, .25)
        peak = self.canvas_event(1200, .9)
        last = self.canvas_event(2000, .4)
        timeline.press(first)
        timeline.motion(peak)
        timeline.motion(last)
        self.assertEqual(self.controller.project, original)
        timeline.release(last)
        edited = self.controller.project
        self.assertNotEqual(edited['intensity_points'], original['intensity_points'])
        self.app.undo()
        self.assertEqual(self.controller.project, original)
        self.assertTrue(self.controller.state()['is_saved'])
        self.assertTrue(self.controller.state()['can_redo'])
        timeline.press(first); timeline.motion(peak)
        timeline.cancel(); timeline.release(peak)
        self.assertEqual(self.controller.project, original)
        self.assertTrue(self.controller.state()['can_redo'])
        self.assertEqual(self.app.player.calls, [])

    def test_real_emotion_buttons_memory_relocation_and_protected_warning(self):
        material = self.import_real()
        self.app.edit('place', material_id=material['id'], start_tick=0)
        ident = self.controller.project['placements'][0]['id']
        self.app.select_target('placement', ident)
        library = copy.deepcopy(self.controller.project['materials'])
        self.app.page.emotion_buttons['hope'].invoke()
        self.root.update()
        placement = self.controller.project['placements'][0]
        self.assertEqual(placement['emotion'], 'hope')
        self.assertFalse(placement['emotion_variant']['generation']['melody_changed'])
        self.assertIn('旋律未改变', self.app.status_text.get())
        self.assertIn('尚未渲染', self.app.detail_text.get())
        self.assertEqual(self.controller.project['materials'], library)
        self.assertTrue(self.app.page.timeline.canvas.find_withtag('memory-range'))
        total = self.controller.project['total_ticks']
        self.app.edit('set_intensity', points=[dict(tick=0,level=.1),
            dict(tick=3000,level=.9),dict(tick=total,level=.1)])
        self.assertEqual(self.controller.state()['memory_info']['state'], 'PENDING_GAP')
        self.assertFalse(self.app.page.timeline.canvas.find_withtag('memory-range'))
        self.app.undo()
        self.assertEqual(self.controller.state()['memory_info']['placement_id'], ident)
        self.assertEqual(self.app.player.calls, [])

    def test_audition_uses_project_snapshot_without_starting_playback(self):
        material = self.import_real()
        self.app.select_target('material', material['id'])
        before = copy.deepcopy(self.controller.project)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'prepared.wav'
            path.write_bytes(b'cache-fixture-not-device-audio')
            asset = dict(wav_path=str(path),body_seconds=8/3,audio_seconds=11/3)
            with patch.object(workflow,'render_audition',return_value=asset) as render:
                self.app.prepare_selected()
                self.settle()
            self.assertEqual(render.call_args.kwargs['bpm'], before['bpm'])
            self.assertEqual(render.call_args.args[0], material)
            self.assertEqual(self.controller.project, before)
            self.assertEqual(self.app.player.calls, [])
