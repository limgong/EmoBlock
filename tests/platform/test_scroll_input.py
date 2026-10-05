"""Exercise page and timeline scrolling against real Tk widgets."""
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from unified_ui import UnifiedApp


class ScrollInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = UnifiedApp(cls.root)
        cls.root.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        cls.root.after_cancel(cls.app.timer)
        cls.root.destroy()

    def test_mouse_wheel_moves_story_timeline_horizontally(self):
        line = self.app.story_page.line
        line.xview_moveto(0)
        with patch.object(self.root, 'winfo_containing', return_value=line):
            result = self.app.wheel(SimpleNamespace(x_root=0, y_root=0, delta=-1))
        self.assertEqual(result, 'break')
        self.assertGreater(line.xview()[0], 0)

    def test_touchpad_moves_story_timeline_and_detail_page(self):
        if not self.root.tk.call('info', 'commands', 'tk::PreciseScrollDeltas'):
            self.skipTest('Tk does not support TouchpadScroll')
        line = self.app.story_page.line
        line.xview_moveto(0)
        with patch.object(self.root, 'winfo_containing', return_value=line):
            result = self.app.touchpad_scroll(SimpleNamespace(widget=line, x_root=0, y_root=0, delta=-1 << 16))
        self.assertEqual(result, 'break')
        self.assertGreater(line.xview()[0], 0)

        page = self.app.detail_pages[0]
        page.canvas.configure(scrollregion=(0, 0, 300, 1000))
        page.canvas.yview_moveto(0)
        with patch.object(self.root, 'winfo_containing', return_value=page.body):
            result = self.app.touchpad_scroll(SimpleNamespace(widget=page.body, x_root=0, y_root=0, delta=-30))
        self.assertEqual(result, 'break')
        self.assertGreater(page.canvas.yview()[0], 0)
