"""Semantic, static P2 themes, isolated from the legacy editor's styles."""
import tkinter as tk
from tkinter import ttk, font as tkfont
import ui_platform

PALETTES = {
    'light': dict(bg='#f1f5f9', panel='#ffffff', inset='#f6f9fd', line='#dbe0ea',
                  ink='#293244', muted='#626d80', accent='#2563eb', selected='#e7f0ff',
                  shadow='#d9dfea', onaccent='#ffffff', error='#ac2336'),
    'dark': dict(bg='#1c1c1e', panel='#2c2c2e', inset='#3a3a3c', line='#66666a',
                 ink='#f5f5f7', muted='#c4c4cc', accent='#0a84ff', selected='#3a3a3c',
                 shadow='#1c1c1e', onaccent='#ffffff', error='#ffb4bc'),
}
EMOTION_COLORS = dict(calm='#c9ded8', hope='#e9ddba', sad='#ccd6e9',
                      suspense='#dccfe4', crisis='#e9cbd0', resolve='#d4e2c9')
EMOTION_INK = '#25313a'
EMOTION_NAMES = dict(calm='平静／安定', hope='温暖／希望', sad='悲伤／失落',
                     suspense='悬疑／不安', crisis='紧张／危机', resolve='振奋／坚定')


def font(size=12, bold=False):
    return (ui_platform.font_family('Microsoft YaHei UI'), size, 'bold' if bold else 'normal')


def title_font(root, size=14):
    available=set(tkfont.families(root))
    family=next((f for f in ('Songti SC','Noto Serif CJK SC','SimSun','STSong','Georgia') if f in available),font()[0])
    return (family,size,'bold')


def rounded(canvas, box, fill, outline='', radius=12, tags=()):
    """One static filled shape; a single pixel outline, at most 12px corners."""
    x1, y1, x2, y2 = box
    r = max(0, min(radius, 12, (x2-x1)/2, (y2-y1)/2))
    points = (x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
              x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1)
    return canvas.create_polygon(points, smooth=True, splinesteps=12, fill=fill,
                                 outline=outline, width=1, tags=tags)


def install_surfaces(root, style, palette, name):
    """Native scalable image elements, with one real soft shadow in light."""
    from curve_raster import surface_image, pixels
    cache=getattr(root,'curve_surface_images',{})
    resource=name+str(pixels(root,44))
    if resource not in cache:
        images=[]
        for role in ('Button','Primary','Header'):
            states=[surface_image(root,palette,role,state) for state in
                    ('normal','active','pressed','focus','disabled','selected')]
            element='CurveSurface'+role+resource
            style.element_create(element,'image',states[0],('disabled',states[4]),('pressed',states[2]),
                                 ('focus',states[3]),('selected',states[5]),('active',states[1]),border=pixels(root,11),width=pixels(root,44),height=pixels(root,44),sticky='nsew')
            images.extend(states)
        small=[image.subsample(2) for image in images[:6]]
        style.element_create('CurveSurfaceSmall'+resource,'image',small[0],('disabled',small[4]),('pressed',small[2]),('focus',small[3]),('selected',small[5]),('active',small[1]),border=pixels(root,1),sticky='nsew')
        images.extend(small)
        cache[resource]=images;root.curve_surface_images=cache
    from curve_raster import transport_surface
    transport_key='Transport'+resource
    if transport_key not in cache:
        images=[transport_surface(root,palette,state) for state in ('normal','active','pressed','focus','disabled')]
        style.element_create(transport_key,'image',images[0],('disabled',images[4]),('pressed',images[2]),('focus',images[3]),('active',images[1]),width=pixels(root,44),height=pixels(root,44),sticky='nsew')
        cache[transport_key]=images
    style.layout('Curve.Transport.TButton',[(transport_key,dict(sticky='nsew',children=[('Button.label',dict(sticky='nsew'))]))])
    style.configure('Curve.Transport.TButton',borderwidth=0,relief='flat',padding=0)
    for suffix,role in (('TButton','Button'),('Primary.TButton','Primary'),('Header.TButton','Header'),
                        ('Compact.TButton','Button'),('Small.TButton','Small'),('TMenubutton','Button')):
        label='Menubutton.label' if suffix=='TMenubutton' else 'Button.label'
        style.layout('Curve.'+suffix,[('CurveSurface'+role+resource,dict(sticky='nsew',children=[
            ('Button.padding',dict(sticky='nsew',children=[(label,dict(sticky='nsew'))]))]))])
        style.configure('Curve.'+suffix,borderwidth=0,relief='flat')


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
        s.configure('Curve.Title.TLabel', background=p['panel'], foreground=p['ink'], font=title_font(self.root))
        s.configure('Curve.Brand.TLabel',background=p['bg'],foreground=p['ink'],font=title_font(self.root,16))
        for name_, background in (('Curve.TButton', p['inset']), ('Curve.Primary.TButton', p['accent'])):
            foreground = p['onaccent'] if 'Primary' in name_ else p['ink']
            if name=='dark' and 'Primary' in name_:
                background,foreground = p['inset'],p['ink']
            s.configure(name_, background=background, foreground=foreground, padding=(5,0), width=0,
                        borderwidth=1, bordercolor=p['accent'] if 'Primary' in name_ else p['line'], font=font())
            s.map(name_, background=[('active', background)],
                  foreground=[('disabled', p['muted'])], bordercolor=[('focus', p['accent'])])
        for style_,padding,size in (('Curve.Compact.TButton',(3,1),11),('Curve.Small.TButton',(5,0),10)):
            s.configure(style_,background=p['inset'],foreground=p['ink'],borderwidth=1,bordercolor=p['line'],
                        padding=padding,font=font(size),width=0)
            s.map(style_,foreground=[('disabled',p['muted'])],bordercolor=[('focus',p['accent'])])
        s.configure('Curve.TMenubutton',background=p['inset'],foreground=p['ink'],padding=(10,8),font=font(),borderwidth=1,width=0)
        for axis in ('Horizontal','Vertical'):
            s.configure('Curve.'+axis+'.TScrollbar',background=p['inset'],troughcolor=p['panel'],
                        borderwidth=0,arrowsize=12,arrowcolor=p['muted'],lightcolor=p['line'],darkcolor=p['line'])
            s.map('Curve.'+axis+'.TScrollbar',background=[('active',p['selected'])])
        self.root.option_add('*Menu.background',p['inset'])
        self.root.option_add('*Menu.foreground',p['ink'])
        self.root.option_add('*Menu.activeBackground',p['selected'])
        self.root.option_add('*Menu.activeForeground',p['ink'])
        self.root.option_add('*Menu.font',font())
        for style_ in ('Curve.TButton','Curve.Primary.TButton','Curve.Compact.TButton','Curve.Small.TButton','Curve.TMenubutton',
                       'Curve.TCombobox','Curve.TSpinbox','Curve.TEntry','Curve.Horizontal.TScale',
                       'Curve.Horizontal.TScrollbar','Curve.Vertical.TScrollbar'):
            s.configure(style_,lightcolor=p['line'],darkcolor=p['line'],relief='solid',borderwidth=1,
                        arrowcolor=p['ink'],bordercolor=p['accent'] if style_=='Curve.Primary.TButton' else p['line'])
            s.map(style_,lightcolor=[('focus',p['accent']),('active',p['line'])],
                  darkcolor=[('focus',p['accent']),('active',p['line'])],
                  relief=[('pressed','solid'),('active','solid')])
            s.map(style_,background=[('disabled',p['inset']),('active',p['accent'] if style_=='Curve.Primary.TButton' and name=='light' else p['inset'])],foreground=[('disabled',p['muted'])])
        for widget in ('TCombobox', 'TSpinbox', 'TEntry'):
            s.configure('Curve.'+widget, fieldbackground=p['inset'], background=p['panel'],
                        foreground=p['ink'], insertcolor=p['ink'], font=font())
            s.map('Curve.'+widget, fieldbackground=[('disabled',p['inset']),('readonly',p['inset'])],
                  foreground=[('disabled',p['muted']),('readonly',p['ink'])])
        s.configure('Curve.Horizontal.TScale', background=p['panel'], troughcolor=p['inset'])
        self.root.option_add('*TCombobox*Listbox.background',p['inset'])
        self.root.option_add('*TCombobox*Listbox.foreground',p['ink'])
        self.root.option_add('*TCombobox*Listbox.selectBackground',p['selected'])
        self.root.option_add('*TCombobox*Listbox.selectForeground',p['ink'])
        self.root.option_add('*TCombobox*Listbox.font',font())
        s.configure('Curve.Header.TButton',background=p['bg'],foreground=p['ink'],padding=0,font=font())
        install_surfaces(self.root,s,p,name)
        for bar in getattr(self.root,'curve_scrollbars',()):bar.draw()
        for button in tuple(getattr(self.root,'curve_icon_buttons',())):
            if button.winfo_exists():button.refresh_icon()


class Tooltip:
    """A nonmodal hover/focus tip. Details remain available explicitly inline."""
    def __init__(self, widget, text):
        self.widget,self.text=widget,text
        self.timer=self.window=None
        self.hovered=self.focused=False
        for event in ('<Enter>','<FocusIn>'):widget.bind(event,self.schedule,add='+')
        for event in ('<Leave>','<FocusOut>'):widget.bind(event,self.depart,add='+')
        for event in ('<ButtonPress>','<Destroy>'):widget.bind(event,self.hide,add='+')

    def schedule(self,event=None):
        if event is not None:
            if event.type==tk.EventType.Enter:self.hovered=True  # Enter
            elif event.type==tk.EventType.FocusIn:self.focused=True  # FocusIn
        self.hide()
        self.timer=self.widget.after(450,self.show)

    def depart(self,event):
        if event.type==tk.EventType.Leave:self.hovered=False  # Leave
        elif event.type==tk.EventType.FocusOut:self.focused=False  # FocusOut
        if not self.hovered and not self.focused:self.hide()

    def show(self):
        self.hide()
        if not self.widget.winfo_exists() or not self.widget.winfo_ismapped():return
        text=self.text() if callable(self.text) else self.text
        if not text:return
        root=self.widget.winfo_toplevel()
        self.window=tk.Toplevel(root)
        self.window.overrideredirect(True)
        # Palette is read at display time, so a theme switch cannot leave an old tip.
        style=ttk.Style(root)
        background=style.lookup('Curve.Panel.TLabel','background')
        foreground=style.lookup('Curve.Panel.TLabel','foreground')
        tk.Label(self.window,text=text,justify='left',wraplength=340,padx=10,pady=8,
                 bg=background,fg=foreground,font=font(),borderwidth=1,relief='solid').pack()
        self.position()

    def position(self):
        root=self.widget.winfo_toplevel()
        self.window.update_idletasks()
        x=min(self.widget.winfo_rootx(),root.winfo_screenwidth()-self.window.winfo_reqwidth()-8)
        y=min(self.widget.winfo_rooty()+self.widget.winfo_height()+4,root.winfo_screenheight()-self.window.winfo_reqheight()-8)
        self.window.geometry(f'+{max(0,x)}+{max(0,y)}')

    def refresh(self):
        """Update a visible tip without stealing focus or restarting its delay."""
        if self.window is None:return
        text=self.text() if callable(self.text) else self.text
        if not text:self.hide();return
        style=ttk.Style(self.widget.winfo_toplevel())
        self.window.winfo_children()[0].configure(text=text,
            bg=style.lookup('Curve.Panel.TLabel','background'),
            fg=style.lookup('Curve.Panel.TLabel','foreground'),font=font())
        self.position()

    def hide(self,event=None):
        if self.timer is not None:
            self.widget.after_cancel(self.timer);self.timer=None
        if self.window is not None:
            self.window.destroy();self.window=None


def hint(widget, text, show):
    existing=getattr(widget,'curve_tooltip',None)
    if existing is not None:
        existing.text=text
        existing.show_detail=show
        existing.refresh()
        return existing
    tooltip=widget.curve_tooltip=Tooltip(widget,text)
    tooltip.show_detail=show
    # Passive hover/focus belongs to the transient tooltip only.
    # Persistent details are written by explicit selection/action handlers.
    return tooltip
