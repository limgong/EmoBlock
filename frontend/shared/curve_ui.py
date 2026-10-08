"""Desktop UI. The frozen Facade owns every musical transaction.

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
from curve_theme import Theme, font, hint, EMOTION_NAMES
from curve_play_intent import PlayIntent
from curve_cards import MaterialCards
from curve_workspace_ui import build_page, build_chrome, build_player
from curve_canvas import CurveCanvas, snap_tick
from curve_completion_ui import CompletionUI
from curve_bridge_ui import BridgeUI
from curve_connection_ui import ConnectionUI
from curve_recommendation_ui import RecommendationUI, playback_asset, MODES, SCOPE_LABELS

METHODS = [('variant','局部变化'),('answer','回答句'),('counter','副旋律规则'),
           ('rhythm','节奏重组'),('develop','动机发展'),('density','疏密变化')]


def _provider():
    return importlib.import_module('curve_workflow')


def snapshot_key(kind, snapshot):
    payload = json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    return kind+':'+hashlib.sha256(payload.encode('utf-8')).hexdigest()


def audition_key(kind, snapshot, bpm):
    return snapshot_key(kind,dict(snapshot=snapshot,bpm=bpm))


class CurvePage(ttk.Frame):
    def __init__(self, parent, app):
        build_page(self,parent,app,METHODS,EMOTION_NAMES)

    def source_selected(self, event=None):
        ids = self.source_list.curselection()
        sources = (self.app.state_data['project'] or {}).get('sources',[])
        if ids and ids[0]<len(sources):
            self.app.select_target('source',sources[ids[0]]['id'])
            self.app.filter_source(sources[ids[0]]['id'])
            self.draw_source()

    def draw_source(self):
        c = self.source_notes
        p = self.app.theme.colors
        c.configure(bg=p['inset'])
        c.delete('all')
        source = next((s for s in (self.app.state_data['project'] or {}).get('sources',[])
                       if s['id']==self.app.selected_source_id),None)
        if not source:
            c.create_text(12,35,anchor='w',text='选择来源查看概览',fill=p['muted'],font=font(9))
            return
        width = max(100,c.winfo_width())-16
        height = max(40,c.winfo_height())
        plot_bottom = height-26
        notes = source['notes']
        low = min((n['pitch'] for n in notes),default=60)
        high = max((n['pitch'] for n in notes),default=72)
        for note in notes:
            x = 8+note['start_tick']/source['length_ticks']*width
            end = 8+(note['start_tick']+note['duration_tick'])/source['length_ticks']*width
            y = plot_bottom-(note['pitch']-low)/max(1,high-low)*max(8,plot_bottom-10)
            c.create_line(x,y,max(x+1,end),y,fill=p['muted'],width=2)
        c.create_text(8,height-10,anchor='w',text=f'{source["length_ticks"]/480:g} 拍 · 原始音符',fill=p['muted'],font=font(8))


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
        self.ready_file_digests = {}
        self.ready_contexts = {}
        self.card_view_flags = None
        self.playing_target = None
        self.play_intent = PlayIntent()
        self.play_duration = 0.
        self.seek_active = False
        self.selected_target = None
        self.selected_source_id = None
        self.selected_material_id = None
        self.selected_history_id = None
        self.combo_inputs = []
        self.material_drag = None
        self.card_scroll_timer = None
        self.drag_ghost = None
        self.status_error = False
        self.full_status='导入旋律，开始创作。'
        self.source_user_collapsed = None
        self.history_expanded = False
        self.last_export = None
        self.state_data = self.controller.state()
        self.accepted_music = None
        root.title('EmoBlocks · 旋律与强度')
        from curve_raster import pixels
        root.minsize(pixels(root,1020),pixels(root,700))
        root.geometry('1280x800')
        self.source_filter_id = None
        self.details_expanded = False
        self.workspace_stage = '编辑'
        self.advanced = False
        self.view_bookmarks = {}
        build_chrome(self)
        self.page = CurvePage(self.shell,self)
        self.page.grid(row=1,column=0,sticky='nsew')
        if controller is None or self.state_data['capabilities'].get('recommendation',False):self.page.timeline.mode='arrange'
        build_player(self)
        self.show_detail(self.detail_text.get())
        self.file_drop = None
        try:
            self.file_drop = FileDrop(root,self.drop_files)
        except (OSError,tk.TclError) as exc:
            self.show_detail('可用“导入旋律”选择文件。文件拖入未启用：'+str(exc))
        self.completion = CompletionUI(self)
        self.bridge = BridgeUI(self)
        self.connection = ConnectionUI(self)
        self.recommendation = RecommendationUI(self)
        self.page.history_mode = ttk.Combobox(self.page.history_panel,textvariable=self.recommendation.mode,
            values=list(MODES.values()),state='readonly',style='Curve.TCombobox')
        self.page.history_mode.bind('<<ComboboxSelected>>',self.recommendation.mode_changed)
        hint(self.page.history_mode,'历史试听/导出明确使用此模式；缺失不回退到另一模式。',self.show_detail)
        self.page.final_button.configure(command=lambda:self.safe(self.generate_recommendations))
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
        self.tell(self.workspace_hint())
        self.timer = root.after(80,self.tick)

    def compact(self, text, width=None):
        width=max(200,self.page.right.winfo_width()-72) if width is None else max(100,width)
        from tkinter import font as tkfont
        actual=tkfont.Font(root=self.root,font=font())
        value=str(text).replace('\n',' · ')
        while len(value)>1 and actual.measure(value+'…')>width:value=value[:-1]
        return value+('…' if value!=str(text).replace('\n',' · ') else '')

    def toggle_details(self):
        self.details_expanded=not self.details_expanded
        self.detail_button.configure(text='收起详情' if self.details_expanded else '详情')
        self.refresh()

    def filter_source(self, ident):
        self.source_filter_id=ident
        self.refresh()

    @staticmethod
    def material_from_source(material, ident):
        if material['provenance'].get('source_id')==ident:return True
        if any((n.get('origin') or {}).get('source_id')==ident for n in material['notes']):return True
        return any(CurveApplication.material_from_source(c['snapshot'],ident) for c in material['children'])

    def generate_recommendations(self):
        if not self.recommendation.available():return False
        if not self.has_generation_input():
            self.tell('请先导入旋律或添加有音符的素材。')
            return False
        self.show_curve_stage('完整建议')
        return self.recommendation.start()

    def has_workspace_content(self):
        project=self.state_data['project']
        return bool(project and any(project[k] for k in ('sources','materials','placements')))

    def has_generation_input(self):
        project=self.state_data['project']
        if not project:return False
        def notes(material):
            return bool(material.get('notes') or any(notes(c['snapshot']) for c in material.get('children',[])))
        return any(notes(m) for m in project['sources']+project['materials']) or any(
            notes(p['emotion_variant'] or p['base_snapshot']) for p in project['placements'])

    def workspace_hint(self):
        if self.state_data['access_mode']!='editable':return '旧工程只读 · 请选择历史版本试听或导出。'
        accepted=getattr(self,'accepted_status',{})
        if accepted.get('status')=='STALE':return accepted['message']
        if accepted.get('status')=='ACTIVE':return '已接受版本 · 可继续编辑或查看历史。'
        rec=getattr(self,'recommendation',None)
        if rec and rec.available() and rec.state['status'] in ('FAILED','INTERRUPTED','STALE','CANCELLED'):
            return rec.status_text()
        project=self.state_data['project']
        if project and project['placements']:return '继续编排或调整强度 · 生成方案仅预览。'
        if project and project['materials']:return '拖入素材，绘制强度，开始逐块编排。'
        if project and project['sources']:return '请选择来源素材，开始逐块编排。'
        return '导入旋律，开始创作。'

    def input_key(self):
        return snapshot_key('input',self.state_data['project'])

    def invalidate_play_intent(self):
        if not hasattr(self,'play_intent'):self.play_intent=PlayIntent()
        self.play_intent.invalidate()

    def audition_target(self, kind, ident):
        if not ident:return False
        target=self.resolve(kind,ident)
        if not target:return False
        self.select_target(kind,ident)
        mode=self.recommendation.mode_key() if kind=='history' and target.get('scope') in ('FULL','LOCAL') else None
        if kind=='history':
            self.invalidate_play_intent()
            return self.play_target(kind,ident)
        return self.request_audition((kind,ident),audition_key(kind,target,self.state_data['project']['bpm']))

    def audition_selected(self):
        if not self.selected_target:
            self.tell('请先选择来源、素材、积木或历史版本。');return False
        if self.selected_target[0]=='draft':return self.audition_combo()
        return self.audition_target(*self.selected_target)

    def audition_combo(self):
        if not self.combo_inputs:return False
        target=('draft',snapshot_key('draft',self.combo_inputs))
        self.selected_target=target
        return self.request_audition(target,audition_key('draft',self.combo_inputs,self.state_data['project']['bpm']))

    def request_audition(self, target, key):
        self.invalidate_play_intent()
        # A newer explicit audition supersedes only audition preparation, never a music-stage job.
        for ident,job in list(self.jobs.items()):
            if job['kind']=='AUDITION' or (job['kind']=='COMBINE' and job.get('audition')):
                self.controller.cancel_job(job['token']);self.jobs.pop(ident)
        if self.jobs:
            self.tell('已有音乐任务运行；可取消后试听。');return False
        self.play_intent.begin(target,None,self.input_key(),key)
        if self._ready_asset(key):
            result=self.play_selected()
            if not result:self.invalidate_play_intent()
            return result
        result=self.prepare_combo() if target[0]=='draft' else self.prepare_target(*target)
        if not result:self.invalidate_play_intent()
        return result

    def play_prepared_intent(self, token, key):
        target=self.selected_target
        if not target or not self.play_intent.accepts(token,target,None,self.input_key(),key):return False
        if not self._ready_asset(key):
            self.invalidate_play_intent();return False
        return self.play_selected()

    def selected_gap(self):
        return next((g for g in self.completion.gaps if g['id']==self.completion.selected_gap_id),None)

    def mark_selected_blank(self):
        gap=self.selected_gap()
        if gap and self.can_edit('completion'):
            return self.edit('mark_blank',start_tick=gap['start_tick'],end_tick=gap['end_tick'],reason='user intent')
        return False

    def toggle_advanced(self):
        self.advanced=not self.advanced
        self.page.advanced_button.configure(text='收起高级' if self.advanced else '高级')
        if self.advanced:
            self.show_curve_stage(self.workspace_stage if self.workspace_stage!='编辑' else '补全')
        else:
            self.suspend_private_view()
            self.workspace_stage='编辑'
            self.refresh()

    def suspend_private_view(self):
        for name,stage,field in self.stages():
            preview=getattr(stage,field)
            if preview is not None:
                self.view_bookmarks[name]=dict(preview=preview,bookmark=stage.bookmark,view=dict(selected=self.page.timeline.selected_id,bridge=self.page.timeline.selected_bridge_id,connection=self.page.timeline.selected_connection_id,scroll=self.page.timeline.canvas.xview()[0],mode=self.page.timeline.mode))
                stage.restore_view()
            if hasattr(stage,'visible'):stage.visible=False

    def stages(self):
        return [('补全',self.completion,'preview_candidate'),('Bridge',self.bridge,'preview'),
                ('连接',self.connection,'preview'),('完整建议',self.recommendation,'preview')]

    def restore_private_view(self, name):
        saved=self.view_bookmarks.pop(name,None)
        if saved:
            stage,field=next((s,f) for n,s,f in self.stages() if n==name)
            setattr(stage,field,saved['preview']);stage.bookmark=saved['bookmark']
            self.resumed_view=saved['view']

    @property
    def editable(self):
        return (not self.jobs and self.state_data['access_mode']=='editable'
                and not (getattr(self,'completion',None) and self.completion.preview_candidate)
                and not (getattr(self,'bridge',None) and self.bridge.preview is not None)
                and not (getattr(self,'connection',None) and self.connection.preview is not None)
                and not (getattr(self,'recommendation',None) and self.recommendation.preview is not None)
                and self.state_data['capabilities'].get('edit',True))

    def can_edit(self, capability):
        return self.editable and self.state_data['capabilities'].get(capability,False)

    def selected_placement(self):
        if self.covered_by_accepted_bridge(self.page.timeline.selected_id):return None
        project = self.state_data['project']
        if not project or not self.selected_target or self.selected_target[0]!='placement':return None
        return next((p for p in project['placements'] if p['id']==self.selected_target[1]),None)

    def update_emotions(self):
        placement = self.selected_placement()
        if not placement or self.private_preview() or self.page.timeline.mode=='gaps':
            self.page.emotion_panel.pack_forget()
            self.page.timeline.all_gaps_button.pack(side='left')
            return
        self.page.timeline.all_gaps_button.pack_forget()
        self.page.emotion_panel.pack(side='right')
        self.page.emotion_title.configure(text='情绪')
        for emotion,button in self.page.emotion_buttons.items():
            button.configure(style='Curve.Primary.TButton' if placement['emotion']==emotion else 'Curve.TButton')
            button.state(['!disabled'] if self.can_edit('emotion') else ['disabled'])

    def set_emotion(self, emotion):
        placement = self.selected_placement()
        if not placement or not self.can_edit('emotion'):return False
        changed = self.edit('set_emotion',placement_ids=[placement['id']],emotion=emotion)
        if self.status_error:return changed
        placement = self.selected_placement()
        generation = (placement['emotion_variant'] or {}).get('generation') or {}
        detail = ''
        if generation:
            messages = [w['message'] for w in generation.get('warnings',[])]
            text = '情绪已设置 · '+('旋律已轻改。' if generation.get('melody_changed',False) else '旋律未改变。')
            if messages:text += ' '+'；'.join(messages)
            if (generation.get('accompaniment_hints') or {}).get('status')=='suggested-not-rendered':
                detail = ' 编配仅为建议，尚未渲染。'
        else:
            text = '情绪已设置 · 使用基础旋律。'
        self.tell(text)
        self.show_detail(text+detail+' 素材试听仍为中性单旋律。')
        return changed

    def memory_description(self, compact=False):
        info = self.state_data['memory_info']
        if not info or not self.state_data['capabilities'].get('memory',False):return '记忆状态尚未接通。'
        if info['state']=='PENDING_GAP':return '记忆待落位 · 峰值处为空缺，尚无音乐保护。'
        if info['state']=='PRESERVE_BLANK':return '记忆保留留白 · 峰值处为主动留白，不填入主旋律。'
        project = self.state_data['project']
        protection = next((p for p in project['protections'] if p['id']==info['protection_id']
                           and p['kind']=='memory' and p['placement_id']==info['placement_id']
                           and p['status']=='CONTENT_READY'),None) if project else None
        region = protection or info['range']
        span = (f'{region["start_tick"]/480:g}–{region["end_tick"]/480:g}拍' if compact else f'{region["start_tick"]}–{region["end_tick"]} tick') if region else '范围未落位'
        status = ('音高与节奏已保护' if compact else '音高与节奏已保护；用户仍可编辑') if protection else '目标未落保护'
        path = ' / '.join(info['component_path'])
        return '记忆积木 · '+status+' · '+span+(' · 组件 '+path if path and not compact else '')

    def toggle_history(self):
        self.invalidate_play_intent()
        if not self.history_expanded:
            self.history_return_stage=self.workspace_stage
            self.suspend_private_view()
            self.workspace_stage='历史'
            self.history_expanded=True
            self.refresh()
        else:
            self.history_expanded=False
            self.show_curve_stage(getattr(self,'history_return_stage','编辑'))


    def safe(self, fn):
        try:
            return fn()
        except Exception as exc:
            self.tell(str(exc),True)
            return False

    def tell(self, text, error=False):
        self.status_error = error
        self.full_status=('失败：' if error else '')+str(text)
        self.status_text.set(self.compact(self.full_status))
        self.status_label.configure(foreground=self.theme.colors['error' if error else 'ink'])
        if error:self.show_detail(self.full_status)

    def status_description(self):
        if self.status_error:return self.full_status
        if self.recommendation.visible or self.recommendation.active_job():return self.recommendation.description()
        if self.connection.visible:return self.connection.description()
        if self.bridge.visible:return self.bridge.description()
        if self.workspace_stage=='补全':return self.completion.description()
        return self.full_status

    def show_detail(self, text):
        self.detail_text.set(str(text))
        self.detail_label.configure(state='normal')
        self.detail_label.delete('1.0','end')
        self.detail_label.insert('1.0',str(text))
        self.detail_label.configure(state='disabled')

    def refresh(self):
        self.state_data = self.controller.state()
        project = self.state_data['project']
        self.accepted_music = (self.controller.effective_music() if project is not None
            and self.state_data['capabilities'].get('recommendation',False) else None)
        if self.state_data['access_mode']!='editable':
            saved_text = '旧工程 · 只读'
        elif self.state_data['is_saved']:
            saved_text = '工程已保存'
        else:
            saved_text = '工程未保存' if self.state_data['saved_path'] else '新工程 · 尚未保存'
        if self.state_data['capabilities'].get('completion',False) or self.state_data['capabilities'].get('recommendation',False):
            saved_text += ' · 候选暂存'+('未保存' if self.state_data['staging_dirty'] else '已保存')
        if self.state_data['capabilities'].get('recommendation',False):
            accepted = self.controller.accepted_state()
            self.accepted_status=accepted
            if accepted['status']!='NONE':saved_text += ' · '+('接受版本有效' if accepted['status']=='ACTIVE' else '接受层已失效')
        self.saved_description=saved_text
        path=self.state_data.get('saved_path')
        self.project_label.configure(text=(Path(path).stem[:9]+'…' if path and len(Path(path).stem)>9 else Path(path).stem if path else '未命名工程'))
        self.save_label.configure(text=('旧工程 · 只读' if self.state_data['access_mode']!='editable' else '已保存' if self.state_data['is_saved'] else '未保存')+(' · 暂存未保存' if self.state_data.get('staging_dirty') else ''))
        self.completion.refresh()
        self.bridge.refresh()
        self.connection.refresh()
        self.recommendation.refresh()
        self.theme_button.set_icon('sun' if self.theme.name=='dark' else 'moon')
        self.page.final_button.configure(text='生成方案' if self.recommendation.available() else '尚未接通')
        self.page.final_button.state(['!disabled'] if self.recommendation.available() and self.has_generation_input() and not self.jobs else ['disabled'])
        sources = project['sources'] if project else []
        materials = project['materials'] if project else []
        if self.source_filter_id:
            materials = [m for m in materials if self.material_from_source(m,self.source_filter_id)]
        if self.selected_source_id not in {v['id'] for v in sources}:
            self.selected_source_id = None
        if self.selected_material_id not in {v['id'] for v in materials}:
            self.selected_material_id = None
        p = self.theme.colors
        self.status_label.configure(foreground=p['error' if self.status_error else 'ink'])
        self.detail_label.configure(bg=p['panel'],fg=p['muted'])
        self.export_receipt.configure(bg=p['panel'],fg=p['ink'])
        for listing in (self.page.source_list,self.page.history_list):
            listing.configure(bg=p['inset'],fg=p['ink'],selectbackground=p['selected'],selectforeground=p['ink'],
                              highlightbackground=p['line'],highlightcolor=p['accent'])
        self.page.source_list.delete(0,'end')
        for i,source in enumerate(sources):
            self.page.source_list.insert('end',source['label'])
            if source['id']==self.selected_source_id:
                self.page.source_list.selection_set(i)
        self.page.draw_source()
        flags = (self.theme.name,self.selected_material_id)
        if materials!=self.page.cards.materials or flags!=self.card_view_flags:
            self.page.cards.render(materials)
            self.card_view_flags = flags
        connection_preview = self.connection.preview
        bridge_preview = connection_preview if connection_preview is not None else self.bridge.preview
        private = self.private_preview()
        recommendation_preview = self.recommendation.preview
        if recommendation_preview is not None:
            bridge_preview = dict(overlays=recommendation_preview['bridge_overlays'],protections=recommendation_preview['protections'])
            connection_preview = recommendation_preview
        if not private and self.selected_target and self.selected_target[0]=='placement':
            if not project or self.selected_target[1] not in {v['id'] for v in project['placements']}:
                self.selected_target = None
            else:self.page.timeline.selected_id = self.selected_target[1]
        self.update_emotions()
        self.page.memory_label.configure(text=self.compact(self.preview_memory_description().split(' · ')[0]+' · 候选只读' if private else self.memory_description(compact=True)),
                                         wraplength=0)
        self.page.timeline.set_project(private['project'] if private else project,
                                       readonly=bool(private),memory_info=private['memory_info'] if private else None,
                                       bridge_preview=bridge_preview,connection_preview=connection_preview,
                                       recommendation_preview=recommendation_preview,accepted_music=self.accepted_music if not private else None)
        if project:
            self.page.grid_count.set(str(project['grid_count']))
            self.page.grid_summary.set(f'{project["grid_count"]}格 · {project["grid_count"]*4}拍')
        self.history = self.controller.history() if self.recommendation.available() else self.controller.history_items()
        self.page.history_list.delete(0,'end')
        for i,item in enumerate(self.history):
            output = self.history_output(item)
            availability = '可试听' if output['availability']['wav'] else '音频不可用'
            if output['errors']['wav']:
                availability += ' · '+output['errors']['wav']['message']
            status={'CURRENT':'编辑一致','HISTORICAL':'历史版本'}.get(item.get('application_status'),'历史版本')
            version = f' · v{item["version"]} · {status} · {SCOPE_LABELS.get(item["scope"],"阶段版本")}' if 'score_ref' in item else ''
            self.page.history_list.insert('end',f'{item["label"]}{version} · {availability}')
            if item['id']==self.selected_history_id:
                self.page.history_list.selection_set(i)
        if any(item.get('scope') in ('FULL','LOCAL') for item in self.history):
            self.page.history_mode.pack(fill='x',before=self.page.history_list,pady=3)
        else:self.page.history_mode.pack_forget()
        if self.history and (self.history_expanded or self.state_data['access_mode']!='editable'):
            self.page.history_panel.pack(fill='x',before=self.page.stage_anchor,pady=(4,0))
        else:
            self.page.history_panel.pack_forget()
        self.history_button.configure(text=f'历史 {len(self.history)}')
        self.version_ids=[item['id'] for item in self.history]
        self.version_selector.configure(values=[f'v{item.get("version",i+1)} · {item["label"]}' for i,item in enumerate(self.history)])
        if self.selected_history_id in self.version_ids:self.version_selector.current(self.version_ids.index(self.selected_history_id))
        else:self.player_version.set('选择导出版本')
        self.version_selector.configure(state='readonly' if self.history else 'disabled')
        self.page.source_audition.state(['!disabled'] if self.selected_source_id else ['disabled'])
        for text,button in self.edit_buttons:
            enabled = self.editable
            if text=='保存快照':
                enabled = self.state_data['access_mode']=='editable' and all(j['kind'] in ('COMPLETION','BRIDGE','CONNECTION','RECOMMENDATION','RECOMMENDATION_MODE') for j in self.jobs.values())
            if text=='撤销':enabled = enabled and self.state_data['can_undo']
            if text=='重做':enabled = enabled and self.state_data['can_redo']
            button.state(['!disabled'] if enabled else ['disabled'])
        for button in (self.page.derive_button,self.page.grid_entry,self.page.resize_button):
            button.state(['!disabled'] if self.editable else ['disabled'])
        if not materials:self.page.derive_button.state(['disabled'])
        self.page.minus_button.state(['!disabled'] if self.editable and project and project['grid_count']>1 else ['disabled'])
        for text,button in self.file_actions:
            enabled=not self.jobs if text!='保存快照' else self.state_data['access_mode']=='editable' and all(j['kind'] in ('COMPLETION','BRIDGE','CONNECTION','RECOMMENDATION','RECOMMENDATION_MODE') for j in self.jobs.values())
            button.state(['!disabled'] if enabled else ['disabled'])
        self.update_exports()
        self.update_workspace()
        if getattr(self,'resumed_view',None):
            if private:
                view=self.resumed_view;canvas=self.page.timeline
                canvas.selected_id=view['selected'];canvas.selected_bridge_id=view['bridge'];canvas.selected_connection_id=view['connection']
                canvas.mode=view['mode'];canvas.canvas.xview_moveto(view['scroll']);canvas.draw()
            self.resumed_view=None
        self.update_transport()
        self.layout_sources()

    def update_workspace(self):
        page=self.page
        empty=(not self.has_workspace_content() and not self.private_preview() and not self.jobs
               and not self.history_expanded and self.state_data['access_mode']=='editable')
        if self.state_data['project'] and self.state_data['project']['materials']:
            page.derive_row.pack(fill='x',before=page.combo_panel if page.combo_panel.winfo_manager() else page.cards)
        else:page.derive_row.pack_forget()
        gap=self.selected_gap()
        if gap and not empty and not self.private_preview() and not self.jobs:
            page.gap_panel.pack(side='right')
            page.gap_label.configure(text=f'空缺 {(gap["end_tick"]-gap["start_tick"])/480:g}拍')
        else:page.gap_panel.pack_forget()
        if self.advanced and not empty:
            first=next(w for w in page.secondary_tools.content.pack_slaves()
                       if w not in (page.creation_row,page.advanced_row))
            page.advanced_row.pack(fill='x',before=first)
            page.timeline.stage_selector.pack(side='right')
            page.timeline.mode_buttons['gaps'].pack(side='left')
            self.recommendation.auto_button.pack(side='left') if self.recommendation.available() else self.recommendation.auto_button.pack_forget()
        else:
            page.timeline.stage_selector.pack_forget()
            page.timeline.mode_buttons['gaps'].pack_forget()
            page.advanced_row.pack_forget()
            self.recommendation.auto_button.pack_forget()
        # Edit-specific controls do not consume review space.
        if empty or self.private_preview() or self.recommendation.visible or self.jobs or self.history_expanded or self.state_data['access_mode']!='editable':
            page.timeline.tools.pack_forget()
            page.emotion_panel.pack_forget()
        else:page.timeline.tools.pack(fill='x',before=page.timeline.canvas,pady=(0,4))
        self.file_menu.entryconfigure('导入旋律',state='normal' if self.editable else 'disabled')
        save_allowed=self.state_data['access_mode']=='editable' and all(j.get('kind') in ('COMPLETION','BRIDGE','CONNECTION','RECOMMENDATION','RECOMMENDATION_MODE') for j in self.jobs.values())
        self.file_menu.entryconfigure('保存快照',state='normal' if save_allowed else 'disabled')
        page.import_button.state(['!disabled'] if self.editable else ['disabled'])
        if getattr(self,'accepted_status',{}).get('status')=='STALE' and not self.recommendation.visible and not self.status_error:self.status_text.set(self.compact(self.accepted_status['message']))
        if self.recommendation.visible and not self.status_error:self.status_text.set(self.compact(self.recommendation.status_text()))
        if self.jobs:
            stage=self.recommendation.status_text() if self.recommendation.active_job() else self.bridge.status_text() if self.bridge.active_job() else self.connection.status_text() if self.connection.active_job() else self.full_status
            self.status_text.set(self.compact(stage))
        if self.details_expanded:
            for _,stage,_ in self.stages():stage.panel.pack_forget()
            page.history_panel.pack_forget();page.advanced_row.pack_forget()
            self.detail_row.pack(fill='x',before=page.stage_anchor,pady=(2,0))
        else:self.detail_row.pack_forget()
        page.footer.pack_configure(pady=0)
        if empty:
            page.creation_row.pack_forget();page.memory_label.pack_forget()
            page.empty_workspace.place(x=0,y=0,relwidth=1,relheight=1);page.empty_workspace.lift()
            page.timeline.empty_import.place(relx=.5,rely=.45,anchor='center');page.timeline.empty_import.lift()
            page.timeline.scrollbar.pack_forget()
            for w in (page.all_materials_button,page.source_frame,page.source_notes,page.source_audition,page.source_reminder):w.pack_forget()
        else:
            page.empty_workspace.place_forget();page.timeline.empty_import.place_forget()
            if self.private_preview() or self.recommendation.visible or any(j['kind']=='RECOMMENDATION' for j in self.jobs.values()):page.creation_row.pack_forget()
            elif self.advanced and not self.jobs:
                page.creation_row.pack(in_=page.secondary_tools.content,fill='x',before=page.advanced_row if page.advanced_row.winfo_manager() else page.stage_anchor)
            else:page.creation_row.pack(in_=page.right,fill='x',before=page.timeline)
            preview=self.private_preview()
            info=preview.get('memory_info') if preview else self.state_data.get('memory_info')
            if (info or {}).get('state')=='BOUND' and page.timeline.memory_overlay():
                # The actual protected badge remains on the canvas; avoid a duplicate
                # bound-memory row while preserving pending-gap/blank explanations.
                page.memory_label.pack_forget()
            else:page.memory_label.pack(fill='x',before=page.timeline,pady=(2,0))
            page.timeline.scrollbar.pack(fill='x')
            page.all_materials_button.pack(fill='x',pady=6)
            page.source_frame.pack(fill='both',expand=True)
            page.source_notes.pack(fill='x',pady=8);page.source_audition.pack(fill='x')
            page.source_reminder.pack(anchor='w',pady=8)
        page.timeline.canvas.configure(takefocus=not empty)
        page.secondary_tools.set_compact(self.advanced and not empty and not self.jobs)

    def preview_memory_description(self,preview=None):
        preview = self.private_preview() if preview is None else preview
        if preview is None:return '候选视图已关闭。'
        info = preview['memory_info']
        if not info:return '候选记忆状态不可用。'
        if info['state']=='PENDING_GAP':return '候选记忆待落位 · 峰值处仍为空缺。'
        if info['state']=='PRESERVE_BLANK':return '候选记忆保留主动留白。'
        protections = preview.get('protections',preview['project']['protections'])
        protection = next((p for p in protections if p['id']==info['protection_id']
            and p['kind']=='memory' and p['placement_id']==info['placement_id'] and p['status']=='CONTENT_READY'),None)
        region = protection or info['range']
        return '候选记忆 · '+('已保护；用户可返回编辑' if protection else '目标未落保护')+f' · {region["start_tick"]}–{region["end_tick"]} tick'

    def current_memory_description(self):
        return self.preview_memory_description() if self.private_preview() is not None else self.memory_description()

    def private_preview(self):
        recommendation = getattr(self,'recommendation',None)
        if recommendation and recommendation.preview is not None:return recommendation.preview
        connection = getattr(self,'connection',None)
        if connection and connection.preview is not None:return connection.preview
        bridge = getattr(self,'bridge',None)
        if bridge and bridge.preview is not None:return bridge.preview
        completion = getattr(self,'completion',None)
        return completion.preview_candidate if completion else None

    def exit_private_preview(self):
        self.invalidate_play_intent()
        if self.recommendation.preview is not None:self.recommendation.exit_preview()
        elif self.connection.preview is not None:self.connection.exit_preview()
        elif self.bridge.preview is not None:self.bridge.exit_preview()
        elif self.completion.preview_candidate:self.completion.exit_preview()

    def show_curve_stage(self, stage):
        self.invalidate_play_intent()
        self.cancel_interaction()
        self.suspend_private_view()
        self.workspace_stage=stage
        self.history_expanded=False
        if stage=='完整建议':self.recommendation.show()
        elif stage=='连接':self.connection.show()
        elif stage=='Bridge':self.bridge.show()
        self.restore_private_view(stage)
        self.refresh()

    def describe_bridge_overlay(self, overlay):
        if self.recommendation.preview is not None:return self.recommendation.describe_overlay(overlay,'Bridge')
        if self.connection.preview is not None:
            return self.bridge.describe_overlay(overlay,self.connection.state['request']['bridge_ref'])
        return self.bridge.describe_overlay(overlay)

    def describe_connection_overlay(self, overlay):
        if self.recommendation.preview is not None:return self.recommendation.describe_overlay(overlay,'连接')
        return self.connection.describe_overlay(overlay)

    def covered_by_accepted_bridge(self, placement_id):
        if not self.accepted_music or not placement_id:return False
        project = self.state_data['project']
        placement = next((p for p in project['placements'] if p['id']==placement_id),None)
        return bool(placement and any(p['kind']=='bridge' and p['origin']=='automatic'
            and p['start_tick']<placement['start_tick']+placement['length_ticks'] and p['end_tick']>placement['start_tick']
            for p in self.accepted_music['protections']))

    def edit(self, action, **args):
        if not self.editable:
            self.tell('当前为只读模式或任务尚未结束。',True)
            return False
        try:
            self.invalidate_play_intent()
            changed = self.controller.edit(action,**args)
        except Exception as exc:
            self.tell(str(exc),True)
            self.refresh()
            return False
        if changed:self.view_bookmarks.clear()
        self.refresh()
        self.tell('工程已更新 · 一次撤销可恢复。' if changed else '位置与工程内容未改变。')
        return changed

    def adjust_grid(self, delta):
        project=self.state_data['project']
        if not project or not self.editable:return False
        return self.edit('resize',grid_count=max(1,project['grid_count']+delta))

    def resize_grid(self):
        try:
            count = int(self.page.grid_count.get())
        except ValueError:
            self.tell('四拍格数必须为整数。',True)
            return
        self.edit('resize',grid_count=count)

    def undo(self):
        if self.material_drag or self.page.timeline.drag or self.page.timeline.intensity_draft:
            self.cancel_interaction()
            return
        if self.editable:
            self.invalidate_play_intent()
            self.view_bookmarks.clear()
            self.controller.undo()
            self.refresh()

    def redo(self):
        if self.editable:
            self.invalidate_play_intent()
            self.view_bookmarks.clear()
            self.controller.redo()
            self.refresh()

    def select_target(self, kind, ident, redraw=True):
        if not ident:
            return
        if self.selected_target!=(kind,ident):self.invalidate_play_intent()
        self.selected_target = (kind,ident)
        if kind=='material':self.selected_material_id = ident
        if kind=='source':self.selected_source_id = ident
        if kind=='history':self.selected_history_id = ident
        if kind=='placement':self.page.timeline.selected_id = ident
        if redraw and kind=='material':
            self.page.cards.render()
            self.card_view_flags = (self.theme.name,self.selected_material_id)
        self.update_emotions()
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
        if kind not in ('AUDITION','COMBINE'):self.invalidate_play_intent()
        captured = self.controller.capture_job(kind,target)
        token,snapshot = copy.deepcopy(captured['token']),copy.deepcopy(captured['snapshot'])
        job = dict(token=token,done=done,kind=kind,snapshot=snapshot)
        self.jobs[token['request_id']] = job
        if kind in ('AUDITION','COMBINE'):
            if not hasattr(self,'play_intent'):self.play_intent=PlayIntent()
            self.play_intent.bind(token,snapshot_key('input',snapshot['project']))
            job['audition']=self.play_intent.current is not None
        def worker():
            try:
                result = work(snapshot)
                self.messages.put((token,True,result))
            except Exception as exc:
                self.messages.put((token,False,str(exc)))
        try:
            if kind in ('AUDITION','COMBINE'):
                snapshot['audition_profile'] = self.audition_profile()
            self.cancel_interaction()
            self.tell('正在准备'+{'IMPORT':'导入','DERIVE':'新旋律','AUDITION':'试听','COMBINE':'组合'}[kind]+'…')
            self.refresh()
            threading.Thread(target=worker,daemon=True).start()
        except Exception as exc:
            try:
                self.controller.cancel_job(token)
            finally:
                if self.jobs.get(token['request_id']) is job:
                    self.jobs.pop(token['request_id'])
            self.refresh()
            self.invalidate_play_intent()
            self.tell('准备启动失败：'+str(exc),True)
            return False
        return True

    def drain_jobs(self):
        self.completion.drain()
        self.bridge.drain()
        self.connection.drain()
        self.recommendation.drain()
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
                    ready_key=job['done'](payload,token,job['snapshot'])
                    acknowledged=self.controller.finish_job(token)
                    if acknowledged and job.get('audition') and isinstance(ready_key,str):self.play_prepared_intent(token,ready_key)
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
        self.invalidate_play_intent()
        self.completion.cancel()
        self.bridge.cancel()
        self.connection.cancel()
        self.recommendation.cancel()
        for job in list(self.jobs.values()):
            if job['kind'] in ('RECOMMENDATION','RECOMMENDATION_MODE'):continue
            self.controller.cancel_job(job['token'])
            self.jobs.pop(job['token']['request_id'],None)
        self.refresh()
        self.tell('取消已请求 · 正在收拢阶段事实；工程和当前播放保持原状。' if self.recommendation.active_job()
                  else '准备已取消 · 工程和当前播放保持原状。')

    def apply_batch(self, batch, token, snapshot=None):
        self.invalidate_play_intent()
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
                self.ready_file_digests.pop(key,None)
                getattr(self,'ready_contexts',{}).pop(key,None)

    def audition_profile(self):
        query = getattr(self.controller,'audition_renderer_profile',None)
        return query() if query is not None else None  # Older injected Facades have no profile query.

    @staticmethod
    def file_digest(path):
        digest = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                digest.update(chunk)
        return digest.hexdigest()

    def _ready_asset(self, key):
        asset = self.ready_assets.get(key)
        if asset:
            identity = self.ready_file_digests.get(key)
            profile = self.audition_profile()
            try:
                valid = (identity is not None and (profile is None or asset.get('renderer_version')==profile)
                         and all(self.file_digest(path)==digest for path,digest in identity.items()))
            except OSError:
                valid = False
            if not valid:
                self._discard_asset_path(Path(asset['wav_path']))
                self.tell('试听输出已缺失或身份已变化，请明确重新准备。')
                return None
        return asset

    def _cache_asset(self, key, asset, expected_profile=None, context=None):
        if not hasattr(self,'ready_contexts'):self.ready_contexts={}
        path = Path(asset['wav_path'])
        profile = self.audition_profile()
        if ((expected_profile is not None and asset.get('renderer_version')!=expected_profile)
                or (profile is not None and asset.get('renderer_version')!=profile)):
            raise ValueError('试听输出版本已变化，请明确重新准备。')
        # Old injected test Facades support WAV only. Frozen providers register all three files.
        fields = ('wav_path','midi_path','mmp_path') if profile is not None else ('wav_path',)
        try:
            identity = {str(Path(asset[field])):self.file_digest(asset[field]) for field in fields}
        except (OSError,KeyError) as exc:
            self._discard_asset_path(path)
            raise ValueError('试听准备失败：输出文件缺失，请重新准备。') from exc
        self.ready_assets[key] = copy.deepcopy(asset)
        self.ready_file_digests[key] = identity
        if context is not None:self.ready_contexts[key]=copy.deepcopy(context)
        protected=(self.playing_target or {}).get('context',{}).get('key')
        for old in list(self.ready_assets):
            if len(self.ready_assets)<=16:break
            if old!=protected and old!=key:
                self.ready_assets.pop(old,None);self.ready_file_digests.pop(old,None);self.ready_contexts.pop(old,None)

    def prepare_target(self, kind, ident):
        target = self.resolve(kind,ident)
        if not target:
            self.tell('请先选择可试听对象。')
            return
        if kind=='history':
            self.tell('历史音频无需准备；请明确点击播放。')
            return
        key = audition_key(kind,target,self.state_data['project']['bpm'])
        ready = self._ready_asset(key)
        if ready:
            self.tell(f'试听已就绪 · 预计正文 {ready["body_seconds"]:.1f} 秒 / 实际音频 {ready["audio_seconds"]:.1f} 秒 · 请明确播放。')
            return
        def done(asset,token,snapshot):
            key = audition_key(kind,snapshot['target'],snapshot['project']['bpm'])
            from curve_playback_ui import neutral_context
            context=neutral_context(kind,ident,snapshot,key,snapshot_key('input',snapshot['project']))
            self._cache_asset(key,asset,snapshot.get('audition_profile'),context)
            self.tell(f'试听已就绪 · 预计正文 {asset["body_seconds"]:.1f} 秒 / 实际音频 {asset["audio_seconds"]:.1f} 秒。')
            return key
        return self._start_job('AUDITION',dict(kind=kind,id=ident),
                              lambda snap:_provider().render_audition(snap['target'],bpm=snap['project']['bpm']),done)

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
        context=None
        if kind=='history':
            output = self.history_output(target)
            if not output['availability']['wav']:
                self.tell(output['errors']['wav']['message'],True)
                return False
            if target.get('scope') in ('FULL','LOCAL'):
                mode = output['mode']
                query=getattr(self.controller,'history_playback',None)
                context=query(ident,mode=mode) if query else None
                asset = playback_asset(context['asset'] if context else self.controller.history_asset(ident,mode=mode))
                label = target['label']+' · '+MODES[mode]
            else:
                asset = dict(wav_path=target['paths']['wav'],audio_seconds=target['audio_seconds'],body_seconds=target['body_seconds'])
                label = target['label']
                query=getattr(self.controller,'history_playback',None)
                if query:context=query(ident);asset=playback_asset(context['asset'])
        else:
            asset = self._ready_asset(audition_key(kind,target,self.state_data['project']['bpm']))
            if not asset:
                self.tell('该对象尚未就绪，请先准备试听。')
                return False
            context=self.ready_contexts.get(audition_key(kind,target,self.state_data['project']['bpm']))
        return self.start_playback(asset,(kind,ident),label if kind=='history' else target['label'],context=context)

    def start_playback(self, asset, target, label, context=None):
        self.invalidate_play_intent()
        path = Path(asset['wav_path'])
        if not path.is_file():
            self._discard_asset_path(path)
            self.tell('试听文件已移动或缺失，请重新准备。',True)
            return False
        expected=(asset.get('files',{}).get('wav') or {}).get('sha256')
        if expected is None and (context or {}).get('neutral'):
            expected=self.ready_file_digests.get(context['key'],{}).get(str(path))
        if expected is None:
            expected=next((self.ready_file_digests.get(key,{}).get(str(path))
                           for key,value in self.ready_assets.items() if value==asset),None)
        try:
            digest=self.file_digest(path)
            if expected is not None and digest!=expected:
                raise ValueError('播放文件字节已变化，请明确重新准备。')
            duration=self._play_checked(path,expected or digest)
        except (ValueError,OSError) as exc:
            self._discard_asset_path(path)
            self.tell(str(exc),True)
            return False
        self.playing_target = dict(target=target,label=label,asset=copy.deepcopy(asset),context=copy.deepcopy(context) or {},
            wav_digest=expected or digest,segments=copy.deepcopy((context or {}).get('segments',[])),
            bpm=(context or {}).get('bpm'),mapping_reason=(context or {}).get('mapping_reason') or (None if context else '无可信音符映射；仅显示实际音频与时间。'))
        self.play_duration = duration
        self.seek.configure(to=duration)
        self.update_transport()
        return True

    def _play_checked(self,path,expected,start=0.):
        """Keep the existing device API; reject mutations while it opens/reads WAV."""
        def stamp():
            state=Path(path).stat()
            return state.st_dev,state.st_ino,state.st_size,state.st_mtime_ns,state.st_ctime_ns
        before=stamp()
        if self.file_digest(path)!=expected or stamp()!=before:
            raise ValueError('播放文件字节已变化，请明确重新准备。')
        try:
            duration=self.player.play(path,start=start)
            if stamp()!=before or self.file_digest(path)!=expected or stamp()!=before:
                raise ValueError('播放文件在读取期间变化，已停止；请明确重新准备。')
            return duration
        except Exception:
            self.stop()
            raise

    def play_selected(self):
        if not self.selected_target:
            return
        kind,ident = self.selected_target
        if kind=='draft':
            key = audition_key('draft',self.combo_inputs,self.state_data['project']['bpm'])
            asset = self._ready_asset(key)
            if asset:
                return self.start_playback(asset,('draft',key),'组合草稿',context=self.ready_contexts.get(key))
            self.tell('组合草稿尚未就绪，请先准备试听。')
            return False
        return self.play_target(kind,ident)

    def toggle_pause(self):
        _,mode = self.player.status()
        if mode=='playing':self.player.pause()
        elif mode=='paused':self.player.resume()
        self.update_transport()

    def stop(self):
        self.invalidate_play_intent()
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
                self.validate_playing()
                self._play_checked(self.playing_target['asset']['wav_path'],self.playing_target['wav_digest'],start=max(0.,position))
                if was_paused:self.player.pause()

    def validate_playing(self):
        playing=self.playing_target
        if not playing:raise ValueError('尚无播放对象。')
        context=playing['context'];old=playing['asset'];target=playing['target']
        if context.get('neutral'):
            asset=self._ready_asset(context['key'])
            if asset!=old:raise ValueError('播放缓存身份已变化，请明确重新准备。')
        elif context.get('schema')=='emoblocks.ui-playback.v1':
            ref=context['target']
            if ref['kind']=='recommendation':facts=self.controller.recommendation_playback(ref['id'],kind=ref['side'],mode=ref['mode'])
            else:facts=self.controller.history_playback(ref['id'],mode=ref['mode'])
            if facts!=context:raise ValueError('播放谱或资产身份已变化，请明确重新选择。')
        elif 'files' in old:
            asset=(self.controller.recommendation_asset(target[1],kind=target[3],mode=target[2])
                   if target[0]=='recommendation' else self.controller.history_asset(target[1],mode=old['mode']))
            if any(asset[k]!=old[k] for k in ('id','version','score_ref','mode')):raise ValueError('播放资产版本已更新，请明确选择后播放。')
        if self.file_digest(old['wav_path'])!=playing['wav_digest']:raise ValueError('播放文件字节已变化，请明确重新准备。')
        return True

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
        # Full names remain available inline on click/focus, without growing the footer.
        limit = max(12,min(36,(self.root.winfo_width()-320)//28))
        playing = playing[:limit]+('…' if len(playing)>limit else '')
        label = label[:limit]+('…' if len(label)>limit else '')
        prefix = {'playing':'播放中','paused':'已暂停','stopped':'已结束','closed':'已停止'}.get(mode,mode)
        asset = self.playing_target['asset'] if self.playing_target else None
        durations = f'\n预计正文 {asset["body_seconds"]:.1f} 秒 / 实际音频 {asset["audio_seconds"]:.1f} 秒' if asset else ''
        mode_label=('编配' if asset.get('mode')=='arranged' else '单旋律') if asset else ''
        side_label=('基础' if asset.get('kind')=='comparison' else '处理后' if asset.get('kind')=='final' else '') if asset else ''
        from tkinter import font as tkfont
        width=max(90,self.transport_label.winfo_width())
        measure=tkfont.Font(root=self.root,font=font()).measure
        name=playing[:9];clock=f' · {position:.1f}/{self.play_duration:.1f}秒'
        suffix=(f' · {mode_label} {side_label}' if asset else '')
        while len(name)>1 and measure(prefix+' · '+name+clock+suffix)>width:name=name[:-1]
        self.transport_label.configure(text=prefix+' · '+name+('…' if name!=playing else '')+clock+suffix+durations,wraplength=0)
        self.cancel_button.state(['!disabled'] if self.jobs else ['disabled'])
        self.pause_button.set_icon('play' if mode=='paused' else 'pause')
        self.pause_button.state(['!disabled'] if mode in ('playing','paused') else ['disabled'])
        from curve_player_ui import update_navigation
        update_navigation(self)
        self.page.timeline.draw_playing()
        self.page.cards.mark_selection()

    def transport_description(self):
        playing = self.playing_target['label'] if self.playing_target else '尚未播放'
        target = self.resolve(*self.selected_target) if self.selected_target and self.selected_target[0]!='draft' else None
        selected = target['label'] if target else ('组合草稿' if self.selected_target and self.selected_target[0]=='draft' else '未选择试听对象')
        asset=self.playing_target['asset'] if self.playing_target else None
        durations=f'\n预计正文 {asset["body_seconds"]:.1f} 秒 / 实际音频 {asset["audio_seconds"]:.1f} 秒' if asset else ''
        return '当前播放：'+playing+'\n当前选择：'+selected+durations

    def ghost(self):
        if self.drag_ghost is None:
            from curve_drag_ui import DragGhost
            self.drag_ghost=DragGhost(self)
        return self.drag_ghost

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
            self.page.cards.show_drop_target(*hit)
            self.ghost().show(d['material'],event.x_root,event.y_root,text='组合 · '+('放在目标之前' if hit[1]=='left' else '放在目标之后'))
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
        self.page.cards.clear_drop_target()
        if d and canvas.contains_root(x,y):
            raw=canvas.root_tick(x,d['offset'])
            canvas.preview = (snap_tick(raw),d['material']['length_ticks'])
            result=self.ghost().check('place',material_id=d['material']['id'],start_tick=canvas.preview[0])
            if raw<0 or raw+d['material']['length_ticks']>canvas.project['total_ticks']:result=dict(allowed=False,error=dict(message='落点超出时间轴'))
            canvas.preview_state=result;canvas.preview_material=d['material']
            self.ghost().show(d['material'],x,y,result)
            canvas.edge_scroll(x,y)
        else:
            canvas.preview = None
            if d and d['active']:self.ghost().show(d['material'],x,y,dict(allowed=False),text='移入画布或素材卡；其它位置取消')
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
            canvas.set_mode('arrange')
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
        if self.drag_ghost:self.drag_ghost.clear()
        self.page.cards.clear_drop_target()
        self.page.timeline.cancel()
        if event is not None:self.exit_private_preview()
        return 'break' if event else None

    def add_combo(self, source, target_id, side):
        self.invalidate_play_intent()
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
        self.page.combo_text.configure(text='组合草稿 · '+str(len(self.combo_inputs))+' 个组件')
        self.show_detail('组合草稿：'+' → '.join(m['label'] for m in self.combo_inputs))
        self.selected_target = ('draft',snapshot_key('draft',self.combo_inputs))
        self.update_transport()
        self.tell('组合尚未加入工程 · 确认或取消。')

    def cancel_combo(self):
        self.invalidate_play_intent()
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
        key = audition_key('draft',inputs,self.state_data['project']['bpm'])
        ready = self._ready_asset(key) if audition else None
        if ready:
            self.tell(f'组合试听已就绪 · 预计正文 {ready["body_seconds"]:.1f} 秒 / 实际音频 {ready["audio_seconds"]:.1f} 秒 · 请明确播放。')
            return
        def work(snapshot):
            material = _provider().combine(snapshot['project'],inputs,label)
            if audition:return dict(asset=_provider().render_audition(material,bpm=snapshot['project']['bpm']),material=material)
            return dict(sources=[],materials=[material],warnings=[])
        def done(payload,token,snapshot):
            if audition:
                prepared_material=payload['material'];payload=payload['asset']
                key = audition_key('draft',inputs,snapshot['project']['bpm'])
                from curve_playback_ui import neutral_context
                target_snapshot=dict(snapshot,target=prepared_material)
                self._cache_asset(key,payload,snapshot.get('audition_profile'),neutral_context('draft',key,target_snapshot,key,snapshot_key('input',snapshot['project'])))
                self.tell(f'组合试听已就绪 · 预计正文 {payload["body_seconds"]:.1f} 秒 / 实际音频 {payload["audio_seconds"]:.1f} 秒。')
                return key
            else:
                self.apply_batch(payload,token)
                self.combo_inputs = []
                self.page.combo_panel.pack_forget()
                self.selected_target = None
        return self._start_job('COMBINE',None,work,done)

    def prepare_combo(self):
        return self._combo_job(True)

    def confirm_combo(self):
        self.invalidate_play_intent()
        return self._combo_job(False)

    def history_selected(self, event=None):
        indices = self.page.history_list.curselection()
        if indices and indices[0]<len(self.history):
            item = self.history[indices[0]]
            self.select_target('history',item['id'])
            self.show_detail(self.history_output_description(item))
            self.update_exports()

    def history_output(self, item):
        mode = self.recommendation.mode_key() if item.get('scope') in ('FULL','LOCAL') else None
        query = getattr(self.controller,'history_output_state',None)
        if query is not None:
            return query(item['id'],mode=mode)
        # Preserve older legacy/injected interfaces, without authorizing native mode fallback.
        availability = dict(item['availability']) if mode is None else dict.fromkeys(('wav','mid','mmp'),False)
        message = '历史输出不可用。' if mode is None else '历史模式认证接口尚未接通。'
        return dict(result_id=item['id'],mode=mode,score_ref=None,asset_ref=None,renderer_profile=None,
                    availability=availability,errors={f:None if available else dict(code='OUTPUT_FILE_UNAVAILABLE',message=message,details={})
                                                     for f,available in availability.items()})

    def history_output_description(self, item):
        output = self.history_output(item)
        mode = ' · '+MODES[output['mode']] if output['mode'] is not None else ''
        text = item['label']+mode+' · 主体 '+str(item['body_seconds'])+' 秒 · 音频 '+str(item['audio_seconds'])+' 秒'
        errors = [f.upper()+': '+error['message'] for f,error in output['errors'].items() if error]
        if errors:text += '\n'+'；'.join(errors)
        if item.get('scope')=='LOCAL':text += '\n局部接受版本 · 不可正式整曲导出。'
        return text

    def update_exports(self):
        item = self.resolve('history',self.selected_history_id)
        output = self.history_output(item) if item else None
        any_enabled=False
        for index,(format_,button) in enumerate(self.page.export_buttons.items()):
            enabled=bool(item and item.get('scope')!='LOCAL' and item.get('capabilities',{}).get('can_export_final',True)
                         and output['availability'][format_])
            button.state(['!disabled'] if enabled else ['disabled'])
            self.export_menu.entryconfigure(index,state='normal' if enabled else 'disabled')
            any_enabled=any_enabled or enabled
        self.export_menu_button.state(['!disabled'] if any_enabled else ['disabled'])

    def export_history(self, format_):
        item = self.resolve('history',self.selected_history_id)
        if not item or item.get('scope')=='LOCAL' or not item.get('capabilities',{}).get('can_export_final',True):
            return
        output = self.history_output(item)
        if not output['availability'][format_]:
            self.tell(output['errors'][format_]['message'],True)
            return
        ident = item['id']
        mode = output['mode']
        destination = filedialog.asksaveasfilename(parent=self.root,defaultextension='.'+format_,
                                                  initialfile='EmoBlocks.'+format_,filetypes=[(format_.upper(),'*.'+format_)])
        if destination:
            label = item['label']
            def export():
                path = Path(self.controller.export_history(ident,format_,destination,mode=mode) if mode is not None
                            else self.controller.export_history(ident,format_,destination)).resolve()
                self.last_export = dict(id=ident,label=label,format=format_,path=path)
                self.export_receipt.configure(state='normal')
                self.export_receipt.delete('1.0','end')
                display_format = {'wav':'WAV','mid':'MIDI','mmp':'MMP'}[format_]
                version = f' · v{item["version"]} · {mode}' if mode is not None else ''
                self.export_receipt.insert('1.0',f'已导出版本：{label} [{ident}]{version} · {display_format}\n{path}')
                self.export_receipt.configure(state='disabled')
                self.export_summary.configure(text=f'{display_format} 已导出')
                self.export_row.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(1,0))
                from curve_raster import pixels
                self.page.footer.configure(height=pixels(self.root,162))
                self.show_detail(f'已导出版本：{label} [{ident}]{version} · {display_format}\n{path}')
                self.tell('导出成功 · '+display_format+' · 完整位置见详情。')
                return path
            self.safe(export)

    def open_export_folder(self):
        if self.last_export:
            return self.safe(lambda:ui_platform.open_folder(self.last_export['path'].parent))

    def save_project(self):
        if self.state_data['access_mode']=='editable' and all(j['kind'] in ('COMPLETION','BRIDGE','CONNECTION','RECOMMENDATION','RECOMMENDATION_MODE') for j in self.jobs.values()):
            path = self.controller.save_snapshot()
            self.refresh()
            self.tell('工程快照已保存：'+str(path))
            return path

    def _switched(self):
        self.invalidate_play_intent()
        self.view_bookmarks.clear()
        self.source_filter_id=None
        self.workspace_stage='编辑'
        self.recommendation.shutdown()
        self.recommendation.runtimes.clear()
        self.recommendation.restore_view()
        self.recommendation.visible = False
        self.recommendation.selected_id = None
        self.jobs.clear()
        self.connection.restore_view()
        self.connection.visible = False
        self.bridge.restore_view()
        self.bridge.visible = False
        self.bridge.choice.set('')
        self.completion.restore_view()
        self.completion.selected_gap_id = None
        self.completion.choice.set('')
        self.cancel_interaction()
        self.combo_inputs = []
        self.page.combo_panel.pack_forget()
        self.selected_target = self.selected_source_id = self.selected_material_id = self.selected_history_id = None
        self.ready_assets.clear()
        self.ready_contexts.clear()
        self.ready_file_digests.clear()
        self.stop()
        self.refresh()
        self.tell(self.workspace_hint())

    def open_project(self, path=None):
        if self.jobs:
            self.tell('请先明确取消当前任务，再打开工程。')
            return False
        path = path or filedialog.askopenfilename(parent=self.root,filetypes=[('工程快照','*.json')])
        if path:
            self.controller.load(path)
            self._switched()
            self.tell('工程已打开 · '+self.workspace_hint())

    def new_project(self):
        if self.jobs:
            self.tell('请先明确取消当前任务，再新建工程。')
            return False
        self.controller.new()
        self._switched()
        self.tell('新的空工程 · 尚未保存。')

    def toggle_sources(self):
        self.source_user_collapsed = bool(self.page.source_panel.winfo_manager())
        self.layout_sources()

    def layout_sources(self):
        collapsed = self.source_user_collapsed if self.source_user_collapsed is not None else self.root.winfo_width()<1180
        if collapsed:self.page.source_panel.grid_remove()
        else:self.page.source_panel.grid()
        self.collapse_button.configure(text='展开来源' if collapsed else '收起来源')

    def resized(self, event):
        if event.widget!=self.root:
            return
        self.layout_sources()
        width = max(400,event.width-50)
        self.status_label.configure(wraplength=0)
        self.page.memory_label.configure(wraplength=0)
        self.page.draw_source()

    def toggle_theme(self):
        self.cancel_interaction()
        self.theme.set('dark' if self.theme.name=='light' else 'light')
        self.theme_button.configure(text='浅色' if self.theme.name=='dark' else '深色')
        self.theme_button.set_icon('sun' if self.theme.name=='dark' else 'moon')
        self.refresh()

    def wheel(self, event):
        widget = self.root.winfo_containing(event.x_root,event.y_root)
        units = ui_platform.wheel_units(event.delta)
        if self.page.secondary_tools.contains(widget) and not isinstance(widget,(tk.Text,ttk.Combobox,ttk.Entry)):
            self.page.secondary_tools.canvas.yview_scroll(units*24,'units')
            return 'break'
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
        if self.page.secondary_tools.contains(widget) and not isinstance(widget,(tk.Text,ttk.Combobox,ttk.Entry)):
            scroll_canvas_pixels(self.page.secondary_tools.canvas,'y',dy)
            return 'break'
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
        self.bridge.update_elapsed()
        self.connection.update_elapsed()
        self.recommendation.update_elapsed()
        self.safe(self.update_transport)
        self.timer = self.root.after(80,self.tick)

    def close(self):
        if self.closed:return True
        if self.jobs:
            self.tell('请先明确取消当前任务，再关闭窗口。')
            return False
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
            self.recommendation.shutdown()
            for job in self.jobs.values():
                if job['kind'] in ('COMPLETION','BRIDGE','CONNECTION'):job['cancel'].set()
            self.closed = True
            if hasattr(self,'timer'):self.root.after_cancel(self.timer)
            if self.card_scroll_timer is not None:self.root.after_cancel(self.card_scroll_timer)
            self.player.close()
            if self.file_drop:self.file_drop.close()
