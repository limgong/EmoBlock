"""P4 private base-completion snapshots and independent gates. No final pipeline.

Only prepare_completion calls the pure search module. Validators never trust
READY, claimed fingerprints, UI coordinates, or the algorithm's coverage claim.
"""
import copy
import math
from functools import wraps

import curve_project as m
import curve_memory as memory

REV = 'curve-workflow-v2-r3-p4'
ALGORITHM = 'curve-completion-v1'
BUDGET = dict(max_expansions=256, beam_width=8, material_limit=24, max_new_notes=256, max_candidates=2)
LIMITS = dict(max_expansions=4096, beam_width=32, material_limit=128, max_new_notes=2048, max_candidates=8)
WEIGHTS = dict(left_fit=.20, right_fit=.20, key_fit=.12, rhythm_fit=.08,
               motif_fit=.10, emotion_fit=.10, intensity_fit=.10, repeat_penalty=-.10)


def _guard(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (KeyError, TypeError, AttributeError, RecursionError, IndexError) as exc:
            raise m.ProjectError('INVALID_CANDIDATE', '补全数据字段缺失或结构无效。') from exc
    return guarded


def error(code, message, **details):
    return dict(code=code, message=message, details=details)


def _version(value, schema):
    if (value['schema'], value['spec_rev'], value['contract_rev']) != (schema, m.SPEC_REV, REV):
        m.reject('补全处理版本不匹配。', 'UNSUPPORTED_VERSION')


def _range(placement):
    return dict(start_tick=placement['start_tick'], end_tick=placement['start_tick'] + placement['length_ticks'])


def _has_bridge(material):
    return material['kind'] == 'bridge' or any(_has_bridge(c['snapshot']) for c in material['children'])


def gap_items(project):
    fingerprint = m.fingerprint(project)
    return [dict(id=m.digest('emoblocks.gap.v1', dict(input_fingerprint=fingerprint, range=r)), **r)
            for r in m.gaps(project)]


def _contexts(project, targets):
    result = []
    for gap in targets:
        lefts = [p for p in project['placements'] if _range(p)['end_tick'] <= gap['start_tick']]
        rights = [p for p in project['placements'] if p['start_tick'] >= gap['end_tick']]
        left = max(lefts, key=lambda p: (_range(p)['end_tick'], p['id'])) if lefts else None
        right = min(rights, key=lambda p: (p['start_tick'], p['id'])) if rights else None
        result.append(dict(gap_id=gap['id'], left=copy.deepcopy(left), right=copy.deepcopy(right),
                           left_notes=__import__('curve_application').context_notes(project,left), right_notes=__import__('curve_application').context_notes(project,right)))
    return result


def _summary(project):
    return dict(fingerprint=m.protection_summary(project['protections']),
                ranges=[dict(start_tick=a, end_tick=b) for a, b in memory.protected_ranges(project['protections'])])


def make_request(project, selected_gap_id=None, seed=31, budget=None, snapshot_id=None, request_id=None):
    m.validate(project); m.integer(seed, 0, 2**32 - 1)
    params = dict(BUDGET)
    if budget is not None:
        if not isinstance(budget, dict) or not set(budget) <= set(BUDGET):
            m.reject('未知补全搜索预算。', 'INVALID_PARAMETERS')
        params.update(budget)
    for key, value in params.items():
        m.integer(value, 1, LIMITS[key])
    gaps = gap_items(project)
    targets = gaps
    if selected_gap_id is not None:
        m.ident(selected_gap_id)
        targets = [g for g in gaps if g['id'] == selected_gap_id]
        if not targets:
            m.reject('选中的空缺已改变，请重新选择。', 'STALE_GAP')
    summary = _summary(project)
    if any(m.intersects(g, r) for g in targets for r in summary['ranges']):
        m.reject('目标空缺与已有保护或桥范围锁冲突，请先检查保护状态。', 'PROTECTION_CONFLICT')
    request_id = m.uid() if request_id is None else request_id
    snapshot_id = m.uid() if snapshot_id is None else snapshot_id
    m.ident(request_id); m.ident(snapshot_id)
    return dict(schema='emoblocks.completion-request.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
                input_contract_rev=project['contract_rev'], request_id=request_id, snapshot_id=snapshot_id,
                input_fingerprint=m.fingerprint(project), project=copy.deepcopy(project),
                scope='all' if selected_gap_id is None else 'selected', target_gaps=copy.deepcopy(targets),
                library_ids=sorted(v['id'] for v in project['materials'] if not _has_bridge(v)),
                contexts=_contexts(project, targets), protection_summary=summary,
                blank_regions=copy.deepcopy(project['blank_regions']), seed=seed,
                algorithm_version=ALGORITHM, budget=params)


@_guard
def validate_request(request):
    m.canonical(request)
    m.shape(request, 'schema spec_rev contract_rev input_contract_rev request_id snapshot_id input_fingerprint project scope target_gaps library_ids contexts protection_summary blank_regions seed algorithm_version budget')
    _version(request, 'emoblocks.completion-request.v1')
    if request['scope'] not in ('all', 'selected') or request['algorithm_version'] != ALGORITHM:
        m.reject('补全范围或算法版本无效。', 'INVALID_PARAMETERS')
    m.shape(request['budget'], 'max_expansions beam_width material_limit max_new_notes max_candidates')
    targets = request['target_gaps']
    selected = None
    if request['scope'] == 'selected':
        if not isinstance(targets, list) or len(targets) != 1:
            m.reject('请选择一个完整实际空缺。', 'STALE_GAP')
        selected = targets[0]['id']
    expected = make_request(request['project'], selected, request['seed'], request['budget'],
                            request['snapshot_id'], request['request_id'])
    if request != expected:
        m.reject('补全请求与实际输入快照、完整空缺或上下文不匹配。', 'STALE_SNAPSHOT')


def request_fingerprint(request):
    return m.digest('emoblocks.completion-request.v1', request)


def _warnings(values):
    for warning in m.objects(values):
        m.shape(warning, 'code message details'); m.ident(warning['code']); m.text(warning['message'])
        if not isinstance(warning['details'], dict):
            m.reject('补全错误或提示详情无效。', 'INVALID_CANDIDATE')
        m.canonical(warning)


def _score(score):
    m.shape(score, 'left_fit right_fit key_fit rhythm_fit motif_fit emotion_fit intensity_fit repeat_penalty total')
    for key, value in score.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            m.reject('补全评分必须是有限数值。', 'INVALID_CANDIDATE')
        if key != 'total' and not 0 <= value <= 1:
            m.reject('补全评分分量超出范围。', 'INVALID_CANDIDATE')
    if abs(score['total'] - sum(score[k] * w for k, w in WEIGHTS.items())) > 1e-9:
        m.reject('补全总评分与公开规则不一致。', 'INVALID_CANDIDATE')


def _material(request, material):
    sources = m.source_index(request['project']['sources'])
    m.material_check(material, sources)
    if _has_bridge(material) or not material['notes']:
        m.reject('补全不能使用bridge或无实际音符的独立素材。', 'NO_VALID_MATERIAL')
    library = m.indexed(request['project']['materials'])
    existing = library.get(material['id'])
    if existing is not None:
        if material != existing or material['id'] not in request['library_ids']:
            m.reject('补全不得更改输入素材快照。', 'INVALID_CANDIDATE')
        return
    provenance = material['provenance'].get('completion')
    m.shape(provenance, 'base_material_id base_snapshot target_ticks')
    base = library.get(provenance['base_material_id'])
    if base is None or base['id'] not in request['library_ids'] or provenance['base_snapshot'] != base:
        m.reject('新补全素材缺少可信基础快照。', 'INVALID_CANDIDATE')
    generation = material['generation']
    required = {'method', 'parameters', 'seed', 'rng_version', 'algorithm_version', 'input_fingerprint',
                'input_material_ids', 'base_notes', 'key_context', 'operations'}
    if not isinstance(generation, dict) or not required <= set(generation):
        m.reject('新补全素材缺少生成记录。', 'INVALID_CANDIDATE')
    if (generation['method'] != 'completion_exact' or generation['algorithm_version'] != ALGORITHM
            or generation['base_notes'] != base['notes'] or generation['input_material_ids'] != [base['id']]
            or provenance['target_ticks'] != material['length_ticks']
            or generation['parameters'].get('target_ticks') != material['length_ticks']):
        m.reject('补全生成方法、基础内容或目标长度不匹配。', 'INVALID_CANDIDATE')
    m.integer(provenance['target_ticks'], 1)
    m.integer(generation['parameters']['target_ticks'], 1)
    m.ident(generation['parameters'].get('rhythm_method'))
    if generation['input_fingerprint'] != m.digest('emoblocks.completion-input.v1', base):
        m.reject('新补全素材基础输入指纹不匹配。', 'INVALID_CANDIDATE')
    m.integer(generation['seed'], 0, 2**32-1); m.ident(generation['rng_version']); m.ident(generation['input_fingerprint'])
    if material['phrase_id'] is not None or material['kind'] not in ('block', 'phrase'):
        m.reject('新作曲必须有独立素材身份，不能冒充旧句子块。', 'INVALID_CANDIDATE')
    base_notes = m.indexed(base['notes'])
    operations = m.objects(generation['operations'])
    if len(operations) != len(material['notes']):
        m.reject('新作曲必须逐音符保留具体基础来源记录。', 'INVALID_CANDIDATE')
    for n, operation in zip(material['notes'], operations):
        if not isinstance(operation, dict) or operation.get('type') != 'motif_cell':
            m.reject('新作曲音符缺少实际动机来源记录。', 'INVALID_CANDIDATE')
        parent = base_notes.get(operation.get('source_note_id'))
        if (parent is None or n['lineage'] != list(dict.fromkeys(parent['lineage'] + [parent['id']]))
                or n['origin'] != parent['origin']
                or any(operation.get(k) != n[k] for k in ('pitch', 'start_tick', 'duration_tick'))):
            m.reject('新作曲音符缺少基础动机血缘。', 'INVALID_CANDIDATE')
        if n['slice'] is not None:
            if any(n[k] != parent[k] for k in ('pitch', 'start_tick', 'duration_tick', 'slice')):
                m.reject('变更音高或时值的新音符不能沿用旧切片。', 'INVALID_CANDIDATE')


def _selections(request, selections):
    targets = m.indexed(request['target_gaps'])
    occupied = {key: [] for key in targets}
    for selection in m.objects(selections):
        m.shape(selection, 'gap_id start_tick material emotion')
        gap = targets.get(selection['gap_id'])
        if gap is None:
            m.reject('补全写入非目标范围。', 'INVALID_CANDIDATE')
        m.integer(selection['start_tick']); _material(request, selection['material'])
        if selection['emotion'] not in m.EMOTIONS:
            m.reject('补全情绪无效。', 'INVALID_CANDIDATE')
        start, end = selection['start_tick'], selection['start_tick'] + selection['material']['length_ticks']
        if start < gap['start_tick'] or end > gap['end_tick']:
            m.reject('补全不得移动邻块或侵入目标之外。', 'INVALID_CANDIDATE')
        occupied[gap['id']].append((start, end))
    for gap in targets.values():
        cursor = gap['start_tick']
        for start, end in sorted(occupied[gap['id']]):
            if start != cursor:
                m.reject('目标未被实际素材完整、不重叠地覆盖。', 'INCOMPLETE_TARGET')
            cursor = end
        if cursor != gap['end_tick']:
            m.reject('目标仍有未覆盖时间，不能标记完成。', 'INCOMPLETE_TARGET')


def _variant_check(project, placement, variant, allow_calm_snapshot=False):
    """Validate persisted P3 evidence, never regenerate a historical melody."""
    if placement['emotion'] == 'calm' and not allow_calm_snapshot:
        if variant is not None:
            m.reject('平静放置应保留基础快照。', 'INVALID_CANDIDATE')
        return
    if variant is None:
        m.reject('新增放置缺少实际情绪快照。', 'INVALID_CANDIDATE')
    base = placement['base_snapshot']
    m.material_check(variant, m.source_index(project['sources']))
    generation = variant['generation']
    required = {'method', 'emotion', 'parameters', 'seed', 'rng_version', 'algorithm_version',
                'input_fingerprint', 'input_material_ids', 'base_notes', 'key_context', 'operations',
                'warnings', 'melody_changed', 'accompaniment_hints', 'protection'}
    if not isinstance(generation, dict) or not required <= set(generation):
        m.reject('保存的情绪结果缺少基础输入和保护证据。', 'INVALID_CANDIDATE')
    if (generation['method'] != 'emotion_variant' or generation['emotion'] != placement['emotion']
            or generation['base_notes'] != base['notes'] or generation['input_material_ids'] != [base['id']]
            or variant['length_ticks'] != base['length_ticks'] or variant['phrase_id'] is not None
            or variant['kind'] != ('phrase' if base['kind'] == 'combination' else base['kind'])
            or variant['children']):
        m.reject('保存的情绪结果与本次基础素材不匹配。', 'INVALID_CANDIDATE')
    if generation['algorithm_version'] != 'curve-emotion-rules-v1':
        m.reject('保存的情绪算法版本不受支持。', 'UNSUPPORTED_VERSION')
    params = generation['parameters']; m.shape(params, 'max_changes max_pitch_shift')
    m.integer(params['max_changes'], 1, 8); m.integer(params['max_pitch_shift'], 1, 4)
    if type(generation['seed']) is not int:
        m.reject('保存的情绪种子无效。', 'INVALID_CANDIDATE')
    m.ident(generation['rng_version'])
    domains = [dict(start_tick=a, end_tick=b) for a, b in memory.protected_ranges(project['protections'])]
    relevant = [r for r in domains if m.intersects(r, _range(placement))]
    protected = memory.base_notes(placement, relevant)
    prefix = placement['id'] + ':'
    protected = [dict(n, id=n['id'][len(prefix):]) for n in protected]
    protected.sort(key=lambda n: n['id'])
    ranges = _union(relevant)
    frozen = {n['id'] for n in protected}
    if generation['protection'] != dict(explicit_note_ids=sorted(frozen), frozen_note_ids=sorted(frozen), ranges=ranges):
        m.reject('保存的情绪保护摘要不匹配实际保护。', 'PROTECTION_CONFLICT')
    fingerprint = m.digest('emoblocks.emotion-input.v1', dict(base=base, emotion=placement['emotion'],
        intensity_points=project['intensity_points'], start_tick=placement['start_tick'],
        protected_notes=protected, protected_ranges=ranges, seed=generation['seed'], parameters=params,
        algorithm_version=generation['algorithm_version']))
    if generation['input_fingerprint'] != fingerprint or variant['id'] != m.digest('emoblocks.emotion-material.v1', fingerprint):
        m.reject('保存的情绪基础输入指纹不匹配。', 'INVALID_CANDIDATE')
    actual = m.indexed(variant['notes']); changed = []
    for original in base['notes']:
        original_id = original['id']
        changed_id = m.digest('emoblocks.emotion-note.v1', [variant['id'], original_id])
        note = actual.pop(original_id, None)
        if note is None:
            note = actual.pop(changed_id, None)
        if note is None:
            m.reject('情绪结果删除或替换了基础发声身份。', 'INVALID_CANDIDATE')
        different = any(note[k] != original[k] for k in ('pitch', 'start_tick', 'duration_tick'))
        if placement['emotion'] == 'calm' and different:
            m.reject('平静情绪快照不得改写基础旋律。', 'INVALID_CANDIDATE')
        if original_id in frozen:
            if m.structural_notes([note]) != m.structural_notes([original]):
                m.reject('保存的情绪结果改变完整保护音符。', 'PROTECTION_CONFLICT')
        elif (note['start_tick'] != original['start_tick'] or not 0 < note['duration_tick'] <= original['duration_tick']
                or abs(note['pitch'] - original['pitch']) > params['max_pitch_shift']
                or note['origin'] != original['origin']):
            m.reject('保存的情绪结果越过轻改范围或基础来源。', 'INVALID_CANDIDATE')
        if note['duration_tick'] != original['duration_tick'] and (
                placement['emotion'] not in ('suspense', 'crisis') or original['duration_tick'] % 10
                or (original['duration_tick'] - note['duration_tick']) % 10
                or note['duration_tick'] * 4 < original['duration_tick'] * 3):
            m.reject('保存的时值轻改不符合已记录的规则单位与幅度。', 'INVALID_CANDIDATE')
        if different:
            if (note['id'] != changed_id or note['slice'] is not None
                    or note['lineage'] != list(dict.fromkeys(original['lineage'] + [original_id]))):
                m.reject('改变的音符缺少本次基础血缘。', 'INVALID_CANDIDATE')
            changed.append(dict(operation='local-emotion-melody', emotion=placement['emotion'], input_note_id=original_id,
                from_pitch=original['pitch'], to_pitch=note['pitch'], start_tick=original['start_tick'],
                original_duration_tick=original['duration_tick'], output_duration_tick=note['duration_tick'],
                shortened_by_tick=original['duration_tick']-note['duration_tick'], rule_unit_ticks=10))
        elif any(note[k] != original[k] for k in ('id', 'origin', 'lineage', 'slice')):
            m.reject('未改写音符的来源与身份必须保持。', 'INVALID_CANDIDATE')
    claimed_changes = [v for v in m.objects(generation['operations']) if isinstance(v, dict) and v.get('operation') == 'local-emotion-melody']
    if (actual or len(changed) > params['max_changes'] or type(generation['melody_changed']) is not bool
            or generation['melody_changed'] != bool(changed) or sorted(changed, key=m.canonical) != sorted(claimed_changes, key=m.canonical)):
        m.reject('实际情绪音符与轻改记录不一致。', 'INVALID_CANDIDATE')
    _warnings(generation['warnings'])
    if not changed and not generation['warnings']:
        m.reject('未改变旋律时必须保留真实限制提示。', 'INVALID_CANDIDATE')
    if not isinstance(generation['accompaniment_hints'], dict) or generation['accompaniment_hints'].get('status') != 'suggested-not-rendered':
        m.reject('基础情绪编配只能是未渲染建议。', 'INVALID_CANDIDATE')


def _private_project(request, selections, stored_variants=None):
    _selections(request, selections)
    before = request['project']; project = copy.deepcopy(before)
    project['contract_rev'] = before['contract_rev'] if before['contract_rev'] == 'curve-workflow-v2-r3-p7' else REV
    library = m.indexed(project['materials'])
    new = []
    for index, selection in enumerate(selections):
        material = copy.deepcopy(selection['material'])
        if material['id'] not in library:
            project['materials'].append(material); library[material['id']] = material
        elif library[material['id']] != material:
            m.reject('同一素材身份不能对应不同快照。', 'INVALID_CANDIDATE')
        identity = m.digest('emoblocks.completion-placement.v1', dict(request=request_fingerprint(request),
                         index=index, selection=selection))
        if identity in m.indexed(before['placements']):
            m.reject('补全放置身份冲突。', 'INVALID_CANDIDATE')
        placement = dict(id=identity, material_id=material['id'], base_snapshot=material,
                         start_tick=selection['start_tick'], length_ticks=material['length_ticks'],
                         emotion=selection['emotion'], emotion_variant=None)
        project['placements'].append(placement); new.append(identity)
    m.invalidate_records(project, before)
    __import__('curve_application').capture_private_music(before,project,new)
    expected_memory = memory.expected_protection(project)
    if stored_variants is None:
        output = memory.recompute(copy.deepcopy(before), copy.deepcopy(project))
        m.shape(output, 'automatic_memory emotion_variants')
        if output['automatic_memory'] != expected_memory or set(output['emotion_variants']) != {p['id'] for p in project['placements']}:
            m.reject('正式记忆重算结果不完整或不匹配。', 'PROTECTION_CONFLICT')
        variants = output['emotion_variants']
    else:
        if set(stored_variants) != set(new):
            m.reject('保存的新增情绪快照与实际放置不匹配。', 'INVALID_CANDIDATE')
        variants = stored_variants
    project['protections'] = [p for p in project['protections'] if not m.managed_memory(project, p)]
    if expected_memory is not None:
        project['protections'].append(copy.deepcopy(expected_memory))
    for p in project['placements']:
        if p['id'] in new:
            p['emotion_variant'] = copy.deepcopy(variants[p['id']])
            _variant_check(project, p, p['emotion_variant'])
    old_memory = next((p for p in before['protections'] if m.managed_memory(before, p)), None)
    if old_memory:
        old = dict(old_memory); current = dict(expected_memory or {})
        old.pop('input_fingerprint', None); current.pop('input_fingerprint', None)
        if old != current:
            m.reject('补全不能移动或放宽已有记忆保护。', 'PROTECTION_CONFLICT')
    # Preserve fixed locks AND their actual music/rest; not just lock metadata.
    original_notes = m.current_notes(before)
    actual_notes = m.current_notes(project)
    for lock in before['protections']:
        ranges = m.protection_ranges(lock)
        def inside(notes):
            return [n for n in notes if any(m.intersects(r, dict(start_tick=n['start_tick'],
                         end_tick=n['start_tick'] + n['duration_tick'])) for r in ranges)]
        if m.structural_notes(inside(original_notes)) != m.structural_notes(inside(actual_notes)):
            m.reject('补全改变既有保护的音乐或休止。', 'PROTECTION_CONFLICT')
    m.validate(project)
    # P3 validates managed memories; independently validate all READY fixed locks.
    for lock in project['protections']:
        if lock['status'] == 'CONTENT_READY' and not (lock['kind'] == 'memory' and not m.managed_memory(project, lock)):
            m.validate_protected_notes([lock], actual_notes)
    return project, new


def music_projection(project):
    """Identity-free sound, tying only one continuous sliced emission occurrence."""
    notes = []
    for p in project['placements']:
        for note in m.placed_notes(p):
            n = copy.deepcopy(note)
            if n['slice'] is not None:
                n['slice']['parent_emission_id'] = p['id'] + ':' + n['slice']['parent_emission_id']
            notes.append(n)
    notes.sort(key=lambda n: (n['start_tick'], n['pitch'], n['duration_tick'], n['id']))
    joined = []
    for note in notes:
        prior = joined[-1] if joined else None
        a, b = (prior or {}).get('slice'), note.get('slice')
        if (prior and a and b and prior['pitch'] == note['pitch'] and prior['origin'] == note['origin']
                and a['parent_emission_id'] == b['parent_emission_id']
                and a['parent_duration_tick'] == b['parent_duration_tick']
                and a['offset_tick'] + prior['duration_tick'] == b['offset_tick']
                and prior['start_tick'] + prior['duration_tick'] == note['start_tick']):
            prior['duration_tick'] += note['duration_tick']
        else:
            joined.append(copy.deepcopy(note))
    return dict(total_ticks=project['total_ticks'], notes=sorted(
        [[n['pitch'], n['start_tick'], n['duration_tick']] for n in joined], key=lambda row: (row[1], row[0], row[2])))


def _musical_differences(candidates):
    result = []
    for i, a in enumerate(candidates):
        for b in candidates[i+1:]:
            x = music_projection(a['project'])['notes']; y = music_projection(b['project'])['notes']
            if x == y:
                continue
            types = []
            if [n[0] for n in x] != [n[0] for n in y]:
                types.append('pitch')
            if [n[1:] for n in x] != [n[1:] for n in y]:
                types.append('rhythm')
            ranges = []
            # Include multiplicity: repeated pitches are not silently discarded.
            from collections import Counter
            delta = (Counter(map(tuple, x)) - Counter(map(tuple, y))) + (Counter(map(tuple, y)) - Counter(map(tuple, x)))
            for pitch, start, duration in sorted(delta):
                ranges.append(dict(start_tick=start, end_tick=start+duration))
            result.append(dict(left_id=a['id'], right_id=b['id'], types=types or ['arrangement'], ranges=_union(ranges)))
    return result


def _union(ranges):
    result = []
    for r in sorted(ranges, key=lambda r: (r['start_tick'], r['end_tick'])):
        r = {k: r[k] for k in ('start_tick', 'end_tick')}
        if result and r['start_tick'] <= result[-1]['end_tick']:
            result[-1]['end_tick'] = max(result[-1]['end_tick'], r['end_tick'])
        else:
            result.append(r)
    return result


def _candidate(request, proposal, stored_variants=None):
    m.shape(proposal, 'id placements score reasons'); m.ident(proposal['id'])
    _score(proposal['score']); _warnings(proposal['reasons'])
    project, added = _private_project(request, proposal['placements'], stored_variants)
    new_ids = set(added)
    notes = m.current_notes(project)
    resolutions = []
    for gap in request['target_gaps']:
        ids = [n['id'] for p in project['placements'] if p['id'] in new_ids for n in m.placed_notes(p)
               if m.intersects(gap, dict(start_tick=n['start_tick'], end_tick=n['start_tick']+n['duration_tick']))]
        if not ids:
            m.reject('每个目标必须有实际有效音符支撑。', 'INCOMPLETE_TARGET')
        resolutions.append(dict(**gap, complete=True, note_ids=ids))
        resolutions[-1]['gap_id'] = resolutions[-1].pop('id')
    fingerprint = m.fingerprint(project)
    old_lib = {v['id'] for v in request['project']['materials']}
    candidate = dict(schema='emoblocks.completed-candidate.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        id=m.digest('emoblocks.completed-candidate.v1', [request_fingerprint(request), fingerprint]),
        snapshot_id=request['snapshot_id'], input_fingerprint=request['input_fingerprint'], request_fingerprint=request_fingerprint(request),
        project=project, added_placement_ids=added, staged_materials=[copy.deepcopy(v) for v in project['materials'] if v['id'] not in old_lib],
        notes=notes, target_resolution=resolutions, remaining_gaps=gap_items(project), base_write_ranges=_union(request['target_gaps']),
        emotion_arrangement=[dict(placement_id=p['id'], emotion=p['emotion']) for p in project['placements'] if p['id'] in new_ids],
        memory_info=memory.memory_info(project), protection_summary=m.protection_summary(project['protections']),
        score=copy.deepcopy(proposal['score']), reasons=copy.deepcopy(proposal['reasons']),
        provenance=dict(placements=[dict(gap_id=v['gap_id'], start_tick=v['start_tick'], material_id=v['material']['id'],
                         provenance=copy.deepcopy(v['material']['provenance']), generation=copy.deepcopy(v['material']['generation']))
                    for v in proposal['placements']]),
        content_fingerprint=fingerprint, music_fingerprint=m.digest('emoblocks.completion-music.v1', music_projection(project)),
        capabilities=dict(score_scope='BASE_COMPLETION', target_complete=True, can_audition=False, can_apply=False, can_export_final=False))
    return candidate


@_guard
def validate_candidate(request, candidate):
    validate_request(request)
    m.shape(candidate, 'schema spec_rev contract_rev id snapshot_id input_fingerprint request_fingerprint project added_placement_ids staged_materials notes target_resolution remaining_gaps base_write_ranges emotion_arrangement memory_info protection_summary score reasons provenance content_fingerprint music_fingerprint capabilities')
    _version(candidate, 'emoblocks.completed-candidate.v1')
    project = candidate['project']; m.validate(project)
    before = request['project']
    # Reconstruct all independent inputs from the actual private arrangement;
    # no claimed derived fields are used as the source of truth.
    if project['placements'][:len(before['placements'])] != before['placements']:
        m.reject('补全改变空缺之外的基础快照、情绪或音乐。', 'INVALID_CANDIDATE')
    additions = project['placements'][len(before['placements']):]
    selections = []
    for p in additions:
        gap = next((g for g in request['target_gaps'] if g['start_tick'] <= p['start_tick']
                    and p['start_tick'] + p['length_ticks'] <= g['end_tick']), None)
        if gap is None:
            m.reject('候选放置不在原目标范围。', 'INVALID_CANDIDATE')
        selections.append(dict(gap_id=gap['id'], start_tick=p['start_tick'], material=p['base_snapshot'], emotion=p['emotion']))
    m.shape(candidate['provenance'], 'placements')
    stored_variants = {p['id']:copy.deepcopy(p['emotion_variant']) for p in additions}
    expected = _candidate(request, dict(id='independent-validation', placements=selections, score=candidate['score'], reasons=candidate['reasons']), stored_variants)
    if candidate != expected:
        m.reject('候选与实际基础排布、保护、音乐或派生摘要不一致。', 'INVALID_CANDIDATE')


def _search_check(request, search):
    m.shape(search, 'expansions generated_notes termination raw_termination rejections')
    for key, limit in [('expansions', 'max_expansions'), ('generated_notes', 'max_new_notes')]:
        if search[key] is None and search['termination'] in ('ERROR', 'CANCELLED'):
            continue
        m.integer(search[key], 0, request['budget'][limit])
    m.ident(search['termination']); m.ident(search['raw_termination']); _warnings(search['rejections'])
    raw_states = {'RAW_POOL_LIMIT', 'RAW_POOL_EXHAUSTED', 'EXHAUSTED', 'BUDGET_EXHAUSTED',
                  'CANCELLED', 'NO_TARGETS', 'PROTECTION_CONFLICT', 'NO_VALID_MATERIAL', 'ERROR', 'UNKNOWN'}
    if search['raw_termination'] not in raw_states or search['termination'] not in raw_states | {'ENOUGH_CANDIDATES'}:
        m.reject('补全搜索终止原因不受支持。', 'INVALID_CANDIDATE')


def outcome(request, status, candidates=None, search=None, failure=None, shortage=None):
    candidates = [] if candidates is None else candidates
    if search is None:
        search = dict(expansions=None, generated_notes=None, termination='ERROR', raw_termination='UNKNOWN', rejections=[])
    return dict(schema='emoblocks.completion-outcome.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
                snapshot_id=request['snapshot_id'], input_fingerprint=request['input_fingerprint'], request_fingerprint=request_fingerprint(request),
                status=status, candidates=copy.deepcopy(candidates), differences=_musical_differences(candidates),
                shortage_reasons=[] if shortage is None else shortage,
                unresolved_targets=[] if candidates or not request['target_gaps'] else copy.deepcopy(request['target_gaps']),
                search=copy.deepcopy(search), error=copy.deepcopy(failure))


@_guard
def validate_outcome(request, value):
    validate_request(request)
    m.shape(value, 'schema spec_rev contract_rev snapshot_id input_fingerprint request_fingerprint status candidates differences shortage_reasons unresolved_targets search error')
    _version(value, 'emoblocks.completion-outcome.v1')
    if value['snapshot_id'] != request['snapshot_id'] or value['input_fingerprint'] != request['input_fingerprint'] or value['request_fingerprint'] != request_fingerprint(request):
        m.reject('候选结果属于其他输入或请求。', 'STALE_SNAPSHOT')
    candidates = value['candidates']; m.indexed(candidates)
    if len(candidates) > request['budget']['max_candidates']:
        m.reject('候选数量超过请求上限。', 'INVALID_CANDIDATE')
    for candidate in candidates:
        validate_candidate(request, candidate)
    music = [c['music_fingerprint'] for c in candidates]
    if len(set(music)) != len(music):
        m.reject('不能用同音乐不同身份伪造第二套候选。', 'INVALID_CANDIDATE')
    if candidates != sorted(candidates, key=lambda c: (-c['score']['total'], c['music_fingerprint'])):
        m.reject('候选排序不符合确定性规则。', 'INVALID_CANDIDATE')
    status = value['status']
    expected = ('NOT_NEEDED' if not request['target_gaps'] else
                'SUCCEEDED' if len(candidates) >= 2 else 'INSUFFICIENT' if candidates else 'FAILED')
    if status != expected and not (status == 'CANCELLED' and not candidates):
        m.reject('基础候选状态与实际完成情况不一致。', 'INVALID_CANDIDATE')
    if value['differences'] != _musical_differences(candidates) or value['unresolved_targets'] != ([] if candidates or not request['target_gaps'] else request['target_gaps']):
        m.reject('实际差异或未解决目标不一致。', 'INVALID_CANDIDATE')
    _warnings(value['shortage_reasons']); _search_check(request, value['search'])
    if status == 'INSUFFICIENT' and not value['shortage_reasons']:
        m.reject('候选不足必须说明真实原因。', 'INVALID_CANDIDATE')
    if (status == 'SUCCEEDED') != (value['search']['termination'] == 'ENOUGH_CANDIDATES'):
        m.reject('不能按原始提案数或无效候选宣称搜索完成。', 'INVALID_CANDIDATE')
    if status == 'CANCELLED' and value['search']['termination'] != 'CANCELLED':
        m.reject('取消结果必须记录实际取消状态。', 'INVALID_CANDIDATE')
    if status in ('FAILED', 'CANCELLED'):
        _warnings([value['error']])
    elif value['error'] is not None:
        m.reject('成功或无需补全结果不能声称失败。', 'INVALID_CANDIDATE')
    if status == 'NOT_NEEDED' and (value['search'] != dict(expansions=0, generated_notes=0, termination='NO_TARGETS', raw_termination='NO_TARGETS', rejections=[]) or candidates):
        m.reject('没有目标时不得创建随机候选或虚假搜索。', 'INVALID_CANDIDATE')


@_guard
def prepare_completion(request, should_cancel=None, on_progress=None):
    validate_request(request)
    should_cancel = should_cancel or (lambda: False)
    if not request['target_gaps']:
        return outcome(request, 'NOT_NEEDED', search=dict(expansions=0, generated_notes=0, termination='NO_TARGETS', raw_termination='NO_TARGETS', rejections=[]))
    sequence = 0
    def progress(event):
        nonlocal sequence
        sequence += 1
        if on_progress is not None:
            on_progress(dict(event_seq=sequence, phase='BASE_COMPLETION', message=str(event.get('message', '计算基础候选')),
                             expansions=event.get('expansions')))
    def cancelled(search=None):
        search = dict(search or dict(expansions=None, generated_notes=None, raw_termination='UNKNOWN', rejections=[]), termination='CANCELLED')
        return outcome(request, 'CANCELLED', search=search, failure=error('CANCELLED', '基础候选计算已取消，当前编辑保持不变。'))
    if should_cancel():
        return cancelled()
    import curve_completion
    raw = curve_completion.propose(copy.deepcopy(request), should_cancel=should_cancel, on_progress=progress)
    m.shape(raw, 'proposals search error')
    search = copy.deepcopy(raw['search']); search.setdefault('raw_termination', search['termination'])
    _search_check(request, search)
    if raw['error'] is not None:
        _warnings([raw['error']])
    proposals = m.objects(raw['proposals'])
    limit = min(32, max(request['budget']['beam_width'], 4*request['budget']['max_candidates']))
    if len(proposals) > limit or sum(len(v['material']['notes']) for p in proposals for v in p['placements']) > 65536:
        m.reject('原始候选池超过有限搜索边界。', 'INVALID_CANDIDATE')
    if should_cancel() or search['termination'] == 'CANCELLED':
        return cancelled(search)
    accepted = {}; rejects = []
    for index, proposal in enumerate(proposals):
        if should_cancel():
            return cancelled(search)
        progress(dict(message='校验实际排布、情绪与记忆保护 · ' + str(index+1), expansions=search['expansions']))
        try:
            candidate = _candidate(request, proposal)
            key = candidate['music_fingerprint']
            if key in accepted:
                rejects.append(error('DUPLICATE_MUSIC', '实际情绪处理后的音乐重复，已去重。'))
                if candidate['score']['total'] > accepted[key]['score']['total']:
                    accepted[key] = candidate
            else:
                accepted[key] = candidate
        except m.ProjectError as exc:
            rejects.append(error(exc.code, str(exc)))
    if should_cancel():
        return cancelled(search)
    candidates = sorted(accepted.values(), key=lambda c: (-c['score']['total'], c['music_fingerprint']))[:request['budget']['max_candidates']]
    search['rejections'].extend(rejects)
    shortage = []
    if len(candidates) >= 2:
        status = 'SUCCEEDED'; search['termination'] = 'ENOUGH_CANDIDATES'
    elif candidates:
        status = 'INSUFFICIENT'
        shortage = [error('INSUFFICIENT_CANDIDATES', '有限备选池经保护校验和实际音乐去重后只有一套；可增加素材或调整搜索预算。',
                          raw_count=len(proposals), valid_unique=len(accepted), returned=len(candidates), max_candidates=request['budget']['max_candidates'], raw_termination=search['raw_termination'])]
    else:
        status = 'FAILED'
    failure = None if candidates else raw['error'] or (rejects[0] if rejects else error('NO_SOLUTION', '有限搜索未得到完整有效候选；请增加有音符素材或检查保护与目标。'))
    value = outcome(request, status, candidates, search, failure, shortage)
    validate_outcome(request, value)
    return value
