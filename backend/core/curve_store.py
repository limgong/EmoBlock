"""Version-dispatched snapshots. No conversion, planning, playback or overwrite."""
import copy
import json
import os
from pathlib import Path

import curve_project as model
from runtime_config import data_root

SCHEMA = 'emoblocks.curve-bundle.v1'
MAX_BYTES = 20 * 1024 * 1024


def new_bundle(project):
    model.validate(project)
    return dict(schema=SCHEMA, spec_rev=model.SPEC_REV, contract_rev=project['contract_rev'],
        project=copy.deepcopy(project), snapshots=[], attempts=[], results=[])


def _validate_bundle(bundle):
    model.canonical(bundle)
    model.shape(bundle, 'schema spec_rev contract_rev project snapshots attempts results')
    if (bundle['schema'], bundle['spec_rev']) != (SCHEMA, model.SPEC_REV) or bundle['contract_rev'] not in model.SUPPORTED_CONTRACT_REVS or bundle['contract_rev'] != bundle['project']['contract_rev']:
        model.reject('保存包版本不受支持。', 'UNSUPPORTED_VERSION')
    model.validate(bundle['project'])
    snapshots = model.indexed(bundle['snapshots'])
    for snap in snapshots.values():
        model.shape(snap, 'id spec_rev contract_rev content_fingerprint project')
        if snap['spec_rev'] != model.SPEC_REV or snap['contract_rev'] not in model.SUPPORTED_CONTRACT_REVS or snap['contract_rev'] != snap['project']['contract_rev']:
            model.reject('输入快照版本不匹配。', 'UNSUPPORTED_VERSION')
        if snap['project']['project_id'] != bundle['project']['project_id'] or model.fingerprint(snap['project']) != snap['content_fingerprint']:
            model.reject('输入快照身份或指纹不匹配。', 'STALE_SNAPSHOT')
    record_scopes = [bundle['project']['records']] + [snap['project']['records'] for snap in snapshots.values()]
    snapshot_edges = {key: [] for key in snapshots}
    for snap in snapshots.values():
        snapshot_edges[snap['id']] = [r['payload']['input_snapshot_id'] for r in snap['project']['records'] if r['kind'] == 'accepted_candidate']
    for attempt in model.indexed(bundle['attempts']).values():
        if 'completion' in attempt:
            _validate_completion_attempt(attempt, snapshots)
            if attempt['state'] in ('READY', 'RUNNING') and attempt['input_fingerprint'] != model.fingerprint(bundle['project']):
                model.reject('当前输入已变化，不能恢复未失效的旧候选。', 'STALE_SNAPSHOT')
            continue
        model.shape(attempt, 'id snapshot_id input_fingerprint state records protections staged_materials error')
        snap = snapshots.get(attempt['snapshot_id'])
        if snap is None or snap['content_fingerprint'] != attempt['input_fingerprint']:
            model.reject('候选缺少可信输入快照。', 'STALE_SNAPSHOT')
        if attempt['state'] not in ('RUNNING', 'FAILED', 'CANCELLED', 'INTERRUPTED', 'READY', 'APPLIED') or (attempt['error'] is not None and not isinstance(attempt['error'], dict)):
            model.reject('候选状态或错误详情无效。')
        record_scopes.append(attempt['records'])
        sources = model.source_index(snap['project']['sources'])
        materials = model.indexed(snap['project']['materials'])
        for material in model.indexed(attempt['staged_materials']).values():
            model.material_check(material, sources)
            if material['id'] in materials:
                model.reject('暂存素材不得覆盖原素材。')
            materials[material['id']] = material
        placements = model.indexed(snap['project']['placements'])
        for p in model.indexed(attempt['protections']).values():
            model.protection_check(p, snap['project']['total_ticks'], placements, sources,
                                   managed=model.managed_memory(snap['project'], p))
        model.records_check(attempt['records'], attempt['protections'], placements, snap['project']['total_ticks'], materials, sources,
                            project_id=snap['project']['project_id'])
    for records in record_scopes:
        for record in records:
            if record['kind'] != 'accepted_candidate':
                continue
            snap = snapshots.get(record['payload']['input_snapshot_id'])
            if snap is None or snap['content_fingerprint'] != record['input_fingerprint']:
                model.reject('接受记录的原输入快照不存在或指纹过期。', 'STALE_SNAPSHOT')
    visiting = set(); visited = set()
    def visit(key):
        if key in visiting:
            model.reject('输入快照引用有环。')
        if key in visited:
            return
        if key not in snapshot_edges:
            model.reject('输入快照引用不存在。')
        visiting.add(key)
        for child in snapshot_edges[key]:
            visit(child)
        visiting.remove(key); visited.add(key)
    for key in snapshot_edges:
        visit(key)
    for result in model.objects(bundle['results']):
        if not isinstance(result, dict):
            model.reject('历史成品记录无效。')


def _validate_completion_attempt(attempt, snapshots):
    import curve_candidates as candidates
    model.shape(attempt, 'id snapshot_id input_fingerprint state records protections staged_materials error completion')
    completion = attempt['completion']
    model.shape(completion, 'schema spec_rev contract_rev request outcome')
    if (completion['schema'], completion['spec_rev'], completion['contract_rev']) != ('emoblocks.completion-attempt.v1', model.SPEC_REV, candidates.REV):
        model.reject('补全暂存版本不匹配。', 'UNSUPPORTED_VERSION')
    request = completion['request']; candidates.validate_request(request)
    snap = snapshots.get(attempt['snapshot_id'])
    if (snap is None or snap['project'] != request['project'] or snap['id'] != request['snapshot_id']
            or attempt['id'] != request['request_id'] or attempt['input_fingerprint'] != request['input_fingerprint']
            or attempt['input_fingerprint'] != snap['content_fingerprint']):
        model.reject('补全暂存缺少匹配原版本输入快照。', 'STALE_SNAPSHOT')
    if not request['target_gaps'] or any(attempt[k] != [] for k in ('records', 'protections', 'staged_materials')):
        model.reject('补全候选不能污染编辑保护或无目标注册暂存。', 'INVALID_CANDIDATE')
    state, outcome = attempt['state'], completion['outcome']
    if state not in ('RUNNING', 'INTERRUPTED', 'READY', 'FAILED', 'CANCELLED', 'STALE'):
        model.reject('基础候选不能被当作已应用或最终方案。', 'INVALID_CANDIDATE')
    if outcome is not None:
        candidates.validate_outcome(request, outcome)
    if state in ('RUNNING', 'INTERRUPTED'):
        valid = outcome is None and attempt['error'] is None
    elif state == 'READY':
        valid = outcome is not None and outcome['status'] in ('SUCCEEDED', 'INSUFFICIENT') and attempt['error'] is None
    elif state in ('FAILED', 'CANCELLED'):
        valid = outcome is not None and outcome['status'] == state and attempt['error'] == outcome['error']
    else:
        valid = (attempt['error'] == (outcome['error'] if outcome is not None else None))
    if not valid:
        model.reject('补全暂存状态、结果及错误不一致。', 'INVALID_CANDIDATE')


def save(bundle, path=None):
    validate_bundle(bundle)
    serialized = json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False)
    if len(serialized.encode('utf-8')) > MAX_BYTES:
        model.reject('工程文件超过20MiB。')
    if path is None:
        folder = data_root() / 'projects'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('curve-' + model.uid() + '.json')
    path = Path(path)
    created = False
    try:
        with path.open('x', encoding='utf-8') as stream:
            created = True
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise
    return path


def _legacy_validate(data, path):
    import assembly
    import story_engine
    import studio_model
    import structure_engine
    import material_engine as materials
    schema = data.get('schema')
    if schema in (assembly.SCHEMA, story_engine.SCHEMA):
        story_engine.validate(data, require_source=False)
    elif schema in (studio_model.SCHEMA, structure_engine.SCHEMA, materials.SCHEMA):
        studio_model.load_project(path)  # validation only; never return its normalization
    else:
        model.reject('请选择受支持的工程文件。', 'UNSUPPORTED_VERSION')


def history_availability(results):
    """Per-format availability is descriptive; callers still recheck on export."""
    rows = []
    for result in results:
        report = result.get('report')
        directory = report.get('output_directory') if isinstance(report, dict) else None
        if not isinstance(directory, str) or not directory:
            rows.append(dict(wav=False, midi=False, mmp=False))
            continue
        folder = Path(directory)
        rows.append(dict(wav=(folder / 'preview.wav').is_file(), midi=(folder / 'composition.mid').is_file(), mmp=(folder / 'composition.mmp').is_file()))
    return rows


def load(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        model.reject('工程文件超过20MiB。')
    try:
        data = json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda _: model.reject('工程含非有限数字。'))
        if not isinstance(data, dict):
            model.reject('工程根对象无效。')
        if data.get('schema') == model.SCHEMA:
            data = new_bundle(data)
        if data.get('schema') == SCHEMA:
            validate_bundle(data)
            bundle = copy.deepcopy(data)
            staging_dirty = False
            for attempt in bundle['attempts']:
                if attempt['state'] == 'RUNNING':
                    attempt['state'] = 'INTERRUPTED'
                    staging_dirty = staging_dirty or 'completion' in attempt
            return dict(format=model.SCHEMA, access_mode='editable', capabilities=dict(edit=True, plan=False,
                history=history_availability(bundle['results'])), bundle=bundle, legacy=None, staging_dirty=staging_dirty)
        _legacy_validate(data, path)
        return dict(format=data['schema'], access_mode='legacy_readonly', capabilities=dict(edit=False, plan=False,
            history=history_availability(data.get('results', []))), bundle=None, legacy=copy.deepcopy(data))
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise model.ProjectError('INVALID_PROJECT', '工程损坏或结构无效，请选择另一个快照。') from exc


def validate_bundle(bundle):
    try:
        _validate_bundle(bundle)
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise model.ProjectError('INVALID_PROJECT', '保存包字段缺失或引用无效。') from exc
