"""P4 snapshot jobs and read-only views; the Facade owns all candidate data."""
import copy
import importlib
import queue
import threading
import tkinter as tk
from tkinter import ttk

from curve_theme import EMOTION_NAMES, hint


def prepare_completion(request, should_cancel=None, on_progress=None):
    return importlib.import_module('curve_candidates').prepare_completion(
        request, should_cancel=should_cancel, on_progress=on_progress)


def error_info(exc):
    details = getattr(exc, 'details', {})
    return dict(code=getattr(exc, 'code', 'ERROR'), message=str(exc),
                details=details if isinstance(details, dict) else {})


class CompletionUI:
    def __init__(self, app):
        self.app = app
        self.messages = queue.Queue()
        self.gaps = []
        self.selected_gap_id = None
        self.candidates = []
        self.preview_candidate = None
        self.bookmark = None
        self.state = dict(status='IDLE', outcome=None, error=None, message='')
        self.panel = ttk.Frame(app.page.stage_area, style='Curve.Panel.TFrame')
        row = ttk.Frame(self.panel, style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.start_button = ttk.Button(row, text='补全基础候选', style='Curve.TButton',
                                      command=lambda: app.safe(self.start))
        self.start_button.pack(side='left')
        self.bridge_button = ttk.Button(row, text='Bridge →', style='Curve.TButton',
                                        command=lambda: app.bridge.show())
        self.cancel_button = ttk.Button(row, text='取消补全', style='Curve.TButton', command=self.cancel)
        self.cancel_button.pack(side='left', padx=4)
        self.choice = tk.StringVar()
        self.selector = ttk.Combobox(row, textvariable=self.choice, state='readonly', width=12,
                                    style='Curve.TCombobox')
        self.selector.pack(side='left', fill='x', expand=True)
        self.selector.bind('<<ComboboxSelected>>', lambda _: self.enter_preview())
        self.selector.bind('<Return>', lambda _: self.enter_preview())
        self.exit_button = ttk.Button(row, text='返回编辑', style='Curve.TButton', command=self.exit_preview)
        self.exit_button.pack(side='right', padx=(4,0))
        self.label = ttk.Label(self.panel, style='Curve.Muted.TLabel', wraplength=360, takefocus=True)
        self.label.pack(fill='x', pady=(2,0))
        hint(self.label, self.description, app.show_detail)
        self.label.bind('<Button-1>', lambda _: app.show_detail(self.description()))
        self.label.bind('<Return>', lambda _: app.show_detail(self.description()))
        hint(self.selector, '只读预览基础排布；尚未处理bridge与连接，不可试听、应用或导出成品。', app.show_detail)

    def refresh(self):
        app = self.app
        available = app.state_data['capabilities'].get('completion', False)
        if not available:
            self.panel.pack_forget()
            self.gaps = []
            self.selected_gap_id = None
            self.preview_candidate = None
            self.bookmark = None
            return
        self.panel.pack(fill='x', before=app.page.stage_anchor, pady=(4,0))
        bridge = getattr(app,'bridge',None)
        connection = getattr(app,'connection',None)
        recommendation = getattr(app,'recommendation',None)
        if app.workspace_stage!='补全' or (bridge and bridge.visible) or (connection and connection.visible) or (recommendation and recommendation.visible):self.panel.pack_forget()
        if app.state_data['capabilities'].get('bridge',False):self.bridge_button.pack(side='left',padx=4)
        else:self.bridge_button.pack_forget()
        self.gaps = app.controller.gap_items()
        if self.selected_gap_id not in {g['id'] for g in self.gaps}:
            self.selected_gap_id = None
        self.state = app.controller.completion_state()
        outcome = self.state['outcome']
        self.candidates = outcome['candidates'] if outcome else []
        values = ['基础候选 '+str(i+1) for i in range(len(self.candidates))]
        self.selector.configure(values=values)
        if self.choice.get() not in values: self.choice.set('')
        if self.preview_candidate and (self.state['status']!='READY' or
                self.preview_candidate['id'] not in {c['id'] for c in self.candidates}):
            self.restore_view()
        self.start_button.state(['!disabled'] if app.editable and self.state['status']!='RUNNING' else ['disabled'])
        active = any(j['kind']=='COMPLETION' for j in app.jobs.values())
        self.cancel_button.state(['!disabled'] if active else ['disabled'])
        self.selector.state(['!disabled','readonly'] if self.state['status']=='READY' and values else ['disabled'])
        self.exit_button.state(['!disabled'] if self.preview_candidate else ['disabled'])
        if self.preview_candidate:self.start_button.pack_forget()
        else:self.start_button.pack(side='left')
        if active:self.cancel_button.pack(side='left',padx=4)
        else:self.cancel_button.pack_forget()
        if self.state['status']=='READY' and values:
            self.selector.pack(side='left',fill='x',expand=True,padx=4)
        else:self.selector.pack_forget()
        if self.preview_candidate:self.exit_button.pack(side='right',padx=(4,0))
        else:self.exit_button.pack_forget()
        status = dict(IDLE='未计算', RUNNING='补全计算中', READY='基础候选已暂存',
                      FAILED='补全失败', CANCELLED='补全已取消', STALE='候选已失效',
                      INTERRUPTED='计算已中断 · 请明确重试', NOT_NEEDED='没有待补全空缺')[self.state['status']]
        if outcome and outcome['status']=='INSUFFICIENT': status += ' · 方案不足'
        target = next((g for g in self.gaps if g['id']==self.selected_gap_id), None)
        scope = f'{target["start_tick"]}–{target["end_tick"]} tick' if target else '全部空缺'
        if self.preview_candidate: status = '基础候选只读 · 尚未处理bridge与连接'
        self.label.configure(text=status if self.preview_candidate else status+' · '+scope, wraplength=450)

    def select_gap(self, ident):
        if self.app.private_preview() or self.app.jobs: return
        if ident is not None and ident not in {g['id'] for g in self.gaps}: return
        self.selected_gap_id = ident
        self.refresh()
        self.app.page.timeline.draw()
        self.app.show_detail(self.label.cget('text'))

    def start(self):
        app = self.app
        if not app.can_edit('completion'): return False
        app.cancel_interaction()
        captured = app.controller.capture_completion(selected_gap_id=self.selected_gap_id)
        if captured['token'] is None:
            app.refresh()
            app.tell(self.state['message'] or '没有待补全空缺。')
            return True
        token, request = copy.deepcopy(captured['token']), copy.deepcopy(captured['request'])
        event = threading.Event()
        job = dict(kind='COMPLETION', token=token, cancel=event, event_seq=-1)
        app.jobs[token['request_id']] = job
        app.refresh()
        app.tell('补全计算中 · 仅暂存基础候选。')
        messages = self.messages
        def progress(value):
            messages.put((token, 'PROGRESS', copy.deepcopy(value)))
        def worker():
            try:
                outcome = prepare_completion(request, should_cancel=event.is_set, on_progress=progress)
                messages.put((token, 'DONE', outcome))
            except Exception as exc:
                messages.put((token, 'ERROR', error_info(exc)))
        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception as exc:
            event.set()
            failed = app.controller.fail_completion(token,error_info(exc))
            if app.jobs.get(token['request_id']) is job: app.jobs.pop(token['request_id'])
            app.refresh()
            if failed or (self.state['attempt_id']==token['request_id'] and self.state['status']=='FAILED'):
                app.tell(self.state['error']['message'],True)
                app.show_detail(self.description())
            return False
        return True

    def drain(self):
        app = self.app
        while True:
            try: token, kind, payload = self.messages.get_nowait()
            except queue.Empty: return
            job = app.jobs.get(token['request_id'])
            if not job or job['kind']!='COMPLETION' or job['token']!=token: continue
            terminal = kind!='PROGRESS'
            try:
                if not app.controller.accepts(token):
                    job['cancel'].set()
                    terminal = True
                    continue
                if kind=='PROGRESS':
                    seq = payload.get('event_seq')
                    if isinstance(seq,bool) or not isinstance(seq,int) or seq<=job['event_seq']: continue
                    if payload.get('phase')!='BASE_COMPLETION': continue
                    job['event_seq'] = seq
                    app.tell('补全计算中 · '+str(payload['message'])+' · 扩展 '+str(payload['expansions']))
                elif kind=='DONE':
                    finished = app.controller.finish_completion(token,payload)
                    app.refresh()
                    if finished or (self.state['attempt_id']==token['request_id'] and self.state['status']=='FAILED'):
                        message = self.state['error']['message'] if self.state['error'] else self.state['message'] or self.label.cget('text')
                        app.tell(message, self.state['status']=='FAILED')
                        app.show_detail(self.description())
                else:
                    if app.controller.fail_completion(token,payload):
                        app.refresh()
                        app.tell(self.state['error']['message'], True)
                        app.show_detail(self.description())
            except Exception as exc:
                terminal = True
                if app.controller.fail_completion(token,error_info(exc)):
                    app.tell(str(exc), True)
            finally:
                if terminal:
                    if app.jobs.get(token['request_id']) is job: app.jobs.pop(token['request_id'])
                    app.refresh()

    def cancel(self):
        changed = False
        for ident, job in list(self.app.jobs.items()):
            if job['kind']!='COMPLETION': continue
            job['cancel'].set()
            changed = self.app.controller.cancel_completion(job['token']) or changed
            self.app.jobs.pop(ident,None)
        self.app.refresh()
        if changed: self.app.tell('补全已取消 · 工程和当前播放保持原状。')
        return changed

    def enter_preview(self):
        if self.state['status']!='READY': return
        index = self.selector.current()
        if not 0<=index<len(self.candidates): return
        self.app.recommendation.restore_view()
        self.app.recommendation.visible = False
        canvas = self.app.page.timeline
        self.app.cancel_interaction()
        self.app.bridge.restore_view()
        self.app.bridge.visible = False
        self.app.connection.restore_view()
        self.app.connection.visible = False
        if self.bookmark is None:
            self.bookmark = dict(selected=canvas.selected_id, scroll=canvas.canvas.xview()[0], mode=canvas.mode)
        self.preview_candidate = copy.deepcopy(self.candidates[index])
        canvas.selected_id = None
        self.app.refresh()
        self.app.show_detail(self.description())

    def restore_view(self):
        self.preview_candidate = None
        if self.bookmark:
            canvas = self.app.page.timeline
            canvas.selected_id = self.bookmark['selected']
            canvas.mode = self.bookmark['mode']
            canvas.canvas.xview_moveto(self.bookmark['scroll'])
            self.bookmark = None

    def exit_preview(self):
        self.restore_view()
        self.app.refresh()

    def describe_placement(self, placement):
        generation = (placement['emotion_variant'] or {}).get('generation') or {}
        parts = [placement['base_snapshot']['label'], EMOTION_NAMES[placement['emotion']]]
        if generation:
            parts.append('旋律已轻改' if generation.get('melody_changed',False) else '旋律未改变')
            parts.extend(w['message'] for w in generation.get('warnings',[]))
            if (generation.get('accompaniment_hints') or {}).get('status')=='suggested-not-rendered':
                parts.append('编配仅为建议，尚未渲染')
        return ' · '.join(parts)

    def description(self):
        parts = [self.label.cget('text'), '基础候选不可完整试听、应用或导出成品；素材试听仍为中性单旋律。']
        outcome = self.state['outcome']
        if self.state['message']: parts.append(self.state['message'])
        if self.state['error']: parts.append(self.state['error']['code']+' · '+self.state['error']['message'])
        if outcome:
            parts.extend(w['message'] for w in outcome['shortage_reasons'])
            parts.append('搜索终止：'+outcome['search']['termination'])
        if self.state.get('request'):
            parts.append('计算目标：'+'；'.join(f'{g["start_tick"]}–{g["end_tick"]} tick' for g in self.state['request']['target_gaps']))
        candidate = self.preview_candidate
        if candidate:
            parts.append('剩余空缺：'+('；'.join(f'{g["start_tick"]}–{g["end_tick"]} tick' for g in candidate['remaining_gaps']) or '无'))
            parts.extend(w['message'] for w in candidate['reasons'])
            added = set(candidate['added_placement_ids'])
            parts.extend(self.describe_placement(p) for p in candidate['project']['placements'] if p['id'] in added)
        return '\n'.join(parts)
