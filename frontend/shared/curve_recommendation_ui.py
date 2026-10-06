"""P7 presentation and acknowledged worker queue; all authority stays in Facade."""
import copy
import importlib
import itertools
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from curve_completion_ui import error_info
from curve_theme import hint

MODES = {'melody_only': '中性单旋律', 'arranged': '情绪编配'}
METHODS = dict(natural_continuation='自然延续',motif_reply='动机回应',gradual_build='渐进铺垫',
    blank_entry='留白进入',resolve_close='回落收束',none='明确保留音乐')
PHASES = dict(BASE_COMPLETION='补全计算中', BRIDGE_DECISION='Bridge位置计算中',
    BRIDGE_LOCKED='Bridge位置已确定、范围已保护', BRIDGE_GENERATION='Bridge生成中',
    CONNECTIONS='连接块处理中', BOUNDARIES='最终块间处理', VALIDATION='独立校验中',
    ARRANGEMENT='编配及复核中', RENDERING='真实音频准备中', AUDITION_READY='可试听/可确认',
    CANCEL_REQUESTED='取消请求已登记 · 正在收拢保护事实')


def prepare_recommendations(request, **kwargs):
    return importlib.import_module('curve_recommendations').prepare_recommendations(request, **kwargs)


def prepare_candidate_mode(request, candidate_id, mode, source_facts, **kwargs):
    return importlib.import_module('curve_recommendations').prepare_candidate_mode(
        request, candidate_id, mode, source_facts, **kwargs)


def playback_asset(asset):
    """Presentation conversion only, after the service authenticated the asset."""
    if 'files' not in asset:
        return copy.deepcopy(asset)
    value = copy.deepcopy(asset)
    value['wav_path'] = asset['files']['wav']['path']
    return value


def reasons_text(reasons):
    return '\n'.join(r['message'] if isinstance(r,dict) else str(r) for r in reasons)


class RecommendationUI:
    def __init__(self, app):
        self.app = app
        self.messages = queue.Queue()
        self.runtimes = {}  # Kept until terminal delivery, including late lock audit/ACK.
        self.visible = False
        self.preview = None
        self.bookmark = None
        self.selected_id = None
        self.state = dict(status='IDLE', phase=None, attempt_id=None, candidates=[], error=None,
            message='', search=None, insufficient_reason=None, accepted_ref=None, capabilities={})
        self.choice = tk.StringVar()
        self.mode = tk.StringVar(value=MODES['melody_only'])
        self.panel = ttk.Frame(app.page.middle, style='Curve.Panel.TFrame')
        row = ttk.Frame(self.panel, style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.calculate_button = ttk.Button(row, text='查看建议', width=0, style='Curve.TButton',
            command=lambda: app.safe(self.start))
        self.calculate_button.pack(side='left')
        self.auto_button = ttk.Button(row, text='自动补全', width=0, style='Curve.TButton',
            command=lambda: app.safe(lambda: self.start(automatic=True)))
        self.auto_button.pack(side='left', padx=3)
        self.cancel_button = ttk.Button(row, text='取消计算', width=0, style='Curve.TButton', command=self.cancel)
        self.cancel_button.pack(side='right')
        self.selector = ttk.Combobox(self.panel, textvariable=self.choice, state='readonly',
            style='Curve.TCombobox')
        self.selector.pack(fill='x', pady=3)
        self.selector.bind('<<ComboboxSelected>>', self.select)
        row = ttk.Frame(self.panel, style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.mode_selector = ttk.Combobox(row, textvariable=self.mode, values=list(MODES.values()),
            state='readonly', width=9, style='Curve.TCombobox')
        self.mode_selector.pack(side='left', fill='x', expand=True)
        self.mode_selector.bind('<<ComboboxSelected>>', self.mode_changed)
        self.retry_button = ttk.Button(row, text='准备/重试', width=0, style='Curve.TButton',
            command=lambda: app.safe(self.prepare_mode))
        self.retry_button.pack(side='right', padx=(3,0))
        row = ttk.Frame(self.panel, style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.comparison_button = ttk.Button(row, text='播放基础', width=0, style='Curve.TButton',
            command=lambda: app.safe(lambda: self.play('comparison')))
        self.comparison_button.pack(side='left')
        self.final_button = ttk.Button(row, text='播放处理后', width=0, style='Curve.TButton',
            command=lambda: app.safe(lambda: self.play('final')))
        self.final_button.pack(side='right')
        row = ttk.Frame(self.panel, style='Curve.Panel.TFrame')
        row.pack(fill='x')
        self.confirm_button = ttk.Button(row, text='确认同谱', width=0, style='Curve.TButton',
            command=lambda: app.safe(self.confirm))
        self.confirm_button.pack(side='left')
        self.back_button = ttk.Button(row, text='返回编辑', width=0, style='Curve.TButton', command=self.exit_preview)
        self.back_button.pack(side='right')
        self.label = ttk.Label(self.panel, style='Curve.Muted.TLabel', takefocus=True)
        self.label.pack(fill='x', pady=2)
        hint(self.label, self.description, app.show_detail)
        hint(self.selector, self.description, app.show_detail)
        self.label.bind('<Button-1>', lambda _: app.show_detail(self.description()))
        self.label.bind('<Return>', lambda _: app.show_detail(self.description()))
        hint(self.retry_button, '只重新编配/准备所选模式的双侧资产，不重新作曲。', app.show_detail)

    def available(self):
        return self.app.state_data['capabilities'].get('recommendation', False)

    def mode_key(self):
        return next(key for key, label in MODES.items() if label == self.mode.get())

    def candidate(self, ident=None):
        return next((c for c in self.state['candidates'] if c['id']==(ident or self.selected_id)), None)

    def mode_data(self, candidate=None):
        candidate = candidate or self.candidate()
        return candidate['modes'].get(self.mode_key(), {}) if candidate else {}

    def active_job(self):
        return next((j for j in self.app.jobs.values() if j['kind'] in ('RECOMMENDATION','RECOMMENDATION_MODE')), None)

    def status_text(self):
        text = dict(IDLE='尚未计算完整建议', RUNNING='完整建议计算中', READY='完整建议已准备',
            FAILED='完整建议失败', CANCELLED='完整建议已取消', INTERRUPTED='已中断 · 请明确重试',
            STALE='建议已失效 · 请重新计算', APPLIED='已接受同一份试听谱')[self.state['status']]
        if self.state['status']=='RUNNING':text = PHASES.get(self.state['phase'],text)
        job = self.active_job()
        if job:
            if job['kind']=='RECOMMENDATION_MODE':text = MODES[job['captured']['mode']]+'资产准备中'
            text += f' · {int(time.monotonic()-job["started"])}秒'
        if self.state['error']:text += ' · '+self.state['error']['message']
        if self.state['insufficient_reason']:text += ' · '+str(self.state['insufficient_reason'])
        if self.state['status']=='RUNNING' and self.state['message']:text += ' · '+self.state['message']
        return text

    def update_elapsed(self):
        limit = max(12,(self.app.page.middle.winfo_width()-20)//13)
        text = self.status_text()
        self.label.configure(text=text[:limit]+('…' if len(text)>limit else ''))

    def refresh(self):
        app = self.app
        if not self.available():
            self.panel.pack_forget()
            self.restore_view()
            self.visible = False
            return
        self.state = app.controller.recommendation_state()
        candidates = self.state['candidates']
        values = [f'{i+1} · {c["title"]} · {c["scope"]}' for i,c in enumerate(candidates)]
        self.selector.configure(values=values)
        candidate = self.candidate()
        self.choice.set(values[next(i for i,c in enumerate(candidates) if c['id']==candidate['id'])] if candidate else '')
        if self.preview is not None:
            if not candidate or self.state['status']=='STALE':self.restore_view()
            else:self.preview = copy.deepcopy(candidate['preview'])
        caps = self.state['capabilities']
        mode = self.mode_data(candidate)
        mc = mode.get('capabilities', {})
        active = self.active_job()
        for button, enabled in ((self.calculate_button, not app.jobs and caps.get('can_calculate',False)),
            (self.auto_button, not app.jobs and caps.get('can_auto_complete',False)),
            (self.cancel_button, bool(active)), (self.retry_button, bool(candidate) and not app.jobs),
            (self.comparison_button, mc.get('can_play_comparison',False)),
            (self.final_button, mc.get('can_play_final',False)),
            (self.confirm_button, not app.jobs and mc.get('can_apply',False))):
            button.state(['!disabled'] if enabled else ['disabled'])
        self.retry_button.state(['disabled'] if mode.get('status')=='RENDERING' else [])
        self.selector.configure(state='readonly' if not app.jobs else 'disabled')
        self.mode_selector.configure(state='readonly' if not app.jobs else 'disabled')
        if self.visible:
            for stage in (app.completion, app.bridge, app.connection):stage.panel.pack_forget()
            self.panel.pack(fill='x', before=app.page.cards, pady=(4,0))
        else:self.panel.pack_forget()
        self.update_elapsed()

    def show(self):
        if not self.available():return False
        self.app.cancel_interaction()
        for stage in (self.app.completion, self.app.bridge, self.app.connection):
            stage.restore_view()
            if hasattr(stage,'visible'):stage.visible = False
        self.visible = True
        self.app.refresh()
        self.app.show_detail(self.description())

    def select(self, event=None):
        index = self.selector.current()
        if index<0 or index>=len(self.state['candidates']):return
        candidate = self.state['candidates'][index]
        self.selected_id = candidate['id']
        if candidate['capabilities']['can_preview']:
            if self.bookmark is None:
                canvas = self.app.page.timeline
                self.bookmark = dict(selected=canvas.selected_id, scroll=canvas.canvas.xview()[0], mode=canvas.mode)
            self.app.cancel_interaction()
            for stage in (self.app.completion,self.app.bridge,self.app.connection):stage.restore_view()
            self.preview = copy.deepcopy(candidate['preview'])
            canvas = self.app.page.timeline
            canvas.selected_id = canvas.selected_bridge_id = canvas.selected_connection_id = None
        else:self.restore_view()
        self.app.refresh()
        self.app.show_detail(self.description())

    def mode_changed(self, event=None):
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

    def start(self, automatic=False):
        app = self.app
        if not self.available() or app.jobs:return False
        cap = 'can_auto_complete' if automatic else 'can_calculate'
        if not self.state['capabilities'].get(cap,False):return False
        self.show()
        captured = app.controller.capture_recommendations(selected_gap_id=app.completion.selected_gap_id,
                                                         mode=self.mode_key())
        return self.register(captured, 'RECOMMENDATION', automatic=automatic)

    def prepare_mode(self):
        if not self.candidate() or self.app.jobs:return False
        captured = self.app.controller.capture_recommendation_mode(self.selected_id,self.mode_key())
        return self.register(captured, 'RECOMMENDATION_MODE')

    def register(self, captured, kind, automatic=False):
        token = copy.deepcopy(captured['token'])
        job = dict(kind=kind, token=token, request=copy.deepcopy(captured['request']),
            cancel=threading.Event(), started=time.monotonic(), last_seq=-1, stage_bundle=None,
            automatic=automatic, captured=copy.deepcopy(captured), shutdown=threading.Event())
        self.app.jobs[token['request_id']] = job
        self.runtimes[token['request_id']] = job
        try:
            self.app.refresh()
            self.launch(job)
        except Exception as exc:
            self.abort(job,error_info(exc))
            self.retire(job)
            return False
        return True

    def launch(self, job):
        # Only immutable input, Events and this queue enter the worker.
        captured, token = copy.deepcopy(job['captured']), copy.deepcopy(job['token'])
        cancel, shutdown, messages, kind = job['cancel'], job['shutdown'], self.messages, job['kind']
        counter = itertools.count(1)
        def send(kind_, payload, ack=None):
            seq = next(counter)
            payload = copy.deepcopy(payload)
            if kind_=='progress':payload['seq'] = seq
            envelope = dict(token=token,seq=seq,kind=kind_,payload=payload)
            messages.put((envelope,ack))
        def worker():
            known_bundle = None
            def progress(event):
                nonlocal known_bundle
                known_bundle = copy.deepcopy(event['stage_bundle'])
                ack = dict(event=threading.Event(), response=None)
                send('progress',event,ack)
                while not ack['event'].wait(.05):
                    if shutdown.is_set():return dict(accepted=False,continue_processing=False)
                return ack['response']
            try:
                if kind=='RECOMMENDATION':
                    outcome = prepare_recommendations(captured['request'], should_cancel=cancel.is_set,
                        on_progress=progress)
                else:
                    outcome = prepare_candidate_mode(captured['request'], captured['candidate_id'], captured['mode'],
                        captured['source_facts'], should_cancel=cancel.is_set)
                send('result',outcome)
            except Exception as exc:
                send('error',dict(error=error_info(exc),stage_bundle=known_bundle))
        threading.Thread(target=worker,daemon=True).start()

    def remove_job(self, job):
        ident = job['token']['request_id']
        if self.app.jobs.get(ident) is job:self.app.jobs.pop(ident)

    def retire(self, job):
        # Retain only the token/sequence tombstone needed for late authenticated audit.
        job['captured'] = job['request'] = job['stage_bundle'] = None

    def report(self, job):
        self.app.refresh()
        if job['kind']=='RECOMMENDATION_MODE' or self.state['attempt_id']==job['token']['request_id']:
            error = self.state['error']
            if job['kind']=='RECOMMENDATION_MODE':
                captured = job['captured']
                candidate = self.candidate(captured['candidate_id'])
                error = candidate['modes'].get(captured['mode'],{}).get('error') if candidate else None
            message = error['message'] if error else self.status_text()
            if error and job['kind']=='RECOMMENDATION_MODE':message = MODES[job['captured']['mode']]+' · '+message
            self.app.tell(message,bool(error))
            self.app.show_detail(message+'\n'+self.description())

    def abort(self, job, error, stage_bundle=None):
        was_live = self.app.jobs.get(job['token']['request_id']) is job
        job['cancel'].set()
        try:
            if job['kind']=='RECOMMENDATION_MODE':self.app.controller.fail_recommendation_mode(job['token'],error)
            else:self.app.controller.fail_recommendations(job['token'],error,
                stage_bundle=stage_bundle if stage_bundle is not None else job['stage_bundle'])
        finally:
            self.remove_job(job)
            if was_live:self.report(job)

    def drain(self):
        while True:
            try:envelope,ack = self.messages.get_nowait()
            except queue.Empty:return
            token,seq,kind,payload = (envelope[k] for k in ('token','seq','kind','payload'))
            job = self.runtimes.get(token['request_id'])
            response = dict(accepted=False,continue_processing=False)
            was_live = job is not None and self.app.jobs.get(token['request_id']) is job
            try:
                if (not job or job['token']!=token or isinstance(seq,bool) or not isinstance(seq,int)
                        or seq<=job['last_seq']):continue
                job['last_seq'] = seq
                if kind=='progress':
                    # Intentionally not Controller.accepts: old lock facts have a pure audit path.
                    response = self.app.controller.record_recommendation_progress(token,payload)
                    if response['accepted'] and was_live:job['stage_bundle'] = copy.deepcopy(payload['stage_bundle'])
                    if was_live and self.state['attempt_id']==token['request_id']:self.report(job)
                elif kind=='result':
                    if job['kind']=='RECOMMENDATION_MODE':
                        self.app.controller.finish_recommendation_mode(token,payload)
                    else:self.app.controller.finish_recommendations(token,payload)
                    self.remove_job(job)
                    if was_live:self.report(job)
                    if (was_live and job['automatic'] and not job['cancel'].is_set() and self.state['attempt_id']==token['request_id']
                            and self.state['status']=='READY'):
                        candidates = sorted(self.state['candidates'],key=lambda c:c['rank'])
                        candidate = next((c for c in candidates if c['modes'].get(job['request']['mode'],{})
                            .get('capabilities',{}).get('can_apply',False)),None)
                        if candidate:
                            try:self.apply(candidate['id'],job['request']['mode'])
                            except Exception as exc:
                                self.app.refresh()
                                self.app.tell('自动确认失败，候选已保留：'+str(exc),True)
                                self.app.show_detail(str(exc)+'\n'+self.description())
                    self.retire(job)
                elif kind=='error':
                    self.abort(job,payload['error'],payload['stage_bundle'])
                    self.retire(job)
            except Exception as exc:
                response = dict(accepted=False,continue_processing=False)
                if job:self.abort(job,error_info(exc),payload.get('stage_bundle') if kind in ('progress','result') else None)
            finally:
                if ack:
                    ack['response'] = response
                    ack['event'].set()

    def cancel(self):
        changed = False
        for job in list(self.app.jobs.values()):
            if job['kind'] not in ('RECOMMENDATION','RECOMMENDATION_MODE'):continue
            job['cancel'].set()
            try:
                if job['kind']=='RECOMMENDATION_MODE':
                    changed = self.app.controller.cancel_recommendation_mode(job['token']) or changed
                    self.remove_job(job)
                else:changed = self.app.controller.cancel_recommendations(job['token']) or changed
                self.report(job)
            except Exception as exc:self.abort(job,error_info(exc))
        return changed

    def shutdown(self):
        for job in self.runtimes.values():
            job['cancel'].set()
            job['shutdown'].set()

    def play(self, kind):
        candidate = self.candidate()
        if not candidate:return False
        mode = self.mode_key()
        if not self.mode_data(candidate).get('capabilities',{}).get('can_play_'+kind,False):return False
        asset = self.app.controller.recommendation_asset(candidate['id'],kind=kind,mode=mode)
        label = candidate['title']+' · '+MODES[mode]+' · '+('基础对比' if kind=='comparison' else '处理后')
        return self.app.start_playback(playback_asset(asset),('recommendation',candidate['id'],mode,kind),label)

    def apply(self, candidate_id, mode):
        ref = self.app.controller.confirmation_ref(candidate_id,mode=mode)
        result = self.app.controller.apply_recommendation(candidate_id,mode=mode,confirmation_ref=ref)
        self.restore_view()
        self.app.refresh()
        self.app.tell('同谱已接受 · 一次撤销可恢复' if result['changed'] else '此版本已经接受')
        self.app.show_detail(str(result['receipt']))
        return result

    def confirm(self):
        if not self.candidate() or self.app.jobs or not self.mode_data().get('capabilities',{}).get('can_apply',False):return False
        return self.apply(self.selected_id,self.mode_key())

    def describe_overlay(self, overlay, kind):
        if kind=='boundary':
            return '\n'.join([f'最终边界 {overlay["id"]} · {overlay["tick"]} tick · {METHODS[overlay["method"]]}',
                '实际操作：'+str(overlay['operation_ids']), '演奏提示：'+str(overlay['performance_hint_ids']),
                '影响范围：'+str(overlay['editable_ranges']),reasons_text(overlay['reasons'])])
        region = overlay['range']
        parts = [f'{kind} {overlay["id"]} · {region["start_tick"]}–{region["end_tick"]} tick',
            dict(CONTENT_READY='实际音乐已就绪',RANGE_LOCKED='范围已保护，尚无就绪音乐',ALLOCATED='连接范围已分配，尚无就绪音乐')[overlay['status']],
            '本候选的实际阶段事实 · 只读']
        if kind=='Bridge':
            protection = next(p for p in self.preview['protections'] if p['id']==overlay['protection_id'])
            parts += [f'原保护计划 {protection["plan_id"]} v{protection["plan_version"]}',
                '保护表示后续算法不得覆盖；不从当前编辑的另一套桥计划借用原因。']
            material = overlay['material']
            if material:
                parts.append(material['label'])
                generation = material.get('generation') or {}
                parts.extend(w['message'] for w in generation.get('warnings',[]))
        else:parts.append(reasons_text(overlay['reasons']))
        if overlay['error']:parts.append(overlay['error']['message'])
        if overlay['result_status'] in ('FAILED','CANCELLED'):parts.append('生成失败' if overlay['result_status']=='FAILED' else '生成已取消')
        return '\n'.join(parts)

    def description(self):
        parts = [self.status_text(),'选卡只选择；基础和处理后均需明确播放。模式只编配/渲染，不重新作曲。']
        if self.state['message']:parts.append(self.state['message'])
        if self.state['search']:parts.append('有限搜索：'+str(self.state['search']))
        candidate = self.candidate()
        if candidate:
            parts += [candidate['title']+' · '+candidate['scope'], '版本：'+str(candidate['version']),
                '剩余空缺：'+str(candidate['remaining_gaps'] or '无'), '推荐原因：'+reasons_text(candidate['reasons'])]
            if candidate['scope']=='LOCAL':parts.append('局部未完成：不可正式整曲导出。')
            mode = self.mode_data(candidate)
            parts.append(MODES[self.mode_key()]+' · '+str(mode.get('status','MISSING')))
            if mode.get('error'):parts.append(mode['error']['message'])
            parts.append(str(mode.get('capabilities',{}).get('blocking_reasons',[])))
            for kind,asset in mode.get('assets',{}).items():
                if asset:parts.append(f'{kind} · 正文 {asset["body_seconds"]:.1f}秒 / 实际音频 {asset["audio_seconds"]:.1f}秒')
        return '\n'.join(parts)
