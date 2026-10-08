"""Shared three-column workspace chrome; no music or service policy lives here."""
import tkinter as tk
from tkinter import ttk
from curve_theme import font, hint
from curve_cards import MaterialCards
from curve_canvas import CurveCanvas
from curve_icons import IconButton
from curve_raster import pixels
from curve_scrollbar import TransientScrollbar


class SecondaryTools(ttk.Frame):
    """Bound advanced controls without changing the single musical viewport."""
    def __init__(self, parent, app):
        super().__init__(parent, style='Curve.Panel.TFrame')
        self.pack_propagate(False)
        self.app = app
        self.compact = False
        self.saved_position = 0.
        self.positions = {}
        self.pending_position = None
        self.busy = False
        self.before_busy_position = 0.
        self.restore_timer = None
        self.next_busy_position = None
        self.canvas = tk.Canvas(self, width=1, height=1, highlightthickness=0,
                                takefocus=True, yscrollincrement=1)
        self.scrollbar = TransientScrollbar(self, app, self.canvas.yview)
        self.scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, style='Curve.Panel.TFrame')
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.attach(self.canvas)
        self.canvas.bind('<Configure>', self.layout)
        self.content.bind('<Configure>', self.layout)
        for event, fraction in (('<Home>', 0), ('<End>', 1)):
            self.canvas.bind(event, lambda _, f=fraction: self.canvas.yview_moveto(f))
        for event, delta in (('<Up>', -1), ('<Down>', 1), ('<Prior>', -6), ('<Next>', 6)):
            self.canvas.bind(event, lambda _, d=delta: self.canvas.yview_scroll(d*8, 'units'))
        self.focus_binding = app.root.bind('<FocusIn>', self.focused, add='+')
        self.bind('<Destroy>', self.destroyed)

    def layout(self, event=None):
        width = max(1, self.canvas.winfo_width())
        self.canvas.itemconfigure(self.window, width=width)
        requested = max(1, self.content.winfo_reqheight())
        page=getattr(self.app,'page',None)
        if page is None or not hasattr(page,'timeline'):return
        container=page.scene_container
        available=max(1,container.winfo_height())
        toolbar=page.timeline.tools.winfo_reqheight() if page.timeline.tools.winfo_manager() else 0
        bars=pixels(self.app.root,12)
        opened=bool(self.app.drawer_mode)
        height=min(requested,pixels(self.app.root,220),max(0,available-toolbar-bars-pixels(self.app.root,240))) if opened else 0
        self.configure(height=max(1,height))
        if height:
            self.place(x=0,y=available-height,relwidth=1,height=height)
            self.lift()
        else:self.place_forget()
        page.timeline.place(x=0,y=0,relwidth=1,relheight=0,height=max(1,available-height))
        scene=max(pixels(self.app.root,400),available-toolbar-bars)
        if page.timeline.scene_height!=scene:
            page.timeline.scene_height=scene
            page.timeline.draw()
        self.canvas.configure(height=max(1,height), bg=self.app.theme.colors['panel'],
                              scrollregion=(0, 0, width, requested), takefocus=requested>height)
        self.scrollbar.configure(takefocus=requested>height)
        if self.pending_position is not None and requested>height:
            self.canvas.yview_moveto(self.pending_position)
            self.pending_position = None

    def set_compact(self, compact):
        if self.compact and not compact: self.saved_position = self.canvas.yview()[0]
        elif compact and not self.compact: self.pending_position = self.saved_position
        self.compact = compact
        self.layout()

    def set_busy(self, busy):
        if busy == self.busy: return
        if busy:
            self.before_busy_position = self.canvas.yview()[0] if self.next_busy_position is None else self.next_busy_position
            self.next_busy_position=None
            self.pending_position = 0.
        else:
            self.pending_position = self.before_busy_position
        self.busy = busy
        self.layout()
        if self.restore_timer is not None:self.after_cancel(self.restore_timer)
        self.restore_timer=None
        if not busy:self.restore_timer=self.after_idle(self.restore_busy_scroll)

    def restore_busy_scroll(self):
        self.restore_timer=None
        # Settle newly restored rows before applying the normalized bookmark.
        self.content.update_idletasks()
        self.layout()
        self.canvas.yview_moveto(self.before_busy_position)

    def contains(self, widget):
        if not isinstance(widget, tk.Misc): return False
        while widget:
            if widget in (self.content, self.canvas, self.scrollbar): return True
            widget = widget.master
        return False

    def focused(self, event):
        # Tk also emits FocusIn for ancestors. Revealing an entire tall panel
        # after its child would scroll the actual focused control out again.
        if (self.contains(event.widget) and str(event.widget) == str(self.app.root.tk.call('focus'))
                and event.widget not in (self.canvas, self.scrollbar)):
            self.reveal(event.widget)

    def reveal(self, widget):
        if not self.canvas.winfo_ismapped(): return
        top = self.canvas.canvasy(0)
        start = top + widget.winfo_rooty() - self.canvas.winfo_rooty()
        end = start + widget.winfo_height()
        height = self.canvas.winfo_height()
        target = start if start < top else end - height if end > top + height else top
        total = max(1, float(self.canvas.cget('scrollregion').split()[3]))
        if target != top: self.canvas.yview_moveto(max(0, target) / total)

    def destroyed(self, event):
        if event.widget == self:
            if self.restore_timer is not None:self.after_cancel(self.restore_timer)
            try: self.app.root.unbind('<FocusIn>', self.focus_binding)
            except tk.TclError: pass  # Root teardown can retire the binding first.


def button(parent, text, command, style='Curve.TButton', **kw):
    return ttk.Button(parent, text=text, command=command, style=style, **kw)


def creation_tools(parent, page, app):
    """Native view controls share variables and commands, never music state."""
    row=ttk.Frame(parent,style='Curve.Panel.TFrame')
    ttk.Label(row,text='情绪搭建画板',style='Curve.Title.TLabel').pack(side='left')
    minus=IconButton(row,app,'minus','减一格',lambda:app.adjust_grid(-1),tip='减少一个四拍格；不会裁切音乐、留白或保护。')
    minus.pack(side='left',padx=2)
    ttk.Label(row,textvariable=page.grid_summary,style='Curve.Muted.TLabel').pack(side='left')
    plus=IconButton(row,app,'plus','加一格',lambda:app.adjust_grid(1),tip='增加一个四拍格；一次撤销可恢复。')
    plus.pack(side='left',padx=2)
    entry=ttk.Entry(row,textvariable=page.grid_count,style='Curve.TEntry')
    final=IconButton(page.dock_row,app,'generate','生成方案',lambda:app.safe(app.generate_recommendations),style='Curve.Primary.TButton',label=True)
    final.pack(side='right')
    advanced=IconButton(page.dock_row,app,'advanced','高级',app.toggle_advanced,label=True)
    advanced.pack(side='right',padx=4)
    return dict(creation_row=row,minus_button=minus,plus_button=plus,
                grid_entry=entry,resize_button=minus,final_button=final,advanced_button=advanced)


def select_creation_tools(page, advanced):
    for name,widget in page.creation_views[False].items():setattr(page,name,widget)


def build_page(page, parent, app, methods, emotions):
    ttk.Frame.__init__(page, parent, style='Curve.TFrame')
    page.app = app
    page.columnconfigure(1, weight=0, minsize=pixels(app.root,252))
    page.columnconfigure(2, weight=1, minsize=pixels(app.root,440))
    page.rowconfigure(0, weight=1)
    page.source_panel = ttk.Frame(page, style='Curve.Panel.TFrame', padding=8, width=pixels(app.root,180))
    page.source_panel.grid(row=0, column=0, sticky='nsew', padx=(0,8))
    page.source_panel.pack_propagate(False)
    row = ttk.Frame(page.source_panel, style='Curve.Panel.TFrame'); row.pack(fill='x')
    ttk.Label(row, text='旋律原料', style='Curve.Title.TLabel').pack(side='left')
    page.import_button = IconButton(row,app,'import','导入',lambda:app.safe(app.import_file))
    page.import_button.pack(side='right')
    page.all_materials_button=button(page.source_panel, '全部素材', lambda:app.filter_source(None))
    page.all_materials_button.pack(fill='x', pady=6)
    sources = page.source_frame = ttk.Frame(page.source_panel, style='Curve.Panel.TFrame'); sources.pack(fill='both', expand=True)
    page.source_list = tk.Listbox(sources, height=3, exportselection=False, activestyle='none', font=font(), borderwidth=0)
    page.source_list.pack(side='left', fill='both', expand=True)
    TransientScrollbar(sources,app,page.source_list.yview).pack(side='right',fill='y')
    page.source_list.configure(yscrollcommand=sources.winfo_children()[-1].set);sources.winfo_children()[-1].attach(page.source_list)
    page.source_list.bind('<<ListboxSelect>>', page.source_selected)
    page.source_list.bind('<Return>', lambda _:app.source_detail())
    hint(page.source_list,lambda:(app.resolve('source',app.selected_source_id) or {}).get('label','选择来源筛选素材；原始音乐保持不变。'),app.show_detail)
    page.source_notes = tk.Canvas(page.source_panel, height=62, highlightthickness=0)
    page.source_notes.pack(fill='x', pady=8)
    page.source_audition = button(page.source_panel, '试听原始旋律', lambda:app.safe(lambda:app.audition_target('source',app.selected_source_id)))
    page.source_audition.pack(fill='x')
    hint(page.source_audition, '选择来源只筛选；试听明确准备并播放该原始旋律。', app.show_detail)
    page.source_reminder=ttk.Label(page.source_panel,text='原始来源始终保留',style='Curve.Muted.TLabel')
    page.source_reminder.pack(anchor='w',pady=8)
    page.middle = ttk.Frame(page, style='Curve.Panel.TFrame', padding=8, width=pixels(app.root,252))
    page.middle.grid(row=0, column=1, sticky='nsew', padx=(0,8));page.middle.pack_propagate(False)
    ttk.Label(page.middle,text='音乐积木库',style='Curve.Title.TLabel').pack(anchor='w',pady=(2,6))
    # Kept as an unmounted compatibility holder; creation is in block menus.
    row=page.derive_row=ttk.Frame(page.middle,style='Curve.Panel.TFrame')
    page.method=tk.StringVar(value=methods[0][1])
    ttk.Combobox(row,textvariable=page.method,values=[v for _,v in methods],state='readonly',width=8,
                 style='Curve.TCombobox').pack(side='left',fill='x',expand=True)
    page.derive_button=IconButton(row,app,'plus','新旋律',app.derive_selected,label=True);page.derive_button.pack(side='right',padx=(4,0))
    hint(page.derive_button,'从所选素材生成独立新旋律；保留原素材、来源和已有放置。',app.show_detail)
    page.combo_panel=ttk.Frame(page.middle,style='Curve.Panel.TFrame')
    page.combo_text=ttk.Label(page.combo_panel,style='Curve.Muted.TLabel',wraplength=228);page.combo_text.pack(fill='x')
    page.combo_name=tk.StringVar(value='组合素材')
    page.combo_name.trace_add('write',lambda *_:app.invalidate_play_intent())
    ttk.Entry(page.combo_panel,textvariable=page.combo_name,style='Curve.TEntry').pack(fill='x')
    row=ttk.Frame(page.combo_panel,style='Curve.Panel.TFrame');row.pack(fill='x',pady=3)
    for text,fn in (('试听',app.audition_combo),('确认',app.confirm_combo),('取消',app.cancel_combo)):
        IconButton(row,app,{'试听':'play','确认':'combine','取消':'cancel'}[text],text,lambda f=fn:app.safe(f)).pack(side='left',padx=1)
    page.cards=MaterialCards(page.middle,app);page.cards.canvas.configure(width=1)
    page.cards.pack(fill='both',expand=True,pady=(6,0))
    page.right=ttk.Frame(page,style='Curve.Panel.TFrame',padding=8);page.right.grid(row=0,column=2,sticky='nsew')
    # Packed bottom first: the player always retains its own space.
    page.footer=ttk.Frame(page.right,style='Curve.Panel.TFrame',height=pixels(app.root,124))
    page.footer.pack(side='bottom',fill='x',pady=(6,0));page.footer.pack_propagate(False)
    page.fixed_stage_area=ttk.Frame(page.right,style='Curve.Panel.TFrame')
    page.fixed_stage_area.pack(side='bottom',fill='x')
    page.dock_row=ttk.Frame(page.fixed_stage_area,style='Curve.Panel.TFrame')
    page.dock_row.pack(side='bottom',fill='x')
    ttk.Label(page.dock_row,text='智能加工',style='Curve.Title.TLabel').pack(side='left',padx=(0,6))
    page.scene_container=ttk.Frame(page.right,style='Curve.Panel.TFrame')
    page.secondary_tools=SecondaryTools(page.scene_container,app)
    page.scene_container.bind('<Configure>',page.secondary_tools.layout)
    # Every stage constructor uses this actual native parent, not pack(in_).
    page.stage_area=page.secondary_tools.content
    page.advanced_row=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame')
    page.stage_anchor=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame',height=1)
    page.stage_anchor.pack(fill='x')
    page.history_panel=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame')
    page.history_list=tk.Listbox(page.history_panel,height=2,exportselection=False,font=font(),borderwidth=0)
    page.history_list.pack(fill='x');page.history_list.bind('<<ListboxSelect>>',app.history_selected)
    history_bar=TransientScrollbar(page.history_panel,app,page.history_list.yview);history_bar.pack(side='right',fill='y',before=page.history_list);page.history_list.configure(yscrollcommand=history_bar.set);history_bar.attach(page.history_list)
    page.grid_count=tk.StringVar(value='8')
    page.grid_summary=tk.StringVar(value='8格 · 32拍')
    creation=creation_tools(page.right,page,app)
    page.creation_views={False:creation,True:creation}
    select_creation_tools(page,False)
    page.creation_row.pack(fill='x')
    page.memory_label=ttk.Label(page.creation_row,style='Curve.Muted.TLabel',takefocus=True)
    page.memory_label.pack(side='right',padx=4)
    hint(page.memory_label,app.current_memory_description,app.show_detail)
    page.memory_label.bind('<Button-1>',lambda _:app.show_detail(app.current_memory_description()))
    page.scene_container.pack(fill='both',expand=True,pady=(2,0))
    page.timeline=CurveCanvas(page.scene_container,app,stage_parent=page.advanced_row)
    page.timeline.place(x=0,y=0,relwidth=1,relheight=1)
    page.gap_panel=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame')
    page.gap_label=ttk.Label(page.gap_panel,style='Curve.Muted.TLabel',takefocus=True);page.gap_label.pack(side='left')
    hint(page.gap_label,lambda:gap_description(app),app.show_detail)
    page.gap_generate=button(page.gap_panel,'补齐此处',lambda:app.safe(app.generate_recommendations),padding=(-pixels(app.root,5),0))
    page.gap_generate.pack(side='left',padx=2)
    button(page.gap_panel,'设为留白',lambda:app.safe(app.mark_selected_blank),padding=(-pixels(app.root,5),0)).pack(side='left')
    page.emotion_panel=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame')
    page.emotion_title=ttk.Label(page.emotion_panel,style='Curve.Muted.TLabel')
    page.emotion_title.pack_forget()
    page.emotion_title.grid(row=0,column=0,columnspan=6,sticky='w')
    page.emotion_buttons={}
    for index,(emotion,text) in enumerate(emotions.items()):
        b=button(page.emotion_panel,text,lambda e=emotion:app.set_emotion(e),padding=(-pixels(app.root,8),0))
        b.grid(row=1,column=index,sticky='ew',padx=1)
        page.emotion_buttons[emotion]=b
        hint(b,lambda e=emotion:'仅修改所选放置的'+emotions[e]+'情绪；不改基础素材。',app.show_detail)
    page.empty_workspace=ttk.Frame(page.timeline.canvas,style='Curve.Panel.TFrame')


def gap_description(app):
    gap=app.selected_gap()
    return (f'空缺范围 {gap["start_tick"]/480+1:g}–{gap["end_tick"]/480+1:g}拍 · 精确ID {gap["id"]}' if gap else '默认处理全部空缺。')


def build_chrome(app):
    root=app.root
    app.shell=ttk.Frame(root,style='Curve.TFrame',padding=8);app.shell.pack(fill='both',expand=True)
    app.shell.columnconfigure(0,weight=1);app.shell.rowconfigure(1,weight=1)
    header=ttk.Frame(app.shell,style='Curve.TFrame',height=pixels(root,48))
    header.grid(row=0,column=0,sticky='ew',pady=(0,8));header.pack_propagate(False)
    app.brand_button=IconButton(header,app,'blocks','EmoBlocks',lambda:None,style='Curve.Header.TButton')
    app.brand_button.pack(side='left')
    ttk.Label(header,text='EmoBlocks',style='Curve.Brand.TLabel').pack(side='left',padx=(0,10))
    app.file_menu=tk.Menu(root,tearoff=False)
    for text,fn in (('新建',app.new_project),('打开',app.open_project),('保存快照',app.save_project),('导入旋律',app.import_file)):
        app.file_menu.add_command(label=text,command=lambda f=fn:app.safe(f))
    app.file_button=ttk.Menubutton(header,text='文件',menu=app.file_menu,style='Curve.TMenubutton');app.file_button.pack_forget()
    app.file_actions=[]
    for icon,text,fn in (('new','新建',app.new_project),('open','打开',app.open_project),('save','保存快照',app.save_project)):
        b=IconButton(header,app,icon,text,lambda f=fn:app.safe(f),style='Curve.Header.TButton')
        b.pack(side='left',padx=1);app.file_actions.append((text,b))
    app.edit_buttons=[]
    for text,fn in (('撤销',app.undo),('重做',app.redo)):
        b=IconButton(header,app,'undo' if text=='撤销' else 'redo',text,lambda f=fn:app.safe(f),style='Curve.Header.TButton')
        b.pack(side='left',padx=2);app.edit_buttons.append((text,b))
    app.project_label=ttk.Label(header,text='未命名工程',style='Curve.TLabel');app.project_label.pack(side='left',padx=4)
    hint(app.project_label,lambda:app.state_data.get('saved_path') or '未命名工程',app.show_detail)
    app.save_label=ttk.Label(header,style='Curve.TLabel');app.save_label.pack(side='left',padx=8)
    hint(app.save_label,lambda:getattr(app,'saved_description',app.save_label.cget('text')),app.show_detail)
    app.theme_button=IconButton(header,app,'moon','深色',app.toggle_theme,tip=lambda:'切换为浅色模式' if app.theme.name=='dark' else '切换为深色模式',style='Curve.Header.TButton')
    app.theme_button.pack(side='right',padx=2)
    app.collapse_button=IconButton(header,app,'sidebar','旋律原料',app.toggle_sources,tip=lambda:'展开旋律原料' if app.source_user_collapsed or not app.page.source_panel.winfo_manager() else '收起旋律原料')
    app.collapse_button.pack(side='left',before=app.brand_button,padx=(0,4))
    app.history_button=button(header,'历史',app.toggle_history);app.history_button.pack(side='right',padx=2)


def build_player(app):
    footer=app.page.footer
    app.status_text=tk.StringVar(value='导入旋律，开始创作。')
    app.detail_text=tk.StringVar(value='点击仅选择；明确试听才播放。')
    app.status_label=ttk.Label(app.page.fixed_stage_area,textvariable=app.status_text,style='Curve.Panel.TLabel',takefocus=True)
    app.status_label.pack(fill='x',before=app.page.dock_row)
    hint(app.status_label,app.status_description,app.show_detail)
    app.detail_row=ttk.Frame(app.page.stage_area,style='Curve.Panel.TFrame')
    app.detail_label=tk.Text(app.detail_row,height=2,wrap='word',font=font(),borderwidth=0,highlightthickness=0,state='disabled')
    app.detail_label.pack(side='left',fill='both',expand=True)
    detail_bar=TransientScrollbar(app.detail_row,app,app.detail_label.yview)
    detail_bar.pack(side='right',fill='y');app.detail_label.configure(yscrollcommand=detail_bar.set);detail_bar.attach(app.detail_label)
    app.detail_button=IconButton(app.page.dock_row,app,'details','详情',app.toggle_details,label=True)
    app.detail_button.pack(side='left')
    app.plan_button=IconButton(app.page.dock_row,app,'recommend','方案',lambda:app.toggle_drawer('plan'),label=True)
    app.plan_button.pack(side='left',padx=2)
    from curve_player_ui import build_transport
    build_transport(app,footer)
    app.export_row=ttk.Frame(app.page.stage_area,style='Curve.Panel.TFrame')
    app.export_receipt=tk.Text(app.export_row,height=1,width=1,wrap='none',font=font(),borderwidth=0,highlightthickness=0,state='disabled')
    app.export_summary=ttk.Label(app.export_row,style='Curve.Muted.TLabel')
    app.export_summary.pack(side='left',fill='x',expand=True)
    hint(app.export_summary,lambda:app.export_receipt.get('1.0','end').strip(),app.show_detail)
    app.export_folder_button=button(app.export_row,'打开位置',app.open_export_folder,style='Curve.Small.TButton');app.export_folder_button.pack(side='right')
