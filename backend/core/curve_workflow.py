"""Public r3 desktop facade: immutable jobs and atomic material/state operations."""
import copy
from pathlib import Path
import wave

import curve_project as model
import curve_session
import curve_store
import curve_memory
import curve_candidates
import curve_bridges
from curve_audition import render_audition
from export_safe import atomic_export

FORMATS = {'wav': 'preview.wav', 'mid': 'composition.mid', 'mmp': 'composition.mmp'}


def decide_bridge(request, should_cancel=None, on_progress=None):
    import story_engine
    return story_engine.decide_bridge_request(request, should_cancel=should_cancel, on_progress=on_progress)


def generate_bridges(request, plan, should_cancel=None, on_progress=None, on_result=None):
    import story_engine
    return story_engine.generate_bridge_request(request, plan, should_cancel=should_cancel,
                                               on_progress=on_progress, on_result=on_result)


def _warning(code, message, **details):
    return dict(code=code, message=message, details=details)


def prepare_import(path, track=0, seed=31):
    """Parse original note data; never remove leading rests or truncate overlaps."""
    import engine as music
    import curve_melody
    model.integer(track)
    native = music.load_source(path)
    if track >= len(native.tracks):
        model.reject('请选择可用旋律轨。', 'INVALID_TRACK')
    melody = native.tracks[track]
    raw = sorted(melody.notes, key=lambda n: (n.start, n.pitch))
    if not raw:
        model.reject('轨道中没有可用旋律。', 'EMPTY_MATERIAL')
    previous_end = -1
    for n in raw:
        if n.start < previous_end:
            model.reject('此轨道有同时发声或交叠音符，请明确提取一条旋律后重新导入。', 'MONOPHONIC_IMPORT_REQUIRED')
        previous_end = n.start + n.duration
    source_id = model.uid(); track_id = 'parsed-track:' + str(track) + ':' + melody.name
    notes = []
    for index, n in enumerate(raw):
        note_id = source_id + ':note:' + str(index)
        notes.append(dict(id=note_id, pitch=n.pitch, start_tick=n.start, duration_tick=n.duration, velocity=n.velocity,
            origin=dict(source_id=source_id, track_id=track_id, source_note_id=note_id), lineage=[], slice=None))
    tonic, mode, confidence = music.infer_key(raw)
    source = dict(id=source_id, label=Path(path).stem, length_ticks=max(n.start + n.duration for n in raw), notes=notes,
        provenance=dict(path=str(Path(path).resolve()), file_fingerprint=native.sha256, track_id=track_id, original_bpm=native.bpm,
            ppq_policy='native parser round to PPQ480; leading rests retained; overlaps rejected',
            import_parameters=dict(parsed_non_drum_track_index=track),
            key_context=dict(tonic=tonic, mode=mode, confidence=confidence, method='existing-note-key-inference')))
    prepared = curve_melody.prepare_source(source, seed=seed)
    warnings = prepared['warnings'] + [_warning('SOURCE_NOTE_ONLY', message) for message in native.warnings]
    return dict(sources=[source], materials=prepared['materials'], warnings=warnings)


def prepare_generation(project, material_id, method, seed=31, parameters=None):
    import curve_melody
    model.validate(project)
    base = next((m for m in project['materials'] if m['id'] == material_id), None)
    if base is None:
        model.reject('选中的旋律素材不存在。')
    derived = curve_melody.derive(copy.deepcopy(base), method, seed=seed, parameters=parameters)
    materials = [derived]
    if derived['kind'] == 'phrase':
        materials.extend(curve_melody.split_phrase(derived))
    signature = curve_melody.music_signature(derived)
    if any(curve_melody.music_signature(m) == signature for m in project['materials']):
        model.reject('没有得到不同的新旋律，请调整方法或选择另一个片段。', 'NO_VALID_VARIATION')
    return dict(sources=[], materials=materials, warnings=[])


def combine(project, inputs, label='组合素材'):
    model.validate(project)
    if not inputs:
        model.reject('请先选择组合片段。', 'EMPTY_MATERIAL')
    library = model.indexed(project['materials'])
    parts = []; notes = []; offset = 0
    for item in inputs:
        snapshot = library.get(item) if isinstance(item, str) else item
        if snapshot is None:
            model.reject('组合中的素材已不可用。')
        snapshot = copy.deepcopy(snapshot)
        model.material_check(snapshot, model.source_index(project['sources']))
        occurrence = model.uid()
        parts.append(dict(occurrence_id=occurrence, offset_tick=offset, snapshot=snapshot))
        notes.extend(dict(n, id=occurrence + ':' + n['id'], start_tick=n['start_tick'] + offset) for n in snapshot['notes'])
        offset += snapshot['length_ticks']
    material = dict(id=model.uid(), label=str(label), kind='combination', length_ticks=offset, notes=notes,
        provenance=dict(method='user-ordered-combination', inputs=[p['snapshot']['id'] for p in parts]),
        generation=None, phrase_id=None, children=parts)
    model.material_check(material, model.source_index(project['sources']))
    return material


class Controller:
    def __init__(self, project=None):
        self.session = curve_session.ProjectSession(project if project is not None else model.new_project(), recompute=curve_memory.recompute)
        self._bundle = curve_store.new_bundle(self.session.project)
        self._initial_fingerprint = model.fingerprint(self.session.project)
        self._loaded = None
        self._saved_path = None
        self._jobs = {}
        self._untouched_new = project is None
        self._staging_dirty = False
        self._completion_id = None
        self._completion_immediate = None
        self._bridge_id = None

    @property
    def readonly(self):
        return self._loaded is not None and self._loaded['access_mode'] == 'legacy_readonly'

    @property
    def project(self):
        return None if self.readonly else self.session.project

    def state(self):
        return dict(access_mode='legacy_readonly' if self.readonly else 'editable', project=self.project,
            capabilities=dict(edit=not self.readonly, derive=not self.readonly, audition=True,
                generate_final=False, intensity_edit=not self.readonly, emotion=not self.readonly, memory=not self.readonly,
                completion=not self.readonly, bridge=not self.readonly),
            is_saved=True if self.readonly else self.session.is_saved,
            saved_path=str(self._saved_path) if self._saved_path else None,
            can_undo=not self.readonly and self.session.can_undo, can_redo=not self.readonly and self.session.can_redo,
            memory_info=None if self.readonly else curve_memory.memory_info(self.session.project),
            staging_dirty=self._staging_dirty)

    def _stale_completions(self):
        for attempt in self._bundle['attempts']:
            if ('completion' in attempt or 'bridge' in attempt) and attempt['state'] in ('RUNNING', 'READY'):
                attempt['state'] = 'STALE'
                self._staging_dirty = True
        self._completion_immediate = None

    def _editable(self):
        if self.readonly:
            model.reject('这是旧工程的只读模式；可试听和导出现有成品，请新建工程开始创作。', 'READ_ONLY')

    def edit(self, action, **args):
        self._editable()
        changed = self.session.edit(action, **args)
        if changed:
            self._stale_completions()
            self._jobs.clear()
            self._untouched_new = False
        return changed

    def undo(self):
        self._editable()
        changed = self.session.undo()
        if changed:
            self._stale_completions()
            self._jobs.clear()
            self._untouched_new = False
        return changed

    def redo(self):
        self._editable()
        changed = self.session.redo()
        if changed:
            self._stale_completions()
            self._jobs.clear()
            self._untouched_new = False
        return changed

    def capture_job(self, kind, target=None):
        if kind not in ('IMPORT', 'DERIVE', 'AUDITION', 'COMBINE'):
            model.reject('不支持的后台任务。')
        self._editable()
        snap = dict(project=self.session.project)
        resolved = None
        if target is not None:
            if not isinstance(target, dict):
                model.reject('请提供明确的试听或生成对象。')
            if target.get('kind') == 'draft':
                resolved = copy.deepcopy(target.get('snapshot'))
                model.material_check(resolved, model.source_index(snap['project']['sources']))
            else:
                field = dict(source='sources', material='materials', placement='placements').get(target.get('kind'))
                if field is None:
                    model.reject('任务对象种类无效。')
                selected = next((v for v in snap['project'][field] if v['id'] == target.get('id')), None)
                if selected is None:
                    model.reject('任务对象已不存在。')
                resolved = selected['emotion_variant'] or selected['base_snapshot'] if field == 'placements' else selected
        snap = self.session.capture()
        payload = dict(project=snap['project'], target=copy.deepcopy(resolved))
        self._jobs[snap['token']['request_id']] = dict(kind=kind, snapshot=copy.deepcopy(payload))
        return dict(token=snap['token'], snapshot=payload)

    def accepts(self, token):
        if not self.session.accepts(token) or token.get('request_id') not in self._jobs:
            return False
        if self._jobs[token['request_id']]['kind'] == 'COMPLETION':
            attempt = self._attempt(token['request_id'])
            return attempt is not None and attempt['state'] == 'RUNNING'
        if self._jobs[token['request_id']]['kind'] == 'BRIDGE':
            attempt = self._bridge_attempt(token['request_id'])
            return attempt is not None and attempt['state'] == 'RUNNING'
        return True

    def cancel_job(self, token):
        context = self._jobs.get(token.get('request_id')) if isinstance(token, dict) else None
        if context is not None and context['kind'] == 'COMPLETION':
            return self.cancel_completion(token)
        if context is not None and context['kind'] == 'BRIDGE':
            return self.cancel_bridge(token)
        return self.finish_job(token)

    def finish_job(self, token):
        if not self.accepts(token):
            return False
        if self._jobs[token['request_id']]['kind'] in ('COMPLETION', 'BRIDGE'):
            return False  # Completion must pass its independent result gate first.
        result = self.session.finish(token)
        self._jobs.pop(token['request_id'], None)
        return result

    def apply_batch(self, batch, token):
        self._editable()
        if not self.accepts(token):
            return dict(changed=False, added_source_ids=[], added_material_ids=[])
        context = self._jobs[token['request_id']]
        if context['kind'] not in ('IMPORT', 'DERIVE', 'COMBINE'):
            model.reject('此任务不能写入素材库。')
        model.shape(batch, 'sources materials warnings')
        sources = model.indexed(batch['sources']); materials = model.indexed(batch['materials'])
        for warning in model.objects(batch['warnings']):
            model.shape(warning, 'code message details'); model.ident(warning['code']); model.text(warning['message'])
            if not isinstance(warning['details'], dict):
                model.reject('任务提示格式无效。')
        if context['kind'] != 'IMPORT' and sources:
            model.reject('生成或组合不能引入新的来源。')
        project = self.session.project
        before = copy.deepcopy(project)
        for name, additions in (('sources', sources), ('materials', materials)):
            existing = {item['id'] for item in project[name]}
            if existing & set(additions):
                model.reject('任务试图覆盖已有素材。')
            for item in additions.values():
                item = copy.deepcopy(item)
                counter = project['label_counters'].get(name, 0) + 1
                project['label_counters'][name] = counter
                item['label'] = item['label'] + ' · ' + ('S' if name == 'sources' else 'M') + str(counter)
                project[name].append(item)
        changed = bool(sources or materials)
        if changed:
            model.invalidate_records(project, before)
            project['contract_rev'] = model.CONTRACT_REV
        # complete source/phrase references validate before a single session write
        committed = self.session.commit(project, token)
        if committed:
            self._stale_completions()
            self._jobs.clear()
            self._untouched_new = False
        elif not changed:
            self._jobs.pop(token['request_id'], None)
        return dict(changed=committed, added_source_ids=list(sources) if committed else [], added_material_ids=list(materials) if committed else [])

    def _attempt(self, identity):
        return next((v for v in self._bundle['attempts'] if v['id'] == identity and 'completion' in v), None)

    def gap_items(self):
        return [] if self.readonly else curve_candidates.gap_items(self.project)

    def capture_completion(self, selected_gap_id=None, seed=31, budget=None):
        self._editable()
        if any(job['kind'] in ('COMPLETION', 'BRIDGE') for job in self._jobs.values()):
            model.reject('基础候选正在计算，请等待或取消。', 'DUPLICATE_REQUEST')
        request = curve_candidates.make_request(self.project, selected_gap_id, seed, budget)
        if not request['target_gaps']:
            result = curve_candidates.prepare_completion(request)
            self._completion_immediate = result
            return dict(token=None, request=request, attempt_id=None, immediate_outcome=copy.deepcopy(result))
        captured = self.session.capture(request['request_id']); token = captured['token']
        request['snapshot_id'] = token['snapshot_id']
        attempt = dict(id=request['request_id'], snapshot_id=request['snapshot_id'], input_fingerprint=request['input_fingerprint'],
            state='RUNNING', records=[], protections=[], staged_materials=[], error=None,
            completion=dict(schema='emoblocks.completion-attempt.v1', spec_rev=model.SPEC_REV, contract_rev=curve_candidates.REV,
                            request=copy.deepcopy(request), outcome=None))
        bundle = self._current_bundle()
        bundle['snapshots'].append(dict(id=request['snapshot_id'], spec_rev=model.SPEC_REV, contract_rev=request['input_contract_rev'],
                                    content_fingerprint=request['input_fingerprint'], project=copy.deepcopy(request['project'])))
        bundle['attempts'].append(attempt)
        try:
            curve_store.validate_bundle(bundle)
        except Exception:
            self.session.finish(token)
            raise
        self._bundle = bundle
        self._jobs[token['request_id']] = dict(kind='COMPLETION', request=copy.deepcopy(request))
        self._completion_id = attempt['id']; self._completion_immediate = None
        self._staging_dirty = True
        return dict(token=token, request=copy.deepcopy(request), attempt_id=attempt['id'], immediate_outcome=None)

    def _completion_finish(self, token, result):
        if not self.accepts(token) or self._jobs[token['request_id']]['kind'] != 'COMPLETION':
            return False
        request = self._jobs[token['request_id']]['request']
        curve_candidates.validate_outcome(request, result)
        bundle = self._current_bundle()
        attempt = next(v for v in bundle['attempts'] if v['id'] == token['request_id'])
        attempt['state'] = 'READY' if result['status'] in ('SUCCEEDED', 'INSUFFICIENT') else result['status']
        attempt['error'] = copy.deepcopy(result['error'])
        attempt['completion']['outcome'] = copy.deepcopy(result)
        curve_store.validate_bundle(bundle)
        if not self.session.finish(token):
            return False
        self._jobs.pop(token['request_id'], None)
        self._bundle = bundle; self._staging_dirty = True
        return True

    def finish_completion(self, token, outcome):
        if not self.accepts(token) or self._jobs[token['request_id']]['kind'] != 'COMPLETION':
            return False
        try:
            return self._completion_finish(token, outcome)
        except Exception as exc:
            return self.fail_completion(token, dict(code=getattr(exc, 'code', 'INVALID_CANDIDATE'), message=str(exc), details={})) and False

    def fail_completion(self, token, error):
        if not self.accepts(token) or self._jobs[token['request_id']]['kind'] != 'COMPLETION':
            return False
        if not isinstance(error, dict):
            error = dict(code=getattr(error, 'code', 'COMPLETION_FAILED'), message=str(error), details={})
        normalized = dict(code=str(error.get('code') or 'COMPLETION_FAILED'), message=str(error.get('message') or '基础候选计算失败，请重试或增加素材。'),
                          details=copy.deepcopy(error.get('details')) if isinstance(error.get('details'), dict) else {})
        try:
            model.canonical(normalized)
        except model.ProjectError:
            normalized['details'] = {}
        request = self._jobs[token['request_id']]['request']
        result = curve_candidates.outcome(request, 'FAILED', failure=normalized)
        return self._completion_finish(token, result)

    def cancel_completion(self, token):
        if not self.accepts(token) or self._jobs[token['request_id']]['kind'] != 'COMPLETION':
            return False
        request = self._jobs[token['request_id']]['request']
        result = curve_candidates.outcome(request, 'CANCELLED', failure=curve_candidates.error('CANCELLED', '基础候选计算已取消，当前编辑保持不变。'),
                     search=dict(expansions=None, generated_notes=None, termination='CANCELLED', raw_termination='UNKNOWN', rejections=[]))
        return self._completion_finish(token, result)

    def completion_state(self):
        attempt = self._attempt(self._completion_id)
        if self._completion_immediate is not None:
            result = self._completion_immediate
            return dict(status='NOT_NEEDED', attempt_id=None, input_fingerprint=result['input_fingerprint'], request=None,
                        outcome=copy.deepcopy(result), error=None, message='没有目标空缺，无需基础补全。')
        if attempt is None:
            return dict(status='IDLE', attempt_id=None, input_fingerprint=None, request=None, outcome=None, error=None, message='基础补全尚未计算。')
        messages = dict(RUNNING='正在计算基础候选；尚未处理bridge与连接。', READY='基础候选已暂存；尚未处理bridge与连接，不能应用或导出整曲。',
                        FAILED='基础候选计算失败；当前编辑与历史保留，可检查素材和保护后重试。', CANCELLED='基础候选计算已取消。',
                        STALE='输入已改变，旧基础候选已失效，请重新计算。', INTERRUPTED='上次计算已中断，请重新计算。')
        return dict(status=attempt['state'], attempt_id=attempt['id'], input_fingerprint=attempt['input_fingerprint'],
                    request=copy.deepcopy(attempt['completion']['request']), outcome=copy.deepcopy(attempt['completion']['outcome']),
                    error=copy.deepcopy(attempt['error']), message=messages[attempt['state']])

    def _bridge_attempt(self, identity):
        return next((a for a in self._bundle['attempts'] if a['id']==identity and 'bridge' in a),None)

    def _active_bridge(self, token):
        return self.accepts(token) and self._jobs[token['request_id']]['kind']=='BRIDGE'

    def capture_bridge(self, candidate_id=None, completion_attempt_id=None, seed=31, parameters=None):
        self._editable()
        if self._jobs:
            model.reject('已有任务正在准备，请等待或明确取消。','DUPLICATE_REQUEST')
        ref=None
        if candidate_id is not None or completion_attempt_id is not None:
            parent=self._attempt(completion_attempt_id)
            if parent is None or parent['state']!='READY':
                model.reject('请重新选择仍有效的基础候选。','STALE_SNAPSHOT')
            previous=parent['completion'];outcome=previous['outcome']
            curve_candidates.validate_outcome(previous['request'],outcome)
            selected=next((c for c in outcome['candidates'] if c['id']==candidate_id),None)
            if selected is None:model.reject('基础候选与所属尝试不匹配。','INVALID_CANDIDATE')
            ref=dict(attempt_id=completion_attempt_id,candidate_id=candidate_id,
                     request=copy.deepcopy(previous['request']),candidate=copy.deepcopy(selected))
        version=max([a['bridge']['request']['plan_version'] for a in self._bundle['attempts'] if 'bridge' in a]+[0])+1
        tentative=curve_bridges.make_request(self.project,ref,seed=seed,values=parameters,plan_version=version)
        captured=self.session.capture(tentative['request_id'],contract_rev=curve_bridges.REV);token=captured['token']
        try:
            request=curve_bridges.make_request(captured['project'],ref,token,seed,parameters,tentative['plan_id'],version)
            attempt=dict(id=request['request_id'],snapshot_id=request['snapshot_id'],input_fingerprint=request['input_fingerprint'],
                state='RUNNING',records=[],protections=copy.deepcopy(request['base_project']['protections']),staged_materials=[],error=None,
                bridge=dict(schema='emoblocks.bridge-attempt.v1',spec_rev=model.SPEC_REV,contract_rev=curve_bridges.REV,
                    request=copy.deepcopy(request),phase='BRIDGE_DECISION',plan=None,results=[],outcome=None))
            bundle=self._current_bundle()
            bundle['snapshots'].append(dict(id=request['snapshot_id'],spec_rev=model.SPEC_REV,contract_rev=request['input_contract_rev'],
                content_fingerprint=request['input_fingerprint'],project=copy.deepcopy(request['input_project'])))
            bundle['attempts'].append(attempt);curve_store.validate_bundle(bundle)
        except Exception:
            self.session.finish(token)
            raise
        self._bundle=bundle;self._jobs[token['request_id']]=dict(kind='BRIDGE',request=copy.deepcopy(request))
        self._bridge_id=attempt['id'];self._staging_dirty=True
        return dict(token=copy.deepcopy(token),request=copy.deepcopy(request),attempt_id=attempt['id'])

    def _publish_bridge(self, token, attempt, terminal=False):
        if not self._active_bridge(token):return False
        bundle=self._current_bundle()
        index=next(i for i,a in enumerate(bundle['attempts']) if a['id']==token['request_id'])
        bundle['attempts'][index]=copy.deepcopy(attempt)
        curve_store.validate_bundle(bundle)
        if not self._active_bridge(token):return False
        if terminal:
            if not self.session.finish(token):return False
            self._jobs.pop(token['request_id'],None)
        self._bundle=bundle;self._staging_dirty=True
        return True

    def lock_bridge(self, token, proposal):
        if not self._active_bridge(token):model.reject('桥决策输入已过期。','STALE_SNAPSHOT')
        attempt=copy.deepcopy(self._bridge_attempt(token['request_id']));stage=attempt['bridge']
        if stage['phase']!='BRIDGE_DECISION' or stage['plan'] is not None:
            model.reject('同一桥计划不能重复登记或改位。','PLAN_VERSION_MISMATCH')
        plan=curve_bridges.make_plan(stage['request'],proposal)
        stage['plan']=plan;stage['phase']='BRIDGE_LOCKED'
        attempt['protections']=curve_bridges.initial_locks(stage['request'],plan)
        if not self._publish_bridge(token,attempt):model.reject('桥决策输入已过期。','STALE_SNAPSHOT')
        return copy.deepcopy(plan)

    def begin_bridge_generation(self, token, plan):
        if not self._active_bridge(token):return False
        attempt=copy.deepcopy(self._bridge_attempt(token['request_id']));stage=attempt['bridge']
        if stage['phase']!='BRIDGE_LOCKED' or stage['plan']!=plan:
            model.reject('生成必须使用已原子锁定的同一计划。','PLAN_VERSION_MISMATCH')
        stage['phase']='BRIDGE_GENERATION'
        return self._publish_bridge(token,attempt)

    def record_bridge_result(self, token, result):
        if not self._active_bridge(token):return False
        attempt=copy.deepcopy(self._bridge_attempt(token['request_id']));stage=attempt['bridge']
        try:
            if stage['phase']!='BRIDGE_GENERATION':model.reject('桥生成尚未正式开始。','PLAN_VERSION_MISMATCH')
            curve_bridges.validate_result(stage['request'],stage['plan'],result)
            old=next((r for r in stage['results'] if r['bridge_id']==result['bridge_id']),None)
            if old is not None:
                if old==result:return False
                model.reject('同一桥不能由不同重复结果替换。','PLAN_VERSION_MISMATCH')
            stage['results'].append(copy.deepcopy(result))
            attempt['protections']=curve_bridges.locks_with_results(stage['request'],stage['plan'],stage['results'])
            attempt['staged_materials']=curve_bridges.staged_materials(stage['results'])
            return self._publish_bridge(token,attempt)
        except Exception as exc:
            self.fail_bridge(token,exc)
            return False

    def finish_bridge(self, token, raw):
        if not self._active_bridge(token):return False
        attempt=copy.deepcopy(self._bridge_attempt(token['request_id']));stage=attempt['bridge']
        try:
            if stage['phase']!='BRIDGE_GENERATION':model.reject('桥生成阶段或版本不匹配。','PLAN_VERSION_MISMATCH')
            curve_bridges.validate_raw(stage['request'],stage['plan'],raw)
            incoming={r['bridge_id']:r for r in raw['results']}
            if any(incoming.get(r['bridge_id'])!=r for r in stage['results']):
                model.reject('桥终态改写了此前认证的内容。','PROTECTION_CONFLICT')
            stage['results']=copy.deepcopy(raw['results'])
            attempt['protections']=curve_bridges.locks_with_results(stage['request'],stage['plan'],stage['results'])
            attempt['staged_materials']=curve_bridges.staged_materials(stage['results'])
            stage['outcome']=curve_bridges.make_outcome(stage['request'],stage['plan'],stage['results'],raw['status'],raw['error'])
            attempt['state']='READY' if raw['status']=='SUCCEEDED' else raw['status']
            attempt['error']=copy.deepcopy(raw['error'])
            if attempt['state']=='READY':stage['phase']='BRIDGES_READY'
            return self._publish_bridge(token,attempt,terminal=True)
        except Exception as exc:
            self.fail_bridge(token,exc)
            return False

    def _bridge_terminate(self, token, failure, state):
        if not self._active_bridge(token):return False
        if not isinstance(failure,dict):failure=dict(code=getattr(failure,'code','BRIDGE_GENERATION_FAILED'),message=str(failure),details={})
        normalized=dict(code=str(failure.get('code') or 'BRIDGE_GENERATION_FAILED'),
            message=str(failure.get('message') or '桥接失败，请检查保护和素材后重试。'),
            details=copy.deepcopy(failure.get('details')) if isinstance(failure.get('details'),dict) else {})
        try:model.canonical(normalized)
        except model.ProjectError:normalized['details']={}
        attempt=copy.deepcopy(self._bridge_attempt(token['request_id']));stage=attempt['bridge']
        plan=stage['plan'];request=stage['request']
        if plan:
            known={r['bridge_id'] for r in stage['results']}
            for ref in plan['protection_refs']:
                if ref['bridge_id'] not in known:
                    stage['results'].append(curve_bridges.failure_result(request,plan,ref['bridge_id'],normalized,state))
        attempt['state']=state;attempt['error']=normalized
        stage['outcome']=curve_bridges.make_outcome(request,plan,stage['results'],state,normalized)
        return self._publish_bridge(token,attempt,terminal=True)

    def fail_bridge(self, token, error):
        return self._bridge_terminate(token,error,'FAILED')

    def cancel_bridge(self, token):
        return self._bridge_terminate(token,curve_bridges.error('CANCELLED','桥接计算已取消，已登记保护与有效内容保留。'),'CANCELLED')

    def bridge_state(self):
        attempt=self._bridge_attempt(self._bridge_id)
        if attempt is None:
            return dict(status='IDLE',phase=None,attempt_id=None,request=None,plan=None,protections=[],results=[],outcome=None,
                        preview=None,remaining_gaps=[],capabilities=curve_bridges.capabilities(),error=None,message='bridge尚未计算。')
        stage=attempt['bridge'];outcome=stage['outcome'];active=attempt['state']=='READY'
        messages=dict(RUNNING='桥接正在计算，锁定范围不等于音乐就绪。',READY='桥内容已认证就绪，尚未处理连接和最终边界。',
            FAILED='桥接失败，保护与已认证内容保留，请明确重试。',CANCELLED='桥接已取消，原编辑与保护保留。',
            STALE='输入已改变，旧桥计划已失效；撤销回原内容也需重新计算。',INTERRUPTED='上次桥接已中断，请明确重新计算。')
        return dict(status=attempt['state'],phase=stage['phase'],attempt_id=attempt['id'],request=copy.deepcopy(stage['request']),
            plan=copy.deepcopy(stage['plan']),protections=copy.deepcopy(attempt['protections']),results=copy.deepcopy(stage['results']),
            outcome=copy.deepcopy(outcome),preview=curve_bridges.preview(stage['request'],stage['plan'],attempt['protections'],stage['results'],outcome),
            remaining_gaps=copy.deepcopy(stage['request']['remaining_gaps']),capabilities=curve_bridges.capabilities(active),
            error=copy.deepcopy(attempt['error']),message=messages[attempt['state']])

    def _current_bundle(self):
        bundle = copy.deepcopy(self._bundle)
        bundle['project'] = self.session.project
        bundle['contract_rev'] = bundle['project']['contract_rev']
        return bundle

    def save_snapshot(self, path=None):
        self._editable()
        path = curve_store.save(self._current_bundle(), path)
        self.session.mark_saved()
        self._saved_path = path
        self._staging_dirty = False
        self._untouched_new = False
        return path

    def autosave_if_needed(self):
        if self.readonly or (self.session.is_saved and not self._staging_dirty):
            return None
        if not self._staging_dirty and self._untouched_new and model.fingerprint(self.session.project) == self._initial_fingerprint:
            return None
        return self.save_snapshot()

    def _replace(self, loaded, path=None):
        project = loaded['bundle']['project'] if loaded and loaded['bundle'] else model.new_project()
        self.session = curve_session.ProjectSession(project, recompute=curve_memory.recompute)
        self._bundle = copy.deepcopy(loaded['bundle']) if loaded and loaded['bundle'] else curve_store.new_bundle(project)
        self._initial_fingerprint = model.fingerprint(project)
        self._loaded = loaded
        self._saved_path = Path(path) if path else None
        self._untouched_new = loaded is None
        self._jobs.clear()
        self._staging_dirty = bool(loaded and loaded.get('staging_dirty', False))
        completions = [v for v in self._bundle['attempts'] if 'completion' in v]
        self._completion_id = completions[-1]['id'] if completions else None
        self._completion_immediate = None
        bridges = [v for v in self._bundle['attempts'] if 'bridge' in v]
        self._bridge_id = bridges[-1]['id'] if bridges else None
        if loaded is not None:
            self.session.mark_saved()

    def load(self, path):
        loaded = curve_store.load(path)
        self.autosave_if_needed()
        self._replace(loaded, path)
        return self.state()

    def new(self, grid_count=8):
        project = model.new_project(grid_count)
        self.autosave_if_needed()
        self._replace(None)
        self.session = curve_session.ProjectSession(project, recompute=curve_memory.recompute)
        self._bundle = curve_store.new_bundle(project)
        self._initial_fingerprint = model.fingerprint(project)
        return self.state()

    def history_items(self):
        results = self._loaded['legacy'].get('results', []) if self.readonly else self._bundle['results']
        rows = []
        for index, result in enumerate(results):
            report = result.get('report') if isinstance(result.get('report'), dict) else {}
            directory = report.get('output_directory')
            paths = {k: str(Path(directory) / filename) if isinstance(directory, str) and directory else None for k, filename in FORMATS.items()}
            available = {k: bool(path and Path(path).is_file()) for k, path in paths.items()}
            body = report.get('duration_seconds')
            audio = None
            if available['wav']:
                try:
                    with wave.open(paths['wav'], 'rb') as stream:
                        audio = stream.getnframes() / stream.getframerate()
                except (OSError, wave.Error):
                    available['wav'] = False
            rows.append(dict(id='history:' + str(index) + ':' + model.digest('history-id', result)[:12], label='V' + str(index + 1).zfill(2),
                generated_at=result.get('generated_at', report.get('generated_at')), body_seconds=body, audio_seconds=audio,
                availability=available, paths=paths, edit_fingerprint=result.get('story_fingerprint')))
        return rows

    def export_history(self, result_id, format, destination):
        if format not in FORMATS:
            model.reject('请选择WAV、MIDI或MMP格式。')
        items = self.history_items()
        row = next((r for r in items if r['id'] == result_id), None)
        if row is None or not row['availability'][format]:
            model.reject('此版本对应格式文件已不可用，请找回文件或选择其他版本。', 'SOURCE_UNAVAILABLE')
        protected = [Path(path) for item in items for path in item['paths'].values() if path]
        # Reports, snapshots, render logs and copied resources are generated
        # sources too. Include all versions and let atomic_export check aliases.
        directories = {path.parent for path in protected}
        for directory in directories:
            protected.extend(path for path in directory.rglob('*') if path.is_file())
        return atomic_export(row['paths'][format], destination, protected)


CurveController = Controller
