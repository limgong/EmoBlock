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
    return dict(schema=SCHEMA, spec_rev=model.SPEC_REV, contract_rev=model.CONTRACT_REV,
        project=copy.deepcopy(project), snapshots=[], attempts=[], results=[])


def _validate_bundle(bundle):
    model.canonical(bundle)
    model.shape(bundle, 'schema spec_rev contract_rev project snapshots attempts results')
    if (bundle['schema'], bundle['spec_rev'], bundle['contract_rev']) != (SCHEMA, model.SPEC_REV, model.CONTRACT_REV):
        model.reject('保存包版本不受支持。', 'UNSUPPORTED_VERSION')
    model.validate(bundle['project'])
    snapshots = model.indexed(bundle['snapshots'])
    for snap in snapshots.values():
        model.shape(snap, 'id spec_rev contract_rev content_fingerprint project')
        if (snap['spec_rev'], snap['contract_rev']) != (model.SPEC_REV, model.CONTRACT_REV):
            model.reject('输入快照版本不匹配。', 'UNSUPPORTED_VERSION')
        if snap['project']['project_id'] != bundle['project']['project_id'] or model.fingerprint(snap['project']) != snap['content_fingerprint']:
            model.reject('输入快照身份或指纹不匹配。', 'STALE_SNAPSHOT')
    for attempt in model.indexed(bundle['attempts']).values():
        model.shape(attempt, 'id snapshot_id input_fingerprint state records protections staged_materials error')
        snap = snapshots.get(attempt['snapshot_id'])
        if snap is None or snap['content_fingerprint'] != attempt['input_fingerprint']:
            model.reject('候选缺少可信输入快照。', 'STALE_SNAPSHOT')
        if attempt['state'] not in ('RUNNING', 'FAILED', 'CANCELLED', 'INTERRUPTED', 'READY', 'APPLIED') or (attempt['error'] is not None and not isinstance(attempt['error'], dict)):
            model.reject('候选状态或错误详情无效。')
        sources = model.indexed(snap['project']['sources'])
        materials = model.indexed(snap['project']['materials'])
        for material in model.indexed(attempt['staged_materials']).values():
            model.material_check(material, sources)
            if material['id'] in materials:
                model.reject('暂存素材不得覆盖原素材。')
            materials[material['id']] = material
        placements = model.indexed(snap['project']['placements'])
        for p in model.indexed(attempt['protections']).values():
            model.protection_check(p, snap['project']['total_ticks'], placements, sources)
        model.records_check(attempt['records'], attempt['protections'], placements, snap['project']['total_ticks'], materials, sources)
    for result in model.objects(bundle['results']):
        if not isinstance(result, dict):
            model.reject('历史成品记录无效。')


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
        report = result.get('report', {})
        folder = Path(report.get('output_directory', ''))
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
            for attempt in bundle['attempts']:
                if attempt['state'] == 'RUNNING':
                    attempt['state'] = 'INTERRUPTED'
            return dict(format=model.SCHEMA, access_mode='editable', capabilities=dict(edit=True, plan=False,
                history=history_availability(bundle['results'])), bundle=bundle, legacy=None)
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
