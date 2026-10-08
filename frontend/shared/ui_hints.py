from ui_scale import font as scaled_font
from ui_theme import color as theme_color
"""Small Tk-only tooltips, compatible with the portable runtime."""
import tkinter as tk


class Tooltip:
    def __init__(self, widget, text):
        self.widget=widget;self.text=text;self.timer=None;self.popup=None;self.value=None
        widget.bind('<Enter>',self.schedule,add='+')
        widget.bind('<Motion>',self.schedule,add='+')
        widget.bind('<Leave>',self.hide,add='+')
        widget.bind('<ButtonPress>',self.hide,add='+')
        widget.bind('<Destroy>',self.hide,add='+')

    def schedule(self,event):
        value=self.text(event) if callable(self.text) else self.text
        if value==self.value and (self.timer or self.popup):return
        self.hide();self.value=value
        if value:
            self.x=event.x_root;self.y=event.y_root
            self.timer=self.widget.after(500,self.show)

    def show(self):
        if self.timer:
            self.widget.after_cancel(self.timer);self.timer=None
        if not self.widget.winfo_exists() or not self.value:return
        self.popup=tk.Toplevel(self.widget);self.popup.withdraw();self.popup.overrideredirect(True)
        tk.Label(self.popup,text=self.value,bg=theme_color('#263746'),fg=theme_color('#edf2f7'),justify='left',
                 padx=12,pady=8,wraplength=320,relief='solid',borderwidth=1,
                 font=scaled_font(('Microsoft YaHei UI',10))).pack()
        self.popup.update_idletasks()
        x=max(0,min(self.x+12,self.popup.winfo_screenwidth()-self.popup.winfo_reqwidth()-12))
        y=max(0,min(self.y+20,self.popup.winfo_screenheight()-self.popup.winfo_reqheight()-12))
        self.popup.geometry(f'+{x}+{y}');self.popup.deiconify()

    def hide(self,event=None):
        if self.timer:
            self.widget.after_cancel(self.timer);self.timer=None
        if self.popup:
            self.popup.destroy();self.popup=None
        self.value=None


def rounded(canvas,x1,y1,x2,y2,fill,outline='',width=1,tags=(),radius=9):
    radius=min(radius,(x2-x1)/4,(y2-y1)/4)
    return canvas.create_polygon(x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,
        x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,
        x1,y1+radius,x1,y1,smooth=True,splinesteps=16,fill=fill,outline=outline,width=width,tags=tags)


def elide(widget, text, width, font=None):
    """Fit one line in physical pixels, preserving an explicit truncation marker."""
    from tkinter.font import Font
    measure=Font(root=widget, font=font or widget.cget('font')).measure
    if measure(text)<=width:return text
    lo,hi=0,len(text)
    while lo<hi:
        mid=(lo+hi+1)//2
        if measure(text[:mid]+'…')<=width:lo=mid
        else:hi=mid-1
    return text[:lo]+'…'


from tkinter import ttk

class BoundedLabel(ttk.Label):
    """Stable-height status text; full content remains available by click or keyboard."""
    def __init__(self,parent,lines=2,**kwargs):
        self.lines=lines;self.full_text=str(kwargs.pop('text',''))
        variable=kwargs.pop('textvariable',None);kwargs.pop('wraplength',None)
        super().__init__(parent,**kwargs,wraplength=0,width=1,takefocus=True,cursor='hand2')
        self.variable=variable
        if variable is not None:
            self.full_text=variable.get();self.trace=variable.trace_add('write',self.variable_changed)
            self.bind('<Destroy>',self.remove_trace,add='+')
        self.bind('<Configure>',lambda _:self.render())
        self.bind('<Button-1>',self.show_full);self.bind('<Return>',self.show_full)
        Tooltip(self,lambda _:self.full_text+'\n点击或按回车查看完整内容。')
        self.render()

    def remove_trace(self,event):
        if event.widget is self:self.variable.trace_remove('write',self.trace)

    def variable_changed(self,*_):
        self.full_text=self.variable.get();self.render()

    def configure(self,cnf=None,**kwargs):
        if isinstance(cnf,dict):kwargs={**cnf,**kwargs};cnf=None
        if 'text' in kwargs:self.full_text=str(kwargs.pop('text'))
        result=super().configure(cnf,**kwargs)
        self.render();return result

    config=configure

    def render(self):
        width=max(20,self.winfo_width()-4)
        parts=self.full_text.splitlines() or ['']
        # Explicit newlines define hierarchy; each line has its own ellipsis.
        if len(parts)>self.lines:parts=parts[:self.lines-1]+[' '.join(parts[self.lines-1:])]
        text='\n'.join(elide(self,t,width) if self.winfo_width()>1 else t for t in parts)
        text+='\n'*max(0,self.lines-len(parts))
        super().configure(text=text)

    def show_full(self,event=None):
        win=tk.Toplevel(self);win.title('完整内容');win.geometry('620x260')
        box=ttk.Frame(win,padding=12);box.pack(fill='both',expand=True)
        text=tk.Text(box,wrap='word',height=6);bar=ttk.Scrollbar(box,command=text.yview)
        text.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0',self.full_text);text.configure(state='disabled')
        ttk.Button(win,text='关闭',command=win.destroy).pack(pady=8)
        win.bind('<Escape>',lambda _:win.destroy())
