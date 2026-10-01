from ui_scale import font as scaled_font
"""Shared native Tk themes: B light is the default, A dark is optional."""
import tkinter as tk
from tkinter import ttk

current = 'light'
PALETTES = {
    'light': dict(bg='#f1f5f9', panel='#ffffff', inset='#f5f6fa', hover='#edf0f7',
                  line='#dbe0ea', ink='#293244', muted='#626d80', accent='#6366f1',
                  onaccent='#ffffff', selected='#e7e7ff', shadow='#d9dfea', memory='#947121'),
    'dark': dict(bg='#1c1c1e', panel='#27272a', inset='#202023', hover='#36363b',
                 line='#414147', ink='#ededf1', muted='#a7a7b2', accent='#97dfba',
                 onaccent='#17281f', selected='#304539', shadow='#141416', memory='#d6b567'),
}
GROUPS = {
    'bg': '#101721',
    'panel': '#192330 #192532 #192a35',
    'inset': '#0c131c #15212c #18242e',
    'hover': '#273648 #3b5268 #243344 #20323d #2c4b4b #263746 #293c45',
    'line': '#334457 #354659 #2e4051 #405a64 #2d3c49 #253345 #1c2b38 #2a3d4c #3b544d',
    'ink': '#edf2f7 #ecf3f8 #eff6fa #ffffff #dbe9ef',
    'muted': '#a4b5c6 #718293 #98afc5 #a3b8c7 #9db7c8 #8ea4b8 #637e92 #759bb8',
    'accent': '#80d9b4 #9ae7c7 #86dcba #a7edd1 #bdebd8 #f1df9a #4c9478',
    'selected': '#203c35 #294438 #183c31',
    'shadow': '#050a10',
    'memory': '#eab970 #f6d477',
}
TOKENS = {value: role for role, values in GROUPS.items() for value in values.split()}
TOKENS.update({'#25644f':'accent', '#225441':'accent', '#2d7158':'accent', '#eefff7':'onaccent'})
TOKENS.update({'#355b60':'selected','#283646':'hover'})


def color(value):
    if value in ('#f4a59d','#f28e89'):
        return '#b42335' if current=='light' else '#f4a59d'
    return PALETTES[current].get(TOKENS.get(value, value), value)


def apply(root, name):
    global current
    if name not in PALETTES:
        raise ValueError('Unknown UI theme')
    old = PALETTES[current]
    current = name
    p = PALETTES[name]
    # Recolor existing native widgets and canvas marks, including hidden editors.
    mapping = {old[key]: value for key, value in p.items()}
    mapping[old['panel']]=p['panel']
    def walk(widget):
        for option in ('background','foreground','activebackground','activeforeground',
                       'highlightbackground','highlightcolor','insertbackground','selectbackground','selectforeground'):
            try:
                value = str(widget.cget(option))
                if value in mapping:
                    new=p['onaccent'] if option in ('foreground','activeforeground') and value==old['onaccent'] else mapping[value]
                    widget.configure(**{option:new})
            except tk.TclError:
                pass
        if isinstance(widget, tk.Canvas):
            for item in widget.find_all():
                for option in ('fill','outline'):
                    try:
                        value = widget.itemcget(item,option)
                        if value in mapping: widget.itemconfigure(item,**{option:mapping[value]})
                    except tk.TclError:
                        pass
        for child in widget.winfo_children(): walk(child)
    walk(root)
    root.configure(background=p['bg'])
    s = ttk.Style(root)
    s.configure('.', background=p['bg'], foreground=p['ink'], font=scaled_font(('Microsoft YaHei UI',10)))
    for style in ('TFrame','TLabel','TCheckbutton','TRadiobutton','TNotebook','TLabelframe'):
        s.configure(style, background=p['bg'], foreground=p['ink'])
    s.configure('Muted.TLabel', foreground=p['muted'])
    s.configure('Panel.TFrame',background=p['panel'])
    s.configure('Panel.TLabel',background=p['panel'],foreground=p['ink'])
    s.configure('PanelMuted.TLabel',background=p['panel'],foreground=p['muted'])
    s.configure('Panel.TCheckbutton',background=p['panel'],foreground=p['ink'])
    s.map('Panel.TCheckbutton',background=[('active',p['panel'])])
    s.configure('TNotebook',borderwidth=0,tabmargins=0,bordercolor=p['bg'],lightcolor=p['bg'],darkcolor=p['bg'])
    s.configure('TNotebook.Tab',borderwidth=0,bordercolor=p['bg'],lightcolor=p['bg'],darkcolor=p['bg'])
    s.layout('Workspace.TNotebook.Tab',[])
    s.configure('Workspace.TNotebook',borderwidth=0,tabmargins=0)
    s.configure('Slim.Horizontal.TProgressbar',thickness=3)
    s.configure('TLabelframe', bordercolor=p['line'])
    s.configure('TLabelframe.Label', background=p['bg'], foreground=p['accent'])
    s.configure('TNotebook.Tab', background=p['panel'], foreground=p['muted'],padding=(14,10))
    s.map('TNotebook.Tab',background=[('selected',p['selected'])],foreground=[('selected',p['accent'])])
    s.configure('Treeview', background=p['panel'],fieldbackground=p['panel'],foreground=p['ink'],bordercolor=p['line'])
    s.configure('Treeview.Heading',background=p['hover'],foreground=p['ink'])
    s.map('Treeview',background=[('selected',p['selected'])],foreground=[('selected',p['ink'])])
    for style in ('TEntry','TSpinbox','TCombobox'):
        s.configure(style,fieldbackground=p['inset'],background=p['inset'],foreground=p['ink'],insertcolor=p['ink'],bordercolor=p['line'],lightcolor=p['line'],darkcolor=p['line'],arrowcolor=p['muted'])
        s.map(style,fieldbackground=[('readonly',p['panel'])],foreground=[('readonly',p['ink']),('disabled',p['muted'])])
    for style in ('TCheckbutton','TRadiobutton'):
        s.map(style,background=[('active',p['hover'])],foreground=[('disabled',p['muted']),('active',p['ink'])])
    for style in ('Horizontal.TScrollbar','Vertical.TScrollbar','Horizontal.TProgressbar','Horizontal.TScale'):
        fill=p['line'] if 'Scrollbar' in style else p['accent']
        s.configure(style,background=fill,troughcolor=p['inset'],bordercolor=p['line'],arrowcolor=p['muted'],lightcolor=p['line'],darkcolor=p['line'])
    root.option_add('*TCombobox*Listbox.background',p['panel'])
    root.option_add('*TCombobox*Listbox.foreground',p['ink'])
    root.option_add('*Menu.background',p['panel'])
    root.option_add('*Menu.foreground',p['ink'])
    root.option_add('*Menu.activeBackground',p['selected'])
    root.option_add('*Menu.activeForeground',p['accent'])
    import card_style
    card_style.install(root,s)
