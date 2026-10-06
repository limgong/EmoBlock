"""P5 decision/lock/generation jobs. Only the Facade publishes bridge facts."""
import copy
import importlib
import itertools
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from curve_completion_ui import error_info
from curve_theme import EMOTION_NAMES, hint


def decide_bridge(request, should_cancel=None, on_progress=None):
    return importlib.import_module('curve_bridges').decide_bridge(
        request, should_cancel=should_cancel, on_progress=on_progress)


def generate_bridges(request, plan, should_cancel=None, on_progress=None, on_result=None):
    return importlib.import_module('curve_bridges').generate_bridges(
        request, plan, should_cancel=should_cancel, on_progress=on_progress, on_result=on_result)


class BridgeUI:
    def __init__(self, app):
        self.app = app
        self.messages = queue.Queue()
        self.visible = False
        self.preview = None
        self.bookmark = None
        self.state = dict(status='IDLE', phase=None, attempt_id=None, request=None, plan=None,
                          protections=[], results=[], outcome=None, preview=None,
                          remaining_gaps=[], capabilities={}, error=None, message='')
        self.inputs = []
        self.panel = ttk.Frame(app.page.right, style='Curve.Panel.TFrame')
        row = ttk.Frame(self.panel, style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.back_button = ttk.Button(row, text='←补全', style='Curve.TButton', command=self.show_completion)
        self.back_button.pack(side='left')
        self.choice = tk.StringVar()
        self.selector = ttk.Combobox(row, textvariable=self.choice, state='readonly', width=10,
                                    style='Curve.TCombobox')
        self.selector.pack(side='left', fill='x', expand=True, padx=4)
        self.start_button = ttk.Button(row, text='判断Bridge', style='Curve.TButton',
                                      command=lambda: app.safe(self.start))
        self.start_button.pack(side='left')
        self.cancel_button = ttk.Button(row, text='取消', style='Curve.TButton', command=self.cancel)
        self.preview_button = ttk.Button(row, text='只读预览', style='Curve.TButton', command=self.toggle_preview)
        self.preview_button.pack(side='right', padx=(4,0))
        self.label = ttk.Label(self.panel, style='Curve.Muted.TLabel', takefocus=True)
        self.label.pack(fill='x', pady=(2,0))
        hint(self.label, self.description, app.show_detail)
        hint(self.selector, '明确选择所属补全候选；当前排布仅在没有空缺时可用。单条有效方案也可进入Bridge。', app.show_detail)
        hint(self.preview_button, '复用唯一画布查看真实桥范围与保护；只读，不改变编辑、选择或播放对象。', app.show_detail)
        self.label.bind('<Button-1>', lambda _: app.show_detail(self.description()))
        self.label.bind('<Return>', lambda _: app.show_detail(self.description()))

    def show(self):
        connection = getattr(self.app,'connection',None)
        if connection:
            connection.restore_view()
            connection.visible = False
        self.visible = True
        self.app.completion.restore_view()
        self.app.refresh()
        self.app.show_detail(self.description())

    def show_completion(self):
        self.app.show_curve_stage('补全')

    def active_job(self):
        return next((j for j in self.app.jobs.values() if j['kind']=='BRIDGE'
                     and j['token']['request_id']==self.state['attempt_id']), None)

    def status_text(self):
        status, phase = self.state['status'], self.state['phase']
        if status=='RUNNING':
            text = dict(BRIDGE_DECISION='Bridge位置判断中', BRIDGE_LOCKED='Bridge位置已确定、范围已保护',
                        BRIDGE_GENERATION='Bridge生成中', BRIDGES_READY='Bridge已就绪')[phase]
            job = self.active_job()
            if job:text += f' · 已用 {int(time.monotonic()-job["started"])} 秒'
            return text
        text = dict(IDLE='Bridge尚未计算', READY='Bridge已就绪', FAILED='Bridge失败',
                    CANCELLED='Bridge已取消', INTERRUPTED='Bridge已中断，请明确重试', STALE='Bridge结果已失效')[status]
        plan = self.state['plan']
        if plan and plan['decision']=='none':text += ' · 明确不使用新Bridge'
        if self.state['error']:text += ' · '+self.state['error']['message']
        return text

    def refresh(self):
        app = self.app
        if not app.state_data['capabilities'].get('bridge',False):
            self.panel.pack_forget()
            self.restore_view()
            self.visible = False
            return
        self.state = app.controller.bridge_state()
        if self.preview is not None:
            if self.state['preview'] is None or self.state['status']=='STALE':self.restore_view()
            else:self.preview = copy.deepcopy(self.state['preview'])
        completion = app.completion
        self.inputs = [(None,None,'当前完整排布')] if not completion.gaps else []
        if completion.state['status']=='READY':
            self.inputs += [(c['id'],completion.state['attempt_id'],f'基础候选 {i+1}')
                            for i,c in enumerate(completion.candidates)]
        values = [item[2] for item in self.inputs]
        self.selector.configure(values=values)
        if self.choice.get() not in values:self.choice.set(values[0] if values else '')
        active = self.active_job() is not None
        self.selector.state(['disabled'] if app.jobs or not values else ['!disabled','readonly'])
        self.start_button.state(['!disabled'] if not app.jobs and values else ['disabled'])
        self.preview_button.state(['!disabled'] if self.state['preview'] is not None and self.state['status']!='STALE' else ['disabled'])
        self.preview_button.configure(text='返回编辑' if self.preview is not None else '只读预览')
        if active:
            self.start_button.pack_forget()
            self.cancel_button.pack(side='left')
        else:
            self.cancel_button.pack_forget()
            self.start_button.pack(side='left')
        connection = getattr(app,'connection',None)
        if self.visible and not (connection and connection.visible):
            self.panel.pack(fill='x',before=app.page.memory_label,pady=(4,0))
            completion.panel.pack_forget()
        else:self.panel.pack_forget()
        self.update_elapsed()

    def update_elapsed(self):
        # Compact single line; full error/reasons remain in focus/click details.
        text = self.status_text()
        limit = max(16,(self.app.page.right.winfo_width()-20)//16)
        self.label.configure(text=text[:limit]+('…' if len(text)>limit else ''))

    def start(self):
        app = self.app
        if app.jobs or app.state_data['access_mode']!='editable' or not app.state_data['capabilities'].get('bridge',False):
            return False
        index = self.selector.current()
        if not 0<=index<len(self.inputs):return False
        candidate_id, attempt_id, _ = self.inputs[index]
        # The Facade resolves IDs from its Bundle; the UI never supplies candidate data.
        try:
            captured = app.controller.capture_bridge(candidate_id=candidate_id, completion_attempt_id=attempt_id)
        except Exception as exc:
            # Capture rejects atomically, so no token exists to fail/cancel.
            app.refresh()
            app.tell(str(exc),True)
            return False
        token, request = copy.deepcopy(captured['token']), copy.deepcopy(captured['request'])
        job = dict(kind='BRIDGE', token=token, request=request, cancel=threading.Event(),
                   stage_id='DECISION', event_seq=-1, started=time.monotonic())
        app.jobs[token['request_id']] = job
        try:
            app.cancel_interaction()
            self.restore_view()
            app.completion.restore_view()
            app.connection.restore_view()
            app.connection.visible = False
            self.visible = True
            app.refresh()
            app.tell(self.status_text())
            self.launch(job)
        except Exception as exc:
            self.abort(job,error_info(exc))
            return False
        return True

    def launch(self, job, plan=None):
        token, request = copy.deepcopy(job['token']), copy.deepcopy(job['request'])
        stage, event, messages = job['stage_id'], job['cancel'], self.messages
        counter = itertools.count()
        def send(kind, value):
            messages.put((token,stage,next(counter),kind,copy.deepcopy(value)))
        def worker():
            try:
                if plan is None:
                    value = decide_bridge(request, should_cancel=event.is_set, on_progress=lambda p:send('PROGRESS',p))
                else:
                    value = generate_bridges(request, copy.deepcopy(plan), should_cancel=event.is_set,
                        on_progress=lambda p:send('PROGRESS',p), on_result=lambda r:send('RESULT',r))
                send('DONE',value)
            except Exception as exc:send('ERROR',error_info(exc))
        threading.Thread(target=worker,daemon=True).start()

    def remove_job(self, job):
        ident = job['token']['request_id']
        if self.app.jobs.get(ident) is job:self.app.jobs.pop(ident)

    def report(self, token):
        self.app.refresh()
        if self.state['attempt_id']==token['request_id']:
            self.app.tell(self.status_text(), self.state['status']=='FAILED')
            self.app.show_detail(self.description())

    def abort(self, job, error):
        job['cancel'].set()
        try:self.app.controller.fail_bridge(job['token'],error)
        finally:
            self.remove_job(job)
            self.report(job['token'])

    def drain(self):
        app = self.app
        while True:
            try:token,stage,seq,kind,payload = self.messages.get_nowait()
            except queue.Empty:return
            job = app.jobs.get(token['request_id'])
            if (not job or job['kind']!='BRIDGE' or job['token']!=token or stage!=job['stage_id']
                    or isinstance(seq,bool) or not isinstance(seq,int) or seq<=job['event_seq']):continue
            try:
                if not app.controller.accepts(token):
                    job['cancel'].set()
                    self.remove_job(job)
                    self.report(token)
                    continue
                job['event_seq'] = seq
                if kind=='PROGRESS':
                    self.state = app.controller.bridge_state()
                    self.update_elapsed()
                    app.tell(self.status_text()+(' · '+str(payload['message']) if payload.get('message') else ''))
                elif kind=='RESULT':
                    app.controller.record_bridge_result(token,payload)
                    self.report(token)
                    if self.state['status']!='RUNNING':
                        job['cancel'].set()
                        self.remove_job(job)
                        app.refresh()
                elif kind=='DONE' and stage=='DECISION':
                    plan = app.controller.lock_bridge(token,payload)
                    self.report(token)  # Publish actual locks before starting the generation request.
                    if not app.controller.begin_bridge_generation(token,plan):
                        self.abort(job,dict(code='BRIDGE_START_REJECTED',message='Bridge生成请求未被接受。',details={}))
                        continue
                    job['stage_id'] = f'GENERATION:{plan["id"]}:{plan["version"]}:{plan["plan_fingerprint"]}'
                    job['event_seq'] = -1
                    self.report(token)
                    self.launch(job,copy.deepcopy(plan))
                elif kind=='DONE':
                    app.controller.finish_bridge(token,payload)
                    self.remove_job(job)
                    self.report(token)
                elif kind=='ERROR':self.abort(job,payload)
            except Exception as exc:self.abort(job,error_info(exc))

    def cancel(self):
        changed = False
        for job in list(self.app.jobs.values()):
            if job['kind']!='BRIDGE':continue
            job['cancel'].set()
            try:
                changed = self.app.controller.cancel_bridge(job['token']) or changed
            except Exception as exc:
                self.abort(job,error_info(exc))
                continue
            self.remove_job(job)
            self.report(job['token'])
        return changed

    def toggle_preview(self):
        if self.preview is not None:
            self.exit_preview()
            return
        self.state = self.app.controller.bridge_state()
        if self.state['preview'] is None or self.state['status']=='STALE':return
        self.app.cancel_interaction()
        self.app.completion.restore_view()
        self.app.connection.restore_view()
        self.app.connection.visible = False
        canvas = self.app.page.timeline
        self.bookmark = dict(selected=canvas.selected_id,scroll=canvas.canvas.xview()[0],mode=canvas.mode)
        self.preview = copy.deepcopy(self.state['preview'])
        canvas.selected_id = None
        canvas.selected_bridge_id = None
        self.app.refresh()
        self.app.show_detail(self.description())

    def restore_view(self):
        self.preview = None
        if self.bookmark:
            canvas = self.app.page.timeline
            canvas.selected_id = self.bookmark['selected']
            canvas.mode = self.bookmark['mode']
            canvas.canvas.xview_moveto(self.bookmark['scroll'])
            canvas.selected_bridge_id = None
            self.bookmark = None

    def exit_preview(self):
        self.restore_view()
        self.app.refresh()

    def describe_overlay(self, overlay, bridge_ref=None):
        facts = self.state if bridge_ref is None else bridge_ref
        plan = facts['plan']
        region = overlay['range']
        parts = [f'Bridge {overlay["id"]} · {region["start_tick"]}–{region["end_tick"]} tick',
                 '内容已就绪、范围已保护' if overlay['status']=='CONTENT_READY' else '范围已保护，尚未生成就绪音乐',
                 '保护约束后续算法，不禁止用户编辑；本预览只读。',
                 '保护记录：'+overlay['protection_id']]
        if plan:
            parts.append(f'计划 {plan["id"]} · v{plan["version"]}')
            if overlay['id'] in plan['inherited_bridge_ids']:parts.append('继承既有Bridge保护，原保护计划绑定保留。')
            window = next((w for w in plan['windows'] if w['id']==overlay['id']),None)
            if window:
                parts.append('情绪：'+'；'.join(f'{s["start_tick"]}–{s["end_tick"]} tick '+EMOTION_NAMES[s['emotion']]
                                            for s in window['emotion_segments']))
            parts.extend(w['message'] for w in plan['reasons'])
        if overlay['result_status']:parts.append('结果：'+overlay['result_status'])
        if overlay['error']:parts.append(overlay['error']['code']+' · '+overlay['error']['message'])
        material = overlay['material']
        if material:
            parts.append(material['label'])
            parts.append('来源：'+str(material['provenance']))
            generation = material['generation'] or {}
            parts.extend(w['message'] for w in generation.get('warnings',[]))
            if (generation.get('accompaniment_hints') or {}).get('status')=='suggested-not-rendered':
                parts.append('编配仅为建议，尚未渲染。')
        result = next((r for r in facts['results'] if r['bridge_id']==overlay['id']),None)
        if result and result['emotion_processing']:
            for segment in result['emotion_processing']['segments']:
                generation = segment['variant']['generation'] or {}
                parts.append(EMOTION_NAMES[segment['emotion']]+' · '+('旋律已轻改' if generation.get('melody_changed',False) else '旋律未改变'))
                parts.extend(w['message'] for w in generation.get('warnings',[]))
                if (generation.get('accompaniment_hints') or {}).get('status')=='suggested-not-rendered':
                    parts.append('编配仅为建议，尚未渲染。')
        return '\n'.join(dict.fromkeys(parts))

    def description(self):
        parts = [self.status_text(),'Bridge阶段只暂存；尚未处理连接块和最终边界，不可完整试听、应用或导出成品。']
        request, plan = self.state['request'], self.state['plan']
        if request:
            parts.append('基础输入：'+('当前完整排布' if request['input_kind']=='current_complete'
                         else request['completion_ref']['attempt_id']+' / '+request['completion_ref']['candidate_id']))
            parts.append('基础已完成范围：'+'；'.join(f'{r["start_tick"]}–{r["end_tick"]} tick' for r in request['resolved_ranges']))
        parts.append('剩余空缺：'+('；'.join(f'{r["start_tick"]}–{r["end_tick"]} tick' for r in self.state['remaining_gaps']) or '无'))
        if self.state['message']:parts.append(self.state['message'])
        if self.state['error']:parts.append(self.state['error']['code']+' · '+self.state['error']['message'])
        if plan:
            parts.append(f'计划 {plan["id"]} · v{plan["version"]} · '+('不使用新Bridge' if plan['decision']=='none' else '已选择Bridge'))
            parts.extend(w['message'] for w in plan['reasons'])
            parts.append('搜索终止：'+plan['search']['termination'])
        preview = self.state['preview']
        if preview:
            parts.extend(self.describe_overlay(o) for o in preview['overlays'])
        return '\n'.join(parts)
