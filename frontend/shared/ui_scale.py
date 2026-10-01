"""Scale fonts and module proportions from the windowed design baseline."""
import tkinter as tk
import ui_platform
from tkinter import ttk

factor=1.


def font(spec):
    return (ui_platform.font_family(spec[0]),max(8,round(spec[1]*factor)))+tuple(spec[2:])


def ratio(width,height):
    return max(1.,min(1.65,width/1300,height/870))


class ResponsiveLayout:
    def __init__(self,app,workspace):
        self.app=app;self.root=app.root;self.workspace=workspace;self.timer=None;self.last=None
        self.root.bind('<Configure>',self.changed,add='+')
        self.root.bind('<Destroy>',self.destroyed,add='+')
        self.timer=self.root.after(80,self.apply)

    def changed(self,event):
        if event.widget is not self.root:return
        if self.timer:self.root.after_cancel(self.timer)
        self.timer=self.root.after(80,self.apply)

    def destroyed(self,event):
        if event.widget is self.root and self.timer:self.root.after_cancel(self.timer);self.timer=None

    def apply(self):
        global factor
        self.timer=None
        width,height=self.root.winfo_width(),self.root.winfo_height()
        if width<100 or height<100:return
        size=(width,height)
        if size==self.last:return
        self.last=size;old=factor;factor=ratio(width,height);app=self.app;p=app.story_page
        # Match the sidebar's share of the window, rather than keeping it 300px wide.
        self.workspace.columnconfigure(1,minsize=max(300,round(width*.27)))
        def walk(widget):
            try:
                current=widget.cget('font')
                if current:
                    if not hasattr(widget,'_base_ui_font'):
                        family=self.root.tk.call('font','actual',current,'-family')
                        size=int(self.root.tk.call('font','actual',current,'-size'))
                        weight=self.root.tk.call('font','actual',current,'-weight')
                        widget._base_ui_font=(family,max(8,round(abs(size)/old)),weight)
                    widget.configure(font=font(widget._base_ui_font))
            except tk.TclError:pass
            for child in widget.winfo_children():walk(child)
        walk(self.root)
        s=ttk.Style(self.root);s.configure('.',font=font(('Microsoft YaHei UI',10)))
        s.configure('Compact.TButton',font=font(('Microsoft YaHei UI',8)))
        p.source_panel.configure(height=round(176*factor))
        app.rail_page.export.configure(height=round(124*factor))
        room=max(350,height-round(110*factor)-round(124*factor)-64)
        app.rail_page.audition.configure(height=min(round(422*factor),room))
        app.history_canvas.configure(height=round(104*factor))
        app.play_canvas.configure(height=round(64*factor))
        app.audition_tiles.configure(height=round(98*factor))
        app.navigation.configure(height=round(36*factor))
        app.rail_page.grid_configure(pady=(round(44*factor),0))
        p.draw_source_cards();p.draw_block_cards();p.draw_source_notes();p.draw()
        app.refresh_surfaces()
