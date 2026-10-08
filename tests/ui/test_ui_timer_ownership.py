"""Real Tcl timers remain owned through early hide/show and widget teardown."""
import copy
import tkinter as tk
from types import SimpleNamespace
import unittest

import test_automatic_memory_ui as legacy_fixture
from ui_hints import Tooltip


class TimerOwnershipTests(unittest.TestCase):
    def setUp(self):
        legacy_fixture.AutomaticMemoryUITests.setUp(self)

    def tearDown(self):
        legacy_fixture.AutomaticMemoryUITests.tearDown(self)

    def registered(self):
        return set(self.root.tk.call('after', 'info'))

    def wait_for_timer(self, milliseconds):
        done = tk.BooleanVar(self.root, False)
        timer = self.root.after(milliseconds, lambda: done.set(True))
        try:
            self.root.wait_variable(done)
        finally:
            if timer in self.registered():
                self.root.after_cancel(timer)

    def scroll(self):
        self.app.results = [dict(mode='fixture', report=dict(
            duration_seconds=8, output_directory=f'missing-{i}', bars=4)) for i in range(8)]
        self.app.refresh_results()
        self.app.scroll_history(SimpleNamespace(delta=-2400))
        return self.app.history_scroll_timer

    def test_public_scroll_early_hide_retires_timer_before_destroy(self):
        timer = self.scroll()
        before = (copy.deepcopy(self.page.project), self.app.selected_report(), self.app.playing_path)
        command = self.root.tk.splitlist(self.root.tk.call('after', 'info', timer))[0]
        self.assertIn(timer, self.registered())
        try:
            self.app.hide_history_scroll()
            self.assertIsNone(self.app.history_scroll_timer)
            self.assertNotIn(timer, self.registered())
            self.assertFalse(self.app.history_canvas.find_withtag('history-scrollbar'))
            self.assertEqual(before, (self.page.project, self.app.selected_report(), self.app.playing_path))
            self.app.history_canvas.destroy()
            self.assertNotIn(timer, self.registered())
            self.assertFalse(self.root.tk.call('info', 'commands', command))
        finally:
            if timer in self.registered():
                self.app.history_canvas.after_cancel(timer)

    def test_drag_repeated_hide_retains_one_timer_and_real_timeout_retires_it(self):
        first = self.scroll()
        self.app.history_drag = (0, 0)
        try:
            self.app.hide_history_scroll()
            second = self.app.history_scroll_timer
            self.assertNotEqual(first, second)
            self.assertNotIn(first, self.registered())
            self.app.hide_history_scroll()
            third = self.app.history_scroll_timer
            self.assertNotIn(second, self.registered())
            self.assertIn(third, self.registered())
            self.assertTrue(self.app.history_scroll_visible)
            self.app.release_history_scroll(SimpleNamespace())
            released = self.app.history_scroll_timer
            self.assertNotIn(third, self.registered())
            self.wait_for_timer(1000)
            self.assertNotIn(released, self.registered())
            self.assertIsNone(self.app.history_scroll_timer)
            self.assertFalse(self.app.history_scroll_visible)
        finally:
            for timer in (first, locals().get('second'), locals().get('third')):
                if timer in self.registered():
                    self.app.history_canvas.after_cancel(timer)

    def test_tooltip_early_show_and_destroy_retire_pending_callback(self):
        button = tk.Button(self.root, text='Named control')
        button.pack()
        tip = Tooltip(button, 'Full explanatory text')
        tip.schedule(SimpleNamespace(x_root=10, y_root=10))
        timer = tip.timer
        command = self.root.tk.splitlist(self.root.tk.call('after', 'info', timer))[0]
        try:
            tip.show()
            self.assertIsNone(tip.timer)
            self.assertNotIn(timer, self.registered())
            popup = tip.popup
            self.assertTrue(popup.winfo_exists())
            button.destroy()
            self.assertIsNone(tip.popup)
            self.assertNotIn(timer, self.registered())
            self.assertFalse(self.root.tk.call('info', 'commands', command))
        finally:
            tip.hide()
            if timer in self.registered():
                button.after_cancel(timer)

    def test_tooltip_timer_show_hide_and_focused_destroy_are_idempotent(self):
        button = tk.Button(self.root, text='Named control')
        button.pack()
        self.root.deiconify(); self.root.update()
        button.focus_force(); self.root.update()
        self.assertEqual(self.root.focus_get(), button)
        tip = Tooltip(button, 'Focus detail')
        tip.schedule(SimpleNamespace(x_root=button.winfo_rootx(), y_root=button.winfo_rooty()))
        timer = tip.timer
        self.wait_for_timer(600)
        self.assertNotIn(timer, self.registered())
        self.assertIsNone(tip.timer)
        self.assertTrue(tip.popup.winfo_exists())
        tip.hide(); tip.hide()
        self.assertIsNone(tip.popup)
        tip.schedule(SimpleNamespace(x_root=10, y_root=10))
        timer = tip.timer
        button.destroy()
        self.assertIsNone(tip.timer)
        self.assertNotIn(timer, self.registered())
