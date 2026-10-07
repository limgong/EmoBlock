"""Semantic, static P2 themes, isolated from the legacy editor's styles."""
import tkinter as tk
from tkinter import ttk
import ui_platform

PALETTES = {
    'light': dict(bg='#eef1f5', panel='#fafbfd', inset='#e7ebf1', line='#cbd2de',
                  ink='#252c38', muted='#536074', accent='#245fc4', selected='#e1eafa',
                  shadow='#d7dde7', onaccent='#ffffff', error='#ac2336'),
    'dark': dict(bg='#1c1c1e', panel='#2c2c2e', inset='#3a3a3c', line='#66666a',
                 ink='#f5f5f7', muted='#c4c4cc', accent='#0a84ff', selected='#3a3a3c',
                 shadow='#1c1c1e', onaccent='#ffffff', error='#ffb4bc'),
}
EMOTION_COLORS = dict(calm='#c9ded8', hope='#e9ddba', sad='#ccd6e9',
                      suspense='#dccfe4', crisis='#e9cbd0', resolve='#d4e2c9')
EMOTION_INK = '#25313a'
EMOTION_NAMES = dict(calm='平静', hope='希望', sad='悲伤', suspense='悬念', crisis='危机', resolve='释然')


def font(size=12, bold=False):
    return (ui_platform.font_family('Microsoft YaHei UI'), size, 'bold' if bold else 'normal')


def rounded(canvas, box, fill, outline='', radius=12, tags=()):
    """One static filled shape; a single pixel outline, at most 12px corners."""
    x1, y1, x2, y2 = box
    r = max(0, min(radius, 12, (x2-x1)/2, (y2-y1)/2))
    points = (x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
              x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1)
    return canvas.create_polygon(points, smooth=True, splinesteps=12, fill=fill,
                                 outline=outline, width=1, tags=tags)


class Theme:
    def __init__(self, root, name='light'):
        self.root = root
        self.set(name)

    def set(self, name):
        if name not in PALETTES:
            raise ValueError('未知主题。')
        self.name = name
        self.colors = PALETTES[name]
        p = self.colors
        self.root.configure(bg=p['bg'])
        s = ttk.Style(self.root)
        # Clam supports explicit surfaces on both systems, without native blur.
        s.theme_use('clam')
        for role, surface in (('', 'bg'), ('Panel.', 'panel')):
            for widget in ('TFrame', 'TLabel', 'TCheckbutton'):
                s.configure('Curve.'+role+widget, background=p[surface], foreground=p['ink'], font=font())
        s.configure('Curve.Muted.TLabel', background=p['panel'], foreground=p['muted'], font=font())
        s.configure('Curve.Title.TLabel', background=p['panel'], foreground=p['ink'], font=font(14, True))
        for name_, background in (('Curve.TButton', p['inset']), ('Curve.Primary.TButton', p['accent'])):
            foreground = p['onaccent'] if 'Primary' in name_ else p['ink']
            if name=='dark' and 'Primary' in name_:
                background,foreground = p['inset'],p['ink']
            s.configure(name_, background=background, foreground=foreground, padding=(10,8), width=0,
                        borderwidth=1, bordercolor=p['accent'] if 'Primary' in name_ else p['line'], font=font())
            s.map(name_, background=[('active', background)],
                  foreground=[('disabled', p['muted'])], bordercolor=[('focus', p['accent'])])
        for widget in ('TCombobox', 'TSpinbox', 'TEntry'):
            s.configure('Curve.'+widget, fieldbackground=p['inset'], background=p['panel'],
                        foreground=p['ink'], insertcolor=p['ink'], font=font())
            s.map('Curve.'+widget, fieldbackground=[('readonly',p['inset'])],
                  foreground=[('readonly',p['ink'])])
        s.configure('Curve.Horizontal.TScale', background=p['panel'], troughcolor=p['inset'])
        self.root.option_add('*TCombobox*Listbox.background',p['inset'])
        self.root.option_add('*TCombobox*Listbox.foreground',p['ink'])
        self.root.option_add('*TCombobox*Listbox.selectBackground',p['selected'])
        self.root.option_add('*TCombobox*Listbox.selectForeground',p['ink'])
        self.root.option_add('*TCombobox*Listbox.font',font())


def hint(widget, text, show):
    """Hover and focus share a persistent inline explanation, never a popup."""
    for event in ('<Enter>', '<FocusIn>'):
        widget.bind(event, lambda _, t=text: show(t() if callable(t) else t), add='+')
