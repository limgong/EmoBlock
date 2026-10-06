"""Windows-specific UI defaults."""
import tkinter as tk
import os
from pathlib import Path
NATIVE_CHROME=False
CONTEXT_EVENTS=('<Button-3>',)
EDIT_SHORTCUT_EVENTS=('<Control-z>','<Control-y>')
UNDO_LABEL='Ctrl+Z';REDO_LABEL='Ctrl+Y'
def create_root():return tk.Tk()
def font_family(name):return name
def wheel_units(delta):return -int(delta/120) if abs(delta)>=120 else (-1 if delta>0 else 1 if delta<0 else 0)
def edit_shortcut(event):return 'redo' if str(getattr(event,'keysym','')).lower()=='y' else 'undo'
def setup_window(root,app):
    root.bind('<Control-s>',lambda event:app.safe(app.save_project))
    root.bind('<Control-o>',lambda event:app.safe(app.open_project))

def open_folder(path):
    folder=Path(path).resolve()
    if not folder.is_dir():raise ValueError('快照所在文件夹已移动或不可用。')
    os.startfile(str(folder))

def prepare_process():
    import ctypes
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):pass

def configure_scaling(root):root.tk.call('tk','scaling',1.25)

def taskbar(root):
    import ctypes
    from ctypes import wintypes
    user=ctypes.windll.user32
    user.GetParent.argtypes=[wintypes.HWND];user.GetParent.restype=wintypes.HWND
    user.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int]
    user.SetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_long]
    user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
    hwnd=user.GetParent(root.winfo_id());flags=user.GetWindowLongW(hwnd,-20)
    user.SetWindowLongW(hwnd,-20,(flags|0x40000)&~0x80)
    user.SetWindowPos(hwnd,None,0,0,0,0,0x0037)

def work_area(root):
    import ctypes
    from ctypes import wintypes
    rect=wintypes.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(48,0,ctypes.byref(rect),0):
        return rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top
    return 0,0,root.winfo_screenwidth(),root.winfo_screenheight()
