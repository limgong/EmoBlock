from ui_scale import font as scaled_font
"""Scalable rounded ttk button backgrounds, generated as native Tk UI assets."""
import tkinter as tk
import ui_theme


def install(root,style):
    name=ui_theme.current;p=ui_theme.PALETTES[name]
    cache=getattr(root,'_theme_button_cache',{})
    if name in cache:
        _layouts(style,name,p)
        return
    images=[]
    def tile(fill,border,size=24,radius=8,background=None):
        image=tk.PhotoImage(master=root,width=size,height=size)
        image.put(background or p['bg'],to=(0,0,size,size))
        for y in range(size):
            dy=max(0,radius-y,y-(size-radius-1));inset=round(radius-(max(0,radius*radius-dy*dy)**.5)) if dy else 0
            image.put(border,to=(inset,y,size-inset,y+1))
            if 0<y<size-1:image.put(fill,to=(max(1,inset+1),y,size-1-max(0,inset),y+1))
        images.append(image);return image
    for element,fill,hover,background in [('CardButton',p['panel'],p['hover'],p['bg']),('AccentCard',p['accent'],p['accent'],p['bg']),
                                        ('PanelButton',p['panel'],p['hover'],p['panel']),('PanelAccent',p['accent'],p['accent'],p['panel'])]:
        normal=tile(fill,p['line'],background=background);active=tile(hover,p['accent'],background=background)
        pressed=tile(fill,p['accent'],background=background);disabled=tile(p['inset'],p['line'],background=background)
        style.element_create(element+name,'image',normal,('disabled',disabled),('pressed',pressed),('active',active),('focus',active),border=9,sticky='nsew')
    small=tile(p['panel'],p['line'],12,3);small_active=tile(p['hover'],p['accent'],12,3)
    style.element_create('CompactCard'+name,'image',small,('active',small_active),('pressed',small_active),border=3,sticky='nsew')
    cache[name]=images;root._theme_button_cache=cache
    _layouts(style,name,p)


def _layouts(style,name,p):
    def layout(element,label='Button.label'):
        return [(element,dict(sticky='nsew',children=[('Button.padding',dict(sticky='nsew',children=[(label,dict(sticky='nsew'))]))]))]
    style.layout('TButton',layout('CardButton'+name))
    style.layout('Quiet.TButton',[('Button.padding',dict(sticky='nsew',children=[('Button.label',dict(sticky='nsew'))]))])
    style.configure('Quiet.TButton',background=p['bg'],padding=(8,6))
    style.configure('PanelQuiet.TButton',background=p['panel'],padding=(6,4))
    style.layout('PanelQuiet.TButton',style.layout('Quiet.TButton'))
    style.layout('Accent.TButton',layout('AccentCard'+name))
    style.layout('Panel.TButton',layout('PanelButton'+name))
    style.layout('PanelAccent.TButton',layout('PanelAccent'+name))
    style.configure('TButton',padding=(8,3),foreground=p['ink'],background=p['bg'],borderwidth=0)
    style.map('TButton',foreground=[('disabled',p['muted'])],background=[('active',p['bg']),('disabled',p['bg'])])
    style.configure('Accent.TButton',foreground=p['onaccent'])
    style.map('Accent.TButton',foreground=[('disabled',p['muted']),('!disabled',p['onaccent'])])
    style.configure('Panel.TButton',background=p['panel'])
    style.configure('PanelAccent.TButton',background=p['panel'],foreground=p['onaccent'])
    style.map('PanelAccent.TButton',foreground=[('disabled',p['muted']),('!disabled',p['onaccent'])])
    style.layout('Compact.TButton',layout('CompactCard'+name))
    style.configure('Compact.TButton',padding=(2,1),font=scaled_font(('Microsoft YaHei UI',8)))
    style.layout('TMenubutton',layout('CompactCard'+name,'Menubutton.label'))
    style.configure('TMenubutton',padding=(5,3),foreground=p['accent'],font=scaled_font(('Microsoft YaHei UI',8)))
