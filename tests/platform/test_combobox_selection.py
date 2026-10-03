import tkinter as tk
import unittest
from combobox_selection import selected_index


class ComboboxSelectionTests(unittest.TestCase):
    def test_unselected_combobox_is_minus_one_on_all_tk_versions(self):
        class EmptyCombobox:
            def current(self):
                raise tk.TclError('expected integer but got ""')
        self.assertEqual(selected_index(EmptyCombobox()), -1)

    def test_other_tk_errors_are_not_hidden(self):
        class BrokenCombobox:
            def current(self):
                raise tk.TclError('widget has been destroyed')
        with self.assertRaisesRegex(tk.TclError, 'destroyed'):
            selected_index(BrokenCombobox())

    def test_existing_selection_is_preserved(self):
        class SelectedCombobox:
            def current(self):
                return 2
        self.assertEqual(selected_index(SelectedCombobox()), 2)
