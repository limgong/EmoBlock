"""Paired teardown contracts; Windows callbacks here are simulated, not hardware."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]


def adapter(platform):
    spec = importlib.util.spec_from_file_location('close_' + platform, ROOT / 'frontend' / platform / 'file_drop.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mac = adapter('macos')
win = adapter('windows')


class FileDropCloseTests(unittest.TestCase):
    def mac_drop(self, error=None, platform='aqua'):
        drop = object.__new__(mac.FileDrop)
        drop.root = Mock()
        drop.root.tk.call.return_value = platform
        drop.root.tk.splitlist.return_value = ('source with spaces.mid',)
        drop.root.drop_target_unregister.side_effect = error
        drop.callback = Mock()
        drop.binding = 'drop-callback'
        drop.closed = False
        return drop

    def test_aqua_unimplemented_unregister_closes_logical_target_and_rejects_late_drop(self):
        drop = self.mac_drop(tk.TclError('todo'))
        self.assertEqual(drop.drop(SimpleNamespace(data='input')), 'copy')
        drop.callback.assert_called_once_with(['source with spaces.mid'])
        drop.callback.reset_mock()
        drop.close()
        drop.close()
        self.assertTrue(drop.closed)
        drop.root.drop_target_unregister.assert_called_once()
        self.assertEqual([c.args for c in drop.root.unbind.call_args_list],
                         [('<<Drop>>', 'drop-callback'), ('<<DropTargetTypes>>',)])
        drop.root.tk.splitlist.reset_mock()
        self.assertEqual(drop.drop(SimpleNamespace(data='late input')), 'refuse_drop')
        drop.callback.assert_not_called()
        drop.root.tk.splitlist.assert_not_called()

    def test_supported_unregister_keeps_original_contract(self):
        drop = self.mac_drop()
        drop.close()
        drop.close()
        drop.root.drop_target_unregister.assert_called_once()
        drop.root.unbind.assert_called_once_with('<<Drop>>', 'drop-callback')

    def test_unknown_errors_and_non_aqua_todo_are_not_hidden(self):
        for platform, message in (('aqua', 'other unregister error'), ('x11', 'todo')):
            with self.subTest(platform=platform, message=message):
                drop = self.mac_drop(tk.TclError(message), platform)
                with self.assertRaisesRegex(tk.TclError, message):drop.close()
                drop.root.unbind.assert_called_once_with('<<Drop>>', 'drop-callback')

    def test_windows_queued_drop_is_rejected_after_close_and_handle_released(self):
        drop = object.__new__(win.FileDrop)
        drop.root = Mock()
        drop.callback = Mock()
        drop.shell = Mock()
        drop.user = Mock()
        drop.setter = Mock()
        drop.hwnd, drop.old, drop.closed = 123, 456, False
        path = 'source with spaces.mid'
        def query(handle, index, buffer, length):
            if index == 0xffffffff:return 1
            if buffer is None:return len(path)
            buffer.value = path
            return len(path)
        drop.shell.DragQueryFileW.side_effect = query
        self.assertEqual(drop.dispatch(123, 0x233, 789, 0), 0)
        queued = drop.root.after.call_args.args[1]
        drop.shell.DragFinish.assert_called_once_with(789)
        drop.close()
        drop.close()
        queued()
        drop.callback.assert_not_called()
        drop.shell.DragAcceptFiles.assert_called_once_with(123, False)
        drop.setter.assert_called_once_with(123, -4, 456)

    def test_windows_live_queued_drop_is_delivered(self):
        drop = object.__new__(win.FileDrop)
        drop.root = Mock()
        drop.callback = Mock()
        drop.shell = Mock()
        drop.user = Mock()
        drop.closed = False
        drop.shell.DragQueryFileW.return_value = 0
        self.assertEqual(drop.dispatch(1, 0x233, 2, 0), 0)
        drop.root.after.call_args.args[1]()
        drop.callback.assert_called_once_with([])
        drop.shell.DragFinish.assert_called_once_with(2)
