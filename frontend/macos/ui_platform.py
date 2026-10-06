"""macOS native conventions; all visual modules are shared."""
import tkinter as tk
import subprocess
from pathlib import Path
NATIVE_CHROME=True
CONTEXT_EVENTS=('<Button-2>','<Button-3>','<Control-Button-1>')
EDIT_SHORTCUT_EVENTS=('<Command-z>','<Command-Z>')  # Z also arrives with Caps Lock; Shift decides
UNDO_LABEL='⌘Z';REDO_LABEL='⇧⌘Z'
def create_root():
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk()
    except (ImportError,tk.TclError):return tk.Tk()
def font_family(name):return 'PingFang SC' if 'YaHei' in name else 'Helvetica Neue' if name=='Segoe UI' else name
def wheel_units(delta):return -round(delta) if abs(delta)>=1 else (-1 if delta>0 else 1 if delta<0 else 0)
def edit_shortcut(event):return 'redo' if int(getattr(event,'state',0))&1 else 'undo'
def setup_window(root,app):
    root.bind('<Command-s>',lambda event:app.safe(app.save_project))
    root.bind('<Command-o>',lambda event:app.safe(app.open_project))
    root.createcommand('tk::mac::Quit',app.close)

def prepare_process():return None
def configure_scaling(root):return None
def taskbar(root):return None
def work_area(root):return 0,0,root.winfo_screenwidth(),root.winfo_screenheight()

def open_folder(path):
    folder=Path(path).resolve()
    if not folder.is_dir():raise ValueError('快照所在文件夹已移动或不可用。')
    subprocess.run(['open',str(folder)],check=True)
