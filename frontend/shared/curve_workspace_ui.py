"""Shared three-column workspace chrome; no music or service policy lives here."""
import tkinter as tk
from tkinter import ttk
from curve_theme import font, hint
from curve_cards import MaterialCards
from curve_canvas import CurveCanvas
from curve_icons import IconButton
from curve_raster import pixels
from curve_scrollbar import TransientScrollbar


def button(parent, text, command, style='Curve.TButton', **kw):
    return ttk.Button(parent, text=text, command=command, style=style, **kw)


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
    ttk.Label(row, text='原始来源', style='Curve.Title.TLabel').pack(side='left')
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
    ttk.Label(page.middle,text='旋律素材',style='Curve.Title.TLabel').pack(anchor='w',pady=(2,6))
    row=page.derive_row=ttk.Frame(page.middle,style='Curve.Panel.TFrame');row.pack(fill='x')
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
    page.footer=ttk.Frame(page.right,style='Curve.Panel.TFrame',height=pixels(app.root,138))
    page.footer.pack(side='bottom',fill='x',pady=(6,0));page.footer.pack_propagate(False)
    page.stage_area=ttk.Frame(page.right,style='Curve.Panel.TFrame')
    page.stage_area.pack(side='bottom',fill='x')
    page.advanced_row=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame')
    page.stage_anchor=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame',height=1)
    page.stage_anchor.pack(fill='x')
    page.history_panel=ttk.Frame(page.stage_area,style='Curve.Panel.TFrame')
    page.history_list=tk.Listbox(page.history_panel,height=2,exportselection=False,font=font(),borderwidth=0)
    page.history_list.pack(fill='x');page.history_list.bind('<<ListboxSelect>>',app.history_selected)
    history_bar=TransientScrollbar(page.history_panel,app,page.history_list.yview);history_bar.pack(side='right',fill='y',before=page.history_list);page.history_list.configure(yscrollcommand=history_bar.set);history_bar.attach(page.history_list)
    row=page.creation_row=ttk.Frame(page.right,style='Curve.Panel.TFrame');row.pack(fill='x')
    ttk.Label(row,text='创作画布',style='Curve.Title.TLabel').pack(side='left')
    ttk.Label(row,text='四拍格',style='Curve.Muted.TLabel').pack(side='left',padx=(8,3))
    page.grid_count=tk.StringVar(value='8')
    page.grid_summary=tk.StringVar(value='8格 · 32拍')
    page.minus_button=IconButton(row,app,'minus','减一格',lambda:app.adjust_grid(-1),tip='减少一个四拍格；不会裁切音乐、留白或保护。')
    page.minus_button.pack(side='left',padx=2)
    ttk.Label(row,textvariable=page.grid_summary,style='Curve.Muted.TLabel').pack(side='left')
    page.plus_button=IconButton(row,app,'plus','加一格',lambda:app.adjust_grid(1),tip='增加一个四拍格；一次撤销可恢复。')
    page.plus_button.pack(side='left',padx=2)
    # Legacy callable resize uses grid_count; there is no editable count field.
    page.grid_entry=ttk.Entry(row,textvariable=page.grid_count,style='Curve.TEntry')
    page.resize_button=page.minus_button
    page.final_button=IconButton(row,app,'generate','生成方案',lambda:app.safe(app.generate_recommendations),style='Curve.Primary.TButton',label=True)
    page.final_button.pack(side='right')
    # Advanced is always reachable, independently of gap selection.
    page.advanced_button=button(row,'高级',app.toggle_advanced,style='Curve.TButton')
    page.advanced_button.pack(side='right',padx=4)
    page.memory_label=ttk.Label(page.right,style='Curve.Muted.TLabel',takefocus=True)
    page.memory_label.pack(fill='x',pady=(2,0))
    hint(page.memory_label,app.current_memory_description,app.show_detail)
    page.memory_label.bind('<Button-1>',lambda _:app.show_detail(app.current_memory_description()))
    page.timeline=CurveCanvas(page.right,app,stage_parent=page.advanced_row);page.timeline.pack(fill='both',expand=True,pady=(2,0))
    page.gap_panel=ttk.Frame(page.timeline.tools,style='Curve.Panel.TFrame')
    page.gap_label=ttk.Label(page.gap_panel,style='Curve.Muted.TLabel',takefocus=True);page.gap_label.pack(side='left')
    hint(page.gap_label,lambda:gap_description(app),app.show_detail)
    button(page.gap_panel,'生成此处方案',lambda:app.safe(app.generate_recommendations),padding=(-pixels(app.root,5),0)).pack(side='left',padx=2)
    button(page.gap_panel,'设为留白',lambda:app.safe(app.mark_selected_blank),padding=(-pixels(app.root,5),0)).pack(side='left')
    page.emotion_panel=ttk.Frame(page.timeline.tools,style='Curve.Panel.TFrame')
    page.emotion_title=ttk.Label(page.emotion_panel,style='Curve.Muted.TLabel')
    page.emotion_buttons={}
    for index,(emotion,text) in enumerate(emotions.items()):
        b=button(page.emotion_panel,text,lambda e=emotion:app.set_emotion(e),padding=(-pixels(app.root,5),0))
        b.grid(row=0,column=index+1,sticky='ew',padx=1)
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
    app.collapse_button=button(header,'收起来源',app.toggle_sources);app.collapse_button.pack(side='right',padx=2)
    app.history_button=button(header,'历史',app.toggle_history);app.history_button.pack(side='right',padx=2)


def build_player(app):
    footer=app.page.footer
    app.status_text=tk.StringVar(value='导入旋律，开始创作。')
    app.detail_text=tk.StringVar(value='点击仅选择；明确试听才播放。')
    app.status_label=ttk.Label(app.page.stage_area,textvariable=app.status_text,style='Curve.Panel.TLabel',takefocus=True)
    app.status_label.pack(fill='x',before=app.page.stage_anchor)
    hint(app.status_label,app.status_description,app.show_detail)
    app.detail_row=ttk.Frame(app.page.stage_area,style='Curve.Panel.TFrame')
    app.detail_label=tk.Text(app.detail_row,height=2,wrap='word',font=font(),borderwidth=0,highlightthickness=0,state='disabled')
    app.detail_label.pack(side='left',fill='both',expand=True)
    detail_bar=TransientScrollbar(app.detail_row,app,app.detail_label.yview)
    detail_bar.pack(side='right',fill='y');app.detail_label.configure(yscrollcommand=detail_bar.set);detail_bar.attach(app.detail_label)
    app.detail_button=button(app.page.stage_area,'详情',app.toggle_details,style='Curve.Small.TButton')
    app.detail_button.place(relx=1.,y=0,anchor='ne')
    from curve_player_ui import build_transport
    build_transport(app,footer)
    app.export_row=ttk.Frame(app.footer_top,style='Curve.Panel.TFrame')
    app.export_receipt=tk.Text(app.export_row,height=1,width=1,wrap='none',font=font(),borderwidth=0,highlightthickness=0,state='disabled')
    app.export_summary=ttk.Label(app.export_row,style='Curve.Muted.TLabel')
    app.export_summary.pack(side='left',fill='x',expand=True)
    hint(app.export_summary,lambda:app.export_receipt.get('1.0','end').strip(),app.show_detail)
    app.export_folder_button=button(app.export_row,'打开位置',app.open_export_folder,style='Curve.Small.TButton');app.export_folder_button.pack(side='right')
