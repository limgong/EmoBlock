"""Frozen r3 musical state. Pure data validation and fixed-time editing, no planning."""
import copy
import hashlib
import math
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

import intensity_curve
import curve_json

SCHEMA = 'emoblocks.assembly.v2'
SPEC_REV = 'curve-workflow-v2-r3'
CONTRACT_REV = 'curve-workflow-v2-r3-p4'
SUPPORTED_CONTRACT_REVS = ('curve-workflow-v2-r3-p0', 'curve-workflow-v2-r3-p23', CONTRACT_REV, 'curve-workflow-v2-r3-p7')
PPQ = 480
BAR = PPQ * 4
EMOTIONS = ('calm', 'hope', 'sad', 'suspense', 'crisis', 'resolve')
_IDENTITY_CONTEXT = ContextVar('curve_private_identity', default=None)
_VALIDATION_CONTEXT = ContextVar('curve_pure_validation', default=None)
RECORD_FIELDS = {
    'bridge_plan': 'candidate_id candidate_fingerprint automatic_decision bridge_ids manual_bridge_ids ranges reasons joint_boundary_conditions',
    'bridge_result': 'bridge_id plan_id plan_version protection_id material_snapshot validation',
    'connection_plan': 'bridge_plan_id bridge_plan_version bridge_layout_fingerprint protection_summary_fingerprint endpoint_refs windows decisions',
    'connection_result': 'plan_id plan_version original_notes output_notes actual_impact_ranges validation',
    'boundary_plan': 'bridge_plan_id bridge_plan_version protection_summary_fingerprint operations original_notes',
    'final_score': 'total_ticks notes protection_summary_fingerprint validation',
    'accepted_candidate': 'final_score_id transaction_id input_snapshot_id',
    'captured_music': 'source_score_ref source_input_fingerprint source_notes performance_map base_binding_fingerprint added_placement_ids',
}


class ProjectError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def reject(message, code='INVALID_PROJECT'):
    raise ProjectError(code, message)


def uid():
    context = _IDENTITY_CONTEXT.get()
    if context is not None:
        context['serial'] += 1
        return digest('emoblocks.private-attempt-id.v1', dict(namespace=context['namespace'], serial=context['serial']))
    return uuid.uuid4().hex


@contextmanager
def deterministic_ids(namespace):
    """Thread-local private facts: replaying one captured request is reproducible."""
    token = _IDENTITY_CONTEXT.set(dict(namespace=namespace,serial=0,validated_projects=set()))
    try: yield
    finally: _IDENTITY_CONTEXT.reset(token)


@contextmanager
def validation_scope():
    """Bounded, operation-local pure checks; changed bytes always get a new key."""
    existing=_VALIDATION_CONTEXT.get()
    if existing is not None:
        yield existing
        return
    context=dict(validated_projects=set(),final_checks={},native_checks={})
    token=_VALIDATION_CONTEXT.set(context)
    try:yield context
    finally:_VALIDATION_CONTEXT.reset(token)


def validated_operation(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        with validation_scope():return fn(*args,**kwargs)
    return wrapped


def cached_validation(fn,args,kwargs):
    """Memoize only successful pure data gates inside one operation, never files."""
    with validation_scope() as context:
        key=digest('emoblocks.native-validation-cache.v1',dict(function=fn.__module__+'.'+fn.__name__,args=args,kwargs=kwargs))
        cache=context['native_checks']
        if key in cache:return copy.deepcopy(cache[key])
        value=fn(*args,**kwargs)
        if len(cache)<128:cache[key]=copy.deepcopy(value)
        return value


def canonical(value):
    try:
        return curve_json.dumps_text(value)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProjectError('INVALID_PROJECT', '工程必须是有限、无环的 JSON 数据。') from exc


def canonical_bytes(value):
    try:
        return curve_json.dumps_bytes(value)
    except UnicodeEncodeError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProjectError('INVALID_PROJECT', '工程必须是有限、无环的 JSON 数据。') from exc


def digest(domain, value):
    return hashlib.sha256(domain.encode('utf-8') + b'\n' + canonical_bytes(value)).hexdigest()


def shape(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        reject('工程对象字段缺失或不受支持。')


def ident(value):
    if not isinstance(value, str) or not value:
        reject('身份必须是非空字符串。')


def integer(value, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        reject('音乐时间或整数超出有效范围。')


def text(value):
    if not isinstance(value, str):
        reject('文本字段无效。')


def objects(value):
    if not isinstance(value, list):
        reject('工程集合必须是列表。')
    return value


def indexed(value):
    result = {}
    for item in objects(value):
        if not isinstance(item, dict):
            reject('工程集合元素无效。')
        ident(item.get('id'))
        if item['id'] in result:
            reject('工程身份重复。')
        result[item['id']] = item
    return result


class SourceIndex(dict):
    def __init__(self, items):
        super().__init__(indexed(items))
        self.note_ids = {key: set(indexed(source.get('notes'))) for key, source in self.items()}


def source_index(items):
    return SourceIndex(items)


def range_check(value, total):
    shape(value, 'start_tick end_tick')
    integer(value['start_tick'], 0, total)
    integer(value['end_tick'], value['start_tick'] + 1, total)


def intersects(a, b):
    return a['start_tick'] < b['end_tick'] and b['start_tick'] < a['end_tick']


def note_check(note, length, sources, absolute_start=0):
    shape(note, 'id pitch start_tick duration_tick velocity origin lineage slice')
    ident(note['id'])
    integer(note['pitch'], 0, 127)
    integer(note['velocity'], 1, 127)
    integer(note['start_tick'], absolute_start, length)
    integer(note['duration_tick'], 1)
    if note['start_tick'] + note['duration_tick'] > length:
        reject('音符超出实际素材或保护长度。')
    if note['origin'] is not None:
        shape(note['origin'], 'source_id track_id source_note_id')
        for v in note['origin'].values():
            ident(v)
        source = sources.get(note['origin']['source_id'])
        note_ids = sources.note_ids.get(note['origin']['source_id'], set()) if isinstance(sources, SourceIndex) else {n.get('id') for n in (source or {}).get('notes', [])}
        if source is None or note['origin']['source_note_id'] not in note_ids:
            reject('音符来源或原音符身份不存在。')
    for value in objects(note['lineage']):
        ident(value)
    if note['slice'] is not None:
        shape(note['slice'], 'parent_emission_id offset_tick parent_duration_tick')
        ident(note['slice']['parent_emission_id'])
        integer(note['slice']['offset_tick'])
        integer(note['slice']['parent_duration_tick'], 1)
        if note['slice']['offset_tick'] + note['duration_tick'] > note['slice']['parent_duration_tick']:
            reject('跨块切片超出原音符。')


def notes_check(notes, length, sources, absolute_start=0):
    indexed(notes)
    for n in notes:
        note_check(n, length, sources, absolute_start)


def musical_notes(notes):
    # Flattened combination IDs are independent; musical ancestry remains exact.
    return sorted([{k: v for k, v in n.items() if k != 'id'} for n in notes], key=canonical)


def material_check(material, sources, depth=0, ancestors=()):
    shape(material, 'id label kind length_ticks notes provenance generation phrase_id children')
    ident(material['id']); text(material['label']); integer(material['length_ticks'], 1)
    if depth > 16 or material['id'] in ancestors:
        reject('组合素材有环或超过16层。')
    if material['kind'] not in ('block', 'phrase', 'combination', 'bridge'):
        reject('未知素材种类。')
    if not isinstance(material['provenance'], dict) or (material['generation'] is not None and not isinstance(material['generation'], dict)):
        reject('素材来源/生成记录无效。')
    if material['phrase_id'] is not None:
        ident(material['phrase_id'])
    notes_check(material['notes'], material['length_ticks'], sources)
    parts = objects(material['children'])
    if material['kind'] != 'combination' and parts:
        reject('非组合素材不能包含组合组件。')
    if material['kind'] == 'combination':
        if not parts:
            reject('组合素材不能为空。')
        offset = 0; seen = set(); combined = []
        for child in parts:
            shape(child, 'occurrence_id offset_tick snapshot')
            ident(child['occurrence_id']); integer(child['offset_tick'])
            if child['occurrence_id'] in seen or child['offset_tick'] != offset:
                reject('组合组件身份重复或排列不连续。')
            seen.add(child['occurrence_id'])
            material_check(child['snapshot'], sources, depth + 1, ancestors + (material['id'],))
            combined.extend(dict(n, start_tick=n['start_tick'] + offset) for n in child['snapshot']['notes'])
            offset += child['snapshot']['length_ticks']
        if offset != material['length_ticks'] or musical_notes(combined) != musical_notes(material['notes']):
            reject('组合音符或时长与组件快照不一致。')


def placement_check(placement, total, materials, sources):
    shape(placement, 'id material_id base_snapshot start_tick length_ticks emotion emotion_variant')
    ident(placement['id'])
    if placement['material_id'] not in materials:
        reject('放置素材不在素材库。')
    material_check(placement['base_snapshot'], sources)
    if placement['base_snapshot']['id'] != placement['material_id']:
        reject('放置快照身份与素材不一致。')
    integer(placement['start_tick']); integer(placement['length_ticks'], 1)
    if placement['length_ticks'] != placement['base_snapshot']['length_ticks'] or placement['start_tick'] + placement['length_ticks'] > total:
        reject('放置越界或改变了素材时长。', 'OUT_OF_BOUNDS')
    if placement['emotion'] not in EMOTIONS:
        reject('未知情绪。')
    if placement['emotion_variant'] is not None:
        material_check(placement['emotion_variant'], sources)
        if placement['emotion_variant']['length_ticks'] != placement['length_ticks']:
            reject('情绪变体不能改变放置时长。')


def structural_notes(notes):
    return [{k: v for k, v in n.items() if k != 'velocity'} for n in sorted(notes, key=lambda n: (n['start_tick'], n['pitch'], n['duration_tick'], n['id']))]


def structure_fingerprint(protection):
    return digest('emoblocks.protection.v1', dict(range=dict(start_tick=protection['start_tick'], end_tick=protection['end_tick']),
        blank_mask=sorted(protection['blank_mask'], key=lambda r: (r['start_tick'], r['end_tick'])), notes=structural_notes(protection['notes'])))


def protection_summary(protections):
    indexed(protections)
    return digest('emoblocks.protection-summary.v1', [dict(p, notes=structural_notes(p['notes']),
        blank_mask=sorted(p['blank_mask'], key=lambda r: (r['start_tick'], r['end_tick']))) for p in sorted(protections, key=lambda p: p['id'])])


def placed_notes(placement):
    material = placement['emotion_variant'] or placement['base_snapshot']
    return [dict(n, id=placement['id'] + ':' + n['id'], start_tick=n['start_tick'] + placement['start_tick']) for n in material['notes']]


def current_notes(project):
    if project['contract_rev'] == 'curve-workflow-v2-r3-p7':
        from curve_application import current_notes as effective
        return effective(project)
    return sorted([n for p in project['placements'] for n in placed_notes(p)], key=lambda n:(n['start_tick'],n['pitch'],n['duration_tick'],n['id']))


def protection_ranges(protection):
    ranges = [{k: protection[k] for k in ('start_tick', 'end_tick')}]
    if protection['kind'] == 'memory':
        ranges += [dict(start_tick=n['start_tick'], end_tick=n['start_tick'] + n['duration_tick'])
                   for n in protection['notes']]
    return ranges


def protection_check(p, total, placements, sources, managed=False):
    shape(p, 'id kind owner_id placement_id component_path start_tick end_tick status origin plan_id plan_version input_fingerprint notes structure_fingerprint blank_mask')
    ident(p['id']); ident(p['owner_id']); text(p['input_fingerprint'])
    range_check({k: p[k] for k in ('start_tick', 'end_tick')}, total)
    if p['kind'] not in ('memory', 'theme', 'manual', 'bridge') or p['origin'] not in ('manual', 'automatic') or p['status'] not in ('RANGE_LOCKED', 'CONTENT_READY'):
        reject('保护种类或状态无效。')
    if p['plan_id'] is not None:
        ident(p['plan_id']); integer(p['plan_version'], 1)
    elif p['plan_version'] is not None or (p['kind'] == 'bridge' and p['origin'] == 'automatic'):
        reject('自动桥保护缺少计划版本。')
    objects(p['component_path'])
    placement = None
    if p['placement_id'] is not None:
        if p['placement_id'] not in placements:
            reject('活动保护引用不存在的放置。')
        placement = placements[p['placement_id']]
        component = placement['base_snapshot']
        for part_id in p['component_path']:
            ident(part_id)
            component = next((c['snapshot'] for c in component['children'] if c['occurrence_id'] == part_id), None)
            if component is None:
                reject('保护组件路径不存在。')
    elif p['component_path']:
        reject('保护组件路径缺少放置身份。')
    if managed and p['kind'] == 'memory' and p['status'] == 'CONTENT_READY':
        if placement is None:
            reject('记忆保护必须绑定基础放置。', 'PROTECTION_CONFLICT')
        notes_check(p['notes'], total, sources)
        import curve_memory
        expected = curve_memory.base_notes(placement, [dict(start_tick=p['start_tick'], end_tick=p['end_tick'])])
        if structural_notes(p['notes']) != structural_notes(expected):
            reject('记忆保护必须保存相交的完整基础音符。', 'PROTECTION_CONFLICT')
    else:
        notes_check(p['notes'], p['end_tick'], sources, p['start_tick'])
    for mask in objects(p['blank_mask']):
        range_check(mask, p['end_tick'])
        if mask['start_tick'] < p['start_tick']:
            reject('留白掩码不在保护范围。')
        if any(intersects(mask, dict(start_tick=n['start_tick'], end_tick=n['start_tick'] + n['duration_tick'])) for n in p['notes']):
            reject('保护主旋律进入主动留白。')
    if p['status'] == 'CONTENT_READY':
        masks = sorted(p['blank_mask'], key=lambda r: r['start_tick'])
        wholly_blank = bool(masks) and masks[0]['start_tick'] == p['start_tick'] and masks[-1]['end_tick'] == p['end_tick'] and all(a['end_tick'] == b['start_tick'] for a, b in zip(masks, masks[1:]))
        if not p['notes'] and not wholly_blank and not (managed and p['kind'] == 'memory'):
            reject('就绪保护没有实际音符。', 'BRIDGE_NOT_READY')
        if p['structure_fingerprint'] != structure_fingerprint(p):
            reject('保护内容指纹不匹配。', 'PROTECTION_CONFLICT')
        if placement and p['kind'] == 'bridge':
            if p['start_tick'] != placement['start_tick'] or p['end_tick'] != placement['start_tick'] + placement['length_ticks'] or structural_notes(p['notes']) != structural_notes(placed_notes(placement)):
                reject('手动桥保护与实际放置不一致。', 'PROTECTION_CONFLICT')
    elif p['structure_fingerprint'] is not None:
        reject('范围锁不能冒充就绪内容指纹。')


def validate_protected_notes(protections, notes):
    """Compare complete supports, including notes originating outside a lock."""
    for p in protections:
        actual = [n for n in notes if any(intersects(r, dict(start_tick=n['start_tick'], end_tick=n['start_tick'] + n['duration_tick']))
                                        for r in protection_ranges(p))]
        if p['status'] != 'CONTENT_READY' or structural_notes(actual) != structural_notes(p['notes']):
            reject('实际旋律改变保护区音符或越过保护范围。', 'PROTECTION_CONFLICT')


def records_check(records, protections, placements, total, materials, sources, project_id=None):
    refs = indexed(records); locks = indexed(protections)
    for record in records:
        shape(record, 'id kind version status input_fingerprint dependencies payload')
        integer(record['version'], 1); text(record['input_fingerprint'])
        if record['status'] not in ('LOCKED', 'READY', 'FAILED', 'INVALIDATED') or record['kind'] not in RECORD_FIELDS:
            reject('未来计划种类或状态无效。')
        payload = record['payload']
        if not isinstance(payload, dict) or not set(RECORD_FIELDS[record['kind']].split()) <= set(payload):
            reject('未来计划缺少必需字段。')
        list_fields = {'bridge_plan': ('bridge_ids', 'manual_bridge_ids', 'ranges', 'reasons', 'joint_boundary_conditions'),
            'connection_plan': ('endpoint_refs', 'windows', 'decisions'),
            'connection_result': ('original_notes', 'output_notes', 'actual_impact_ranges'),
            'boundary_plan': ('operations', 'original_notes'), 'final_score': ('notes',)}
        for name in list_fields.get(record['kind'], ()):
            objects(payload[name])
        string_fields = {'bridge_plan': ('candidate_id', 'candidate_fingerprint'),
            'bridge_result': ('bridge_id', 'plan_id', 'protection_id'),
            'connection_plan': ('bridge_plan_id', 'bridge_layout_fingerprint', 'protection_summary_fingerprint'),
            'connection_result': ('plan_id',), 'boundary_plan': ('bridge_plan_id', 'protection_summary_fingerprint'),
            'final_score': ('protection_summary_fingerprint',),
            'accepted_candidate': ('final_score_id', 'transaction_id', 'input_snapshot_id')}
        for name in string_fields.get(record['kind'], ()):
            ident(payload[name])
        for name in ('plan_version', 'bridge_plan_version'):
            if name in payload:
                integer(payload[name], 1)
        if 'validation' in payload and not isinstance(payload['validation'], dict):
            reject('阶段校验报告必须是对象。')
        for name, expected_kind, version_field in (
            ('plan_id', 'bridge_plan' if record['kind'] == 'bridge_result' else 'connection_plan', 'plan_version'),
            ('bridge_plan_id', 'bridge_plan', 'bridge_plan_version'), ('final_score_id', 'final_score', None)):
            if name not in payload:
                continue
            target = refs.get(payload[name])
            if target is None or target['kind'] != expected_kind or (version_field and target['version'] != payload[version_field]):
                reject('阶段实际输入引用不存在或版本不匹配。', 'PLAN_VERSION_MISMATCH')
            if record['status'] in ('READY', 'LOCKED') and target['status'] in ('FAILED', 'INVALIDATED'):
                reject('阶段不能消费失败或失效的实际输入。', 'PLAN_VERSION_MISMATCH')
            if record['kind'] == 'accepted_candidate' and record['status'] == 'READY' and target['status'] != 'READY':
                reject('接受记录必须引用校验就绪的最终乐谱。', 'INVALID_FINAL_SCORE')
        for dep in objects(record['dependencies']):
            shape(dep, 'id version'); integer(dep['version'], 1)
            target = refs.get(dep['id'])
            if target is None or target['version'] != dep['version']:
                reject('计划依赖版本不存在。', 'PLAN_VERSION_MISMATCH')
            if record['status'] not in ('FAILED', 'INVALIDATED') and target['status'] in ('FAILED', 'INVALIDATED'):
                reject('活动计划不能消费失败或失效依赖。', 'PLAN_VERSION_MISMATCH')
        scope_placements, scope_locks = placements, locks
        scope_total = total
        if record['status'] == 'INVALIDATED':
            context = payload.get('audit_context'); shape(context, 'placements protections')
            scope_placements = indexed(context['placements']); scope_locks = indexed(context['protections'])
            scope_total = payload.get('audit_total_ticks', max([total, payload.get('total_ticks', 0)] + [p['start_tick'] + p['length_ticks'] for p in scope_placements.values()] + [p['end_tick'] for p in scope_locks.values()]))
            integer(scope_total, 1)
            for place in scope_placements.values():
                placement_check(place, scope_total, materials, sources)
            for lock in scope_locks.values():
                is_managed = project_id is not None and managed_memory(dict(project_id=project_id), lock)
                protection_check(lock, scope_total, scope_placements, sources, managed=is_managed)
            audit_memories = [p for p in scope_locks.values() if project_id is not None
                             and managed_memory(dict(project_id=project_id), p) and p['status'] == 'CONTENT_READY']
            if audit_memories:
                validate_protected_notes(audit_memories, [n for p in scope_placements.values() for n in placed_notes(p)])
        kind = record['kind']
        if kind == 'bridge_plan':
            if payload['automatic_decision'] not in ('none', 'selected'):
                reject('桥决策必须明确。')
            automatic = objects(payload['bridge_ids']); manual = objects(payload['manual_bridge_ids'])
            ids = automatic + manual
            if len(ids) != len(set(ids)) or (payload['automatic_decision'] == 'none' and automatic) or (payload['automatic_decision'] == 'selected' and not automatic):
                reject('桥计划集合与决策不一致。')
            for bridge_id in ids:
                ident(bridge_id)
                if not any(p['owner_id'] == bridge_id and p['kind'] == 'bridge' for p in scope_locks.values()):
                    reject('桥计划缺少范围保护。')
            for r in objects(payload['ranges']):
                range_check(r, scope_total)
            for name in ('reasons', 'joint_boundary_conditions'):
                objects(payload[name])
        if kind == 'bridge_result':
            plan = refs.get(payload['plan_id']); lock = scope_locks.get(payload['protection_id'])
            if plan is None or plan['kind'] != 'bridge_plan' or plan['version'] != payload['plan_version'] or lock is None or lock['owner_id'] != payload['bridge_id'] or lock['plan_id'] != plan['id'] or lock['plan_version'] != plan['version']:
                reject('桥结果计划/保护引用无效。', 'PLAN_VERSION_MISMATCH')
            material_check(payload['material_snapshot'], sources)
            if record['status'] == 'READY':
                snapshot = payload['material_snapshot']
                actual = [dict(n, id=payload['bridge_id'] + ':' + n['id'], start_tick=n['start_tick'] + lock['start_tick']) for n in snapshot['notes']]
                if snapshot['length_ticks'] != lock['end_tick'] - lock['start_tick'] or structural_notes(actual) != structural_notes(lock['notes']):
                    reject('桥结果实际内容与保护不一致。', 'PROTECTION_CONFLICT')
            if record['status'] == 'READY' and lock['status'] != 'CONTENT_READY':
                reject('桥结果没有就绪保护。', 'BRIDGE_NOT_READY')
        if kind in ('connection_plan', 'boundary_plan'):
            plan = refs.get(payload['bridge_plan_id'])
            if plan is None or plan['kind'] != 'bridge_plan' or plan['version'] != payload['bridge_plan_version']:
                reject('连接或边界依赖桥版本不匹配。', 'PLAN_VERSION_MISMATCH')
            if record['status'] not in ('FAILED', 'INVALIDATED'):
                if plan['status'] != 'READY' or any(p['status'] != 'CONTENT_READY' for p in scope_locks.values() if p['kind'] == 'bridge'):
                    reject('桥未全部就绪，不能登记下游计划。', 'BRIDGE_NOT_READY')
                selected = plan['payload']['bridge_ids'] + plan['payload']['manual_bridge_ids']
                actual_locks = [p for p in scope_locks.values() if p['kind'] == 'bridge']
                if {p['owner_id'] for p in actual_locks} != set(selected):
                    reject('就绪桥集合与完整计划不一致。', 'BRIDGE_NOT_READY')
                for bridge_id in plan['payload']['bridge_ids']:
                    results = [r for r in records if r['kind'] == 'bridge_result' and r['payload'].get('bridge_id') == bridge_id and r['payload'].get('plan_id') == plan['id'] and r['payload'].get('plan_version') == plan['version']]
                    if len(results) != 1 or results[0]['status'] != 'READY':
                        reject('选定桥缺少唯一就绪结果。', 'BRIDGE_NOT_READY')
                if payload['protection_summary_fingerprint'] != protection_summary(list(scope_locks.values())):
                    reject('计划保护摘要过期。', 'PROTECTION_CONFLICT')
        if kind == 'connection_plan':
            for window in objects(payload['windows']):
                range_check(window, scope_total)
                if any(intersects(window, p) for p in scope_locks.values()):
                    reject('连接窗口进入保护。', 'PROTECTION_CONFLICT')
        if kind == 'connection_result':
            plan = refs.get(payload['plan_id'])
            if plan is None or plan['kind'] != 'connection_plan' or plan['version'] != payload['plan_version']:
                reject('连接结果依赖版本错误。', 'PLAN_VERSION_MISMATCH')
            for name in ('original_notes', 'output_notes'):
                notes_check(payload[name], scope_total, sources)
            for r in objects(payload['actual_impact_ranges']):
                range_check(r, scope_total)
            if record['status'] == 'READY':
                if plan['payload']['protection_summary_fingerprint'] != protection_summary(list(scope_locks.values())):
                    reject('连接结果父计划保护摘要过期。', 'PROTECTION_CONFLICT')
                validate_protected_notes(list(scope_locks.values()), payload['output_notes'])
        if kind == 'final_score':
            integer(payload['total_ticks'], 1)
            if record['status'] != 'INVALIDATED' and payload['total_ticks'] != total:
                reject('最终乐谱改变作品长度。')
            notes_check(payload['notes'], scope_total, sources)
            if record['status'] == 'READY' and payload['protection_summary_fingerprint'] != protection_summary(protections):
                reject('最终乐谱保护摘要不匹配。', 'PROTECTION_CONFLICT')
            if record['status'] == 'READY':
                validate_protected_notes(protections, payload['notes'])
        if kind == 'accepted_candidate' and (payload['final_score_id'] not in refs or refs[payload['final_score_id']]['kind'] != 'final_score'):
            reject('接受结果引用最终乐谱不存在。')
    visiting = set(); visited = set()
    def visit(key):
        if key in visiting:
            reject('阶段依赖有环。')
        if key in visited:
            return
        visiting.add(key)
        for dep in refs[key]['dependencies']:
            visit(dep['id'])
        visiting.remove(key); visited.add(key)
    for key in refs:
        visit(key)
    for lock in protections:
        if lock['plan_id'] is not None:
            plan = refs.get(lock['plan_id'])
            if plan is None or plan['kind'] != 'bridge_plan' or plan['version'] != lock['plan_version']:
                reject('保护计划引用失效。', 'PLAN_VERSION_MISMATCH')
            field = 'manual_bridge_ids' if lock['origin'] == 'manual' else 'bridge_ids'
            if lock['owner_id'] not in plan['payload'][field]:
                reject('保护所有者不在完整桥计划中。', 'PLAN_VERSION_MISMATCH')
    for plan in records:
        if plan['kind'] != 'bridge_plan' or plan['status'] == 'INVALIDATED':
            continue
        selected = plan['payload']['bridge_ids']
        if len(plan['payload']['ranges']) != len(selected):
            reject('自动桥范围集合不完整。')
        for owner, r in zip(selected, plan['payload']['ranges']):
            matched = [p for p in protections if p['plan_id'] == plan['id'] and p['owner_id'] == owner and p['plan_version'] == plan['version']]
            if len(matched) != 1 or any(matched[0][k] != r[k] for k in ('start_tick', 'end_tick')):
                reject('自动桥范围与原子锁不一致。')
        if plan['status'] == 'READY':
            for owner in selected:
                matched = [r for r in records if r['kind'] == 'bridge_result' and r['payload']['plan_id'] == plan['id'] and r['payload']['plan_version'] == plan['version'] and r['payload']['bridge_id'] == owner]
                if len(matched) != 1 or matched[0]['status'] != 'READY':
                    reject('桥计划不能跳过实际结果声明就绪。', 'BRIDGE_NOT_READY')


def _validate(project):
    canonical(project)
    shape(project, 'schema spec_rev contract_rev project_id ppq bpm grid_count total_ticks sources materials label_counters placements intensity_points blank_regions protections records accepted_candidate_id settings')
    if (project['schema'], project['spec_rev']) != (SCHEMA, SPEC_REV) or project['contract_rev'] not in SUPPORTED_CONTRACT_REVS:
        reject('工程格式或契约版本不受支持。', 'UNSUPPORTED_VERSION')
    ident(project['project_id']); integer(project['ppq'], PPQ, PPQ); integer(project['bpm'], 120, 120)
    integer(project['grid_count'], 1); integer(project['total_ticks'], 1)
    total = project['total_ticks']
    if total != project['grid_count'] * BAR:
        reject('固定时间轴长度与四拍格数不一致。')
    sources = source_index(project['sources']); materials = indexed(project['materials']); placements = indexed(project['placements'])
    for source in sources.values():
        shape(source, 'id label length_ticks notes provenance'); text(source['label']); integer(source['length_ticks'], 1)
        if not isinstance(source['provenance'], dict):
            reject('原始来源记录无效。')
        notes_check(source['notes'], source['length_ticks'], sources)
    def phrase_refs(material):
        if material['phrase_id'] is not None:
            parent = materials.get(material['phrase_id'])
            if parent is None or parent['kind'] != 'phrase' or parent['id'] == material['id']:
                reject('子块所属乐句引用无效。')
        for child in material['children']:
            phrase_refs(child['snapshot'])
    for material in materials.values():
        material_check(material, sources)
        phrase_refs(material)
    if not isinstance(project['label_counters'], dict):
        reject('显示编号计数器无效。')
    for key, value in project['label_counters'].items():
        text(key); integer(value)
    occupied = []
    for place in placements.values():
        placement_check(place, total, materials, sources)
        phrase_refs(place['base_snapshot'])
        if place['emotion_variant'] is not None:
            phrase_refs(place['emotion_variant'])
        occupied.append(dict(start_tick=place['start_tick'], end_tick=place['start_tick'] + place['length_ticks']))
    for blank in indexed(project['blank_regions']).values():
        shape(blank, 'id start_tick end_tick reason'); text(blank['reason'])
        r = dict(start_tick=blank['start_tick'], end_tick=blank['end_tick']); range_check(r, total); occupied.append(r)
    occupied.sort(key=lambda r: r['start_tick'])
    if any(intersects(a, b) for a, b in zip(occupied, occupied[1:])):
        reject('放置或主动留白相互重叠。', 'OVERLAP')
    points = objects(project['intensity_points']); previous = -1
    if len(points) < 2:
        reject('强度线缺少端点。')
    for point in points:
        shape(point, 'tick level'); integer(point['tick'], 0, total)
        v = point['level']
        if point['tick'] <= previous or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1:
            reject('强度控制点无效。')
        previous = point['tick']
    if points[0]['tick'] != 0 or points[-1]['tick'] != total:
        reject('强度线必须覆盖固定时间轴。')
    for p in indexed(project['protections']).values():
        # P0/P2 manual memory has the original range-contained snapshot semantics.
        # Only the identified automatic memory owns P3's full base-note contract.
        protection_check(p, total, placements, sources, managed=managed_memory(project, p))
    import curve_memory
    managed = next((p for p in project['protections'] if p['id'] == curve_memory.managed_id(project)), None)
    if managed is not None and managed != curve_memory.expected_protection(project):
        reject('自动记忆范围、基础内容或输入指纹已过期。', 'PROTECTION_CONFLICT')
    memories = [p for p in project['protections'] if managed_memory(project, p) and p['status'] == 'CONTENT_READY']
    if memories:
        validate_protected_notes(memories, [n for p in project['placements'] for n in placed_notes(p)])
    records_check(project['records'], project['protections'], placements, total, materials, sources,
                  project_id=project['project_id'])
    accepted = project['accepted_candidate_id']
    if accepted is not None and not any(r['id'] == accepted and r['kind'] == 'accepted_candidate' for r in project['records']):
        reject('接受候选引用不存在。')
    shape(project['settings'], 'melody_only')
    if type(project['settings']['melody_only']) is not bool:
        reject('仅主旋律设置必须是bool。')


def new_project(grid_count=8):
    integer(grid_count, 1)
    total = grid_count * BAR
    return dict(schema=SCHEMA, spec_rev=SPEC_REV, contract_rev=CONTRACT_REV, project_id=uid(), ppq=PPQ, bpm=120,
        grid_count=grid_count, total_ticks=total, sources=[], materials=[], label_counters={}, placements=[],
        intensity_points=[dict(tick=0, level=.25), dict(tick=total, level=.25)], blank_regions=[], protections=[],
        records=[], accepted_candidate_id=None, settings=dict(melody_only=False))


def fingerprint(project):
    validate(project)
    return digest('emoblocks.project.v2.1', project)


def gaps(project):
    validate(project)
    occupied = [dict(start_tick=p['start_tick'], end_tick=p['start_tick'] + p['length_ticks']) for p in project['placements']]
    occupied += [dict(start_tick=b['start_tick'], end_tick=b['end_tick']) for b in project['blank_regions']]
    result = []; cursor = 0
    for r in sorted(occupied, key=lambda r: r['start_tick']):
        if r['start_tick'] > cursor:
            result.append(dict(start_tick=cursor, end_tick=r['start_tick']))
        cursor = r['end_tick']
    if cursor < project['total_ticks']:
        result.append(dict(start_tick=cursor, end_tick=project['total_ticks']))
    return result


def intensity_at(project, tick):
    validate(project)
    if isinstance(tick, bool) or not isinstance(tick, (int, float)) or not math.isfinite(tick):
        reject('强度查询时间无效。')
    return intensity_curve.evaluate([dict(time=p['tick'], level=p['level']) for p in project['intensity_points']], tick)


def invalidate_records(project, before):
    fixed = set()
    if before['contract_rev'] == 'curve-workflow-v2-r3-p7':
        from curve_application import binding_fingerprint
        if binding_fingerprint(project) == binding_fingerprint(before): return
        # A fixed bridge is an immutable accepted fact, not a proposal to rerun.
        old = indexed(before['protections'])
        for lock in project['protections']:
            if lock['kind']=='bridge' and old.get(lock['id'])==lock:
                fixed.add(lock['plan_id'])
    for record in project['records']:
        if record['kind']=='bridge_plan' and record['id'] in fixed: continue
        if record['kind']=='bridge_result' and record['payload']['plan_id'] in fixed: continue
        if record['status'] != 'INVALIDATED':
            record['payload']['audit_total_ticks'] = before['total_ticks']
            record['payload']['audit_context'] = copy.deepcopy(dict(placements=before['placements'], protections=before['protections']))
            record['status'] = 'INVALIDATED'


def register_manual_bridge(project, placement, old_version=0):
    plan_id = uid(); version = old_version + 1
    p = dict(id=uid(), kind='bridge', owner_id=placement['id'], placement_id=placement['id'], component_path=[],
        start_tick=placement['start_tick'], end_tick=placement['start_tick'] + placement['length_ticks'], status='CONTENT_READY',
        origin='manual', plan_id=plan_id, plan_version=version, input_fingerprint=digest('emoblocks.manual-bridge-input.v1', placement),
        notes=placed_notes(placement), structure_fingerprint=None, blank_mask=[])
    p['structure_fingerprint'] = structure_fingerprint(p)
    project['protections'].append(p)
    project['records'].append(dict(id=plan_id, kind='bridge_plan', version=version, status='READY', input_fingerprint=p['input_fingerprint'], dependencies=[],
        payload=dict(candidate_id=placement['id'], candidate_fingerprint=p['input_fingerprint'], automatic_decision='none', bridge_ids=[],
        manual_bridge_ids=[placement['id']], ranges=[], reasons=['manual placement'], joint_boundary_conditions=[])))


def manual_bridge_material(project, material):
    return material['kind']=='bridge' or (project['contract_rev']=='curve-workflow-v2-r3-p7'
        and (material.get('generation') or {}).get('method')=='bridge_emotion_once')


def _edit(project, action, recompute=None, **args):
    validate(project)
    result = copy.deepcopy(project)
    if action in ('add_source', 'add_material'):
        key = 'sources' if action == 'add_source' else 'materials'
        result[key].append(copy.deepcopy(args['source' if action == 'add_source' else 'material']))
    elif action == 'place':
        material = next((m for m in result['materials'] if m['id'] == args['material_id']), None)
        if material is None:
            reject('请先选择可用素材。')
        ident_ = args.get('placement_id') or uid()
        placement = dict(id=ident_, material_id=material['id'], base_snapshot=copy.deepcopy(material), start_tick=args['start_tick'],
            length_ticks=material['length_ticks'], emotion='calm', emotion_variant=None)
        result['placements'].append(placement)
    elif action in ('move', 'delete'):
        placement = next((p for p in result['placements'] if p['id'] == args['placement_id']), None)
        if placement is None:
            reject('选中的放置不存在。')
        if action == 'move':
            placement['start_tick'] = args['start_tick']
        else:
            result['placements'].remove(placement)
    elif action == 'resize':
        integer(args['grid_count'], 1); total = args['grid_count'] * BAR
        old_points = result['intensity_points']
        if total != result['total_ticks']:
            level = intensity_at(result, total)
            points = [p for p in old_points[:-1] if p['tick'] < total]
            if any(p['tick'] > total for p in old_points[1:-1]):
                reject('缩短会截断已编辑的强度控制点。', 'OUT_OF_BOUNDS')
            if total > result['total_ticks']:
                points.append(old_points[-1])
            result.update(grid_count=args['grid_count'], total_ticks=total, intensity_points=points + [dict(tick=total, level=level)])
    elif action == 'set_intensity':
        result['intensity_points'] = copy.deepcopy(args['points'])
    elif action == 'mark_blank':
        result['blank_regions'].append(dict(id=args.get('blank_id') or uid(), start_tick=args['start_tick'], end_tick=args['end_tick'], reason=args.get('reason', 'user intent')))
    elif action == 'delete_blank':
        blank = next((b for b in result['blank_regions'] if b['id'] == args['blank_id']), None)
        if blank is None:
            reject('留白不存在。')
        result['blank_regions'].remove(blank)
    elif action == 'set_emotion':
        if args['emotion'] not in EMOTIONS:
            reject('未知情绪。')
        ids = objects(args['placement_ids'])
        if not ids or len(ids) != len(set(ids)) or not set(ids) <= {p['id'] for p in result['placements']}:
            reject('请明确选择作品积木。')
        for p in result['placements']:
            if p['id'] in ids and p['emotion'] != args['emotion']:
                p.update(emotion=args['emotion'], emotion_variant=None)
    elif action == 'set_melody_only':
        result['settings']['melody_only'] = args['value']
    else:
        reject('不支持的工程编辑操作。')
    if result == project:
        validate(result)
        return result
    write_ranges = []
    if action == 'place':
        write_ranges.append(dict(start_tick=placement['start_tick'], end_tick=placement['start_tick'] + placement['length_ticks']))
    elif action in ('move', 'delete', 'set_emotion'):
        affected_ids = {args['placement_id']} if action in ('move', 'delete') else set(args['placement_ids'])
        for p in project['placements'] + result['placements']:
            if p['id'] in affected_ids:
                write_ranges.append(dict(start_tick=p['start_tick'], end_tick=p['start_tick'] + p['length_ticks'], placement_id=p['id']))
    elif action == 'mark_blank':
        write_ranges.append(dict(start_tick=args['start_tick'], end_tick=args['end_tick']))
    for r in write_ranges:
        integer(r['start_tick']); integer(r['end_tick'], r['start_tick'] + 1)
        for lock in project['protections']:
            if recompute is not None and managed_memory(project, lock):
                continue
            placement_id = r.get('placement_id')
            existing = next((p for p in project['placements'] if p['id'] == placement_id), None)
            own_manual_bridge = (placement_id is not None and existing is not None
                and manual_bridge_material(project, existing['base_snapshot'])
                and action in ('move', 'delete', 'set_emotion')
                and lock['kind'] == 'bridge' and lock['origin'] == 'manual'
                and lock['placement_id'] == placement_id)
            if any(intersects(r, domain) for domain in protection_ranges(lock)) and not own_manual_bridge:
                reject('该范围已受保护，请先通过新的计划更新保护。', 'PROTECTION_CONFLICT')
    invalidate_records(result, project)
    if action == 'place' and manual_bridge_material(result, placement['base_snapshot']):
        register_manual_bridge(result, placement)
    elif action in ('move', 'delete', 'set_emotion'):
        affected = {args['placement_id']} if action in ('move', 'delete') else set(args['placement_ids'])
        removed = [p for p in result['protections'] if p['placement_id'] in affected
                   and not (recompute is not None and managed_memory(project, p))]
        if any(p['kind'] != 'bridge' or p['origin'] != 'manual' for p in removed):
            reject('该编辑需要同步重算现有保护，当前数据阶段不能丢弃保护。', 'PROTECTION_RECOMPUTE_REQUIRED')
        result['protections'] = [p for p in result['protections'] if p not in removed]
        if action != 'delete':
            for p in result['placements']:
                if p['id'] in affected and manual_bridge_material(result, p['base_snapshot']):
                    register_manual_bridge(result, p, max((q['plan_version'] or 0 for q in removed if q['placement_id'] == p['id']), default=0))
    result['contract_rev'] = project['contract_rev'] if project['contract_rev'] == 'curve-workflow-v2-r3-p7' else CONTRACT_REV
    if recompute is not None:
        apply_recompute(project, result, recompute)
    validate(result)
    return result


def managed_memory(project, protection):
    return (protection['id'] == 'memory:' + project['project_id']
            and protection['owner_id'] == protection['id']
            and protection['kind'] == 'memory' and protection['origin'] == 'automatic')


def apply_recompute(before, edited, recompute):
    """A callback cannot edit geometry, library, fixed locks or arbitrary state."""
    import curve_memory
    output = recompute(copy.deepcopy(before), copy.deepcopy(edited))
    shape(output, 'automatic_memory emotion_variants')
    expected = curve_memory.expected_protection(edited)
    if output['automatic_memory'] != expected:
        reject('保护重算没有返回当前基础素材的正确记忆。', 'PROTECTION_CONFLICT')
    variants = output['emotion_variants']
    ids = {p['id'] for p in edited['placements']}
    if not isinstance(variants, dict) or set(variants) != ids:
        reject('情绪重算没有覆盖实际放置。', 'PROTECTION_CONFLICT')
    edited['protections'] = [p for p in edited['protections'] if not managed_memory(edited, p)]
    if expected is not None:
        edited['protections'].append(copy.deepcopy(expected))
    sources = source_index(edited['sources'])
    fixed = [p for p in edited['protections'] if not managed_memory(edited, p)]
    original_lock_ids = {p['id'] for p in before['protections']}
    original_notes = current_notes(before)
    for placement in edited['placements']:
        variant = variants[placement['id']]
        if variant is None and placement['emotion'] != 'calm':
            reject('情绪重算缺少该次基础素材的有效结果。', 'PROTECTION_CONFLICT')
        if variant is not None:
            material_check(variant, sources)
            if variant['length_ticks'] != placement['length_ticks']:
                reject('情绪重算不能改变素材长度。', 'PROTECTION_CONFLICT')
            generation = variant['generation']
            if (not isinstance(generation, dict) or generation.get('emotion') != placement['emotion']
                    or generation.get('base_notes') != placement['base_snapshot']['notes']
                    or generation.get('input_material_ids') != [placement['material_id']]):
                reject('情绪结果与当前情绪和基础快照不匹配。', 'PROTECTION_CONFLICT')
        placement['emotion_variant'] = copy.deepcopy(variant)
    actual_notes = current_notes(edited)
    for lock in fixed:
        if lock['id'] not in original_lock_ids:
            continue  # Explicitly replanned manual bridge is validated below.
        domains = protection_ranges(lock)
        def inside(notes):
            return [n for n in notes if any(intersects(r, dict(start_tick=n['start_tick'], end_tick=n['start_tick'] + n['duration_tick']))
                                            for r in domains)]
        if structural_notes(inside(original_notes)) != structural_notes(inside(actual_notes)):
            reject('重算不能改变已有固定保护的内容或休止。', 'PROTECTION_CONFLICT')
    locks = [p for p in edited['protections'] if p['status'] == 'CONTENT_READY'
             and (p['kind'] != 'memory' or managed_memory(edited, p))]
    if locks:
        validate_protected_notes(locks, actual_notes)


def edit(project, action, recompute=None, **args):
    allowed = {
        'add_source': ({'source'}, set()), 'add_material': ({'material'}, set()),
        'place': ({'material_id', 'start_tick'}, {'placement_id'}),
        'move': ({'placement_id', 'start_tick'}, set()), 'delete': ({'placement_id'}, set()),
        'resize': ({'grid_count'}, set()), 'set_intensity': ({'points'}, set()),
        'mark_blank': ({'start_tick', 'end_tick'}, {'blank_id', 'reason'}),
        'delete_blank': ({'blank_id'}, set()), 'set_emotion': ({'placement_ids', 'emotion'}, set()),
        'set_melody_only': ({'value'}, set()),
    }
    if action not in allowed:
        reject('不支持的工程编辑操作。')
    required, optional = allowed[action]
    if not required <= set(args) or not set(args) <= required | optional:
        reject('工程编辑参数缺失或不受支持。')
    try:
        return _edit(project, action, recompute=recompute, **args)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ProjectError('INVALID_PROJECT', '工程编辑参数无效。') from exc


def validate(project):
    context = _VALIDATION_CONTEXT.get() or _IDENTITY_CONTEXT.get()
    key = digest('emoblocks.validation-cache.v1',project) if context is not None else None
    if context is not None and key in context['validated_projects']: return
    try:
        _validate(project)
        if context is not None and len(context['validated_projects'])<128: context['validated_projects'].add(key)
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ProjectError('INVALID_PROJECT', '工程损坏或字段类型无效。') from exc
