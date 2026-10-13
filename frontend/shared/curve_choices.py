"""Inline, keyboard-accessible block choices with two visible cells."""
import tkinter as tk
import weakref
from tkinter import ttk
from curve_theme import hint
from curve_raster import pixels
from curve_scrollbar import TransientScrollbar


class BlockChoices(ttk.Frame):
    def __init__(self,parent,app,textvariable,values=(),state='readonly',width=8,**kwargs):
        kwargs.pop('style',None);kwargs.pop('takefocus',None)
        super().__init__(parent,style='Curve.Panel.TFrame')
        self.app=app;self.variable=textvariable;self.values=();self.choice_state=state;self.buttons=[]
        if not hasattr(app.root,'curve_block_choices'):app.root.curve_block_choices=weakref.WeakSet()
        app.root.curve_block_choices.add(self)
        self.canvas=tk.Canvas(self,height=pixels(app.root,38),width=pixels(app.root,200),highlightthickness=0,takefocus=True)
        self.canvas.pack(fill='x',expand=True)
        self.body=ttk.Frame(self.canvas,style='Curve.Panel.TFrame')
        self.placeholder=ttk.Label(self.body,textvariable=self.variable,style='Curve.Muted.TLabel')
        self.window=self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self.bar=TransientScrollbar(self,app,self.canvas.xview,orient='horizontal')
        self.bar.pack(fill='x');self.bar.attach(self.canvas)
        self.canvas.configure(xscrollcommand=self.bar.set)
        self.canvas.bind('<Configure>',lambda _:self.layout())
        self.canvas.bind('<Left>',lambda _:self.choose(max(0,self.current()-1)))
        self.canvas.bind('<Right>',lambda _:self.choose(min(len(self.values)-1,self.current()+1)))
        self.trace=self.variable.trace_add('write',lambda *_:self.highlight())
        self.bind('<Destroy>',self.destroyed,add='+')
        self.configure(values=values,state=state)

    def configure(self,cnf=None,**kwargs):
        if cnf:kwargs.update(cnf)
        values=kwargs.pop('values',None);state=kwargs.pop('state',None);kwargs.pop('width',None)
        result=super().configure(**kwargs)
        if state is not None:self.choice_state=state
        if values is not None and tuple(values)!=self.values:
            self.values=tuple(values)
            for button in self.buttons:button.destroy()
            self.buttons=[]
            for i,value in enumerate(self.values):
                label=value if len(value)<=12 else value[:11]+'…'
                button=ttk.Button(self.body,text=label,width=10,style='Curve.Small.TButton',command=lambda n=i:self.choose(n),takefocus=True)
                button.grid(row=0,column=i,padx=(0,3),sticky='nsew')
                button.bind('<FocusIn>',lambda _,n=i:self.reveal(n))
                button.bind('<Left>',lambda _,n=i:self.step(n,-1))
                button.bind('<Right>',lambda _,n=i:self.step(n,1))
                hint(button,value,self.app.show_detail);self.buttons.append(button)
            self.layout()
        self.highlight()
        return result

    config=configure
    def current(self,index=None):
        if index is not None and 0<=index<len(self.values) and self.variable.get()!=self.values[index]:
            self.variable.set(self.values[index])
            self.reveal(index)
        try:return self.values.index(self.variable.get())
        except ValueError:return -1
    def reveal(self,index):
        if not 0<=index<len(self.values):return
        first,last=self.canvas.xview()
        position=index/len(self.values)
        if position<first or (index+1)/len(self.values)>last:
            self.canvas.xview_moveto(max(0,(index-1)/len(self.values)))
    def step(self,index,direction):
        if self.choice_state=='disabled':return 'break'
        target=max(0,min(len(self.values)-1,index+direction))
        self.buttons[target].focus_set()
        return self.choose(target)
    def choose(self,index):
        if self.choice_state=='disabled' or not 0<=index<len(self.values):return 'break'
        self.current(index);self.event_generate('<<ComboboxSelected>>');return 'break'
    def instate(self,states,callback=None,*args):
        yes=all((self.choice_state!='disabled') if s=='!disabled' else (self.choice_state=='disabled') if s=='disabled' else True for s in states)
        return callback(*args) if yes and callback else yes
    def highlight(self):
        if self.values:self.placeholder.grid_remove()
        else:self.placeholder.grid(row=0,column=0,padx=6,sticky='w')
        for i,b in enumerate(self.buttons):
            b.state(['disabled'] if self.choice_state=='disabled' else ['!disabled'])
            b.configure(style='Curve.Primary.TButton' if i==self.current() else 'Curve.Small.TButton')
    def layout(self):
        if not hasattr(self,'canvas'):return
        cell=max(pixels(self.app.root,90),self.canvas.winfo_width()//2)
        height=pixels(self.app.root,38)
        self.canvas.configure(width=pixels(self.app.root,200),height=height,bg=self.app.theme.colors['panel'],scrollregion=(0,0,max(cell,len(self.values)*cell),height))
        for i in range(len(self.values)):self.body.columnconfigure(i,minsize=cell)
        self.canvas.itemconfigure(self.window,height=height)
    def destroyed(self,event):
        if event.widget==self:self.variable.trace_remove('write',self.trace)
