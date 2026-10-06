"""Native, dependency-free window chrome and rounded workspace surfaces."""
import math
import sys
import tkinter as tk
from tkinter import ttk
from ui_theme import color
from ui_hints import rounded, Tooltip
import ui_scale
import ui_platform


class IconButton(tk.Canvas):
    def __init__(self,parent,icon,command,hint='',size=32,surface='bg',primary=False):
        super().__init__(parent,width=size,height=size,highlightthickness=0,takefocus=True,cursor='hand2')
        self.icon=icon;self.command=command;self.size=size;self.hovered=False;self.surface=surface;self.primary=primary;self.enabled=True
        self.bind('<Button-1>',lambda _:self.invoke())
        self.bind('<Return>',lambda _:self.invoke());self.bind('<space>',lambda _:self.invoke())
        self.bind('<Enter>',lambda _:self.highlight(True));self.bind('<Leave>',lambda _:self.highlight(False))
        self.bind('<FocusIn>',lambda _:self.highlight(True));self.bind('<FocusOut>',lambda _:self.highlight(False))
        if hint:Tooltip(self,hint)
        self.refresh_theme()

    def highlight(self,value):self.hovered=value;self.refresh_theme()

    def invoke(self):
        if self.enabled:return self.command()

    def set_enabled(self,enabled):
        if self.enabled==bool(enabled):return
        self.enabled=bool(enabled);self.configure(cursor='hand2' if enabled else '');self.refresh_theme()

    def refresh_theme(self):
        self.configure(width=round(self.size*ui_scale.factor),height=round(self.size*ui_scale.factor))
        self.configure(bg=color(self.surface));self.delete('all')
        size=self.size;mid=size/2;fg=(color('onaccent') if self.primary else color('ink')) if self.enabled else color('muted')
        bg=color('accent') if self.primary else color('hover') if self.hovered else color(self.surface)
        rounded(self,1,1,size-1,size-1,bg)
        if self.icon=='play':self.create_polygon(mid-4,mid-7,mid+7,mid,mid-4,mid+7,fill=fg,outline='')
        elif self.icon=='pause':
            for x in (mid-5,mid+2):self.create_rectangle(x,mid-7,x+3,mid+7,fill=fg,outline='')
        elif self.icon in ('previous','next'):
            direction=-1 if self.icon=='previous' else 1
            self.create_polygon(mid-5*direction,mid-6,mid+4*direction,mid,mid-5*direction,mid+6,fill=fg,outline='')
            self.create_line(mid+6*direction,mid-6,mid+6*direction,mid+6,fill=fg,width=2)
        elif self.icon=='moon':
            self.create_oval(mid-8,mid-8,mid+8,mid+8,fill=fg,outline='')
            self.create_oval(mid-2,mid-11,mid+11,mid+2,fill=bg,outline='')
        elif self.icon=='sun':
            self.create_oval(mid-4,mid-4,mid+4,mid+4,outline=fg,width=2)
            for i in range(8):
                angle=i*math.pi/4
                self.create_line(mid+7*math.cos(angle),mid+7*math.sin(angle),mid+10*math.cos(angle),mid+10*math.sin(angle),fill=fg,width=2)
        elif self.icon=='close':
            self.create_line(mid-5,mid-5,mid+5,mid+5,fill=fg,width=2)
            self.create_line(mid+5,mid-5,mid-5,mid+5,fill=fg,width=2)
        elif self.icon=='minimize':self.create_line(mid-6,mid+3,mid+6,mid+3,fill=fg,width=2)
        elif self.icon=='maximize':self.create_rectangle(mid-5,mid-5,mid+5,mid+5,outline=fg,width=2)
        elif self.icon=='restore':
            self.create_rectangle(mid-2,mid-6,mid+6,mid+2,outline=fg,width=1)
            self.create_rectangle(mid-6,mid-2,mid+2,mid+6,fill=bg,outline=fg,width=1)
        elif self.icon=='blocks':
            # Three interlocking outlined blocks, matching the preview mark.
            for x,y,w,h in ((8,5,12,12),(5,20,12,12),(22,20,10,10)):
                rounded(self,x,y,x+w,y+h,'',color('accent'),2,radius=4)
        self.scale('all',0,0,ui_scale.factor,ui_scale.factor)


class RoundedPanel(tk.Canvas):
    def __init__(self,parent,padding=12,**kwargs):
        super().__init__(parent,highlightthickness=0,bg=color('bg'),**kwargs)
        self.padding=padding
        self.body=ttk.Frame(self,style='Panel.TFrame')
        self.window=self.create_window(padding,padding,anchor='nw',window=self.body)
        self.bind('<Configure>',self.layout)
        self.body.bind('<Configure>',lambda _:self.refresh_theme())

    def layout(self,event=None):
        pad=self.padding
        self.itemconfigure(self.window,width=max(1,self.winfo_width()-2*pad),height=max(1,self.winfo_height()-2*pad))
        self.refresh_theme()

    def refresh_theme(self):
        self.configure(bg=color('bg'));self.delete('surface')
        rounded(self,1,1,max(2,self.winfo_width()-1),max(2,self.winfo_height()-1),color('panel'),color('line'),1,tags='surface',radius=24)
        self.tag_lower('surface')
        def style(widget):
            if isinstance(widget,ttk.Frame):widget.configure(style='Panel.TFrame')
            elif isinstance(widget,ttk.Label):
                widget.configure(style='PanelMuted.TLabel' if 'Muted' in widget.cget('style') else 'Panel.TLabel')
            elif isinstance(widget,ttk.Checkbutton):widget.configure(style='Panel.TCheckbutton')
            elif isinstance(widget,ttk.Button):
                if widget.cget('style') in ('','TButton'):widget.configure(style='Panel.TButton')
                elif widget.cget('style')=='Accent.TButton':widget.configure(style='PanelAccent.TButton')
            for child in widget.winfo_children():style(child)
        style(self.body)


class FixedRail(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.columnconfigure(0,weight=1);self.rowconfigure(0,weight=1)
        self.audition=RoundedPanel(self,padding=14,height=490)
        self.audition.grid(row=0,column=0,sticky='nsew',pady=(0,16))
        self.export=RoundedPanel(self,padding=14,height=132)
        self.export.grid(row=1,column=0,sticky='ew')
        self.body=self.audition.body;self.footer=self.export.body


class WindowChrome:
    def __init__(self,root,header,close):
        self.root=root;self.maximized=False;self.saved_geometry=None;self.drag=None
        if ui_platform.NATIVE_CHROME:
            self.buttons=[]
            root.overrideredirect(False)
            root.protocol('WM_DELETE_WINDOW',close)
            return
        root.overrideredirect(True)
        self.buttons=[]
        for icon,command,hint in [('close',close,'关闭'),('maximize',self.toggle_maximize,'最大化 / 还原'),('minimize',self.minimize,'最小化')]:
            b=IconButton(header,icon,command,hint);b.pack(side='right',padx=2)
            self.buttons.append(b)
        self.bind_drag(header)
        root.bind('<Map>',self.restore_borderless,add='+')
        root.bind('<Alt-F4>',lambda _:close())
        for edge,cursor in [('n','sb_v_double_arrow'),('s','sb_v_double_arrow'),('w','sb_h_double_arrow'),('e','sb_h_double_arrow'),('se','size_nw_se'),('sw','size_ne_sw'),('ne','size_ne_sw'),('nw','size_nw_se')]:
            grip=tk.Frame(root,bg=color('bg'),cursor=cursor)
            if len(edge)==2:grip.place(relx=1 if 'e' in edge else 0,rely=1 if 's' in edge else 0,anchor=edge,width=8,height=8)
            elif edge in ('n','s'):grip.place(relx=.5,rely=1 if edge=='s' else 0,anchor=edge,relwidth=1,height=3)
            else:grip.place(relx=1 if edge=='e' else 0,rely=.5,anchor=edge,width=3,relheight=1)
            grip.bind('<Button-1>',lambda e,side=edge:self.start_resize(e,side))
            grip.bind('<B1-Motion>',self.resize)
        root.after_idle(self.taskbar)

    def bind_drag(self,widget):
        widget.bind('<Button-1>',self.start_drag)
        widget.bind('<B1-Motion>',self.move)
        widget.bind('<Double-Button-1>',lambda _:self.toggle_maximize())

    def taskbar(self):
        ui_platform.taskbar(self.root)

    def minimize(self):
        self.root.overrideredirect(False);self.root.iconify()

    def restore_borderless(self,event):
        if event.widget is self.root:
            self.root.after_idle(self._restore)

    def _restore(self):
        if self.root.state()=='normal':
            self.root.overrideredirect(True);self.taskbar()

    def toggle_maximize(self):
        if self.maximized:
            self.root.geometry(self.saved_geometry);self.maximized=False
        else:
            self.saved_geometry=self.root.geometry()
            x,y,width,height=ui_platform.work_area(self.root)
            self.root.geometry(f'{width}x{height}+{x}+{y}');self.maximized=True
        self.buttons[1].icon='restore' if self.maximized else 'maximize';self.buttons[1].refresh_theme()

    def start_drag(self,event):self.drag=(event.x_root-self.root.winfo_x(),event.y_root-self.root.winfo_y())
    def move(self,event):
        if self.drag:
            if self.maximized:self.toggle_maximize();self.drag=(100,20)
            self.root.geometry(f'+{event.x_root-self.drag[0]}+{event.y_root-self.drag[1]}')

    def start_resize(self,event,edge):
        self.resize_origin=(event.x_root,event.y_root,self.root.winfo_x(),self.root.winfo_y(),self.root.winfo_width(),self.root.winfo_height(),edge)
    def resize(self,event):
        if self.maximized:return
        sx,sy,x,y,w,h,edge=self.resize_origin;dx=event.x_root-sx;dy=event.y_root-sy
        minw,minh=self.root.minsize()
        nw=max(minw,w+dx if 'e' in edge else w-dx if 'w' in edge else w)
        nh=max(minh,h+dy if 's' in edge else h-dy if 'n' in edge else h)
        self.root.geometry(f'{nw}x{nh}+{x+w-nw if "w" in edge else x}+{y+h-nh if "n" in edge else y}')
