"""P2 desktop UI. The frozen Facade owns every musical transaction.

The provider is imported only on construction without an injected controller,
or when a pure preparation service is explicitly requested. No legacy editor
or planner is instantiated. Workers never access Tk or the active controller.
"""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog

import ui_platform
from audio_player import WavePlayer
from file_drop import FileDrop
from scroll_input import touchpad_deltas, scroll_canvas_pixels
from curve_theme import Theme, font, hint
from curve_cards import MaterialCards
from curve_canvas import CurveCanvas, snap_tick

METHODS = [('variant','局部变化'),('answer','回答句'),('counter','副旋律规则'),
           ('rhythm','节奏重组'),('develop','动机发展'),('density','疏密变化')]


def _provider():
    return importlib.import_module('curve_workflow')


def snapshot_key(kind, snapshot):
    payload = json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    return kind+':'+hashlib.sha256(payload.encode('utf-8')).hexdigest()


class CurvePage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent,style='Curve.TFrame')
        self.app = app
        self.columnconfigure(1,weight=0,minsize=280)
        self.columnconfigure(2,weight=1,minsize=380)
        self.rowconfigure(0,weight=1)
        self.source_panel = ttk.Frame(self,style='Curve.Panel.TFrame',padding=10,width=210)
        self.source_panel.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        self.source_panel.grid_propagate(False)
        ttk.Label(self.source_panel,text='原始来源',style='Curve.Title.TLabel').pack(anchor='w',pady=(0,8))
        self.source_list = tk.Listbox(self.source_panel,height=6,exportselection=False,activestyle='none',font=font())
        self.source_list.pack(fill='x')
        self.source_list.bind('<<ListboxSelect>>',self.source_selected)
        self.source_list.bind('<Return>',lambda _:app.source_detail())
        self.source_notes = tk.Canvas(self.source_panel,height=110,highlightthickness=0)
        self.source_notes.pack(fill='x',pady=10)
        for text,fn in (('准备整体试听',lambda:app.prepare_target('source',app.selected_source_id)),
                        ('播放原始旋律',lambda:app.play_target('source',app.selected_source_id)),
                        ('查看完整来源',app.source_detail)):
            ttk.Button(self.source_panel,text=text,style='Curve.TButton',command=lambda f=fn:app.safe(f)).pack(fill='x',pady=3)
        ttk.Label(self.source_panel,text='保留原始来源\n新旋律进入中栏',style='Curve.Muted.TLabel').pack(anchor='w',pady=12)
        self.middle = ttk.Frame(self,style='Curve.Panel.TFrame',padding=8,width=300)
        self.middle.grid(row=0,column=1,sticky='nsew',padx=(0,8))
        self.middle.grid_propagate(False)
        ttk.Label(self.middle,text='旋律素材',style='Curve.Title.TLabel').pack(anchor='w',pady=(0,6))
        row = ttk.Frame(self.middle,style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.method = tk.StringVar(value=METHODS[0][1])
        box = ttk.Combobox(row,textvariable=self.method,values=[v for _,v in METHODS],state='readonly',width=10,style='Curve.TCombobox')
        box.pack(side='left',fill='x',expand=True)
        self.derive_button = ttk.Button(row,text='生成新旋律',style='Curve.TButton',command=app.derive_selected)
        self.derive_button.pack(side='right',padx=(4,0))
        hint(self.derive_button,'对当前素材生成独立新旋律；不改变已选素材或已有放置。',app.show_detail)
        self.combo_panel = ttk.Frame(self.middle,style='Curve.Panel.TFrame')
        self.combo_text = ttk.Label(self.combo_panel,style='Curve.Muted.TLabel',wraplength=260)
        self.combo_text.pack(fill='x',pady=4)
        self.combo_name = tk.StringVar(value='组合素材')
        ttk.Entry(self.combo_panel,textvariable=self.combo_name,style='Curve.TEntry').pack(fill='x')
        buttons = ttk.Frame(self.combo_panel,style='Curve.Panel.TFrame')
        buttons.pack(fill='x',pady=4)
        for text,fn in (('试听准备',app.prepare_combo),('确认',app.confirm_combo),('取消',app.cancel_combo)):
            ttk.Button(buttons,text=text,style='Curve.TButton',command=lambda f=fn:app.safe(f)).pack(side='left',padx=2)
        self.cards = MaterialCards(self.middle,app)
        self.cards.pack(fill='both',expand=True,pady=(6,0))
        self.right = ttk.Frame(self,style='Curve.Panel.TFrame',padding=10)
        self.right.grid(row=0,column=2,sticky='nsew')
        row = ttk.Frame(self.right,style='Curve.Panel.TFrame')
        row.pack(fill='x')
        ttk.Label(row,text='强度画布',style='Curve.Title.TLabel').pack(side='left')
        ttk.Label(row,text='四拍格',style='Curve.Muted.TLabel').pack(side='left',padx=(12,4))
        self.grid_count = tk.StringVar(value='8')
        self.grid_entry = ttk.Spinbox(row,from_=1,to=999,textvariable=self.grid_count,width=4,style='Curve.TSpinbox')
        self.grid_entry.pack(side='left')
        self.grid_entry.bind('<Return>',lambda _:app.resize_grid())
        self.resize_button = ttk.Button(row,text='更新长度',style='Curve.TButton',command=app.resize_grid)
        self.resize_button.pack(side='right')
        self.history_panel = ttk.Frame(self.right,style='Curve.Panel.TFrame')
        ttk.Label(self.history_panel,text='已有成品 · 选择后明确播放',style='Curve.Muted.TLabel').pack(anchor='w')
        self.history_list = tk.Listbox(self.history_panel,height=3,exportselection=False,font=font())
        self.history_list.pack(fill='x')
        self.history_list.bind('<<ListboxSelect>>',app.history_selected)
        controls = ttk.Frame(self.history_panel,style='Curve.Panel.TFrame')
        controls.pack(fill='x')
        self.export_buttons = {}
        for format_,text in (('wav','导出 WAV'),('mid','导出 MIDI'),('mmp','导出 MMP')):
            b = ttk.Button(controls,text=text,style='Curve.TButton',command=lambda f=format_:app.export_history(f))
            b.pack(side='left',padx=2,pady=4)
            self.export_buttons[format_] = b
        self.timeline = CurveCanvas(self.right,app)
        self.timeline.pack(fill='both',expand=True,pady=(10,4))
        self.final_button = ttk.Button(self.right,text='整曲生成尚未接通',style='Curve.TButton',state='disabled')
        self.timeline.pack_forget()
        self.final_button.pack(side='bottom',anchor='e')
        ttk.Label(self.right,text='当前支持素材创作与试听；整曲生成尚未接通。',style='Curve.Muted.TLabel',wraplength=360).pack(side='bottom',anchor='w')
        self.timeline.pack(fill='both',expand=True,pady=(10,4))

    def source_selected(self, event=None):
        ids = self.source_list.curselection()
        sources = (self.app.state_data['project'] or {}).get('sources',[])
        if ids and ids[0]<len(sources):
            self.app.select_target('source',sources[ids[0]]['id'])
            self.app.source_detail()
            self.draw_source()

    def draw_source(self):
        c = self.source_notes
        p = self.app.theme.colors
        c.configure(bg=p['inset'])
        c.delete('all')
        source = next((s for s in (self.app.state_data['project'] or {}).get('sources',[])
                       if s['id']==self.app.selected_source_id),None)
        if not source:
            c.create_text(12,35,anchor='w',text='未导入来源',fill=p['muted'],font=font(9))
            return
        width = max(100,c.winfo_width())-16
        notes = source['notes']
        low = min((n['pitch'] for n in notes),default=60)
        high = max((n['pitch'] for n in notes),default=72)
        for note in notes:
            x = 8+note['start_tick']/source['length_ticks']*width
            end = 8+(note['start_tick']+note['duration_tick'])/source['length_ticks']*width
            y = 85-(note['pitch']-low)/max(1,high-low)*64
            c.create_line(x,y,max(x+1,end),y,fill=p['muted'],width=2)
        c.create_text(8,101,anchor='w',text=f'{source["length_ticks"]/480:g} 拍 · 原始音符',fill=p['muted'],font=font(8))


class CurveApplication:
    def __init__(self, root, controller=None):
        self.root = root
        self.controller = _provider().Controller() if controller is None else controller
        self.theme = Theme(root)
        self.player = WavePlayer()
        self.closed = False
        self.jobs = {}
        self.messages = queue.Queue()
        self.ready_assets = {}
        self.playing_target = None
        self.play_duration = 0.
        self.seek_active = False
        self.selected_target = None
        self.selected_source_id = None
        self.selected_material_id = None
        self.selected_history_id = None
        self.combo_inputs = []
        self.material_drag = None
        self.card_scroll_timer = None
        self.status_error = False
        self.source_user_collapsed = None
        self.state_data = self.controller.state()
        root.title('EmoBlocks · 旋律与强度')
        root.minsize(1020,700)
        root.geometry('1280x800')
        self.shell = ttk.Frame(root,style='Curve.TFrame',padding=12)
        self.shell.pack(fill='both',expand=True)
        self.shell.columnconfigure(0,weight=1)
        self.shell.rowconfigure(1,weight=1)
        header = ttk.Frame(self.shell,style='Curve.TFrame')
        header.grid(row=0,column=0,sticky='ew',pady=(0,10))
        brand = ttk.Frame(header,style='Curve.TFrame')
        brand.pack(fill='x')
        ttk.Label(brand,text='EmoBlocks',style='Curve.TLabel',font=font(18,True)).pack(side='left',padx=(0,12))
        self.save_label = ttk.Label(brand,style='Curve.TLabel')
        self.save_label.pack(side='left')
        actions = ttk.Frame(header,style='Curve.TFrame')
        actions.pack(fill='x',pady=(6,0))
        self.edit_buttons = []
        for text,fn,editable in (('新建',self.new_project,False),('打开',self.open_project,False),
                                 ('保存快照',self.save_project,True),('导入旋律',self.import_file,True),
                                 ('撤销',self.undo,True),('重做',self.redo,True)):
            b = ttk.Button(actions,text=text,style='Curve.TButton',command=lambda f=fn:self.safe(f))
            b.pack(side='left',padx=2)
            if editable:
                self.edit_buttons.append((text,b))
        self.collapse_button = ttk.Button(brand,text='收起来源',style='Curve.TButton',command=self.toggle_sources)
        self.collapse_button.pack(side='right')
        self.theme_button = ttk.Button(brand,text='黑暗主题',style='Curve.TButton',command=self.toggle_theme)
        self.theme_button.pack(side='right',padx=4)
        self.page = CurvePage(self.shell,self)
        self.page.grid(row=1,column=0,sticky='nsew')
        footer = ttk.Frame(self.shell,style='Curve.Panel.TFrame',padding=10)
        footer.grid(row=2,column=0,sticky='ew',pady=(10,0))
        self.status_text = tk.StringVar(value='导入原始旋律，选择或拖动素材开始创作。')
        self.detail_text = tk.StringVar(value='点击仅选择；准备试听只缓存音频，明确播放才开始。')
        self.status_label = ttk.Label(footer,textvariable=self.status_text,style='Curve.Panel.TLabel',wraplength=970)
        self.status_label.pack(fill='x')
        detail_row = ttk.Frame(footer,style='Curve.Panel.TFrame')
        detail_row.pack(fill='x',pady=(3,5))
        self.detail_label = tk.Text(detail_row,height=2,wrap='word',font=font(),borderwidth=0,highlightthickness=0,
                                    bg=self.theme.colors['panel'],fg=self.theme.colors['muted'],state='disabled')
        self.detail_label.pack(side='left',fill='x',expand=True)
        detail_scroll = ttk.Scrollbar(detail_row,command=self.detail_label.yview)
        detail_scroll.pack(side='right',fill='y')
        self.detail_label.configure(yscrollcommand=detail_scroll.set)
        self.show_detail(self.detail_text.get())
        self.transport_label = ttk.Label(footer,text='尚未播放 · 未选择试听对象',style='Curve.Panel.TLabel')
        self.transport_label.pack(anchor='w')
        controls = ttk.Frame(footer,style='Curve.Panel.TFrame')
        controls.pack(fill='x',pady=(4,0))
        self.prepare_button = ttk.Button(controls,text='准备试听',style='Curve.TButton',command=lambda:self.safe(self.prepare_selected))
        self.prepare_button.pack(side='left')
        self.play_button = ttk.Button(controls,text='播放已就绪对象',style='Curve.Primary.TButton',command=lambda:self.safe(self.play_selected))
        self.play_button.pack(side='left',padx=4)
        ttk.Button(controls,text='暂停 / 继续',style='Curve.TButton',command=lambda:self.safe(self.toggle_pause)).pack(side='left')
        ttk.Button(controls,text='停止',style='Curve.TButton',command=self.stop).pack(side='left',padx=4)
        self.seek_value = tk.DoubleVar(value=0.)
        self.seek = ttk.Scale(controls,variable=self.seek_value,from_=0,to=1,style='Curve.Horizontal.TScale')
        self.seek.pack(side='left',fill='x',expand=True,padx=8)
        self.seek.bind('<ButtonPress-1>',lambda _:setattr(self,'seek_active',True))
        self.seek.bind('<ButtonRelease-1>',lambda _:self.safe(self.seek_release))
        self.cancel_button = ttk.Button(controls,text='取消准备',style='Curve.TButton',command=self.cancel_jobs)
        self.cancel_button.pack(side='right')
        self.file_drop = None
        try:
            self.file_drop = FileDrop(root,self.drop_files)
        except (OSError,tk.TclError) as exc:
            self.show_detail('可用“导入旋律”选择文件。文件拖入未启用：'+str(exc))
        ui_platform.setup_window(root,self)
        for event in ui_platform.EDIT_SHORTCUT_EVENTS:
            root.bind(event,self.edit_shortcut,add='+')
        root.bind('<Escape>',self.cancel_interaction,add='+')
        self.wheel_bind = root.bind('<MouseWheel>',self.wheel,add='+')
        if root.tk.call('info','commands','tk::PreciseScrollDeltas'):
            root.bind('<TouchpadScroll>',self.touchpad,add='+')
        root.bind('<Configure>',self.resized,add='+')
        root.bind('<Destroy>',self.destroyed,add='+')
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()
        self.timer = root.after(80,self.tick)

    @property
    def editable(self):
        return (not self.jobs and self.state_data['access_mode']=='editable'
                and self.state_data['capabilities'].get('edit',True))

    def safe(self, fn):
        try:
            return fn()
        except Exception as exc:
            self.tell(str(exc),True)
            return False

    def tell(self, text, error=False):
        self.status_error = error
        self.status_text.set(('失败：' if error else '')+str(text))
        self.status_label.configure(foreground=self.theme.colors['error' if error else 'ink'])

    def show_detail(self, text):
        self.detail_text.set(str(text))
        self.detail_label.configure(state='normal')
        self.detail_label.delete('1.0','end')
        self.detail_label.insert('1.0',str(text))
        self.detail_label.configure(state='disabled')

    def refresh(self):
        self.state_data = self.controller.state()
        project = self.state_data['project']
        if self.state_data['access_mode']!='editable':
            saved_text = '旧工程 · 只读'
        elif self.state_data['is_saved']:
            saved_text = '工程已保存'
        else:
            saved_text = '工程未保存' if self.state_data['saved_path'] else '新工程 · 尚未保存'
        self.save_label.configure(text=saved_text)
        sources = project['sources'] if project else []
        materials = project['materials'] if project else []
        if self.selected_source_id not in {v['id'] for v in sources}:
            self.selected_source_id = None
        if self.selected_material_id not in {v['id'] for v in materials}:
            self.selected_material_id = None
        p = self.theme.colors
        self.status_label.configure(foreground=p['error' if self.status_error else 'ink'])
        self.detail_label.configure(bg=p['panel'],fg=p['muted'])
        for listing in (self.page.source_list,self.page.history_list):
            listing.configure(bg=p['inset'],fg=p['ink'],selectbackground=p['selected'],selectforeground=p['ink'],
                              highlightbackground=p['line'],highlightcolor=p['accent'])
        self.page.source_list.delete(0,'end')
        for i,source in enumerate(sources):
            self.page.source_list.insert('end',source['label'])
            if source['id']==self.selected_source_id:
                self.page.source_list.selection_set(i)
        self.page.draw_source()
        self.page.cards.render(materials)
        self.page.timeline.set_project(project)
        if project:
            self.page.grid_count.set(str(project['grid_count']))
        self.history = self.controller.history_items()
        self.page.history_list.delete(0,'end')
        for i,item in enumerate(self.history):
            availability = '可试听' if item['availability']['wav'] else '音频不可用'
            self.page.history_list.insert('end',f'{item["label"]} · {availability}')
            if item['id']==self.selected_history_id:
                self.page.history_list.selection_set(i)
        if self.history:
            self.page.history_panel.pack(fill='x',before=self.page.timeline,pady=(8,0))
        else:
            self.page.history_panel.pack_forget()
        for text,button in self.edit_buttons:
            enabled = self.editable
            if text=='撤销':enabled = enabled and self.state_data['can_undo']
            if text=='重做':enabled = enabled and self.state_data['can_redo']
            button.state(['!disabled'] if enabled else ['disabled'])
        for button in (self.page.derive_button,self.page.grid_entry,self.page.resize_button):
            button.state(['!disabled'] if self.editable else ['disabled'])
        self.update_exports()
        self.update_transport()
        self.layout_sources()

    def edit(self, action, **args):
        if not self.editable:
            self.tell('当前为只读模式或任务尚未结束。',True)
            return False
        try:
            changed = self.controller.edit(action,**args)
        except Exception as exc:
            self.tell(str(exc),True)
            self.refresh()
            return False
        self.refresh()
        self.tell('工程已更新 · 一次撤销可恢复。' if changed else '位置与工程内容未改变。')
        return changed

    def resize_grid(self):
        try:
            count = int(self.page.grid_count.get())
        except ValueError:
            self.tell('四拍格数必须为整数。',True)
            return
        self.edit('resize',grid_count=count)

    def undo(self):
        if self.material_drag or self.page.timeline.drag:
            self.cancel_interaction()
            return
        if self.editable:
            self.controller.undo()
            self.refresh()

    def redo(self):
        if self.editable:
            self.controller.redo()
            self.refresh()

    def select_target(self, kind, ident, redraw=True):
        if not ident:
            return
        self.selected_target = (kind,ident)
        if kind=='material':self.selected_material_id = ident
        if kind=='source':self.selected_source_id = ident
        if kind=='history':self.selected_history_id = ident
        if redraw and kind=='material':self.page.cards.render()
        self.update_transport()

    def source_detail(self):
        source = self.resolve('source',self.selected_source_id)
        if source:
            self.show_detail(source['label']+' · '+json.dumps(source['provenance'],ensure_ascii=False))

    def resolve(self, kind, ident):
        project = self.state_data['project']
        if kind=='history':
            return next((h for h in self.history if h['id']==ident),None)
        if not project:
            return None
        if kind=='placement':
            place = next((p for p in project['placements'] if p['id']==ident),None)
            return (place['emotion_variant'] or place['base_snapshot']) if place else None
        return next((v for v in project['sources' if kind=='source' else 'materials'] if v['id']==ident),None)

    def _start_job(self, kind, target, work, done):
        if self.jobs:
            self.tell('已有任务正在准备；可以取消。')
            return False
        captured = self.controller.capture_job(kind,target)
        token,snapshot = copy.deepcopy(captured['token']),copy.deepcopy(captured['snapshot'])
        self.jobs[token['request_id']] = dict(token=token,done=done,kind=kind)
        self.cancel_interaction()
        self.tell('正在准备'+{'IMPORT':'导入','DERIVE':'新旋律','AUDITION':'试听','COMBINE':'组合'}[kind]+'…')
        self.refresh()
        def worker():
            try:
                result = work(snapshot)
                self.messages.put((token,True,result))
            except Exception as exc:
                self.messages.put((token,False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        return True

    def drain_jobs(self):
        while True:
            try:
                token,success,payload = self.messages.get_nowait()
            except queue.Empty:
                return
            job = self.jobs.get(token['request_id'])
            if not job or job['token']!=token:
                continue
            try:
                if not self.controller.accepts(token):
                    self.tell('准备结果已过期，请重新准备。')
                    continue
                if success:
                    job['done'](payload,token)
                    self.controller.finish_job(token)
                else:
                    self.controller.finish_job(token)
                    self.tell(payload,True)
            except Exception as exc:
                self.controller.cancel_job(token)
                self.tell(str(exc),True)
            finally:
                self.jobs.pop(token['request_id'],None)
                self.refresh()

    def cancel_jobs(self):
        for job in list(self.jobs.values()):
            self.controller.cancel_job(job['token'])
        self.jobs.clear()
        self.refresh()
        self.tell('准备已取消 · 工程和当前播放保持原状。')

    def apply_batch(self, batch, token):
        self.controller.apply_batch(batch,token)
        warnings = batch['warnings']
        self.tell('素材已加入 · 一次撤销可恢复。'+(' '+ '；'.join(w['message'] for w in warnings) if warnings else ''))

    def import_file(self, path=None):
        if not self.editable:
            return
        path = path or filedialog.askopenfilename(parent=self.root,filetypes=[('旋律文件','*.mid *.midi *.mmp')])
        if path:
            return self._start_job('IMPORT',None,lambda _: _provider().prepare_import(path),self.apply_batch)

    def drop_files(self, paths):
        if len(paths)!=1:
            self.tell('请一次导入一个旋律文件。',True)
            return
        self.safe(lambda:self.import_file(paths[0]))

    def derive_selected(self):
        if not self.editable or not self.selected_material_id:
            self.tell('请先选择中栏素材。')
            return
        ident = self.selected_material_id
        method = next(k for k,v in METHODS if v==self.page.method.get())
        self.safe(lambda:self._start_job('DERIVE',dict(kind='material',id=ident),
                  lambda snap:_provider().prepare_generation(snap['project'],ident,method),self.apply_batch))

    def _discard_asset_path(self, path):
        for key,asset in list(self.ready_assets.items()):
            if Path(asset['wav_path'])==path:
                self.ready_assets.pop(key,None)

    def _ready_asset(self, key):
        asset = self.ready_assets.get(key)
        if asset and not Path(asset['wav_path']).is_file():
            self._discard_asset_path(Path(asset['wav_path']))
            return None
        return asset

    def _cache_asset(self, key, asset):
        path = Path(asset['wav_path'])
        if not path.is_file():
            self._discard_asset_path(path)
            raise ValueError('试听准备失败：音频文件缺失，请重新准备。')
        self.ready_assets[key] = copy.deepcopy(asset)

    def prepare_target(self, kind, ident):
        target = self.resolve(kind,ident)
        if not target:
            self.tell('请先选择可试听对象。')
            return
        if kind=='history':
            self.tell('历史音频无需准备；请明确点击播放。')
            return
        key = snapshot_key(kind,target)
        if self._ready_asset(key):
            self.tell('试听已就绪 · 请明确点击播放。')
            return
        def done(asset,token):
            self._cache_asset(key,asset)
            self.tell('试听已就绪 · 当前播放器未改变，请点击播放。')
        return self._start_job('AUDITION',dict(kind=kind,id=ident),
                              lambda snap:_provider().render_audition(snap['target']),done)

    def prepare_selected(self):
        if self.selected_target:
            kind,ident = self.selected_target
            if kind=='draft':return self.prepare_combo()
            return self.prepare_target(kind,ident)
        self.tell('请先选择来源、素材、放置或历史成品。')

    def play_target(self, kind, ident):
        target = self.resolve(kind,ident)
        if not target:
            self.tell('请选择可播放对象。')
            return False
        if kind=='history':
            if not target['availability']['wav']:
                self.tell('历史音频不可用；其他格式仍可单独导出。',True)
                return False
            asset = dict(wav_path=target['paths']['wav'],audio_seconds=target['audio_seconds'],body_seconds=target['body_seconds'])
        else:
            asset = self._ready_asset(snapshot_key(kind,target))
            if not asset:
                self.tell('该对象尚未就绪，请先准备试听。')
                return False
        return self.start_playback(asset,(kind,ident),target['label'])

    def start_playback(self, asset, target, label):
        path = Path(asset['wav_path'])
        if not path.is_file():
            self._discard_asset_path(path)
            self.tell('试听文件已移动或缺失，请重新准备。',True)
            return False
        duration = self.player.play(path)
        self.playing_target = dict(target=target,label=label,asset=copy.deepcopy(asset))
        self.play_duration = duration
        self.seek.configure(to=duration)
        self.update_transport()
        return True

    def play_selected(self):
        if not self.selected_target:
            return
        kind,ident = self.selected_target
        if kind=='draft':
            key = snapshot_key('draft',self.combo_inputs)
            asset = self._ready_asset(key)
            if asset:
                return self.start_playback(asset,('draft',key),'组合草稿')
            self.tell('组合草稿尚未就绪，请先准备试听。')
            return False
        return self.play_target(kind,ident)

    def toggle_pause(self):
        _,mode = self.player.status()
        if mode=='playing':self.player.pause()
        elif mode=='paused':self.player.resume()
        self.update_transport()

    def stop(self):
        self.player.close()
        self.playing_target = None
        self.play_duration = 0.
        self.seek_value.set(0.)
        self.update_transport()

    def seek_release(self):
        self.seek_active = False
        if self.playing_target:
            position = self.seek_value.get()
            if position>=self.play_duration:
                self.stop()
            else:
                was_paused = self.player.status()[1]=='paused'
                self.player.play(self.playing_target['asset']['wav_path'],start=max(0.,position))
                if was_paused:self.player.pause()

    def update_transport(self):
        position,mode = self.player.status()
        if not self.seek_active:
            self.seek_value.set(position)
        playing = self.playing_target['label'] if self.playing_target else '尚未播放'
        selected = self.selected_target
        label = '未选择试听对象'
        if selected:
            if selected[0]=='draft':label = '组合草稿'
            else:
                target = self.resolve(*selected)
                label = target['label'] if target else '选择已失效'
        prefix = {'playing':'播放中','paused':'已暂停','stopped':'已结束','closed':'已停止'}.get(mode,mode)
        self.transport_label.configure(text=f'{prefix}：{playing} · {position:.1f}/{self.play_duration:.1f} 秒   |   已选：{label}')
        self.cancel_button.state(['!disabled'] if self.jobs else ['disabled'])

    def begin_material_drag(self, event, material, card):
        self.select_target('material',material['id'],redraw=False)
        self.page.cards.mark_selection()
        self.show_detail(self.page.cards.describe(material))
        if not self.editable:
            return
        self.material_drag = dict(material=copy.deepcopy(material),widget=event.widget,
                                  start=(event.x_root,event.y_root),offset=event.x_root-card.winfo_rootx(),active=False)

    def material_motion(self, event):
        d = self.material_drag
        if not d:
            return
        if not d['active']:
            if max(abs(event.x_root-d['start'][0]),abs(event.y_root-d['start'][1]))<5:
                return
            d['active'] = True
            d['widget'].grab_set()
        self.card_scroll_pointer = (event.x_root,event.y_root)
        self.material_preview(event.x_root,event.y_root)
        hit = self.page.cards.at_root(event.x_root,event.y_root)
        if hit:
            self.card_scroll_pointer = (event.x_root,event.y_root)
            if self.card_scroll_timer is None:
                self.card_scroll_timer = self.root.after(60,self.cards_edge_step)
            self.show_detail('松开后加入行内组合草稿：'+('放在目标左侧' if hit[1]=='left' else '放在目标右侧'))

    def cards_edge_step(self):
        self.card_scroll_timer = None
        if not self.material_drag or not self.material_drag['active']:
            return
        x,y = self.card_scroll_pointer
        c = self.page.cards.canvas
        if not (c.winfo_rootx()<=x<c.winfo_rootx()+c.winfo_width() and c.winfo_rooty()<=y<c.winfo_rooty()+c.winfo_height()):
            return
        local = y-c.winfo_rooty()
        direction = -1 if local<28 else 1 if local>c.winfo_height()-28 else 0
        if direction:
            c.yview_scroll(direction,'units')
            self.card_scroll_timer = self.root.after(60,self.cards_edge_step)

    def material_preview(self, x, y):
        d = self.material_drag
        canvas = self.page.timeline
        canvas.edge_pointer = (x,y)
        if d and canvas.contains_root(x,y):
            canvas.preview = (snap_tick(canvas.root_tick(x,d['offset'])),d['material']['length_ticks'])
            canvas.edge_scroll(x,y)
        else:
            canvas.preview = None
        canvas.draw()

    def material_release(self, event):
        d = self.material_drag
        if not d:
            return
        canvas = self.page.timeline
        hit = self.page.cards.at_root(event.x_root,event.y_root)
        inside = canvas.contains_root(event.x_root,event.y_root)
        raw = canvas.root_tick(event.x_root,d['offset'])
        self.cancel_interaction()
        if not d['active']:
            self.page.cards.render()
            return
        if inside:
            if raw<0 or raw+d['material']['length_ticks']>canvas.project['total_ticks']:
                self.tell('放置已取消：落点超出时间轴。',True)
                return
            self.edit('place',material_id=d['material']['id'],start_tick=snap_tick(raw))
        elif hit:
            self.add_combo(d['material'],hit[0],hit[1])
        else:
            self.tell('拖放已取消 · 工程未改变。')

    def cancel_interaction(self, event=None):
        if self.card_scroll_timer is not None:
            self.root.after_cancel(self.card_scroll_timer)
            self.card_scroll_timer = None
        if self.material_drag:
            widget = self.material_drag['widget']
            if widget.winfo_exists() and widget.grab_current()==widget:
                widget.grab_release()
        self.material_drag = None
        self.page.timeline.cancel()
        return 'break' if event else None

    def add_combo(self, source, target_id, side):
        target = self.resolve('material',target_id)
        if not target:
            return
        if not self.combo_inputs:
            self.combo_inputs = [copy.deepcopy(source),copy.deepcopy(target)] if side=='left' else [copy.deepcopy(target),copy.deepcopy(source)]
        else:
            index = next((i for i,m in enumerate(self.combo_inputs) if m['id']==target_id),None)
            if index is None:
                self.combo_inputs.append(copy.deepcopy(target))
                index = len(self.combo_inputs)-1
            self.combo_inputs.insert(index if side=='left' else index+1,copy.deepcopy(source))
        self.page.combo_panel.pack(fill='x',before=self.page.cards,pady=6)
        self.page.combo_text.configure(text='组合草稿：'+' → '.join(m['label'] for m in self.combo_inputs))
        self.selected_target = ('draft',snapshot_key('draft',self.combo_inputs))
        self.update_transport()
        self.tell('组合尚未加入工程 · 确认或取消。')

    def cancel_combo(self):
        for request,job in list(self.jobs.items()):
            if job['kind']=='COMBINE':
                self.controller.cancel_job(job['token'])
                self.jobs.pop(request)
        self.combo_inputs = []
        self.page.combo_panel.pack_forget()
        if self.selected_target and self.selected_target[0]=='draft':
            self.selected_target = ('material',self.selected_material_id) if self.selected_material_id else None
        self.refresh()
        self.tell('组合已取消 · 工程和素材库未改变。')

    def _combo_job(self, audition):
        if not self.editable or not self.combo_inputs:
            return
        inputs = copy.deepcopy(self.combo_inputs)
        label = self.page.combo_name.get().strip()
        key = snapshot_key('draft',inputs)
        if audition and self._ready_asset(key):
            self.tell('组合试听已就绪 · 请明确点击底部播放。')
            return
        def work(snapshot):
            material = _provider().combine(snapshot['project'],inputs,label)
            if audition:return _provider().render_audition(material)
            return dict(sources=[],materials=[material],warnings=[])
        def done(payload,token):
            if audition:
                self._cache_asset(key,payload)
                self.tell('组合试听已就绪 · 请明确点击底部播放。')
            else:
                self.apply_batch(payload,token)
                self.combo_inputs = []
                self.page.combo_panel.pack_forget()
                self.selected_target = None
        self._start_job('COMBINE',None,work,done)

    def prepare_combo(self):
        return self._combo_job(True)

    def confirm_combo(self):
        return self._combo_job(False)

    def history_selected(self, event=None):
        indices = self.page.history_list.curselection()
        if indices and indices[0]<len(self.history):
            item = self.history[indices[0]]
            self.select_target('history',item['id'])
            self.show_detail(item['label']+' · 主体 '+str(item['body_seconds'])+' 秒 · 音频 '+str(item['audio_seconds'])+' 秒')
            self.update_exports()

    def update_exports(self):
        item = self.resolve('history',self.selected_history_id)
        for format_,button in self.page.export_buttons.items():
            button.state(['!disabled'] if item and item['availability'][format_] else ['disabled'])

    def export_history(self, format_):
        item = self.resolve('history',self.selected_history_id)
        if not item or not item['availability'][format_]:
            return
        ident = item['id']
        destination = filedialog.asksaveasfilename(parent=self.root,defaultextension='.'+format_,
                                                  initialfile='EmoBlocks.'+format_,filetypes=[(format_.upper(),'*.'+format_)])
        if destination:
            self.safe(lambda:self.controller.export_history(ident,format_,destination))

    def save_project(self):
        if not self.jobs and self.state_data['access_mode']=='editable':
            path = self.controller.save_snapshot()
            self.refresh()
            self.tell('工程快照已保存：'+str(path))
            return path

    def _switched(self):
        self.jobs.clear()
        self.cancel_interaction()
        self.combo_inputs = []
        self.page.combo_panel.pack_forget()
        self.selected_target = self.selected_source_id = self.selected_material_id = self.selected_history_id = None
        self.ready_assets.clear()
        self.stop()
        self.refresh()

    def open_project(self, path=None):
        path = path or filedialog.askopenfilename(parent=self.root,filetypes=[('工程快照','*.json')])
        if path:
            self.controller.load(path)
            self._switched()
            self.tell('工程已打开'+(' · 旧工程只读' if self.state_data['access_mode']!='editable' else ''))

    def new_project(self):
        self.controller.new()
        self._switched()
        self.tell('新的空工程 · 尚未保存。')

    def toggle_sources(self):
        self.source_user_collapsed = bool(self.page.source_panel.winfo_manager())
        self.layout_sources()

    def layout_sources(self):
        collapsed = self.source_user_collapsed if self.source_user_collapsed is not None else self.root.winfo_width()<1150
        if collapsed:self.page.source_panel.grid_remove()
        else:self.page.source_panel.grid()
        self.collapse_button.configure(text='展开来源' if collapsed else '收起来源')

    def resized(self, event):
        if event.widget!=self.root:
            return
        self.layout_sources()
        width = max(400,event.width-50)
        self.status_label.configure(wraplength=width)
        self.page.draw_source()

    def toggle_theme(self):
        self.cancel_interaction()
        self.theme.set('dark' if self.theme.name=='light' else 'light')
        self.theme_button.configure(text='明亮主题' if self.theme.name=='dark' else '黑暗主题')
        self.refresh()

    def wheel(self, event):
        widget = self.root.winfo_containing(event.x_root,event.y_root)
        units = ui_platform.wheel_units(event.delta)
        if widget==self.page.timeline.canvas:
            widget.xview_scroll(units*24,'units')
            return 'break'
        while widget:
            if isinstance(widget,(tk.Listbox,tk.Text,ttk.Combobox,ttk.Entry,ttk.Spinbox)):
                return
            if widget==self.page.cards or widget==self.page.cards.canvas:
                self.page.cards.canvas.yview_scroll(units,'units')
                return 'break'
            widget = widget.master

    def touchpad(self, event):
        widget = self.root.winfo_containing(event.x_root,event.y_root)
        dx,dy = touchpad_deltas(event)
        if widget==self.page.timeline.canvas:
            scroll_canvas_pixels(widget,'x',dx if abs(dx)>abs(dy) else dy)
            return 'break'
        while widget:
            if isinstance(widget,(tk.Listbox,tk.Text,ttk.Combobox,ttk.Entry,ttk.Spinbox)):
                return
            if widget==self.page.cards or widget==self.page.cards.canvas:
                scroll_canvas_pixels(self.page.cards.canvas,'y',dy)
                return 'break'
            widget = widget.master

    def edit_shortcut(self, event):
        if isinstance(event.widget,(tk.Entry,tk.Text,ttk.Entry,ttk.Combobox,ttk.Spinbox)):
            return None
        self.safe(self.redo if ui_platform.edit_shortcut(event)=='redo' else self.undo)
        return 'break'

    def tick(self):
        if self.closed:
            return
        self.drain_jobs()
        self.safe(self.update_transport)
        self.timer = self.root.after(80,self.tick)

    def close(self):
        try:
            self.controller.autosave_if_needed()
        except Exception as exc:
            self.tell('保存失败，窗口和当前工作已保留：'+str(exc),True)
            return False
        self.cancel_jobs()
        self.cancel_interaction()
        self.player.close()
        if self.file_drop:self.file_drop.close()
        self.closed = True
        self.root.after_cancel(self.timer)
        self.root.destroy()
        return True

    def destroyed(self, event):
        if event.widget==self.root and not self.closed:
            self.closed = True
            if hasattr(self,'timer'):self.root.after_cancel(self.timer)
            if self.card_scroll_timer is not None:self.root.after_cancel(self.card_scroll_timer)
            self.player.close()
            if self.file_drop:self.file_drop.close()
