"""Actual P2 Facade + mapped Tk; device/renderer evidence is separate."""
import copy
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
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
