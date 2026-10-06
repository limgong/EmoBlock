"""Equal-sized material cards and independently usable phrase child cards."""
import tkinter as tk
from tkinter import ttk
from curve_theme import font, hint, rounded


class MaterialCards(ttk.Frame):
    CARD_HEIGHT = 132

    def __init__(self, parent, app):
        super().__init__(parent,style='Curve.Panel.TFrame')
        self.app = app
        self.expanded = set()
        self.rows = {}
        self.materials = []
        self.canvas = tk.Canvas(self,highlightthickness=0,takefocus=True)
        self.canvas.pack(side='left',fill='both',expand=True)
        bar = ttk.Scrollbar(self,command=self.canvas.yview)
        bar.pack(side='right',fill='y')
        self.canvas.configure(yscrollcommand=bar.set)
        self.body = tk.Frame(self.canvas)
        self.window = self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self.canvas.bind('<Configure>',self.configure_size)
        self.body.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))

    def configure_size(self, event):
        self.canvas.itemconfigure(self.window,width=event.width)

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
        view = self.canvas.yview()[0]
        p = self.app.theme.colors
        self.canvas.configure(bg=p['panel'])
        self.body.configure(bg=p['panel'])
        for widget in self.body.winfo_children():
            widget.destroy()
        self.rows = {}
        for material,child in self.visible_materials():
            ident = material['id']
            selected = ident==self.app.selected_material_id
            surface = p['selected'] if selected else p['inset']
            card = tk.Canvas(self.body,bg=p['panel'],height=self.CARD_HEIGHT,highlightthickness=0,borderwidth=0)
            card.pack(fill='x',padx=(16 if child else 4,4),pady=4)
            self.rows[ident] = card
            content = tk.Frame(card,bg=surface)
            window = card.create_window(8,6,anchor='nw',window=content,height=self.CARD_HEIGHT-14)
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
            title = tk.Label(content,text=prefix+label,anchor='w',bg=surface,fg=p['ink'],font=font(12,True),
                             takefocus=True,cursor='hand2')
            title.pack(fill='x',padx=10,pady=(8,0))
            title.bind('<Configure>',lambda e,w=title,t=prefix+label:w.configure(text=t[:max(6,e.width//17)]+('…' if len(t)>max(6,e.width//17) else '')))
            kind = '子块' if child else {'block':'原始分块','phrase':'乐句','combination':'组合','bridge':'Bridge'}.get(material['kind'],'素材')
            if material['generation']:
                kind = '新旋律 · '+str(material['generation'].get('method',''))
            info = tk.Label(content,text=f'{kind} · {material["length_ticks"]/480:g} 拍',bg=surface,fg=p['muted'],anchor='w',font=font(11))
            info.pack(fill='x',padx=10,pady=3)
            row = tk.Frame(content,bg=surface)
            row.pack(fill='x',padx=8)
            for text,command in (('准备试听',lambda m=material:self.app.prepare_target('material',m['id'])),
                                 ('播放',lambda m=material:self.app.play_target('material',m['id']))):
                b = ttk.Button(row,text=text,style='Curve.TButton',command=lambda fn=command:self.app.safe(fn))
                b.pack(side='left',padx=2)
                hint(b,'准备只缓存音频；明确点击播放才开始试听。',self.app.show_detail)
            if material['kind']=='phrase' and any(v['phrase_id']==ident for v in self.materials):
                ttk.Button(row,text='收起' if ident in self.expanded else '展开',style='Curve.TButton',
                           command=lambda i=ident:self.toggle(i)).pack(side='right')
            for widget in (card,title,info):
                widget.bind('<ButtonPress-1>',lambda e,m=material,w=card:self.app.begin_material_drag(e,m,w))
                widget.bind('<B1-Motion>',self.app.material_motion)
                widget.bind('<ButtonRelease-1>',self.app.material_release)
                widget.bind('<Escape>',self.app.cancel_interaction)
            title.bind('<Return>',lambda _,m=material:self.select(m))
            hint(title,lambda m=material:self.describe(m),self.app.show_detail)
        if not self.rows:
            tk.Label(self.body,text='导入原始旋律后，分块、乐句和新旋律会出现在这里。',
                     wraplength=240,bg=p['panel'],fg=p['muted'],font=font()).pack(padx=12,pady=30)
        self.body.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.canvas.yview_moveto(view)

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
