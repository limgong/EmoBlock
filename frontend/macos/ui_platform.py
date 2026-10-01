"""macOS native conventions; all visual modules are shared."""
import tkinter as tk
NATIVE_CHROME=True
CONTEXT_EVENTS=('<Button-2>','<Button-3>','<Control-Button-1>')
def create_root():
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk()
    except (ImportError,tk.TclError):return tk.Tk()
def font_family(name):return 'PingFang SC' if 'YaHei' in name else 'Helvetica Neue' if name=='Segoe UI' else name
def wheel_units(delta):return -round(delta) if abs(delta)>=1 else (-1 if delta>0 else 1 if delta<0 else 0)
def setup_window(root,app):
    root.bind('<Command-s>',lambda event:app.safe(app.save_project))
    root.bind('<Command-o>',lambda event:app.safe(app.open_project))
    root.bind('<Command-z>',lambda event:app.safe(app.story_page.undo))
    root.createcommand('tk::mac::Quit',app.close)

def prepare_process():return None
def configure_scaling(root):return None
def taskbar(root):return None
def work_area(root):return 0,0,root.winfo_screenwidth(),root.winfo_screenheight()
