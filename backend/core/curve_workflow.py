"""Public r3 desktop facade: immutable jobs and atomic material/state operations."""
import copy
from pathlib import Path
import wave

import curve_project as model
import curve_session
import curve_store
import curve_memory
from curve_audition import render_audition
from export_safe import atomic_export

FORMATS = {'wav': 'preview.wav', 'mid': 'composition.mid', 'mmp': 'composition.mmp'}


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

    @property
    def readonly(self):
        return self._loaded is not None and self._loaded['access_mode'] == 'legacy_readonly'

    @property
    def project(self):
        return None if self.readonly else self.session.project

    def state(self):
        return dict(access_mode='legacy_readonly' if self.readonly else 'editable', project=self.project,
            capabilities=dict(edit=not self.readonly, derive=not self.readonly, audition=True,
                generate_final=False, intensity_edit=not self.readonly, emotion=not self.readonly, memory=not self.readonly),
            is_saved=True if self.readonly else self.session.is_saved,
            saved_path=str(self._saved_path) if self._saved_path else None,
            can_undo=not self.readonly and self.session.can_undo, can_redo=not self.readonly and self.session.can_redo,
            memory_info=None if self.readonly else curve_memory.memory_info(self.session.project))

    def _editable(self):
        if self.readonly:
            model.reject('这是旧工程的只读模式；可试听和导出现有成品，请新建工程开始创作。', 'READ_ONLY')

    def edit(self, action, **args):
        self._editable()
        changed = self.session.edit(action, **args)
        if changed:
            self._jobs.clear()
            self._untouched_new = False
        return changed

    def undo(self):
        self._editable()
        changed = self.session.undo()
        if changed:
            self._jobs.clear()
            self._untouched_new = False
        return changed

    def redo(self):
        self._editable()
        changed = self.session.redo()
        if changed:
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
        return self.session.accepts(token) and token.get('request_id') in self._jobs

    def cancel_job(self, token):
        return self.finish_job(token)

    def finish_job(self, token):
        if not self.accepts(token):
            return False
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
            self._jobs.clear()
            self._untouched_new = False
        elif not changed:
            self._jobs.pop(token['request_id'], None)
        return dict(changed=committed, added_source_ids=list(sources) if committed else [], added_material_ids=list(materials) if committed else [])

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
        self._untouched_new = False
        return path

    def autosave_if_needed(self):
        if self.readonly or self.session.is_saved:
            return None
        if self._untouched_new and model.fingerprint(self.session.project) == self._initial_fingerprint:
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
