"""Equal-sized material cards and independently usable phrase child cards."""
import copy
import math
import tkinter as tk
from tkinter import ttk
from curve_theme import font, hint, rounded


class MaterialCards(ttk.Frame):
    CARD_HEIGHT = 96

    def __init__(self, parent, app):
        super().__init__(parent,style='Curve.Panel.TFrame')
        self.app = app
        self.expanded = set()
        self.rows = {}
        self.row_versions = {}
        self.pending_render = None
        self.last_view = None
        self.rendering = False
        self.materials = []
        self.canvas = tk.Canvas(self,highlightthickness=0,takefocus=True)
        self.canvas.pack(side='left',fill='both',expand=True)
        bar = ttk.Scrollbar(self,style='Curve.Vertical.TScrollbar',command=self.canvas.yview)
        bar.pack(side='right',fill='y')
        self.scrollbar = bar
        self.canvas.configure(yscrollcommand=self.scrolled)
        self.body = tk.Frame(self.canvas)
        self.body.pack_propagate(False)
        self.window = self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self.canvas.bind('<Configure>',self.configure_size)
        self.empty_label = None
        self.bind('<Destroy>',self.destroyed,add='+')

    def destroyed(self, event):
        if event.widget==self and self.pending_render is not None:
            self.after_cancel(self.pending_render)
            self.pending_render = None

    def scrolled(self, first, last):
        self.scrollbar.set(first,last)
        view = (first,last,self.canvas.winfo_width(),self.canvas.winfo_height())
        if view!=self.last_view and self.pending_render is None:
            self.last_view = view
            self.pending_render = self.after_idle(self.render_view)

    def render_view(self):
        self.pending_render = None
        self.render()

    def configure_size(self, event):
        self.canvas.itemconfigure(self.window,width=event.width)
        self.scrolled(*self.canvas.yview())

    def visible_materials(self):
        ids = {m['id'] for m in self.materials}
        for m in self.materials:
            if m['phrase_id'] in ids:
                continue
            yield m,False
            if m['id'] in self.expanded:
                children = sorted((v for v in self.materials if v['phrase_id']==m['id']),
                                  key=lambda v:v['provenance']['relative_start_tick'])
                for child in children:
                    yield child,True

    def render(self, materials=None):
        if materials is not None:
            self.materials = materials
        if self.rendering:return
        self.rendering = True
        try:self.render_rows()
        finally:self.rendering = False

    def render_rows(self):
        visible = list(self.visible_materials())
        stride = self.CARD_HEIGHT+8
        width = max(1,self.canvas.winfo_width())
        height = max(1,len(visible)*stride)
        self.canvas.itemconfigure(self.window,width=width,height=height)
        self.canvas.configure(scrollregion=(0,0,width,height))
        start = max(0,int(self.canvas.canvasy(0)//stride)-2)
        end = min(len(visible),int(math.ceil((self.canvas.canvasy(0)+self.canvas.winfo_height())/stride))+2)
        mounted = set(range(start,end))
        drag = self.app.material_drag
        if drag:
            mounted.update(i for i,(material,_) in enumerate(visible) if material['id']==drag['material']['id'])
        wanted = {visible[i][0]['id'] for i in mounted}
        for ident in list(self.rows):
            if ident not in wanted:
                self.rows.pop(ident).destroy()
                self.row_versions.pop(ident,None)
        p = self.app.theme.colors
        self.canvas.configure(bg=p['panel'])
        self.body.configure(bg=p['panel'])
        if visible and self.empty_label is not None:
            self.empty_label.destroy();self.empty_label = None
        for index in sorted(mounted):
            material,child = visible[index]
            ident = material['id']
            selected = ident==self.app.selected_material_id
            expandable = material['kind']=='phrase' and any(v['phrase_id']==ident for v in self.materials)
            version = (material,child,self.app.theme.name,selected,expandable,ident in self.expanded)
            left = 16 if child else 4
            old_version = self.row_versions.get(ident)
            dragging = drag and ident==drag['material']['id'] and ident in self.rows
            if dragging and (old_version[0]!=material or old_version[2]!=self.app.theme.name):
                self.app.cancel_interaction();drag = None;dragging = False
            if old_version==version or dragging:
                self.rows[ident].place_configure(x=left,y=index*stride+4,width=max(1,width-left-4))
                continue
            if ident in self.rows:self.rows.pop(ident).destroy()
            self.row_versions[ident] = copy.deepcopy(version)
            surface = p['selected'] if selected else p['inset']
            card = tk.Canvas(self.body,bg=p['panel'],height=self.CARD_HEIGHT,highlightthickness=0,borderwidth=0)
            card.place(x=left,y=index*stride+4,width=max(1,width-left-4),height=self.CARD_HEIGHT)
            self.rows[ident] = card
            content = tk.Frame(card,bg=surface)
            window = card.create_window(8,3,anchor='nw',window=content,height=self.CARD_HEIGHT-6)
            def background(event,canvas=card,window=window,fill=surface,selected=selected):
                canvas.itemconfigure(window,width=max(1,event.width-16))
                canvas.delete('surface')
                if self.app.theme.name=='light':
                    rounded(canvas,(3,4,event.width-1,self.CARD_HEIGHT-1),p['shadow'],tags='surface')
                rounded(canvas,(1,1,event.width-4,self.CARD_HEIGHT-4),fill,
                        p['accent'] if selected else p['line'],tags='surface')
                canvas.tag_lower('surface')
            card.bind('<Configure>',background)
            prefix = '↳ ' if child else ''
            label = material['label']
            parts=label.split(' · ')
            if len(parts)>1 and any(ch.isdigit() for ch in parts[-1]):label=parts[-1]+' · '+' · '.join(parts[:-1])
            title = tk.Label(content,text=prefix+label,anchor='w',bg=surface,fg=p['ink'],font=font(12,True),
                             takefocus=True,cursor='hand2')
            content.columnconfigure(0,weight=1)
            title.grid(row=0,column=0,sticky='ew',padx=(4,2))
            def shorten(event,widget=title,text=prefix+label):
                from tkinter import font as tkfont
                measure=tkfont.Font(root=widget,font=widget.cget('font')).measure
                value=text
                while len(value)>1 and measure(value+'…')>event.width:value=value[:-1]
                widget.configure(text=value+('…' if value!=text else ''))
            title.bind('<Configure>',shorten)
            kind='子块' if child else {'block':'原始分块','phrase':'乐句','combination':'组合','bridge':'Bridge'}.get(material['kind'],'素材')
            if material['generation']:kind='新旋律'
            info=tk.Label(content,text=f'{kind} · {material["length_ticks"]/480:g} 拍',bg=surface,fg=p['muted'],anchor='w',font=font(10))
            info.grid(row=1,column=0,sticky='ew',padx=4)
            b=ttk.Button(content,text='试听',style='Curve.Compact.TButton',
                         command=lambda m=material:self.app.safe(lambda:self.app.audition_target('material',m['id'])))
            b.grid(row=0,column=1,rowspan=2,sticky='ns',padx=2)
            hint(b,'明确试听此素材；准备完成后仅有效播放意图可开始。',self.app.show_detail)
            thumb=tk.Canvas(content,height=28,width=80,bg=surface,highlightthickness=0)
            thumb.grid(row=2,column=0,sticky='ew',padx=4,pady=0)
            def notes(event,c=thumb,m=material):
                c.delete('all')
                pitches=[n['pitch'] for n in m['notes']]
                low,high=min(pitches,default=60),max(pitches,default=72)
                for n in m['notes']:
                    x=n['start_tick']/m['length_ticks']*max(1,event.width-4)+2
                    end=(n['start_tick']+n['duration_tick'])/m['length_ticks']*max(1,event.width-4)+2
                    y=24-(n['pitch']-low)/max(1,high-low)*20
                    c.create_line(x,y,max(x+1,end),y,fill=p['muted'],width=2)
            thumb.bind('<Configure>',notes)
            if expandable:
                ttk.Button(content,text='收起' if ident in self.expanded else '展开',style='Curve.Compact.TButton',
                           command=lambda i=ident:self.toggle(i)).grid(row=2,column=1,sticky='ns',padx=2)
            for widget in (card,title,info,thumb):
                widget.bind('<ButtonPress-1>',lambda e,m=material,w=card:self.app.begin_material_drag(e,m,w))
                widget.bind('<B1-Motion>',self.app.material_motion)
                widget.bind('<ButtonRelease-1>',self.app.material_release)
                widget.bind('<Escape>',self.app.cancel_interaction)
            title.bind('<Return>',lambda _,m=material:self.select(m))
            hint(title,lambda m=material:self.describe(m),self.app.show_detail)
        if not visible:
            self.canvas.itemconfigure(self.window,height=max(100,self.canvas.winfo_height()))
            if self.empty_label is None:
                self.empty_label = tk.Label(self.body,text='导入原始旋律后，分块、乐句和新旋律会出现在这里。',font=font())
            self.empty_label.configure(wraplength=max(1,width-24),bg=p['panel'],fg=p['muted'])
            self.empty_label.place(x=12,y=30,width=max(1,width-24))

    def describe(self, material):
        source = material['provenance'].get('source_id','')
        parent = material['phrase_id'] or ''
        method = (material['generation'] or {}).get('method','原始')
        return f'{material["label"]} · {material["length_ticks"]/480:g} 拍 · 来源 {source or "见保存的来源快照"} · 乐句 {parent or "独立素材"} · 方法 {method}'

    def select(self, material):
        self.app.select_target('material',material['id'])
        self.app.show_detail(self.describe(material))

    def toggle(self, ident):
        if ident in self.expanded:
            self.expanded.remove(ident)
        else:
            self.expanded.add(ident)
        self.render()

    def mark_selection(self):
        for ident,row in self.rows.items():
            surfaces = row.find_withtag('surface')
            if surfaces:
                row.itemconfigure(surfaces[-1],outline=self.app.theme.colors[
                    'accent' if ident==self.app.selected_material_id else 'line'])

    def at_root(self, x, y):
        if not (self.canvas.winfo_rootx()<=x<self.canvas.winfo_rootx()+self.canvas.winfo_width()
                and self.canvas.winfo_rooty()<=y<self.canvas.winfo_rooty()+self.canvas.winfo_height()):
            return None
        for ident,row in self.rows.items():
            if row.winfo_rooty()<=y<row.winfo_rooty()+row.winfo_height():
                return ident,'left' if x<row.winfo_rootx()+row.winfo_width()/2 else 'right'
        return None
