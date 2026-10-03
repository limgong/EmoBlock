"""Read an unset ttk Combobox consistently across Tcl/Tk versions."""
import tkinter as tk


def selected_index(widget):
    try:
        return widget.current()
    except tk.TclError as exc:
        if str(exc) != 'expected integer but got ""':
            raise
        return -1
