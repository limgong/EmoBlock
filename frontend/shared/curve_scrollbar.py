"""Reserved-layout transient scrollbar. It never owns musical scroll state."""
import tkinter as tk
import weakref
from curve_raster import pixels


class TransientScrollbar(tk.Canvas):
    def __init__(self,parent,app,command,orient='vertical'):
        self.app,self.command,self.orient=app,command,orient
        self.first,self.last=0.,1.
        self.visible=self.hovered=self.dragging=self.focused=False
        self.timer=None;self.thumb=(0,0)
        self.slot=pixels(app.root,12);self.minimum=pixels(app.root,24)
        super().__init__(parent,width=self.slot,height=self.slot,highlightthickness=0,takefocus=True)
        if not hasattr(app.root,'curve_scrollbars'):app.root.curve_scrollbars=weakref.WeakSet()
        app.root.curve_scrollbars.add(self)
        self.near_binding=app.root.bind('<Motion>',self.near,add='+')
        self.content=None
        self.bind('<Configure>',self.draw)
        self.bind('<Enter>',self.enter);self.bind('<Leave>',self.leave)
        self.bind('<FocusIn>',self.focus);self.bind('<FocusOut>',self.blur)
        self.bind('<ButtonPress-1>',self.press);self.bind('<B1-Motion>',self.motion);self.bind('<ButtonRelease-1>',self.release)
        for key,delta in (('<Up>',-1),('<Left>',-1),('<Down>',1),('<Right>',1)):
            self.bind(key,lambda _,d=delta:self.keyboard(d))
        self.bind('<Destroy>',self.destroyed)

    def attach(self,widget):
        self.content=widget
        for event in ('<FocusIn>','<KeyPress>'):
            widget.bind(event,self.reveal,add='+')

    def near(self,event):
        if not self.winfo_ismapped() or self.content is None:return
        widget=self.content
        if self.orient=='vertical':
            inside=widget.winfo_rooty()<=event.y_root<=widget.winfo_rooty()+widget.winfo_height()
            distance=abs(event.x_root-(self.winfo_rootx()+self.slot/2))
        else:
            inside=widget.winfo_rootx()<=event.x_root<=widget.winfo_rootx()+widget.winfo_width()
            distance=abs(event.y_root-(self.winfo_rooty()+self.slot/2))
        if inside and distance<=self.slot*2:self.reveal()

    def set(self,first,last):
        value=(float(first),float(last))
        changed=value!=(self.first,self.last)
        self.first,self.last=value
        if changed and self.last-self.first<.999:self.reveal()
        else:self.draw()

    def reveal(self,event=None):
        if self.timer is not None:self.after_cancel(self.timer)
        self.visible=self.last-self.first<.999
        self.timer=self.after(900,self.hide)
        self.draw()

    def hide(self):
        if self.timer is not None:self.after_cancel(self.timer)
        self.timer=None
        if self.dragging or self.focused:self.timer=self.after(900,self.hide)
        else:self.visible=False;self.draw()

    def draw(self,event=None):
        p=self.app.theme.colors;self.configure(bg=p['panel']);self.delete('all')
        length=self.winfo_height() if self.orient=='vertical' else self.winfo_width()
        size=min(length,max(self.minimum,length*(self.last-self.first)))
        start=(length-size)*self.first/max(.001,1-(self.last-self.first))
        self.thumb=(start,size)
        if not self.visible or self.last-self.first>=.999:return
        width=pixels(self.app.root,6 if self.dragging or self.hovered else 4)
        ink=p['ink'] if self.dragging else p['muted']
        if self.orient=='vertical':self.create_line(self.slot/2,start+width/2,self.slot/2,start+size-width/2,width=width,fill=ink,capstyle='round',tags='thumb')
        else:self.create_line(start+width/2,self.slot/2,start+size-width/2,self.slot/2,width=width,fill=ink,capstyle='round',tags='thumb')

    def enter(self,event=None):self.hovered=True;self.reveal()
    def leave(self,event=None):self.hovered=False;self.reveal()
    def focus(self,event=None):self.focused=True;self.reveal()
    def blur(self,event=None):self.focused=False;self.reveal()

    def position(self,event):return event.y if self.orient=='vertical' else event.x

    def press(self,event):
        if self.last-self.first>=.999:return 'break'
        self.focus_set();self.dragging=True;self.reveal();self.grab_set()
        start,size=self.thumb
        self.offset=self.position(event)-start if start<=self.position(event)<=start+size else size/2
        self.motion(event);return 'break'

    def motion(self,event):
        if not self.dragging:return
        length=self.winfo_height() if self.orient=='vertical' else self.winfo_width()
        fraction=(self.position(event)-self.offset)/max(1,length-self.thumb[1])*(1-(self.last-self.first))
        self.command('moveto',max(0,min(1,fraction)));self.reveal();return 'break'

    def release(self,event=None):
        self.dragging=False
        if self.grab_current()==self:self.grab_release()
        self.reveal();return 'break'

    def keyboard(self,direction):self.command('scroll',direction,'units');self.reveal();return 'break'

    def destroyed(self,event):
        if event.widget==self:
            if self.timer is not None:self.after_cancel(self.timer);self.timer=None
            try:self.app.root.unbind('<Motion>',self.near_binding)
            except tk.TclError:pass
