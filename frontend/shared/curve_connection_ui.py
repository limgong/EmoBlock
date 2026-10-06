"""P6 private connection stages; publication and music remain Facade-owned."""
import copy
import importlib
import itertools
import queue
import threading
import time
from tkinter import ttk

from curve_completion_ui import error_info
from curve_theme import hint

TECHNIQUES = dict(diatonic_guide='调内导向', motif_reply='动机回应', density_shift='疏密发展',
                  retain_develop='保留并发展', breath_close='呼吸收束')


def plan_connection_blocks(request, should_cancel=None, on_progress=None):
    return importlib.import_module('curve_connections').plan_connection_blocks(
        request, should_cancel=should_cancel, on_progress=on_progress)


def generate_connection_blocks(request, plan, actual_layout, should_cancel=None, on_progress=None, on_result=None):
    return importlib.import_module('curve_connections').generate_connection_blocks(
        request, plan, actual_layout, should_cancel=should_cancel, on_progress=on_progress, on_result=on_result)


class ConnectionUI:
    def __init__(self, app):
        self.app = app
        self.messages = queue.Queue()
        self.visible = False
        self.preview = None
        self.bookmark = None
        self.state = dict(status='IDLE', phase=None, attempt_id=None, request=None, plan=None,
            protections=[], results=[], outcome=None, preview=None, remaining_gaps=[],
            capabilities={}, error=None, message='连接尚未计算。')
        self.panel = ttk.Frame(app.page.right,style='Curve.Panel.TFrame')
        row = ttk.Frame(self.panel,style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.back_button = ttk.Button(row,text='←Bridge',width=0,style='Curve.TButton',command=self.show_bridge)
        self.back_button.pack(side='left')
        self.start_button = ttk.Button(row,text='判断连接',width=0,style='Curve.TButton',command=lambda:app.safe(self.start))
        self.start_button.pack(side='left',padx=4)
        self.cancel_button = ttk.Button(row,text='取消连接',width=0,style='Curve.TButton',command=self.cancel)
        self.preview_button = ttk.Button(row,text='只读预览',width=0,style='Curve.TButton',command=self.toggle_preview)
        self.preview_button.pack(side='right')
        self.label = ttk.Label(self.panel,style='Curve.Muted.TLabel',takefocus=True)
        self.label.pack(fill='x',pady=(2,0))
        hint(self.label,self.description,app.show_detail)
        hint(self.start_button,'只捕获当前真实就绪的桥；连接范围先由后端分配，再生成和独立认证。',app.show_detail)
        hint(self.preview_button,'唯一画布的私有只读覆盖层；分配不表示桥保护或音乐就绪。',app.show_detail)
        self.label.bind('<Button-1>',lambda _:app.show_detail(self.description()))
        self.label.bind('<Return>',lambda _:app.show_detail(self.description()))

    def show(self):
        recommendation = getattr(self.app,'recommendation',None)
        if recommendation:
            recommendation.restore_view()
            recommendation.visible = False
        self.app.cancel_interaction()
        self.app.completion.restore_view()
        self.app.bridge.restore_view()
        self.app.bridge.visible = False
        self.visible = True
        self.app.refresh()
        self.app.show_detail(self.description())

    def show_bridge(self):
        self.restore_view()
        self.visible = False
        self.app.bridge.show()

    def active_job(self):
        return next((j for j in self.app.jobs.values() if j['kind']=='CONNECTION'
                     and j['token']['request_id']==self.state['attempt_id']),None)

    def status_text(self):
        status,phase = self.state['status'],self.state['phase']
        if status=='RUNNING':
            text = dict(CONNECTION_PLANNING='连接规划中',CONNECTION_PLANNED='连接范围已分配',
                        CONNECTION_GENERATION='连接块生成中',CONNECTIONS_READY='连接已就绪')[phase]
            job = self.active_job()
            if job:text += f' · 已用 {int(time.monotonic()-job["started"])} 秒'
            return text
        text = dict(IDLE='连接尚未计算',READY='连接已就绪 · 最终边界未处理',FAILED='连接失败',
                    CANCELLED='连接已取消',INTERRUPTED='连接已中断，请明确重试',STALE='连接结果已失效')[status]
        plan = self.state['plan']
        if plan and plan['decision']=='none':
            if status=='READY':text = '连接判断完成 · 最终边界未处理'
            text += ' · '+dict(NOT_NEEDED='明确保留音乐',NO_LEGAL_WINDOW='没有合法连接范围')[plan['none_reason']]
        if self.state['error']:text += ' · '+self.state['error']['message']
        return text

    def refresh(self):
        app = self.app
        if not app.state_data['capabilities'].get('connection',False):
            self.panel.pack_forget()
            self.restore_view()
            self.visible = False
            return
        self.state = app.controller.connection_state()
        if self.preview is not None:
            if self.state['preview'] is None or self.state['status']=='STALE':self.restore_view()
            else:self.preview = copy.deepcopy(self.state['preview'])
        parent = app.bridge.state
        ready_parent = parent['status']=='READY' and parent['capabilities'].get('can_plan_connections',False)
        active = self.active_job() is not None
        self.start_button.state(['!disabled'] if not app.jobs and ready_parent else ['disabled'])
        self.preview_button.state(['!disabled'] if self.state['preview'] is not None and self.state['status']!='STALE' else ['disabled'])
        self.preview_button.configure(text='返回编辑' if self.preview is not None else '只读预览')
        if active:
            self.start_button.pack_forget()
            self.cancel_button.pack(side='left',padx=4)
        else:
            self.cancel_button.pack_forget()
            self.start_button.pack(side='left',padx=4)
        if self.visible:
            app.completion.panel.pack_forget()
            app.bridge.panel.pack_forget()
            self.panel.pack(fill='x',before=app.page.memory_label,pady=(4,0))
        else:self.panel.pack_forget()
        self.update_elapsed()

    def update_elapsed(self):
        text = self.status_text()
        limit = max(16,(self.app.page.right.winfo_width()-20)//16)
        self.label.configure(text=text[:limit]+('…' if len(text)>limit else ''))

    def start(self, bridge_attempt_id=None):
        app = self.app
        if app.jobs or app.state_data['access_mode']!='editable' or not app.state_data['capabilities'].get('connection',False):return False
        parent = app.bridge.state
        if bridge_attempt_id is None:
            if parent['status']!='READY' or not parent['capabilities'].get('can_plan_connections',False):return False
            bridge_attempt_id = parent['attempt_id']
        self.start_button.state(['disabled'])
        self.label.configure(text='正在验证Bridge就绪输入…')
        app.tell('正在验证Bridge快照和保护；通过后开始连接规划。')
        app.root.update_idletasks()
        try:
            captured = app.controller.capture_connection(bridge_attempt_id=bridge_attempt_id)
        except Exception as exc:
            app.refresh()
            app.tell(str(exc),True)
            return False  # Atomic rejection: no token has been registered.
        token,request = copy.deepcopy(captured['token']),copy.deepcopy(captured['request'])
        job = dict(kind='CONNECTION',token=token,request=request,cancel=threading.Event(),
                   stage_id='PLANNING',event_seq=-1,started=time.monotonic())
        app.jobs[token['request_id']] = job
        try:
            app.cancel_interaction()
            self.restore_view()
            app.bridge.restore_view()
            app.completion.restore_view()
            app.bridge.visible = False
            self.visible = True
            app.refresh()
            app.tell(self.status_text())
            self.launch(job)
        except Exception as exc:
            self.abort(job,error_info(exc))
            return False
        return True

    def launch(self, job, plan=None):
        token,request = copy.deepcopy(job['token']),copy.deepcopy(job['request'])
        stage,event,messages = job['stage_id'],job['cancel'],self.messages
        counter = itertools.count()
        def send(kind,payload):
            messages.put((token,stage,next(counter),kind,copy.deepcopy(payload)))
        def worker():
            try:
                if plan is None:
                    value = plan_connection_blocks(request,should_cancel=event.is_set,on_progress=lambda p:send('PROGRESS',p))
                else:
                    value = generate_connection_blocks(request,copy.deepcopy(plan),copy.deepcopy(request['actual_layout']),
                        should_cancel=event.is_set,on_progress=lambda p:send('PROGRESS',p),on_result=lambda r:send('RESULT',r))
                send('DONE',value)
            except Exception as exc:send('ERROR',error_info(exc))
        threading.Thread(target=worker,daemon=True).start()

    def remove_job(self, job):
        ident = job['token']['request_id']
        if self.app.jobs.get(ident) is job:self.app.jobs.pop(ident)

    def report(self, token):
        self.app.refresh()
        if self.state['attempt_id']==token['request_id']:
            self.app.tell(self.status_text(),self.state['status']=='FAILED')
            self.app.show_detail(self.description())

    def abort(self, job, error):
        job['cancel'].set()
        try:self.app.controller.fail_connection(job['token'],error)
        finally:
            self.remove_job(job)
            self.report(job['token'])

    def drain(self):
        app = self.app
        while True:
            try:token,stage,seq,kind,payload = self.messages.get_nowait()
            except queue.Empty:return
            job = app.jobs.get(token['request_id'])
            if (not job or job['kind']!='CONNECTION' or job['token']!=token or stage!=job['stage_id']
                    or isinstance(seq,bool) or not isinstance(seq,int) or seq<=job['event_seq']):continue
            try:
                if not app.controller.accepts(token):
                    job['cancel'].set()
                    self.remove_job(job)
                    self.report(token)
                    continue
                job['event_seq'] = seq
                if kind=='PROGRESS':
                    self.state = app.controller.connection_state()
                    self.update_elapsed()
                    app.tell(self.status_text()+' · '+payload)
                elif kind=='RESULT':
                    app.controller.record_connection_result(token,payload)
                    self.report(token)
                    if self.state['status']!='RUNNING':
                        job['cancel'].set()
                        self.remove_job(job)
                        app.refresh()
                elif kind=='DONE' and stage=='PLANNING':
                    plan = app.controller.plan_connection(token,payload)
                    self.report(token)
                    if not app.controller.begin_connection_generation(token,plan):
                        self.abort(job,dict(code='CONNECTION_START_REJECTED',message='连接生成请求未被接受。',details={}))
                        continue
                    job['stage_id'] = f'GENERATION:{plan["id"]}:{plan["version"]}:{plan["plan_fingerprint"]}'
                    job['event_seq'] = -1
                    self.report(token)
                    self.launch(job,copy.deepcopy(plan))
                elif kind=='DONE':
                    app.controller.finish_connection(token,payload)
                    self.remove_job(job)
                    self.report(token)
                elif kind=='ERROR':self.abort(job,payload)
            except Exception as exc:self.abort(job,error_info(exc))

    def cancel(self):
        changed = False
        for job in list(self.app.jobs.values()):
            if job['kind']!='CONNECTION':continue
            job['cancel'].set()
            try:changed = self.app.controller.cancel_connection(job['token']) or changed
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
        self.state = self.app.controller.connection_state()
        if self.state['preview'] is None or self.state['status']=='STALE':return
        self.app.cancel_interaction()
        self.app.completion.restore_view()
        self.app.bridge.restore_view()
        canvas = self.app.page.timeline
        self.bookmark = dict(selected=canvas.selected_id,scroll=canvas.canvas.xview()[0],mode=canvas.mode)
        self.preview = copy.deepcopy(self.state['preview'])
        canvas.selected_id = canvas.selected_bridge_id = canvas.selected_connection_id = None
        self.app.refresh()
        self.app.show_detail(self.description())

    def restore_view(self):
        self.preview = None
        if self.bookmark:
            canvas = self.app.page.timeline
            canvas.selected_id = self.bookmark['selected']
            canvas.mode = self.bookmark['mode']
            canvas.canvas.xview_moveto(self.bookmark['scroll'])
            canvas.selected_bridge_id = canvas.selected_connection_id = None
            self.bookmark = None

    def exit_preview(self):
        self.restore_view()
        self.app.refresh()

    def describe_overlay(self, overlay):
        region = overlay['range']
        parts = [f'连接 {overlay["id"]} · {region["start_tick"]}–{region["end_tick"]} tick',
            '实际连接音乐已认证' if overlay['status']=='CONTENT_READY' else '连接范围已分配，尚无就绪音乐',
            '连接分配不是Bridge保护锁；本预览只读。']
        window = next(w for w in self.state['plan']['windows'] if w['id']==overlay['id'])
        parts.append('方法：'+TECHNIQUES[window['technique']])
        parts.extend(w['message'] for w in overlay['reasons'])
        if overlay['result_status']:parts.append('结果：'+overlay['result_status'])
        if overlay['error']:parts.append(overlay['error']['code']+' · '+overlay['error']['message'])
        if overlay['status']=='CONTENT_READY':
            parts.append('实际音符：'+str(len(overlay['notes'])))
            result = next(r for r in self.state['results'] if r['connection_id']==overlay['id'])
            for cell in result['operations']:
                parts.append('来源：'+str(cell['parent_ref'])+' · 父发声 '+cell['input_note_id'])
        return '\n'.join(parts)

    def description(self):
        parts = [self.status_text(),'连接阶段只暂存；尚未最终块间处理，不可完整试听、应用或导出成品。']
        request,plan = self.state['request'],self.state['plan']
        if request:
            parent = request['bridge_ref']
            parts.append(f'输入桥尝试 {parent["attempt_id"]} · 计划 {parent["plan"]["id"]} v{parent["plan"]["version"]}')
            parts.append('实际桥布局：'+request['layout_fingerprint'])
        if self.state['message']:parts.append(self.state['message'])
        if self.state['error']:parts.append(self.state['error']['code']+' · '+self.state['error']['message'])
        parts.append('剩余空缺：'+('；'.join(f'{r["start_tick"]}–{r["end_tick"]} tick' for r in self.state['remaining_gaps']) or '无'))
        if plan:
            parts.append(f'连接计划 {plan["id"]} · v{plan["version"]}')
            parts.extend(w['message'] for w in plan['reasons'])
            parts.append('搜索终止：'+plan['search']['termination'])
        preview = self.state['preview']
        if preview:
            parts.extend(self.app.bridge.describe_overlay(o,request['bridge_ref']) for o in preview['overlays'])
            parts.extend(self.describe_overlay(o) for o in preview['connection_overlays'])
        return '\n'.join(parts)
