"""One drawn icon vocabulary on accessible native ttk buttons."""
import math
import weakref
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from curve_raster import bitmap, blend, pixels


def icon_image(root, name, ink, background):
    if name=='brand':
        path=Path(__file__).resolve().parents[2]/'assets/brand/emoblocks-icon.png'
        source=tk.PhotoImage(master=root,file=str(path))
        factor=max(1,round(source.width()/pixels(root,28)))
        return source.subsample(factor)
    segments=[];circles=[];solids=[]
    def line(points):segments.extend(zip(points,points[1:]))
    def rect(box):
        a,b,c,d=box;line([(a,b),(c,b),(c,d),(a,d),(a,b)])
    if name=='blocks':
        for box in ((5,2,13,10),(2,12,10,20),(13,12,20,19)):rect(box)
    elif name=='play':solids.append([(6,3),(19,11),(6,19)])
    elif name=='pause':
        for a in (5,13):solids.append([(a,3),(a+4,3),(a+4,19),(a,19)])
    elif name=='stop':solids.append([(5,5),(17,5),(17,17),(5,17)])
    elif name=='cancel':line([(5,5),(17,17)]);line([(17,5),(5,17)])
    elif name in ('generate','recommend'):
        line([(4,18),(14,8)]);line([(4,15),(7,18)])
        for a,b,r in ((16,4,3),(5,5,2),(18,14,2)):
            line([(a-r,b),(a+r,b)]);line([(a,b-r),(a,b+r)])
    elif name=='details':
        circles.append((11,11,9));line([(11,10),(11,16)]);circles.append((11,6,1))
    elif name=='advanced':
        for y,x in ((5,8),(11,15),(17,6)):
            line([(3,y),(x-2,y)]);line([(x+2,y),(19,y)]);circles.append((x,y,2))
    elif name in ('previous','next'):
        flip=lambda x:22-x if name=='next' else x
        line([(flip(16),5),(flip(7),11),(flip(16),17),(flip(16),5)])
        line([(flip(4),5),(flip(4),17)])
    elif name=='moon':line([(13,2),(7,3),(3,7),(3,13),(7,18),(13,20),(19,16),(13,15),(9,10),(10,5),(13,2)])
    elif name=='sun':
        circles.append((11,11,4))
        for i in range(8):
            a=i*math.pi/4;line([(11+7*math.cos(a),11+7*math.sin(a)),(11+10*math.cos(a),11+10*math.sin(a))])
    elif name in ('plus','new','minus'):
        line([(4,11),(18,11)])
        if name!='minus':line([(11,4),(11,18)])
        if name=='new':rect((2,2,20,20))
    elif name=='open':line([(2,18),(2,6),(9,6),(11,9),(20,9),(18,18),(2,18)])
    elif name=='save':rect((3,3,19,19));rect((7,3,15,9));rect((7,13,15,19))
    elif name in ('import','export'):
        d=1 if name=='import' else -1
        line([(11,11-7*d),(11,11+4*d),(7,11),(11,11+4*d),(15,11)])
        line([(3,14),(3,19),(19,19),(19,14)])
    elif name=='delete':
        line([(4,6),(18,6)]);rect((6,6,16,19));line([(8,3),(14,3)]);line([(9,9),(9,16)]);line([(13,9),(13,16)])
    elif name in ('undo','redo'):
        f=lambda x:22-x if name=='redo' else x
        line([(f(3),10),(f(8),5),(f(8),9),(f(13),9),(f(18),12),(f(18),18)])
        line([(f(3),10),(f(8),15)])
    elif name=='sidebar':rect((3,3,19,19));line([(9,3),(9,19)])
    elif name=='combine':rect((2,5,9,17));rect((13,5,20,17));line([(9,11),(13,11)])
    elif name=='complete':line([(3,12),(8,17),(19,5)])
    elif name=='phrase':line([(3,17),(3,5),(19,5),(19,17)]);line([(7,10),(7,16),(15,10),(15,16)])
    else:rect((4,4,18,18))
    size=pixels(root,22)
    def color(x,y):
        x=(x+.5)*22/size;y=(y+.5)*22/size
        distance=22
        for (a,b),(c,d) in segments:
            u=max(0,min(1,((x-a)*(c-a)+(y-b)*(d-b))/max(.001,(c-a)**2+(d-b)**2)))
            distance=min(distance,math.hypot(x-a-u*(c-a),y-b-u*(d-b)))
        for a,b,r in circles:distance=min(distance,abs(math.hypot(x-a,y-b)-r))
        for polygon in solids:
            inside=False
            for (a,b),(c,d) in zip(polygon,polygon[1:]+polygon[:1]):
                if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:inside=not inside
            if inside:return ink
        return blend(background,ink,max(0,min(1,1.7-distance)))
    return bitmap(root,size,color)


class IconButton(ttk.Button):
    def __init__(self,parent,app,icon,text,command,tip=None,label=False,style='Curve.TButton',**kwargs):
        self.app,self.icon,self.show_label=app,icon,label
        super().__init__(parent,text=text,command=command,style=style,compound='left' if label else 'image',takefocus=True,padding=0,**kwargs)
        root=self.winfo_toplevel()
        if not hasattr(root,'curve_icon_buttons'):root.curve_icon_buttons=weakref.WeakSet()
        root.curve_icon_buttons.add(self)
        self.bind('<Return>',self.activate)
        self.bind('<space>',self.activate)
        self.bind('<FocusIn>',lambda _:self.state(['focus']),add='+')
        self.bind('<FocusOut>',lambda _:self.state(['!focus']),add='+')
        from curve_theme import hint
        hint(self,tip or text,app.show_detail)
        self.refresh_icon()

    def refresh_icon(self):
        p=self.app.theme.colors
        ink=p['onaccent'] if self.cget('style')=='Curve.Primary.TButton' and self.app.theme.name=='light' else p['ink']
        background=p['accent'] if ink==p['onaccent'] and self.app.theme.name=='light' else p['inset']
        root=self.winfo_toplevel()
        cache=getattr(root,'curve_icon_images',{})
        for color,bg in ((ink,background),(p['muted'],p['inset'])):
            key=(self.icon,color,bg,pixels(root,22))
            if key not in cache:cache[key]=icon_image(root,self.icon,color,bg)
        self.image_ref=cache[(self.icon,ink,background,pixels(root,22))]
        self.disabled_image=cache[(self.icon,p['muted'],p['inset'],pixels(root,22))]
        while len(cache)>128:cache.pop(next(iter(cache)))
        root.curve_icon_images=cache
        self.configure(image=(self.image_ref,'disabled',self.disabled_image))

    def set_icon(self,name):
        if name!=self.icon:self.icon=name;self.refresh_icon()

    def activate(self,event=None):
        self.invoke()
        return 'break'


class CardIconButton(tk.Button):
    """Real native Button fallback for an embedded card, with an explicit Tcl name."""
    def __init__(self,parent,app,icon,text,command):
        self.app,self.icon=app,icon;self.states=set();self.image_ref=None
        super().__init__(parent,text=text,command=command,compound='none',takefocus=True,
                         relief='flat',borderwidth=0,highlightthickness=0,padx=0,pady=0)
        self.bind('<Enter>',lambda _:self.state(['active']))
        self.bind('<Leave>',lambda _:self.state(['!active','!pressed']))
        self.bind('<FocusIn>',lambda _:self.state(['focus']))
        self.bind('<FocusOut>',lambda _:self.state(['!focus']))
        self.bind('<ButtonPress-1>',lambda _:self.state(['pressed']),add='+')
        self.bind('<ButtonRelease-1>',lambda _:self.state(['!pressed']),add='+')
        for event in ('<Return>','<space>'):self.bind(event,self.activate)
        root=app.root
        if not hasattr(root,'curve_icon_buttons'):root.curve_icon_buttons=weakref.WeakSet()
        root.curve_icon_buttons.add(self)
        from curve_theme import hint
        hint(self,text,app.show_detail);self.refresh_icon()

    def state(self,changes=None):
        if changes is not None:
            for change in changes:
                if change.startswith('!'):self.states.discard(change[1:])
                else:self.states.add(change)
            self.configure(state='disabled' if 'disabled' in self.states else 'normal')
            self.refresh_icon()
        return tuple(self.states)

    def instate(self,states):return all((s[1:] not in self.states) if s.startswith('!') else s in self.states for s in states)

    def refresh_icon(self):
        from curve_raster import surface_image
        p=dict(self.app.theme.colors);p['panel']=self.master.cget('bg')
        state=next((s for s in ('disabled','pressed','focus','active') if s in self.states),'normal')
        key=(self.icon,p['panel'],self.app.theme.name,state,pixels(self.app.root,44))
        cache=getattr(self.app.root,'curve_card_controls',{})
        if key not in cache:
            ink=p['muted'] if state=='disabled' else p['ink']
            fill=p['selected'] if state=='pressed' else p['inset']
            image=surface_image(self.app.root,p,'Button',state)
            icon=icon_image(self.app.root,self.icon,ink,fill)
            image.tk.call(str(image),'copy',str(icon),'-to',pixels(self.app.root,11),pixels(self.app.root,11))
            cache[key]=image
        self.image_ref=cache[key]
        while len(cache)>80:cache.pop(next(iter(cache)))
        self.app.root.curve_card_controls=cache
        self.configure(image=self.image_ref,bg=p['panel'],activebackground=p['panel'],fg=p['ink'],disabledforeground=p['muted'])

    def activate(self,event=None):self.invoke();return 'break'
