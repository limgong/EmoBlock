"""P5 bounded position proposals and locked, whole-phrase bridge music.

Pure data only. Publication/authentication of a lock and all readiness decisions
belong to curve_bridges/Controller. No rendering, project edits or P6 calls.
"""
import copy
import math
import bisect
import collections

import curve_emotion as emotion
import curve_melody as melody
import curve_project as m
import intensity_curve

CONTRACT_REV = 'curve-workflow-v2-r3-p5'
ALGORITHM_VERSION = 'curve-bridge-v1'
GLOBAL_ALGORITHM = 'curve-bridge-global-v2'
REQUEST_FIELDS = ('schema spec_rev contract_rev request_id snapshot_id session_id edit_revision '
    'input_contract_rev input_fingerprint input_project input_kind completion_ref base_project '
    'base_fingerprint resolved_ranges remaining_gaps base_notes protection_summary blank_regions '
    'plan_id plan_version seed algorithm_version parameters')
PLAN_FIELDS = ('schema spec_rev contract_rev id version request_id snapshot_id input_fingerprint '
    'base_fingerprint candidate_id request_fingerprint decision windows inherited_bridge_ids '
    'protection_refs reasons assessments joint_boundary_conditions search range_lock_fingerprint plan_fingerprint')


def _fail(code, message):
    raise m.ProjectError(code, message)


def _range(a, b):
    return dict(start_tick=a, end_tick=b)


def _support(note):
    return _range(note['start_tick'], note['start_tick'] + note['duration_tick'])


def _ordered(notes):
    return sorted(copy.deepcopy(notes), key=lambda n: (n['start_tick'], n['pitch'], n['duration_tick'], n['id']))


def _warning(code, message):
    return dict(code=code, message=message, details={})


def _check(cancel):
    if cancel is not None and cancel():
        _fail('CANCELLED', '桥阶段已协作取消。')


def _progress(callback, seq, phase, message):
    if callback is not None:
        callback(dict(event_seq=seq, phase=phase, message=message))


def _request_hash(request):
    return m.digest('emoblocks.bridge-request.v1', request)


def _forbidden(project):
    # Every layer is independent. Full supports are a ban even for historical
    # notes crossing the nominal memory range.
    ranges = [r for p in project['protections'] for r in m.protection_ranges(p)]
    ranges += [_support(n) for p in project['protections'] for n in p['notes']]
    return sorted({_pair(r) for r in ranges})


def _pair(region):
    return region['start_tick'], region['end_tick']


def _resolved(project):
    cursor = 0; result = []
    for gap in m.gaps(project):
        if cursor < gap['start_tick']:
            result.append(_range(cursor, gap['start_tick']))
        cursor = gap['end_tick']
    if cursor < project['total_ticks']:
        result.append(_range(cursor, project['total_ticks']))
    return result


def _writable_regions(request):
    regions = copy.deepcopy(request['resolved_ranges'])
    for a, b in _forbidden(request['base_project']):
        kept = []
        for r in regions:
            x, y = _pair(r)
            if b <= x or y <= a:
                kept.append(r)
            else:
                if x < a:
                    kept.append(_range(x, a))
                if b < y:
                    kept.append(_range(b, y))
        regions = kept
    return sorted(regions, key=_pair)


def _validate_request(request):
    m.canonical(request); m.shape(request, REQUEST_FIELDS)
    if ((request['schema'], request['spec_rev'], request['contract_rev']) != (
            'emoblocks.bridge-request.v1', m.SPEC_REV, CONTRACT_REV)
            or request['algorithm_version'] not in (ALGORITHM_VERSION, GLOBAL_ALGORITHM)):
        _fail('PLAN_VERSION_MISMATCH', '桥请求处理版本不匹配。')
    for key in ('request_id', 'snapshot_id', 'session_id', 'plan_id'):
        m.ident(request[key])
    m.integer(request['edit_revision']); m.integer(request['plan_version'], 1)
    m.integer(request['seed'], 0, 2**32-1)
    p = request['parameters']
    m.shape(p, 'policy max_windows max_window_blocks max_window_tests max_notes')
    if p['policy'] not in ('auto', 'none'):
        _fail('INVALID_PARAMETERS', '未知桥位置策略。')
    for key, limit in [('max_windows', 8), ('max_window_blocks', 32), ('max_window_tests', 2048), ('max_notes', 4096)]:
        m.integer(p[key], 1, limit)
    m.validate(request['input_project']); m.validate(request['base_project'])
    if (request['input_contract_rev'] != request['input_project']['contract_rev']
            or request['input_fingerprint'] != m.fingerprint(request['input_project'])
            or request['base_fingerprint'] != m.fingerprint(request['base_project'])):
        _fail('STALE_SNAPSHOT', '桥请求基础快照或输入指纹不匹配。')
    if request['input_kind'] == 'current_complete':
        if request['completion_ref'] is not None or request['base_project'] != request['input_project'] or m.gaps(request['base_project']):
            _fail('INVALID_CANDIDATE', '当前基础尚未实际完整，不能跳过补全。')
    elif request['input_kind'] == 'completed_candidate':
        import curve_candidates
        ref = request['completion_ref']
        m.shape(ref, 'attempt_id candidate_id request candidate')
        m.ident(ref['attempt_id']); m.ident(ref['candidate_id'])
        curve_candidates.validate_request(ref['request'])
        curve_candidates.validate_candidate(ref['request'], ref['candidate'])
        if (ref['attempt_id'] != ref['request']['request_id'] or ref['candidate_id'] != ref['candidate']['id']
                or ref['request']['project'] != request['input_project'] or ref['candidate']['project'] != request['base_project']):
            _fail('INVALID_CANDIDATE', '基础补全候选引用不闭合。')
    else:
        _fail('INVALID_CANDIDATE', '未知桥基础输入种类。')
    base = request['base_project']
    notes = _ordered(m.current_notes(base))
    if request['base_notes'] != notes or request['blank_regions'] != base['blank_regions']:
        _fail('INVALID_CANDIDATE', '请求未保留真实基础发声或主动留白。')
    actual_gaps = m.gaps(base)
    m.objects(request['remaining_gaps'])
    expected_gaps = [dict(id=m.digest('emoblocks.gap.v1',dict(input_fingerprint=request['base_fingerprint'],range=r)), **r) for r in actual_gaps]
    if request['remaining_gaps'] != expected_gaps:
        _fail('INVALID_CANDIDATE', '基础剩余空缺不准确。')
    if request['resolved_ranges'] != _resolved(base):
        _fail('INVALID_CANDIDATE', '基础已解决范围不是实际空缺的补集。')
    expected_ranges = sorted({_pair(r) for p in base['protections'] for r in m.protection_ranges(p)})
    if request['protection_summary'] != dict(fingerprint=m.protection_summary(base['protections']),
            ranges=[_range(a, b) for a, b in expected_ranges]):
        _fail('PROTECTION_CONFLICT', '基础保护摘要不匹配。')
    owners = [p['owner_id'] for p in base['protections'] if p['kind'] == 'bridge']
    if len(owners) != len(set(owners)):
        _fail('PROTECTION_CONFLICT', '基础桥锁的owner身份重复。')


def _mask(project, region):
    return [_range(max(b['start_tick'], region['start_tick']), min(b['end_tick'], region['end_tick']))
            for b in sorted(project['blank_regions'], key=lambda b: b['start_tick']) if m.intersects(b, region)]


def _segments(project, region):
    return [dict(start_tick=max(p['start_tick'], region['start_tick']),
        end_tick=min(p['start_tick'] + p['length_ticks'], region['end_tick']), emotion=p['emotion'])
        for p in sorted(project['placements'], key=lambda p: (p['start_tick'], p['id']))
        if m.intersects(_range(p['start_tick'], p['start_tick']+p['length_ticks']), region)]


def _legal(request, region):
    a, b = _pair(region); base = request['base_project']
    if not 0 <= a < b <= base['total_ticks']:
        return False
    if not any(r['start_tick'] <= a < b <= r['end_tick'] for r in request['resolved_ranges']):
        return False
    if any(a < y and x < b for x, y in _forbidden(base)):
        return False
    for note in request['base_notes']:
        r = _support(note)
        if m.intersects(r, region) and not a <= r['start_tick'] < r['end_tick'] <= b:
            return False
    return any(m.intersects(_support(n), region) for n in request['base_notes'])


def _contexts(request, regions):
    base = request['base_project']; places = sorted(base['placements'], key=lambda p: (p['start_tick'], p['id']))
    unaffected = [p for p in places if not any(m.intersects(_range(p['start_tick'], p['start_tick']+p['length_ticks']), r) for r in regions)]
    windows = []
    for r in regions:
        lefts = [p for p in unaffected if p['start_tick']+p['length_ticks'] <= r['start_tick']]
        rights = [p for p in unaffected if p['start_tick'] >= r['end_tick']]
        left = lefts[-1] if lefts else None; right = rights[0] if rights else None
        inner = [n for n in request['base_notes'] if m.intersects(_support(n), r)]
        motif = inner[:8] + (__import__('curve_application').context_notes(base,left)[-2:] if left else []) + (__import__('curve_application').context_notes(base,right)[:2] if right else [])
        # Capture key from the actual effective snapshot, including a non-C key.
        touched = [p for p in places if m.intersects(_range(p['start_tick'], p['start_tick']+p['length_ticks']), r)]
        first = touched[0]['emotion_variant'] or touched[0]['base_snapshot']
        key = melody._key(first, inner)
        windows.append(dict(id=m.digest('emoblocks.bridge-window.v1', dict(request_fingerprint=_request_hash(request), range=r)),
            **r, placement_ids=[p['id'] for p in touched], context=dict(
                left=dict(placement_id=left['id'], notes=__import__('curve_application').context_notes(base,left)) if left else None,
                right=dict(placement_id=right['id'], notes=__import__('curve_application').context_notes(base,right)) if right else None,
                motif_note_ids=list(dict.fromkeys(n['id'] for n in motif)), key_context=key),
            emotion_segments=_segments(base, r), blank_mask=_mask(base, r)))
    return windows


def _assess(request, region):
    notes = [n for n in request['base_notes'] if m.intersects(_support(n), region)]
    leaps = [abs(a['pitch']-b['pitch']) for a, b in zip(notes, notes[1:])]
    roughness = sum(max(0, leap-7) / 17 for leap in leaps) / max(1, len(leaps))
    durations = [n['duration_tick'] for n in notes]
    rhythm = sum(abs(math.log2(max(a, b)/min(a, b))) for a, b in zip(durations, durations[1:])) / max(1, len(durations)-1)
    all_notes = request['base_notes']
    before = [n for n in all_notes if _support(n)['end_tick'] <= region['start_tick']]
    after = [n for n in all_notes if n['start_tick'] >= region['end_tick']]
    edges = ([abs(before[-1]['pitch']-notes[0]['pitch'])] if before else []) + ([abs(notes[-1]['pitch']-after[0]['pitch'])] if after else [])
    edge = sum(max(0, leap-7)/17 for leap in edges) / max(1, len(edges))
    places = [p for p in request['base_project']['placements'] if m.intersects(_range(p['start_tick'], p['start_tick']+p['length_ticks']), region)]
    keys = [melody._key(p['emotion_variant'] or p['base_snapshot'], m.placed_notes(p)) for p in places]
    key_changes = sum(a['tonic'] != b['tonic'] or a['mode'] != b['mode'] for a, b in zip(keys, keys[1:])) / max(1, len(keys)-1)
    points = [dict(time=p['tick'], level=p['level']) for p in request['base_project']['intensity_points']]
    levels = [intensity_curve.evaluate(points, n['start_tick']) for n in notes]
    trajectory = max(levels)-min(levels) if levels else 0
    coverage = sum(n['duration_tick'] for n in notes) / melody.BAR
    baseline_cost = (.65*roughness + .08*rhythm + .15*key_changes) * coverage + .25*edge
    # Cost of replacing coherent music is explicit; emotion/length alone cannot
    # create a positive benefit. Intensity only modulates an actual music cost.
    change_cost = .13 + .01*math.ceil((region['end_tick']-region['start_tick'])/melody.BAR)
    bridge_cost = .2*baseline_cost + change_cost
    benefit = baseline_cost*(1+.1*trajectory) - bridge_cost
    return dict(range=copy.deepcopy(region), baseline_score=round(1-baseline_cost, 8),
        bridge_score=round(1-bridge_cost, 8), benefit=round(benefit, 8),
        features=dict(interval_roughness=roughness, boundary_leaps=edge, rhythm_contrast=rhythm,
            key_changes=key_changes, intensity_trend=trajectory),
        reasons=[_warning('MUSICAL_COMPARISON', '比较实际音程、节奏、调性入口与换写成本；长度及同情绪不单独触发桥。')])


def _joint_conditions(windows):
    result = []
    for left, right in zip(windows, windows[1:]):
        if left['end_tick'] != right['start_tick']:
            continue
        tick = left['end_tick']; tonic = right['context']['key_context']['tonic']
        scale = [p for p in range(128) if p % 12 == tonic]
        # This frozen pair is chosen jointly, before either bridge exists. It
        # does not pretend the replaced endpoints are the future bridge ends.
        pitch = min(scale, key=lambda p: (abs(p-64), p))
        def endpoint(window, entering):
            a, b = window['start_tick'], window['end_tick']
            available = [(a, b)]
            for mask in window['blank_mask']:
                available = [(x, min(y, mask['start_tick'])) for x, y in available if x < mask['start_tick']] + [
                    (max(x, mask['end_tick']), y) for x, y in available if y > mask['end_tick']]
            available = sorted((x, y) for x, y in available if x < y)
            if not available:
                return None
            x, y = available[0 if entering else -1]; duration = min(120, y-x)
            return dict(pitch=pitch, start_tick=x if entering else y-duration, duration_tick=duration)
        result.append(dict(id=m.digest('emoblocks.bridge-joint.v1', [left['id'], right['id'], tick]),
            left_bridge_id=left['id'], right_bridge_id=right['id'], tick=tick, relation='shared-tonic-arrival-entry',
            reasons=[_warning('JOINT_ENDPOINTS', '共同冻结相邻完整桥的实际到达与进入音符。')],
            left_endpoint=endpoint(left, False), right_endpoint=endpoint(right, True)))
    return result


def decide(request, should_cancel=None, on_progress=None):
    """Finite evaluation, global conflict resolution, then joint endpoints."""
    if request['algorithm_version'] == GLOBAL_ALGORITHM:
        return _decide_global(request, should_cancel, on_progress)
    _validate_request(request); _check(should_cancel)
    _progress(on_progress, 1, 'BRIDGE_DECISION', '比较完整基础排布与可写桥窗口。')
    assessments = []; tested = 0; termination = 'EXHAUSTED'; candidates = []
    base = request['base_project']; params = request['parameters']
    if params['policy'] == 'none':
        termination = 'POLICY_NONE'
    else:
        writable = _writable_regions(request)
        points = {r[k] for r in writable for k in ('start_tick', 'end_tick')}
        points.update(v for p in base['placements'] for v in (p['start_tick'], p['start_tick']+p['length_ticks']))
        points.update(b[k] for b in base['blank_regions'] for k in ('start_tick', 'end_tick'))
        # An independent whole phrase can span many blocks. Its placement
        # edges alone must not prevent selecting its unprotected interior.
        points.update(v for n in request['base_notes'] for v in (n['start_tick'], n['start_tick']+n['duration_tick']))
        points = sorted(points)
        # Enumerate starts in time order. The upper block bound also limits
        # scanning in very long projects; no unbounded retry loop.
        for i, a in enumerate(points):
            for b in points[i+1:]:
                _check(should_cancel)
                blocks = math.ceil((b-a)/melody.BAR)
                if blocks > params['max_window_blocks']:
                    break
                if blocks < 2:
                    continue
                if not any(r['start_tick'] <= a < b <= r['end_tick'] for r in writable):
                    continue
                if tested >= params['max_window_tests']:
                    termination = 'WINDOW_BUDGET'; break
                tested += 1; r = _range(a, b)
                if not _legal(request, r):
                    assessments.append(dict(range=r, baseline_score=None, bridge_score=None, benefit=None,
                        reasons=[_warning('UNWRITABLE_WINDOW', '未解决空缺、完整音符边缘或独立保护层禁止换写。')]))
                    continue
                assessment = _assess(request, r); assessments.append(assessment)
                if assessment['benefit'] > .03:
                    candidates.append(assessment)
            if termination == 'WINDOW_BUDGET':
                break
        if not assessments:
            assessments.append(dict(range=None, baseline_score=1., bridge_score=0., benefit=-1.,
                reasons=[_warning('NO_WRITABLE_WINDOW', '没有两块以上且具有实际动机的合法窗口。')]))
    # Weighted interval DP for up to max_windows. Deterministic preference for
    # fewer/shorter/earlier edits breaks equal musical scores.
    candidates.sort(key=lambda v: (v['range']['end_tick'], v['range']['start_tick']))
    states = {(0, 0): (0., [])}
    def rank(state):
        score, rs = state
        return (-round(score, 8), len(rs), sum(b-a for a, b in map(_pair, rs)), tuple(map(_pair, rs)))
    for i, item in enumerate(candidates, 1):
        _check(should_cancel)
        r = item['range']
        previous = next((j for j in range(i-1, 0, -1) if candidates[j-1]['range']['end_tick'] <= r['start_tick']), 0)
        for count in range(params['max_windows']+1):
            options = [states.get((i-1, count), (0., []))]
            if count:
                old = states.get((previous, count-1), (0., []))
                # Splitting one contiguous change into two independent phrases
                # creates another constrained joint. Account for that cost;
                # otherwise external edge rewards double-count that boundary.
                joint_cost = .35 if old[1] and old[1][-1]['end_tick'] == r['start_tick'] else 0.
                options.append((old[0]+item['benefit']-joint_cost, old[1]+[r]))
            states[i, count] = min(options, key=rank)
    best = min((states.get((len(candidates), k), (0., [])) for k in range(params['max_windows']+1)), key=rank)
    windows = _contexts(request, sorted(best[1], key=_pair))
    decision = 'selected' if windows else 'none'
    if params['policy'] == 'none':
        assessments.append(dict(range=None, baseline_score=1., bridge_score=None, benefit=None,
            reasons=[_warning('POLICY_NONE', '按用户明确选择保留完整基础音乐。')]))
    reasons = [_warning('SELECTED' if windows else 'RETAIN_BASE',
        '实际音乐比较有正收益，先提交整体选位提案。' if windows else '保留实际基础音乐；无可写窗口或换写收益不足。')]
    _progress(on_progress, 2, 'BRIDGE_DECISION', '位置比较完成；等待后端原子登记所有范围。')
    return dict(schema='emoblocks.bridge-proposal.v1', spec_rev=m.SPEC_REV, contract_rev=CONTRACT_REV,
        request_fingerprint=_request_hash(request), decision=decision, windows=windows, reasons=reasons,
        assessments=assessments, joint_boundary_conditions=_joint_conditions(windows),
        search=dict(tested_windows=tested, termination=termination))


def _validate_windows(request, windows, joints):
    m.indexed(windows); m.objects(joints)
    regions = []
    for window in windows:
        m.shape(window, 'id start_tick end_tick placement_ids context emotion_segments blank_mask')
        m.range_check(_range(window['start_tick'], window['end_tick']), request['base_project']['total_ticks'])
        if not _legal(request, window):
            _fail('PROTECTION_CONFLICT', '锁定窗口与空缺、原保护或完整音符冲突。')
        regions.append(_range(window['start_tick'], window['end_tick']))
    ordered = sorted(regions, key=_pair)
    if any(m.intersects(a, b) for a, b in zip(ordered, ordered[1:])):
        _fail('PROTECTION_CONFLICT', '桥窗口重叠。')
    expected = _contexts(request, regions)
    for actual, exp in zip(windows, expected):
        m.ident(actual['id']); m.shape(actual['context'], 'left right motif_note_ids key_context')
        # A legal proposal may use a subset of genuine motif parents, but may
        # not borrow arbitrary library or other placement ancestry.
        if any(actual[k] != exp[k] for k in ('placement_ids', 'emotion_segments', 'blank_mask')):
            _fail('PROTECTION_CONFLICT', '冻结窗口位置、情绪或留白摘要不准确。')
        if any(actual['context'][k] != exp['context'][k] for k in ('left', 'right')):
            _fail('INVALID_CANDIDATE', '桥邻接上下文不是计划外实际最近放置。')
        allowed = {n['id'] for n in request['base_notes'] if m.intersects(_support(n), actual)}
        allowed.update(n['id'] for side in ('left', 'right') for n in (actual['context'][side] or {}).get('notes', []))
        ids = actual['context']['motif_note_ids']
        if not ids or len(ids) != len(set(ids)) or not set(ids) <= allowed:
            _fail('INVALID_CANDIDATE', '动机父发声不属于窗口或真实邻接上下文。')
        melody._key(dict(provenance=dict(key_context=actual['context']['key_context']), generation=None),
                    [n for n in request['base_notes'] if n['id'] in ids])
    adjacent = {(a['id'], b['id']) for a in windows for b in windows if a['end_tick'] == b['start_tick']}
    seen = set(); window_map = {w['id']:w for w in windows}
    for joint in joints:
        m.shape(joint, 'id left_bridge_id right_bridge_id tick relation reasons left_endpoint right_endpoint')
        m.ident(joint['id']); m.ident(joint['relation']); m.objects(joint['reasons'])
        pair = joint['left_bridge_id'], joint['right_bridge_id']
        if pair not in adjacent or pair in seen or joint['tick'] != window_map[pair[0]]['end_tick']:
            _fail('PROTECTION_CONFLICT', '共同条件缺失、重复或不对应相邻冻结窗。')
        seen.add(pair)
        for key, ident in [('left_endpoint', pair[0]), ('right_endpoint', pair[1])]:
            note = joint[key]
            if note is None:
                continue
            m.shape(note, 'pitch start_tick duration_tick'); m.integer(note['pitch'], 0, 127); m.integer(note['duration_tick'], 1)
            r = _support(note); window = window_map[ident]
            if not window['start_tick'] <= r['start_tick'] < r['end_tick'] <= window['end_tick'] or any(m.intersects(r, b) for b in window['blank_mask']):
                _fail('PROTECTION_CONFLICT', '共同音符进入留白或越出桥范围。')
    if seen != adjacent or len({j['id'] for j in joints}) != len(joints):
        _fail('PROTECTION_CONFLICT', '共同边界集合不完整。')


def _validate_plan(request, plan):
    _validate_request(request); m.canonical(plan); m.shape(plan, PLAN_FIELDS)
    if (plan['schema'], plan['spec_rev'], plan['contract_rev']) != ('emoblocks.bridge-plan.v1', m.SPEC_REV, CONTRACT_REV):
        _fail('PLAN_VERSION_MISMATCH', '冻结桥计划版本错误。')
    for key, reqkey in [('id', 'plan_id'), ('version', 'plan_version'), ('request_id', 'request_id'),
            ('snapshot_id', 'snapshot_id'), ('input_fingerprint', 'input_fingerprint'), ('base_fingerprint', 'base_fingerprint')]:
        if plan[key] != request[reqkey]:
            _fail('PLAN_VERSION_MISMATCH', '生成器收到其他请求或版本的计划。')
    candidate = request['completion_ref']['candidate_id'] if request['completion_ref'] else None
    if plan['candidate_id'] != candidate or plan['request_fingerprint'] != _request_hash(request):
        _fail('STALE_SNAPSHOT', '冻结计划与基础候选不一致。')
    if plan['plan_fingerprint'] != m.digest('emoblocks.bridge-plan.v1', {k:v for k,v in plan.items() if k != 'plan_fingerprint'}):
        _fail('PLAN_VERSION_MISMATCH', '冻结计划指纹不匹配。')
    if plan['decision'] not in ('selected', 'none') or bool(plan['windows']) != (plan['decision'] == 'selected'):
        _fail('INVALID_CANDIDATE', '计划none与真实窗口矛盾。')
    if request['parameters']['policy'] == 'none' and plan['windows']:
        _fail('INVALID_CANDIDATE', '冻结计划违背用户明确none选择。')
    if len(plan['windows']) > request['parameters']['max_windows']:
        _fail('INVALID_CANDIDATE', '冻结窗口超过请求预算。')
    if any(w['end_tick']-w['start_tick'] > request['parameters']['max_window_blocks']*melody.BAR for w in plan['windows']):
        _fail('INVALID_CANDIDATE', '冻结窗口长度超过请求明确预算。')
    if request['algorithm_version'] == GLOBAL_ALGORITHM:
        validate_search(request, plan)
    else:
        m.shape(plan['search'], 'tested_windows termination')
    m.integer(plan['search']['tested_windows'], 0, request['parameters']['max_window_tests'])
    m.ident(plan['search']['termination']); m.objects(plan['reasons']); m.objects(plan['assessments'])
    _validate_windows(request, plan['windows'], plan['joint_boundary_conditions'])
    inherited = {p['owner_id']:p for p in request['base_project']['protections'] if p['kind'] == 'bridge'}
    if len(plan['inherited_bridge_ids']) != len(inherited) or set(plan['inherited_bridge_ids']) != set(inherited):
        _fail('PROTECTION_CONFLICT', '计划遗漏或添加基础继承桥。')
    expected_ids = [w['id'] for w in plan['windows']] + plan['inherited_bridge_ids']
    if len(set(expected_ids)) != len(expected_ids):
        _fail('PROTECTION_CONFLICT', '自动桥与继承桥身份重复。')
    refs = plan['protection_refs']; m.objects(refs)
    for ref in refs:
        m.shape(ref, 'bridge_id protection_id'); m.ident(ref['bridge_id']); m.ident(ref['protection_id'])
    if (len(refs) != len(expected_ids) or set(r['bridge_id'] for r in refs) != set(expected_ids)
            or len(set(r['protection_id'] for r in refs)) != len(refs)):
        _fail('PROTECTION_CONFLICT', '公开保护映射缺项、重复或额外。')
    mapping = {r['bridge_id']:r['protection_id'] for r in refs}
    locks = copy.deepcopy(request['base_project']['protections']); original_ids = {p['id'] for p in locks}
    for ident, protection in inherited.items():
        if mapping[ident] != protection['id']:
            _fail('PROTECTION_CONFLICT', '继承桥保护ID被重绑。')
    for w in plan['windows']:
        if mapping[w['id']] in original_ids:
            _fail('PROTECTION_CONFLICT', '新桥锁占用原保护身份。')
        locks.append(dict(id=mapping[w['id']], kind='bridge', owner_id=w['id'], placement_id=None,
            component_path=[], start_tick=w['start_tick'], end_tick=w['end_tick'], status='RANGE_LOCKED', origin='automatic',
            plan_id=plan['id'], plan_version=plan['version'], input_fingerprint=request['input_fingerprint'],
            notes=[], structure_fingerprint=None, blank_mask=copy.deepcopy(w['blank_mask'])))
    if m.protection_summary(locks) != plan['range_lock_fingerprint']:
        _fail('PROTECTION_CONFLICT', '冻结计划没有完整初始范围锁摘要。')
    return mapping


def _result(request, plan, ident, protection_id, origin, region, status='READY', error=None):
    return dict(schema='emoblocks.bridge-result.v1', spec_rev=m.SPEC_REV, contract_rev=CONTRACT_REV,
        request_id=request['request_id'], snapshot_id=request['snapshot_id'], request_fingerprint=_request_hash(request),
        base_fingerprint=request['base_fingerprint'], plan_id=plan['id'], plan_version=plan['version'],
        plan_fingerprint=plan['plan_fingerprint'], bridge_id=ident, protection_id=protection_id, origin=origin,
        range=region, status=status, base_material=None, material=None, children=[], emotion_processing=None,
        operations=[], notes=[], content_fingerprint=None, error=error)


def _content(result, mask):
    return m.digest('emoblocks.bridge-content.v1', dict(range=result['range'], blank_mask=sorted(mask, key=_pair), notes=_ordered(result['notes'])))


def _emotion_once(request, window, base, joints, cancel):
    variants = []; merged = []
    endpoints = [n for n in melody._bridge_endpoints(window, joints) if n is not None]
    absolute = [dict(n, start_tick=n['start_tick']+window['start_tick']) for n in base['notes']]
    for segment in window['emotion_segments']:
        _check(cancel)
        a, b = segment['start_tick'], segment['end_tick']
        frozen_ranges = copy.deepcopy(window['blank_mask'])
        if window['start_tick'] < a:
            frozen_ranges.append(_range(window['start_tick'], a))
        if b < window['end_tick']:
            frozen_ranges.append(_range(b, window['end_tick']))
        frozen_ranges.extend(_support(n) for n in endpoints)
        protected = [n for n in absolute if any(m.intersects(_support(n), r) for r in frozen_ranges)]
        seed = int(m.digest('emoblocks.bridge-emotion-seed.v1', dict(
            music_seed=base['generation']['seed'], range=_range(a, b), emotion=segment['emotion']))[:8], 16)
        variant = emotion.emotion_variant(base, segment['emotion'], request['base_project']['intensity_points'],
            window['start_tick'], protected, protected_ranges=frozen_ranges, seed=seed)
        merged.extend(copy.deepcopy(n) for n in variant['notes'] if a <= window['start_tick']+n['start_tick'] < b)
        variants.append(dict(range=_range(a, b), emotion=segment['emotion'], seed=seed, variant=variant))
    if len(merged) != len(base['notes']):
        _fail('BRIDGE_GENERATION_FAILED', '情绪段未按音符起点覆盖一次完整母句。')
    final = copy.deepcopy(base)
    final['notes'] = sorted(merged, key=lambda n: (n['start_tick'], n['id']))
    # Final identity derives from music inputs, not a mutable plan/session UUID.
    final['id'] = m.digest('emoblocks.bridge-final-material.v1', dict(base=base, segments=variants))
    final['generation'] = dict(method='bridge_emotion_once', parameters=dict(pass_count=1,
            segments=[dict(range=v['range'], emotion=v['emotion'], seed=v['seed'], input_material_id=base['id']) for v in variants]),
        seed=base['generation']['seed'], rng_version=emotion.RNG_VERSION, algorithm_version=ALGORITHM_VERSION,
        input_fingerprint=m.digest('emoblocks.bridge-emotion-input.v1', dict(base=base, segments=variants)),
        input_material_ids=[base['id']], base_notes=copy.deepcopy(base['notes']), key_context=copy.deepcopy(base['generation']['key_context']),
        operations=[dict(range=v['range'], emotion=v['emotion'], operations=copy.deepcopy(v['variant']['generation']['operations'])) for v in variants])
    melody.music_signature(final)
    return final, dict(pass_count=1, algorithm_version=emotion.ALGORITHM_VERSION, segments=variants)


def _automatic(request, plan, window, protection_id, cancel):
    _check(cancel)
    base = melody.compose_bridge_phrase(request, window, plan['joint_boundary_conditions'], should_cancel=cancel)
    _verify_base_music(request, window, base)
    final, processing = _emotion_once(request, window, base, plan['joint_boundary_conditions'], cancel)
    result = _result(request, plan, window['id'], protection_id, 'automatic', _range(window['start_tick'], window['end_tick']))
    result.update(base_material=base, material=final, children=melody.split_phrase(final), emotion_processing=processing,
        operations=copy.deepcopy(base['generation']['operations']),
        notes=_ordered([dict(n, id=window['id']+':'+n['id'], start_tick=n['start_tick']+window['start_tick']) for n in final['notes']]))
    result['content_fingerprint'] = _content(result, window['blank_mask'])
    return result


def _verify_base_music(request, window, base):
    """Local defensive checks; backend still authenticates independently."""
    melody.music_signature(base)
    if base['kind'] != 'phrase' or base['length_ticks'] != window['end_tick']-window['start_tick'] or not base['notes']:
        _fail('BRIDGE_GENERATION_FAILED', '统一作曲没有返回精确长度的实际完整句。')
    if len(base['notes']) > request['parameters']['max_notes']:
        _fail('BRIDGE_GENERATION_FAILED', '本桥实际音符超出独立预算。')
    parents = melody._bridge_parent_table(request['base_project'])
    motif = window['context']['motif_note_ids']; gen = base['generation']
    if (gen['method'] != 'bridge_phrase' or gen['base_notes'] != [parents[i]['note'] for i in motif]
            or gen['input_material_ids'] != list(dict.fromkeys(parents[i]['snapshot']['id'] for i in motif))):
        _fail('INVALID_CANDIDATE', '桥基础来源快照与实际动机不一致。')
    cells = gen['operations']; emitted = m.indexed(base['notes'])
    if len(cells) != len(emitted) or {c.get('output_note_id') for c in cells} != set(emitted):
        _fail('INVALID_CANDIDATE', '桥逐音符账本缺项、重复或额外。')
    for cell in cells:
        m.shape(cell, 'operation input_note_id parent_ref output_note_id motif_index cycle_index rule from_pitch to_pitch start_tick duration_tick')
        parent = parents.get(cell['input_note_id']); note = emitted[cell['output_note_id']]
        m.integer(cell['motif_index'], 0, len(motif)-1); m.integer(cell['cycle_index'])
        if (parent is None or motif[cell['motif_index']] != cell['input_note_id'] or cell['operation'] != 'bridge-motif-cell'
                or cell['parent_ref'] != parent['parent_ref'] or cell['from_pitch'] != parent['note']['pitch']
                or cell['rule'] not in ('opening', 'sequence', 'answer', 'rhythm', 'arrival')
                or (cell['to_pitch'], cell['start_tick'], cell['duration_tick']) != (note['pitch'], note['start_tick'], note['duration_tick'])
                or note['origin'] != parent['note']['origin']
                or note['lineage'] != list(dict.fromkeys(parent['note']['lineage']+[parent['note']['id']])) or note['slice'] is not None):
            _fail('INVALID_CANDIDATE', '桥音符与真实父发声、来源、组件或操作不一致。')
        if any(m.intersects(_range(note['start_tick']+window['start_tick'], note['start_tick']+window['start_tick']+note['duration_tick']), r) for r in window['blank_mask']):
            _fail('PROTECTION_CONFLICT', '实际桥音符进入主动留白。')


def _inherited(request, plan, lock):
    if lock['status'] != 'CONTENT_READY':
        _fail('BRIDGE_NOT_READY', '继承桥原范围锁尚无实际就绪内容。')
    base = request['base_project']
    if lock['origin'] == 'manual':
        matches = [p for p in base['placements'] if p['id'] == lock['placement_id']]
        if len(matches) != 1:
            _fail('BRIDGE_NOT_READY', '手动继承桥没有原实际放置。')
        place = matches[0]; material = copy.deepcopy(place['emotion_variant'] or place['base_snapshot'])
        notes = _ordered(__import__('curve_application').context_notes(base,place)); base_material = copy.deepcopy(place['base_snapshot'])
        children = []; processing = None; operations = []
    else:
        # Historical P0 records retain their own shape and old lock bindings.
        plans = [r for r in base['records'] if r['id'] == lock['plan_id'] and r['kind'] == 'bridge_plan' and r['status'] == 'READY' and r['version'] == lock['plan_version']]
        records = [r for r in base['records'] if r['kind'] == 'bridge_result' and r['status'] == 'READY'
            and r['payload'].get('bridge_id') == lock['owner_id'] and r['payload'].get('plan_id') == lock['plan_id']
            and r['payload'].get('plan_version') == lock['plan_version']]
        if len(plans) != 1 or len(records) != 1:
            _fail('BRIDGE_NOT_READY', '历史自动桥缺少原计划及唯一实际READY结果。')
        payload = records[0]['payload']; material = copy.deepcopy(payload.get('material_snapshot'))
        if material is None:
            _fail('BRIDGE_NOT_READY', '历史自动桥结果不能解析实际音乐。')
        base_material = copy.deepcopy(material); children = []; processing = None; operations = []
        notes = _ordered([n for n in request['base_notes'] if m.intersects(_support(n), lock)])
    if not notes or m.structural_notes(notes) != m.structural_notes(lock['notes']):
        _fail('BRIDGE_NOT_READY', '继承桥原保护与当前实际发声不一致。')
    result = _result(request, plan, lock['owner_id'], lock['id'], 'inherited', _range(lock['start_tick'], lock['end_tick']))
    result.update(base_material=base_material, material=material, children=children,
        emotion_processing=processing, operations=operations, notes=notes)
    result['content_fingerprint'] = _content(result, lock['blank_mask'])
    return result


def generate(request, locked_plan, should_cancel=None, on_progress=None, on_result=None):
    """Generate only a structurally locked plan; stream facts, never clear locks.

    Callback errors propagate so the backend can fail the active job while
    retaining already authenticated results. Ordinary generation errors abort
    later work and return an explicit terminal row for every planned identity.
    """
    mapping = _validate_plan(request, locked_plan)
    plan = locked_plan; jobs = [(w['id'], 'automatic', w) for w in plan['windows']]
    by_owner = {p['owner_id']:p for p in request['base_project']['protections'] if p['kind'] == 'bridge'}
    jobs.extend((ident, 'inherited', by_owner[ident]) for ident in plan['inherited_bridge_ids'])
    results = []; terminal_error = None; terminal = 'SUCCEEDED'
    _progress(on_progress, 1, 'BRIDGE_GENERATION', '已收到完整冻结计划；开始完整句构作。')
    for index, (ident, origin, item) in enumerate(jobs):
        if terminal_error is None:
            try:
                _check(should_cancel)
                result = (_automatic(request, plan, item, mapping[ident], should_cancel) if origin == 'automatic'
                          else _inherited(request, plan, item))
            except m.ProjectError as exc:
                terminal = 'CANCELLED' if exc.code == 'CANCELLED' else 'FAILED'
                terminal_error = _warning(exc.code, str(exc))
                result = _result(request, plan, ident, mapping[ident], origin,
                    _range(item['start_tick'], item['end_tick']), terminal, terminal_error)
        else:
            result = _result(request, plan, ident, mapping[ident], origin,
                _range(item['start_tick'], item['end_tick']), terminal,
                dict(terminal_error, details=dict(not_generated=True, stopped_after=results[-1]['bridge_id'])))
        results.append(result)
        if on_result is not None:
            on_result(copy.deepcopy(result))
        _progress(on_progress, index+2, 'BRIDGE_GENERATION',
            '已产出真实完整桥结果，等待独立内容认证。' if result['status'] == 'READY' else '已停止后续生成并保留全部冻结范围。')
    # Cancel can arrive after the last complete fact was streamed. Keep that
    # fact, but never upgrade a cancelled attempt to overall success.
    if terminal_error is None:
        try:
            _check(should_cancel)
        except m.ProjectError as exc:
            terminal = 'CANCELLED'; terminal_error = _warning(exc.code, str(exc))
    return dict(schema='emoblocks.bridge-raw-outcome.v1', spec_rev=m.SPEC_REV, contract_rev=CONTRACT_REV,
        request_fingerprint=_request_hash(request), plan_id=plan['id'], plan_version=plan['version'],
        status=terminal, results=results, error=terminal_error)


# Global-v2 positioning only. All composition/emotion functions above remain v1.
def _select_global(assessments, max_windows, should_cancel=None):
    """Exact-last interval DP. Separate strict/equal-end predecessor queries.

    At most K*M*log(M); impossible exact-count states never become zero. Scores
    are integers so adjacent costs and deterministic ties have exact semantics.
    """
    items=sorted((a for a in assessments if a.get('benefit') is not None and a['benefit']>.03),
                 key=lambda a:(a['range']['end_tick'],a['range']['start_tick']))
    ends=[a['range']['end_tick'] for a in items]
    def rank(state):
        score,rs=state
        return (-score,len(rs),sum(b-a for a,b in rs),rs)
    best=(0,());previous=None
    for k in range(1,min(max_windows,len(items))+1):
        if previous is not None:
            prefixes=[];current=None;equal={}
            for item,state in zip(items,previous):
                if state is not None:
                    current=state if current is None else min(current,state,key=rank)
                    end=item['range']['end_tick']
                    equal[end]=state if end not in equal else min(equal[end],state,key=rank)
                prefixes.append(current)
        row=[]
        for i,item in enumerate(items):
            _check(should_cancel);a,b=_pair(item['range']);score=round(item['benefit']*100000000)
            if k==1:state=(score,((a,b),))
            else:
                options=[];index=bisect.bisect_left(ends,a)-1
                strict=prefixes[index] if index>=0 else None
                if strict is not None:options.append((strict[0]+score,strict[1]+((a,b),)))
                adjacent=equal.get(a)
                if adjacent is not None:options.append((adjacent[0]+score-35000000,adjacent[1]+((a,b),)))
                state=min(options,key=rank) if options else None
            row.append(state)
            if state is not None:best=min(best,state,key=rank)
        previous=row
    return [_range(a,b) for a,b in best[1]]


def _regions(total):
    count=min(8,total)
    return [_range(i*total//count,(i+1)*total//count) for i in range(count)]


def _fair_queue(request, analysis, should_cancel=None):
    import curve_phrase_analysis as phrase
    points=[b['tick'] for b in analysis['boundaries']];writable=_writable_regions(request)
    params=request['parameters'];universe=[]
    for i,a in enumerate(points):
        _check(should_cancel)
        region=next((r for r in writable if r['start_tick']<=a<r['end_tick']),None)
        if region is None:continue
        for b in points[i+1:]:
            blocks=math.ceil((b-a)/melody.BAR)
            if blocks>params['max_window_blocks'] or b>region['end_tick']:break
            if blocks<2:continue
            universe.append((a,b))
            if len(universe)>phrase.LIMITS['candidates']:_fail('SEARCH_LIMIT','Candidate range universe exceeds fixed budget.')
    regions=_regions(analysis['total_ticks']);representatives=[]
    for r in regions:
        _check(should_cancel)
        choices=[u for u in universe if r['start_tick']<=u[0]<r['end_tick']]
        if choices:representatives.append(min(choices,key=lambda u:(abs(2*u[0]-r['start_tick']-r['end_tick']),u[1]-u[0],*u)))
    boundaries=[b['tick'] for b in analysis['boundaries'] if 0<b['tick']<analysis['total_ticks'] and b['confidence']>=.60]
    subsets=collections.deque([boundaries])
    while subsets:
        _check(should_cancel);ticks=subsets.popleft()
        if not ticks:continue
        mid=(len(ticks)-1)//2;tick=ticks[mid]
        choices=[u for u in universe if u[0]<=tick<=u[1]]
        if choices:representatives.append(min(choices,key=lambda u:(u[1]-u[0],abs(u[0]+u[1]-2*tick),*u)))
        subsets.append(ticks[:mid]);subsets.append(ticks[mid+1:])
    seed=list(dict.fromkeys(representatives));seen=set(seed)
    confidence={b['tick']:b['confidence'] for b in analysis['boundaries']}
    phrases={p['id']:p for p in analysis['phrases']};returns={}
    for r in analysis['motif_relations']:
        if r['relation']=='return':
            tick=phrases[r['right_phrase_id']]['start_tick']
            returns[tick]=max(returns.get(tick,0),min(r['contour_similarity'],r['rhythm_similarity']))
    def order(u):
        a,b=u;priority=confidence[a]+confidence[b]+returns.get(b,0)-.01*math.ceil((b-a)/melody.BAR)
        return (-priority,b-a,a,b)
    queue=seed+sorted((u for u in universe if u not in seen),key=order)
    _check(should_cancel)
    return queue,len(seed),regions,boundaries


def _global_assessment(request, region, analysis, keys):
    import curve_phrase_analysis as phrase
    if not _legal(request,region):
        return dict(range=copy.deepcopy(region),baseline_score=None,bridge_score=None,benefit=None,
                    reasons=[_warning('UNWRITABLE_WINDOW','Actual full support/rest/protection prevents rewriting.')])
    # Measure actual local notes directly. No obsolete placement tonal inference
    # is invoked for an accepted score, even as a discarded intermediate value.
    notes=[n for n in request['base_notes'] if m.intersects(_support(n),region)]
    leaps=[abs(x['pitch']-y['pitch']) for x,y in zip(notes,notes[1:])]
    roughness=sum(max(0,v-7)/17 for v in leaps)/max(1,len(leaps))
    durations=[n['duration_tick'] for n in notes]
    rhythm=sum(abs(math.log2(y/x)) for x,y in zip(durations,durations[1:]))/max(1,len(durations)-1)
    before=[n for n in request['base_notes'] if _support(n)['end_tick']<=region['start_tick']]
    after=[n for n in request['base_notes'] if n['start_tick']>=region['end_tick']]
    edges=([abs(before[-1]['pitch']-notes[0]['pitch'])] if before else [])+([abs(notes[-1]['pitch']-after[0]['pitch'])] if after else [])
    edge=sum(max(0,v-7)/17 for v in edges)/max(1,len(edges))
    features=dict(interval_roughness=roughness,boundary_leaps=edge,rhythm_contrast=rhythm)
    row=dict(range=copy.deepcopy(region),features=features,
             reasons=[_warning('MUSICAL_COMPARISON','Actual intervals, rhythm, parent tonality and rewrite cost; predicted only.')])
    contexts=[keys[n['id']] for n in notes]
    changes=sum((a['tonic'],a['mode'])!=(b['tonic'],b['mode']) for a,b in zip(contexts,contexts[1:]))/max(1,len(contexts)-1)
    global_features=phrase.window_features(analysis,region)
    points=[dict(time=p['tick'],level=p['level']) for p in request['base_project']['intensity_points']]
    features.update(key_changes=changes,intensity_trend=intensity_curve.evaluate(points,region['end_tick'])-intensity_curve.evaluate(points,region['start_tick']),
                    **{'global':global_features,'analysis_fingerprint':analysis['analysis_fingerprint']})
    cost=(.65*features['interval_roughness']+.08*features['rhythm_contrast']+.15*changes)*sum(n['duration_tick'] for n in notes)/melody.BAR+.25*features['boundary_leaps']
    rewrite=.13+.01*math.ceil((region['end_tick']-region['start_tick'])/melody.BAR)
    gain=global_features['global_gain']
    row.update(baseline_score=round(1-cost,8),bridge_score=round(1-(.2*cost+rewrite-gain),8),benefit=round(.8*cost-rewrite+gain,8))
    row['reasons']+=copy.deepcopy(global_features['reason_codes'])
    return row


def _coverage(regions,boundaries,queue,assessments,termination):
    legal=[a['range'] for a in assessments if a['benefit'] is not None]
    evaluated=[r for r in regions if any(r['start_tick']<=a['start_tick']<r['end_tick'] for a in legal)]
    visited=[t for t in boundaries if any(a['start_tick']<=t<=a['end_tick'] for a in legal)]
    return dict(regions=regions,evaluated_regions=evaluated,unevaluated_regions=[r for r in regions if r not in evaluated],
                evaluated_boundaries=visited,unevaluated_boundaries=[t for t in boundaries if t not in visited],
                generated_candidates=len(queue),selection_method='weighted-interval-dp-on-evaluated-candidates',
                coverage_complete=termination=='EXHAUSTED' and len(assessments)==len(queue))


def _global_windows(request,ranges,keys):
    windows=_contexts(request,ranges)
    for window in windows:
        first=next(n for n in request['base_notes'] if m.intersects(_support(n),window))
        window['context']['key_context']=copy.deepcopy(keys[first['id']])
    return windows


def _global_reasons(windows,termination,assessments):
    incomplete=termination in ('REGION_BUDGET','WINDOW_BUDGET')
    if termination=='POLICY_NONE':code='POLICY_NONE'
    elif windows:code='SELECTED'
    elif incomplete:code='SEARCH_INCOMPLETE'
    elif not any(a['benefit'] is not None for a in assessments):code='NO_WRITABLE_WINDOW'
    else:code='NO_PREDICTED_GAIN'
    result=[_warning(code,'Bounded prediction from actual whole-score music; not generated quality.')]
    if windows and incomplete:result.append(_warning('SEARCH_INCOMPLETE','Selected only among evaluated ranges; full universe not exhausted.'))
    return result


def _decide_global(request,should_cancel,on_progress):
    import curve_phrase_analysis as phrase
    _check(should_cancel);phrase._preflight(request);_validate_request(request)
    _progress(on_progress,1,'BRIDGE_DECISION','Analyzing actual whole-score parents, phrases and trajectory.')
    assessments=[];analysis=None;keys={};queue=[]
    if request['parameters']['policy']=='none':
        termination='POLICY_NONE';regions=_regions(request['base_project']['total_ticks']);boundaries=[]
    else:
        analysis=phrase.analyze(request,should_cancel);keys=phrase.note_keys(request)
        queue,seed_count,regions,boundaries=_fair_queue(request,analysis,should_cancel)
        for a,b in queue[:request['parameters']['max_window_tests']]:
            _check(should_cancel)
            assessments.append(_global_assessment(request,_range(a,b),analysis,keys))
        tested=len(assessments)
        termination=('EXHAUSTED' if tested==len(queue) else 'REGION_BUDGET' if tested<seed_count else 'WINDOW_BUDGET')
    ranges=_select_global(assessments,request['parameters']['max_windows'],should_cancel)
    windows=_global_windows(request,ranges,keys);_check(should_cancel)
    _progress(on_progress,2,'BRIDGE_DECISION','Finite comparison complete; backend must atomically lock all ranges.')
    return dict(schema='emoblocks.bridge-proposal.v1',spec_rev=m.SPEC_REV,contract_rev=CONTRACT_REV,
                request_fingerprint=_request_hash(request),decision='selected' if windows else 'none',windows=windows,
                reasons=_global_reasons(windows,termination,assessments),assessments=assessments,
                joint_boundary_conditions=_joint_conditions(windows),search=dict(tested_windows=len(assessments),termination=termination,
                    analysis=analysis,coverage=_coverage(regions,boundaries,queue,assessments,termination)))


def validate_search(request,proposal):
    """Pure global-v2 authentication for Proposal or Plan. Never calls providers.

    Rebuilds factual arithmetic only; does not issue a new decision, repair the
    supplied object, evaluate unbudgeted music, or generate notes. Public backend
    still authenticates header/session/locks independently.
    """
    import curve_phrase_analysis as phrase
    phrase._preflight(request);_validate_request(request)
    if request['algorithm_version']!=GLOBAL_ALGORITHM:_fail('PLAN_VERSION_MISMATCH','Global search proof requires global-v2.')
    search=proposal['search'];m.shape(search,'tested_windows termination analysis coverage');m.canonical(search)
    m.integer(search['tested_windows'],0,request['parameters']['max_window_tests'])
    if request['parameters']['policy']=='none':
        if search['analysis'] is not None:_fail('INVALID_ANALYSIS','Policy none cannot publish an analysis.')
        queue=[];regions=_regions(request['base_project']['total_ticks']);boundaries=[];expected=[];termination='POLICY_NONE';keys={}
    else:
        phrase.validate(request,search['analysis']);analysis=search['analysis'];keys=phrase.note_keys(request)
        queue,seed_count,regions,boundaries=_fair_queue(request,analysis)
        tested=min(len(queue),request['parameters']['max_window_tests'])
        expected=[_global_assessment(request,_range(a,b),analysis,keys) for a,b in queue[:tested]]
        termination=('EXHAUSTED' if tested==len(queue) else 'REGION_BUDGET' if tested<seed_count else 'WINDOW_BUDGET')
    if (m.canonical(proposal['assessments'])!=m.canonical(expected) or search['tested_windows']!=len(expected)
            or search['termination']!=termination or m.canonical(search['coverage'])!=m.canonical(_coverage(regions,boundaries,queue,expected,termination))):
        _fail('INVALID_SEARCH','Assessment arithmetic/queue prefix/coverage does not match actual bounded search.')
    ranges=_select_global(expected,request['parameters']['max_windows'])
    windows=_global_windows(request,ranges,keys)
    if (m.canonical(proposal['windows'])!=m.canonical(windows) or proposal['decision']!=('selected' if windows else 'none')
            or m.canonical(proposal['joint_boundary_conditions'])!=m.canonical(_joint_conditions(windows))
            or m.canonical(proposal['reasons'])!=m.canonical(_global_reasons(windows,termination,expected))):
        _fail('INVALID_SEARCH','Stored selection/joints do not prove the adjacent-cost optimum on evaluated candidates.')
