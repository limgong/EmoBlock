"""Small app-local confirmations with the current semantic theme."""
import tkinter as tk
from tkinter import ttk
from curve_theme import font
from curve_raster import pixels


def confirm_combination(app, name, beats):
    root=app.root;previous=root.focus_get();result=False
    window=tk.Toplevel(root)
    window.withdraw();window.title('组合积木');window.transient(root)
    window.resizable(False,False);window.configure(bg=app.theme.colors['panel'])
    body=ttk.Frame(window,style='Curve.Panel.TFrame',padding=pixels(root,20))
    body.pack(fill='both',expand=True)
    ttk.Label(body,text='组合积木',style='Curve.Title.TLabel').pack(anchor='w')
    tk.Label(body,text=name,wraplength=pixels(root,320),justify='left',font=font(12,True),
             bg=app.theme.colors['panel'],fg=app.theme.colors['ink']).pack(anchor='w',pady=(12,4))
    ttk.Label(body,text=f'{beats:g}拍',style='Curve.Muted.TLabel').pack(anchor='w')
    row=ttk.Frame(body,style='Curve.Panel.TFrame');row.pack(fill='x',pady=(16,0))
    def finish(confirmed=False):
        nonlocal result
        result=confirmed;window.destroy()
    ttk.Button(row,text='取消',command=finish,style='Curve.TButton',takefocus=True).pack(side='left')
    accept=ttk.Button(row,text='组合',command=lambda:finish(True),style='Curve.Primary.TButton',takefocus=True)
    accept.pack(side='right')
    window.bind('<Escape>',lambda _:finish())
    window.bind('<Return>',lambda _:finish(True) if window.focus_get()==accept else None)
    window.protocol('WM_DELETE_WINDOW',finish)
    window.update_idletasks()
    width=max(pixels(root,280),window.winfo_reqwidth());height=window.winfo_reqheight()
    window.geometry(f'{width}x{height}+{root.winfo_rootx()+max(0,(root.winfo_width()-width)//2)}+{root.winfo_rooty()+max(0,(root.winfo_height()-height)//2)}')
    window.deiconify();window.grab_set();accept.focus_set()
    root.wait_window(window)
    if previous is not None and previous.winfo_exists():previous.focus_set()
    return result
