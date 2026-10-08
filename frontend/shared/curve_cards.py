"""Equal-sized material cards and independently usable phrase child cards."""
import copy
import math
import tkinter as tk
from tkinter import ttk
from curve_theme import font, hint, rounded
from curve_visuals import TYPE_COLORS, TYPE_NAMES, DATA_INK, material_type, stable_number, draw_notes, source_badge
from curve_icons import CardIconButton
from curve_scrollbar import TransientScrollbar
from curve_raster import pixels


class MaterialCards(ttk.Frame):
    CARD_HEIGHT = 96

    def __init__(self, parent, app):
        super().__init__(parent,style='Curve.Panel.TFrame')
        self.app = app
        self.CARD_HEIGHT=pixels(app.root,96)
        self.gap=pixels(app.root,8)
        self.expanded = set()
        self.rows = {}
        self.row_versions = {}
        self.pending_render = None
        self.last_view = None
        self.rendering = False
        self.materials = []
        self.canvas = tk.Canvas(self,highlightthickness=0,takefocus=True)
        self.canvas.pack(side='left',fill='both',expand=True)
        bar = TransientScrollbar(self,app,self.canvas.yview)
        bar.pack(side='right',fill='y')
        self.scrollbar = bar
        bar.attach(self.canvas)
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
        parents={m['id']:m for m in self.materials if m['kind']=='phrase'}
        originals={(m['provenance'].get('source_id'),m['provenance'].get('source_start_tick'),m['length_ticks'])
                   for m in self.materials if m['kind']=='block' and not m['phrase_id'] and not m['generation']}
        for m in self.materials:
            if m['kind']=='phrase':continue
            parent=parents.get(m['phrase_id'])
            if parent and not parent['generation']:
                key=(m['provenance'].get('source_id'),m['provenance'].get('source_start_tick'),m['length_ticks'])
                if key in originals:continue
            yield m,bool(parent and parent['generation'])

    def locate(self, ident):
        visible=list(self.visible_materials())
        index=next((i for i,(m,_) in enumerate(visible) if m['id']==ident),None)
        if index is not None:
            total=max(1,len(visible)*(self.CARD_HEIGHT+self.gap))
            self.canvas.yview_moveto(index*(self.CARD_HEIGHT+self.gap)/total)
            self.render()

    def context_menu(self, event, material):
        from curve_ui import METHODS
        keyboard=getattr(event,'keysym','')=='F10'
        x=event.widget.winfo_rootx()+12 if keyboard else event.x_root
        y=event.widget.winfo_rooty()+event.widget.winfo_height() if keyboard else event.y_root
        self.select(material)
        previous=getattr(self,'context',None)
        if previous and previous.winfo_exists():previous.destroy()
        menu=tk.Menu(self.app.root,tearoff=False)
        generation=tk.Menu(menu,tearoff=False)
        for method,label in METHODS:
            generation.add_command(label=label,state='normal' if self.app.editable else 'disabled',
                command=lambda ident=material['id'],method=method:self.app.derive_selected(ident,method))
        menu.add_cascade(label='拓展积木',menu=generation)
        menu.add_command(label='试听',command=lambda:self.app.safe(lambda:self.app.audition_target('material',material['id'])))
        self.context=menu
        menu.tk_popup(x,y)
        menu.grab_release()
        return 'break'

    def render(self, materials=None):
        if materials is not None:
            self.materials = materials
        if self.rendering:return
        self.rendering = True
        try:self.render_rows()
        finally:self.rendering = False

    def render_rows(self):
        visible = list(self.visible_materials())
        stride = self.CARD_HEIGHT+self.gap
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
            parent=next((v for v in self.materials if v['id']==material['phrase_id']),None)
            version = (material,child,self.app.theme.name,selected,expandable,ident in self.expanded,parent)
            left = 4
            old_version = self.row_versions.get(ident)
            dragging = drag and ident==drag['material']['id'] and ident in self.rows
            if dragging and (old_version[0]!=material or old_version[2]!=self.app.theme.name):
                self.app.cancel_interaction();drag = None;dragging = False
            if old_version==version or dragging:
                self.rows[ident].place_configure(x=left,y=index*stride+4,width=max(1,width-left-4))
                continue
            if ident in self.rows:self.rows.pop(ident).destroy()
            self.row_versions[ident] = copy.deepcopy(version)
            category = material_type(material,self.materials)
            surface = TYPE_COLORS[category]
            card = tk.Canvas(self.body,bg=p['panel'],height=self.CARD_HEIGHT,highlightthickness=0,borderwidth=0)
            card.place(x=left,y=index*stride+4,width=max(1,width-left-4),height=self.CARD_HEIGHT)
            self.rows[ident] = card
            content = tk.Frame(card,bg=surface)
            window = card.create_window(8,3,anchor='nw',window=content,height=self.CARD_HEIGHT-pixels(self.app.root,6))
            def background(event,canvas=card,window=window,fill=surface,selected=selected):
                canvas.itemconfigure(window,width=max(1,event.width-16))
                canvas.delete('surface')
                rounded(canvas,(1,1,event.width-4,self.CARD_HEIGHT-4),fill,
                        p['accent'] if selected else p['line'],tags='surface')
                canvas.tag_lower('surface')
            card.bind('<Configure>',background)
            prefix = ''
            label = stable_number(material)
            title = tk.Canvas(content,height=pixels(self.app.root,28),width=1,bg=surface,highlightthickness=0,takefocus=True,cursor='hand2')
            content.columnconfigure(0,weight=1)
            title.grid(row=0,column=0,sticky='ew',padx=(4,2))
            def shorten(event,widget=title,text=prefix+label):
                from tkinter import font as tkfont
                measure=tkfont.Font(root=widget,font=font(12,True)).measure
                value=text
                while len(value)>1 and measure(value+'…')>widget.winfo_width()-4:value=value[:-1]
                widget.delete('all')
                widget.create_text(1,widget.winfo_height()/2,anchor='w',text=value+('…' if value!=text else ''),fill=DATA_INK,font=font(12,True),tags='card-title')
                if widget.focus_get()==widget:widget.create_rectangle(0,0,max(1,widget.winfo_width()-1),max(1,widget.winfo_height()-1),outline=self.app.theme.colors['accent'],width=1,tags='card-focus')
            title.bind('<Configure>',shorten);title.bind('<FocusIn>',shorten,add='+');title.bind('<FocusOut>',shorten,add='+')
            kind=TYPE_NAMES[category]
            parent=next((v for v in self.materials if v['id']==material['phrase_id']),None)
            group=('Bridge' if category=='bridge' else '新旋律')+' · '+stable_number(parent) if child and parent else ''
            info=tk.Canvas(content,height=pixels(self.app.root,24),width=1,bg=surface,highlightthickness=0)
            info.grid(row=1,column=0,sticky='ew',padx=4)
            badge=source_badge(material,self.app.state_data['project'])
            def type_label(event,widget=info,text=f'{material["length_ticks"]/480:g}拍'+(' · '+(group or badge) if group or badge else '')):
                widget.delete('all');widget.create_text(1,widget.winfo_height()/2,anchor='w',text=text,fill=DATA_INK,font=font(10),tags='card-type')
            info.bind('<Configure>',type_label)
            controls=tk.Frame(content,bg=surface);controls.grid(row=0,column=1,rowspan=3,sticky='ns',padx=2)
            b=CardIconButton(controls,self.app,'play','试听',
                         command=lambda m=material:self.app.safe(lambda:self.app.audition_target('material',m['id'])))
            b.pack(side='top')
            hint(b,'明确试听此素材；准备完成后仅有效播放意图可开始。',self.app.show_detail)
            thumb=tk.Canvas(content,height=pixels(self.app.root,28),width=80,bg=surface,highlightthickness=0)
            thumb.material_thumbnail=True
            thumb.grid(row=2,column=0,sticky='ew',padx=4,pady=0)
            def notes(event,c=thumb,m=material):
                c.delete('all')
                draw_notes(c,(2,2,event.width-2,c.winfo_height()-2),m['notes'],0,m['length_ticks'],DATA_INK,tags='material-note')
            thumb.bind('<Configure>',notes)
            if expandable:
                ttk.Button(controls,text='收起' if ident in self.expanded else '展开',style='Curve.Compact.TButton',
                           command=lambda i=ident:self.toggle(i)).pack(side='bottom')
            for widget in (card,title,info,thumb):
                widget.bind('<ButtonPress-1>',lambda e,m=material,w=card:self.app.begin_material_drag(e,m,w))
                widget.bind('<B1-Motion>',self.app.material_motion)
                widget.bind('<ButtonRelease-1>',self.app.material_release)
                widget.bind('<Escape>',self.app.cancel_interaction)
            import ui_platform
            for widget in (card,title,info,thumb):
                for event in ui_platform.CONTEXT_EVENTS:
                    widget.bind(event,lambda e,m=material:self.context_menu(e,m))
                widget.bind('<Shift-F10>',lambda e,m=material:self.context_menu(e,m))
            title.bind('<Return>',lambda _,m=material:self.select(m))
            hint(title,lambda m=material:self.describe(m),self.app.show_detail)
        if not visible:
            self.canvas.itemconfigure(self.window,height=max(100,self.canvas.winfo_height()))
            if self.empty_label is None:
                self.empty_label = tk.Label(self.body,text='导入旋律，开始逐块创作。',font=font())
            self.empty_label.configure(wraplength=max(1,width-24),bg=p['panel'],fg=p['muted'])
            self.empty_label.place(x=12,y=30,width=max(1,width-24))

    def describe(self, material):
        source = material['provenance'].get('source_id','')
        original=next((s for s in self.app.state_data['project']['sources'] if s['id']==source),None)
        source=(original['label']+' · '+str(original.get('provenance',{}).get('path',''))) if original else source
        parent = next((m['label'] for m in self.materials if m['id']==material['phrase_id']),material['phrase_id'] or '')
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
            row.delete('playing-card')
            from curve_playback_ui import same_card
            material=next((m for m in self.materials if m['id']==ident),None)
            if material and self.app.player.status()[1] in ('playing','paused') and same_card(self.app.playing_target,material):
                row.create_line(8,self.CARD_HEIGHT-8,row.winfo_width()-10,self.CARD_HEIGHT-8,fill=self.app.theme.colors['accent'],width=2,dash=(4,2),tags='playing-card')

    def clear_drop_target(self):
        for row in self.rows.values():row.delete('combine-preview')

    def show_drop_target(self,ident,side):
        self.clear_drop_target()
        row=self.rows.get(ident)
        if row:
            x=3 if side=='left' else row.winfo_width()-4
            row.create_line(x,5,x,self.CARD_HEIGHT-5,fill=self.app.theme.colors['accent'],width=3,tags='combine-preview')

    def at_root(self, x, y):
        if not (self.canvas.winfo_rootx()<=x<self.canvas.winfo_rootx()+self.canvas.winfo_width()
                and self.canvas.winfo_rooty()<=y<self.canvas.winfo_rooty()+self.canvas.winfo_height()):
            return None
        for ident,row in self.rows.items():
            if row.winfo_rooty()<=y<row.winfo_rooty()+row.winfo_height():
                return ident,'left' if x<row.winfo_rootx()+row.winfo_width()/2 else 'right'
        return None
