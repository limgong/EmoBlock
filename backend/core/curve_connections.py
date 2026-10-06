"""P6 immutable connection facts and independent, non-composing validators."""
import copy
import math
from functools import wraps

import curve_project as m
import curve_bridges as b

REV = 'curve-workflow-v2-r3-p6'
ALGORITHM = 'curve-connection-v1'
DEFAULTS = dict(policy='auto', max_windows=3, max_window_tests=128,
                max_window_ticks=3840, min_window_ticks=240, max_notes=512)
LIMITS = dict(max_windows=8, max_window_tests=2048, max_window_ticks=15360, max_notes=4096)
TECHNIQUES = ('diatonic_guide', 'motif_reply', 'density_shift', 'retain_develop', 'breath_close')
REQUEST_FIELDS = ('schema spec_rev contract_rev request_id snapshot_id session_id edit_revision input_contract_rev '
                  'input_fingerprint input_project bridge_ref actual_layout layout_fingerprint protection_summary '
                  'plan_id plan_version seed algorithm_version parameters')
PROPOSAL_FIELDS = ('schema spec_rev contract_rev request_fingerprint decision none_reason windows reasons '
                   'assessments joint_boundary_conditions search')
PLAN_FIELDS = ('schema spec_rev contract_rev id version request_id snapshot_id request_fingerprint bridge_plan_id '
               'bridge_plan_version bridge_plan_fingerprint layout_fingerprint protection_summary_fingerprint '
               'decision none_reason windows reasons assessments joint_boundary_conditions search plan_fingerprint')
RESULT_FIELDS = ('schema spec_rev contract_rev request_id snapshot_id request_fingerprint plan_id plan_version '
                 'plan_fingerprint connection_id range status original_notes notes operations generation content_fingerprint error')
OUTCOME_FIELDS = ('schema spec_rev contract_rev request_fingerprint plan_id plan_version plan_fingerprint status '
                  'results notes content_fingerprint layout_fingerprint protection_summary remaining_gaps error capabilities')


def guard(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
            raise m.ProjectError('INVALID_CONNECTION', '连接数据字段缺失或结构无效。') from exc
    return wrapped


error = b.error
ordered = b.ordered
support = b.support


def version(value, schema):
    if (value['schema'], value['spec_rev'], value['contract_rev']) != (schema, m.SPEC_REV, REV):
        m.reject('连接阶段版本不匹配。', 'UNSUPPORTED_VERSION')


def parameters(values=None):
    result = dict(DEFAULTS)
    if values is not None:
        if not isinstance(values, dict) or set(values) - set(result):
            m.reject('连接参数字段不受支持。', 'INVALID_CONNECTION')
        result.update(values)
    if result['policy'] not in ('auto', 'none'):
        m.reject('连接策略不受支持。', 'INVALID_CONNECTION')
    for key, limit in LIMITS.items():
        m.integer(result[key], 1, limit)
    m.integer(result['min_window_ticks'], 1, result['max_window_ticks'])
    return result


def request_fingerprint(request):
    return m.digest('emoblocks.connection-request.v1', request)


def layout_fingerprint(layout):
    return m.digest('emoblocks.connection-layout.v1', layout)


def plan_fingerprint(plan):
    return m.digest('emoblocks.connection-plan.v1', {k: v for k, v in plan.items() if k != 'plan_fingerprint'})


def content_fingerprint(region, notes):
    return m.digest('emoblocks.connection-content.v1', dict(range=region, notes=ordered(notes)))


def splice_fingerprint(total, notes):
    return m.digest('emoblocks.connection-splice.v1', dict(total_ticks=total, notes=ordered(notes)))


def protection_ranges(protections):
    return b.union([r for lock in protections for r in [b.extent(dict(start_tick=lock['start_tick'],
        length_ticks=lock['end_tick'] - lock['start_tick']))] + [support(n) for n in lock['notes']]])


@guard
def validate_bridge_ref(ref):
    m.shape(ref, 'attempt_id request plan protections results outcome')
    m.ident(ref['attempt_id'])
    request, plan, outcome = ref['request'], ref['plan'], ref['outcome']
    if ref['attempt_id'] != request['request_id'] or plan is None or outcome is None:
        m.reject('请先完成并认证对应的bridge。', 'BRIDGE_NOT_READY')
    b.validate_request(request); b.validate_plan(request, plan); b.validate_outcome(request, plan, outcome)
    if outcome['status'] != 'SUCCEEDED' or ref['results'] != outcome['results']:
        m.reject('bridge没有完整、匹配的实际就绪结果。', 'BRIDGE_NOT_READY')
    if ref['protections'] != b.locks_with_results(request, plan, ref['results']):
        m.reject('bridge保护摘要或实际锁不匹配。', 'PROTECTION_CONFLICT')
    if any(p['kind'] == 'bridge' and p['status'] != 'CONTENT_READY' for p in ref['protections']):
        m.reject('仍有仅锁范围或失败的bridge。', 'BRIDGE_NOT_READY')


def actual_layout(ref):
    validate_bridge_ref(ref)
    request = ref['request']; project = request['base_project']
    view = b.preview(request, ref['plan'], ref['protections'], ref['results'], ref['outcome'])
    return dict(total_ticks=project['total_ticks'], bpm=project['bpm'], notes=copy.deepcopy(ref['outcome']['notes']),
        base_project=copy.deepcopy(project), bridge_overlays=view['overlays'], protections=copy.deepcopy(ref['protections']),
        blank_regions=copy.deepcopy(project['blank_regions']), remaining_gaps=copy.deepcopy(request['remaining_gaps']))


@guard
def make_request(project, bridge_ref, token=None, seed=41, values=None, plan_id=None, plan_version=1):
    m.validate(project); validate_bridge_ref(bridge_ref)
    if project != bridge_ref['request']['input_project']:
        m.reject('bridge输入不属于当前编辑快照。', 'STALE_SNAPSHOT')
    m.integer(seed, 0, 2**32 - 1); m.integer(plan_version, 1)
    token = token or dict(request_id=m.uid(), snapshot_id=m.uid(), session_id=m.uid(), edit_revision=0,
                         input_fingerprint=m.fingerprint(project))
    for key in ('request_id', 'snapshot_id', 'session_id'): m.ident(token[key])
    m.integer(token['edit_revision'])
    if token['input_fingerprint'] != m.fingerprint(project): m.reject('连接输入快照已失效。', 'STALE_SNAPSHOT')
    layout = actual_layout(bridge_ref)
    m.notes_check(layout['notes'], layout['total_ticks'], m.source_index(layout['base_project']['sources']))
    b.monotone_notes(layout['notes'])
    return dict(schema='emoblocks.connection-request.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        request_id=token['request_id'], snapshot_id=token['snapshot_id'], session_id=token['session_id'],
        edit_revision=token['edit_revision'], input_contract_rev=project['contract_rev'], input_fingerprint=m.fingerprint(project),
        input_project=copy.deepcopy(project), bridge_ref=copy.deepcopy(bridge_ref), actual_layout=layout,
        layout_fingerprint=layout_fingerprint(layout), protection_summary=dict(fingerprint=m.protection_summary(layout['protections']),
        ranges=protection_ranges(layout['protections'])), plan_id=plan_id or m.uid(), plan_version=plan_version,
        seed=seed, algorithm_version=ALGORITHM, parameters=parameters(values))


@guard
def validate_request(request):
    m.shape(request, REQUEST_FIELDS); version(request, 'emoblocks.connection-request.v1')
    m.ident(request['plan_id'])
    rebuilt = make_request(request['input_project'], request['bridge_ref'], request, request['seed'],
                           request['parameters'], request['plan_id'], request['plan_version'])
    if m.canonical(request) != m.canonical(rebuilt): m.reject('连接实际布局、保护或输入指纹不一致。', 'STALE_SNAPSHOT')


def forbidden_ranges(request):
    layout = request['actual_layout']
    return b.union(request['protection_summary']['ranges'] +
                   [{k: r[k] for k in ('start_tick', 'end_tick')} for r in layout['blank_regions'] + layout['remaining_gaps']])


def music_projection(request):
    layout = request['actual_layout']; project = layout['base_project']
    return dict(total_ticks=layout['total_ticks'], bpm=layout['bpm'],
        notes=sorted([{k: n[k] for k in ('pitch', 'start_tick', 'duration_tick', 'velocity')} for n in layout['notes']], key=m.canonical),
        intensity_points=copy.deepcopy(project['intensity_points']),
        emotion_segments=sorted([dict(start_tick=p['start_tick'], end_tick=p['start_tick'] + p['length_ticks'], emotion=p['emotion'])
            for p in project['placements']], key=lambda p: (p['start_tick'], p['end_tick'])),
        protection_ranges=copy.deepcopy(request['protection_summary']['ranges']),
        blank_regions=b.union([{k: r[k] for k in ('start_tick', 'end_tick')} for r in layout['blank_regions']]),
        remaining_gaps=b.union([{k: r[k] for k in ('start_tick', 'end_tick')} for r in layout['remaining_gaps']]))


def musical_joints(plan, window):
    return sorted([{k: v for k, v in j.items() if k not in ('id', 'left_connection_id', 'right_connection_id')}
        for j in plan['joint_boundary_conditions'] if window['id'] in (j['left_connection_id'], j['right_connection_id'])], key=m.canonical)


def musical_seed(request, plan, window):
    value = dict(music_fingerprint=m.digest('emoblocks.connection-music.v1', music_projection(request)),
        seed=request['seed'], range={k: window[k] for k in ('start_tick', 'end_tick')}, technique=window['technique'],
        parameters=window['parameters'], key_context=window['key_context'], joints=musical_joints(plan, window))
    return int(m.digest('emoblocks.connection-music-seed.v1', value)[:8], 16)


def window_context(request, window, windows):
    notes = request['actual_layout']['notes']
    usable = [n for n in notes if not any(m.intersects(support(n), w) for w in windows)]
    left = [n for n in usable if support(n)['end_tick'] <= window['start_tick']]
    right = [n for n in usable if n['start_tick'] >= window['end_tick']]
    return (copy.deepcopy(max(left, key=lambda n: (support(n)['end_tick'], n['start_tick'], n['id']))) if left else None,
            copy.deepcopy(min(right, key=lambda n: (n['start_tick'], n['id']))) if right else None)


def parent_ref(request, emission_id):
    for result in request['bridge_ref']['results']:
        if any(n['id'] == emission_id for n in result['notes']):
            local = next(n for n in result['material']['notes'] if result['bridge_id'] + ':' + n['id'] == emission_id) if result['origin'] == 'automatic' else None
            # Inherited bridges retain their original placement's emission identity.
            if local is None:
                old = b.parent_ref(request['bridge_ref']['request'], emission_id)
                local = next(n for n in result['material']['notes'] if n['id'] == old['note_id'])
            return dict(kind='bridge', owner_id=result['bridge_id'], component_path=[],
                        material_snapshot_id=result['material']['id'], note_id=local['id'])
    old = b.parent_ref(request['bridge_ref']['request'], emission_id)
    return dict(kind='placement', owner_id=old['placement_id'], component_path=old['component_path'],
                material_snapshot_id=old['material_snapshot_id'], note_id=old['note_id'])


def compose_fingerprint(request, plan, window):
    parents = m.indexed(request['actual_layout']['notes'])
    value = dict(layout_fingerprint=request['layout_fingerprint'], range={k: window[k] for k in ('start_tick', 'end_tick')},
        technique=window['technique'], parameters=window['parameters'], key_context=window['key_context'],
        motif=[parents[n] for n in window['context']['motif_note_ids']], joints=musical_joints(plan, window),
        seed=musical_seed(request, plan, window), algorithm_version=ALGORITHM)
    return m.digest('emoblocks.connection-compose-input.v1', value)


def generation_data(request, plan, window, operations):
    parents = m.indexed(request['actual_layout']['notes'])
    return dict(method='connection_phrase', parameters=copy.deepcopy(window['parameters']), seed=musical_seed(request, plan, window),
        rng_version='python.random-v3', algorithm_version=ALGORITHM, input_fingerprint=compose_fingerprint(request, plan, window),
        input_material_ids=sorted({parent_ref(request, n)['material_snapshot_id'] for n in window['context']['motif_note_ids']}),
        base_notes=[copy.deepcopy(parents[n]) for n in window['context']['motif_note_ids']],
        key_context=copy.deepcopy(window['key_context']), operations=copy.deepcopy(operations))


def scale_pitches(key):
    intervals = (0, 2, 4, 5, 7, 9, 11) if key['mode'] == 'major' else (0, 2, 3, 5, 7, 8, 10)
    return {(key['tonic'] + i) % 12 for i in intervals}


@guard
def validate_proposal(request, proposal):
    m.shape(proposal, PROPOSAL_FIELDS); version(proposal, 'emoblocks.connection-proposal.v1')
    if proposal['request_fingerprint'] != request_fingerprint(request): m.reject('连接提案输入已失效。', 'STALE_SNAPSHOT')
    windows = m.objects(proposal['windows']); m.indexed(windows)
    params = request['parameters']; total = request['actual_layout']['total_ticks']
    if len(windows) > params['max_windows']: m.reject('连接窗口超出预算。', 'INVALID_CONNECTION')
    if proposal['decision'] == 'none':
        if windows or proposal['none_reason'] not in ('NOT_NEEDED', 'NO_LEGAL_WINDOW'): m.reject('无连接必须有准确原因。', 'INVALID_CONNECTION')
    elif proposal['decision'] != 'selected' or not windows or proposal['none_reason'] is not None:
        m.reject('连接决策与实际窗口不符。', 'INVALID_CONNECTION')
    if params['policy'] == 'none' and windows: m.reject('明确保留策略不能产生连接。', 'INVALID_CONNECTION')
    if not proposal['reasons']: m.reject('连接决策缺少原因。', 'INVALID_CONNECTION')
    for reason in m.objects(proposal['reasons']): b.warning_check(reason)
    for row in m.objects(proposal['assessments']):
        if not isinstance(row, dict): m.reject('连接评价必须是对象。', 'INVALID_CONNECTION')
        m.canonical(row)
    m.shape(proposal['search'], 'tested_windows termination')
    m.integer(proposal['search']['tested_windows'], 0, params['max_window_tests']); m.ident(proposal['search']['termination'])
    if not windows and proposal['search']['termination'] == 'WINDOW_BUDGET':
        m.reject('搜索预算用尽，尚未证明没有合法连接窗口。', 'SEARCH_BUDGET_EXHAUSTED')
    notes = request['actual_layout']['notes']
    for index, win in enumerate(windows):
        m.shape(win, 'id start_tick end_tick technique context original_notes reasons key_context parameters')
        m.range_check({k: win[k] for k in ('start_tick', 'end_tick')}, total)
        size = win['end_tick'] - win['start_tick']
        if not params['min_window_ticks'] <= size <= params['max_window_ticks']: m.reject('连接实际长度超出预算。', 'INVALID_CONNECTION')
        if win['technique'] not in TECHNIQUES: m.reject('连接音乐手段无效。', 'INVALID_CONNECTION')
        if any(m.intersects(win, r) for r in forbidden_ranges(request)):
            m.reject('连接窗口侵入bridge、记忆、留白或未解决范围。', 'PROTECTION_CONFLICT')
        if any(m.intersects(win, other) for other in windows[:index]): m.reject('连接窗口互相覆盖。', 'PROTECTION_CONFLICT')
        originals = ordered([n for n in notes if m.intersects(support(n), win)])
        if m.canonical(win['original_notes']) != m.canonical(originals) or any(n['start_tick'] < win['start_tick'] or support(n)['end_tick'] > win['end_tick'] for n in originals):
            m.reject('连接原音符快照错误或切断完整发声。', 'PROTECTION_CONFLICT')
        m.shape(win['context'], 'left right motif_note_ids')
        left, right = window_context(request, win, windows)
        if m.canonical([win['context']['left'], win['context']['right']]) != m.canonical([left, right]): m.reject('连接端点不是实际bridge后音乐。', 'INVALID_CONNECTION')
        allowed = {n['id'] for n in originals + [n for n in (left, right) if n]}
        motifs = win['context']['motif_note_ids']
        if not isinstance(motifs, list) or not motifs or len(motifs) != len(set(motifs)) or not set(motifs) <= allowed:
            m.reject('连接动机没有真实相邻父音符。', 'INVALID_CONNECTION')
        for reason in m.objects(win['reasons']): b.warning_check(reason)
        if not win['reasons']: m.reject('连接改写缺少取舍原因。', 'INVALID_CONNECTION')
        key = win['key_context']; m.shape(key, 'tonic mode confidence method'); m.integer(key['tonic'], 0, 11)
        if key['mode'] not in ('major', 'minor') or type(key['confidence']) not in (int, float) or not math.isfinite(key['confidence']) or not 0 <= key['confidence'] <= 1:
            m.reject('连接调性记录无效。', 'INVALID_CONNECTION')
        m.ident(key['method']); m.shape(win['parameters'], 'target_ticks unit_ticks')
        if win['parameters']['target_ticks'] != size or type(win['parameters']['target_ticks']) is not int or type(win['parameters']['unit_ticks']) is not int or win['parameters']['unit_ticks'] not in (1, 10):
            m.reject('连接精确时值参数不匹配。', 'INVALID_CONNECTION')
        if win['parameters']['unit_ticks'] == 10 and any(n[k] % 10 for n in originals + [n for n in (left, right) if n] for k in ('start_tick', 'duration_tick')):
            m.reject('连接不能隐式量化真实端点。', 'OUTPUT_TIME_UNREPRESENTABLE')
    joints = m.objects(proposal['joint_boundary_conditions']); m.indexed(joints)
    expected = {(a['id'], z['id']) for a in windows for z in windows if a['end_tick'] == z['start_tick']}
    seen = set(); by_id = m.indexed(windows)
    for joint in joints:
        m.shape(joint, 'id left_connection_id right_connection_id tick relation left_endpoint right_endpoint')
        pair = (joint['left_connection_id'], joint['right_connection_id'])
        if pair not in expected or pair in seen: m.reject('连接共同边界缺失、重复或引用错误。', 'INVALID_CONNECTION')
        seen.add(pair); m.ident(joint['relation'])
        m.integer(joint['tick'], 0, total)
        if joint['tick'] != by_id[pair[0]]['end_tick']: m.reject('共同边界位置不符。', 'INVALID_CONNECTION')
        for which, owner in [('left', pair[0]), ('right', pair[1])]:
            endpoint = joint[which + '_endpoint']; win = by_id[owner]
            if endpoint is not None:
                m.shape(endpoint, 'pitch start_tick duration_tick'); m.integer(endpoint['pitch'], 0, 127)
                m.integer(endpoint['start_tick'], win['start_tick']); m.integer(endpoint['duration_tick'], 1)
                if support(endpoint)['end_tick'] > win['end_tick']: m.reject('共同端点越界。', 'INVALID_CONNECTION')
    if seen != expected: m.reject('相邻连接未统一确定共同端点。', 'INVALID_CONNECTION')


def make_plan(request, proposal):
    validate_proposal(request, proposal)
    bridge = request['bridge_ref']['plan']
    plan = dict(schema='emoblocks.connection-plan.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        id=request['plan_id'], version=request['plan_version'], request_id=request['request_id'], snapshot_id=request['snapshot_id'],
        request_fingerprint=request_fingerprint(request), bridge_plan_id=bridge['id'], bridge_plan_version=bridge['version'],
        bridge_plan_fingerprint=bridge['plan_fingerprint'], layout_fingerprint=request['layout_fingerprint'],
        protection_summary_fingerprint=request['protection_summary']['fingerprint'],
        **{k: copy.deepcopy(proposal[k]) for k in ('decision', 'none_reason', 'windows', 'reasons', 'assessments', 'joint_boundary_conditions', 'search')})
    plan['plan_fingerprint'] = plan_fingerprint(plan)
    return plan


@guard
def validate_plan(request, plan):
    m.shape(plan, PLAN_FIELDS); version(plan, 'emoblocks.connection-plan.v1')
    m.integer(plan['version'], 1)
    if plan_fingerprint(plan) != plan['plan_fingerprint']: m.reject('连接计划指纹错误。', 'PLAN_VERSION_MISMATCH')
    proposal = dict(schema='emoblocks.connection-proposal.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        request_fingerprint=request_fingerprint(request), **{k: plan[k] for k in
            ('decision', 'none_reason', 'windows', 'reasons', 'assessments', 'joint_boundary_conditions', 'search')})
    if plan != make_plan(request, proposal): m.reject('连接计划与bridge版本或保护摘要不匹配。', 'PLAN_VERSION_MISMATCH')


def result_header(request, plan, connection_id):
    win = next((w for w in plan['windows'] if w['id'] == connection_id), None)
    if win is None: m.reject('连接结果不属于本次计划。', 'PLAN_VERSION_MISMATCH')
    return dict(schema='emoblocks.connection-result.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        request_id=request['request_id'], snapshot_id=request['snapshot_id'], request_fingerprint=request_fingerprint(request),
        plan_id=plan['id'], plan_version=plan['version'], plan_fingerprint=plan['plan_fingerprint'], connection_id=connection_id,
        range={k: win[k] for k in ('start_tick', 'end_tick')}, original_notes=copy.deepcopy(win['original_notes']))


def failure_result(request, plan, connection_id, failure, status='FAILED'):
    return dict(**result_header(request, plan, connection_id), status=status, notes=[], operations=[], generation=None,
                content_fingerprint=None, error=copy.deepcopy(failure))


def music_signature(notes):
    return sorted((n['pitch'], n['start_tick'], n['duration_tick']) for n in notes)


def validate_development(window, notes, operations):
    original = window['original_notes']; technique = window['technique']
    if len(notes) < 2 or music_signature(notes) == music_signature(original):
        m.reject('连接必须有真实旋律或节奏发展，不能只换标签或单音改高。', 'NO_CONNECTION_DEVELOPMENT')
    if technique in ('diatonic_guide', 'motif_reply', 'density_shift') and any(n['pitch'] % 12 not in scale_pitches(window['key_context']) for n in notes):
        m.reject('连接未兑现调内规则。', 'INVALID_CONNECTION')
    if technique == 'diatonic_guide' and window['context']['right'] and abs(notes[-1]['pitch'] - window['context']['right']['pitch']) > abs(notes[0]['pitch'] - window['context']['right']['pitch']):
        m.reject('调内连接没有朝真实后方入口导向。', 'NO_CONNECTION_DEVELOPMENT')
    if technique == 'motif_reply' and (len(notes) < 3 or len({n['pitch'] for n in notes}) < 2 or len({op['input_note_id'] for op in operations if op['rule'] != 'preserve'}) < 2):
        m.reject('回应必须发展多个真实动机发声。', 'NO_CONNECTION_DEVELOPMENT')
    if technique == 'density_shift' and len(notes) == len(original): m.reject('疏密连接没有实际攻击数量变化。', 'NO_CONNECTION_DEVELOPMENT')
    if technique == 'retain_develop':
        middle = (window['start_tick'] + window['end_tick']) / 2
        if any(n not in notes for n in original if support(n)['end_tick'] <= middle): m.reject('连接没有保留原句前段。', 'NO_CONNECTION_DEVELOPMENT')
        later = [n for n in notes if n['start_tick'] >= middle]
        if not any(op['rule'] != 'preserve' and op['start_tick'] >= middle for op in operations) or music_signature(later) == music_signature([n for n in original if n['start_tick'] >= middle]):
            m.reject('连接后段没有实际展开。', 'NO_CONNECTION_DEVELOPMENT')
    if technique == 'breath_close' and support(notes[-1])['end_tick'] > window['end_tick'] - max(1, min(120, (window['end_tick'] - window['start_tick']) // 8)):
        m.reject('收束没有保留真实句尾呼吸。', 'NO_CONNECTION_DEVELOPMENT')


@guard
def validate_result(request, plan, result):
    validate_plan(request, plan)
    m.shape(result, RESULT_FIELDS); version(result, 'emoblocks.connection-result.v1')
    m.integer(result['plan_version'], 1); m.range_check(result['range'], request['actual_layout']['total_ticks'])
    header = result_header(request, plan, result['connection_id'])
    if any(result[k] != v for k, v in header.items()): m.reject('连接结果身份、范围或原音符不匹配。', 'PLAN_VERSION_MISMATCH')
    if result['status'] in ('FAILED', 'CANCELLED'):
        b.warning_check(result['error'])
        if result['notes'] != [] or result['operations'] != [] or result['generation'] is not None or result['content_fingerprint'] is not None:
            m.reject('失败连接不能冒充实际音乐。', 'INVALID_CONNECTION')
        return
    if result['status'] != 'READY' or result['error'] is not None: m.reject('连接结果状态无效。', 'INVALID_CONNECTION')
    win = next(w for w in plan['windows'] if w['id'] == result['connection_id'])
    notes = result['notes']; m.notes_check(notes, request['actual_layout']['total_ticks'], m.source_index(request['actual_layout']['base_project']['sources']))
    b.monotone_notes(notes)
    if notes != ordered(notes) or len(notes) > request['parameters']['max_notes'] or any(n['start_tick'] < win['start_tick'] or support(n)['end_tick'] > win['end_tick'] for n in notes):
        m.reject('连接实际音符越过窗口或超出预算。', 'PROTECTION_CONFLICT')
    if any(m.intersects(support(n), r) for n in notes for r in forbidden_ranges(request)):
        m.reject('连接实际延音侵入bridge或其他保护。', 'PROTECTION_CONFLICT')
    parents = m.indexed(request['actual_layout']['notes']); operations = result['operations']
    if len(operations) != len(notes): m.reject('连接来源账本没有逐音符覆盖。', 'INVALID_CONNECTION')
    for n, op in zip(notes, operations):
        m.shape(op, 'operation input_note_id parent_ref output_note_id rule from_pitch to_pitch start_tick duration_tick')
        for key in ('from_pitch', 'to_pitch'): m.integer(op[key], 0, 127)
        m.integer(op['start_tick']); m.integer(op['duration_tick'], 1)
        parent = parents.get(op['input_note_id'])
        if (parent is None or parent['id'] not in win['context']['motif_note_ids'] or op['operation'] != 'connection-motif-cell'
                or op['parent_ref'] != parent_ref(request, parent['id']) or op['output_note_id'] != n['id']
                or op['from_pitch'] != parent['pitch'] or op['to_pitch'] != n['pitch']
                or any(op[k] != n[k] for k in ('start_tick', 'duration_tick'))):
            m.reject('连接音符未回指实际动机父快照或操作。', 'INVALID_CONNECTION')
        if op['rule'] == 'preserve':
            if n != parent or n not in win['original_notes']: m.reject('保留发声实际被改写。', 'INVALID_CONNECTION')
        elif op['rule'] != win['technique'] or n['id'] in parents or n['origin'] != parent['origin'] or n['lineage'] != list(dict.fromkeys(parent['lineage'] + [parent['id']])) or n['slice'] is not None:
            m.reject('连接派生身份、来源或完整血缘错误。', 'INVALID_CONNECTION')
    if m.canonical(result['generation']) != m.canonical(generation_data(request, plan, win, operations)):
        m.reject('连接参数、种子、输入或来源摘要错误。', 'INVALID_CONNECTION')
    validate_development(win, notes, operations)
    for joint in plan['joint_boundary_conditions']:
        for which in ('left', 'right'):
            if joint[which + '_connection_id'] != win['id']: continue
            n = notes[-1] if which == 'left' else notes[0]; ep = joint[which + '_endpoint']
            if ep is not None and ep != {k: n[k] for k in ('pitch', 'start_tick', 'duration_tick')}:
                m.reject('连接实际首尾没有兑现共同端点。', 'PROTECTION_CONFLICT')
            if ep is None and (support(n)['end_tick'] >= win['end_tick'] if which == 'left' else n['start_tick'] <= win['start_tick']):
                m.reject('连接声称边界休止但实际有发声。', 'PROTECTION_CONFLICT')
    if result['content_fingerprint'] != content_fingerprint(result['range'], notes): m.reject('连接内容指纹错误。', 'INVALID_CONNECTION')


def splice(request, plan, results):
    removed = {n['id'] for w in plan['windows'] for n in w['original_notes']}
    notes = [n for n in request['actual_layout']['notes'] if n['id'] not in removed]
    notes += [n for r in results if r['status'] == 'READY' for n in r['notes']]
    return ordered(notes)


def capabilities(ready=False):
    return dict(score_scope='CONNECTION_STAGE', can_plan_boundaries=bool(ready), can_apply=False, can_audition=False, can_export_final=False)


def raw_outcome(request, plan, results, status='SUCCEEDED', failure=None):
    return dict(schema='emoblocks.connection-raw-outcome.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        request_fingerprint=request_fingerprint(request), plan_id=plan['id'], plan_version=plan['version'], status=status,
        results=copy.deepcopy(results), error=copy.deepcopy(failure))


def make_outcome(request, plan, results, status, failure=None):
    notes = splice(request, plan, results) if status == 'SUCCEEDED' and plan is not None else None
    return dict(schema='emoblocks.connection-outcome.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        request_fingerprint=request_fingerprint(request), plan_id=request['plan_id'], plan_version=request['plan_version'],
        plan_fingerprint=plan['plan_fingerprint'] if plan else None, status=status, results=copy.deepcopy(results), notes=notes,
        content_fingerprint=splice_fingerprint(request['actual_layout']['total_ticks'], notes) if notes is not None else None,
        layout_fingerprint=request['layout_fingerprint'], protection_summary=request['protection_summary']['fingerprint'],
        remaining_gaps=copy.deepcopy(request['actual_layout']['remaining_gaps']), error=copy.deepcopy(failure),
        capabilities=capabilities(status == 'SUCCEEDED'))


@guard
def validate_raw(request, plan, raw):
    validate_plan(request, plan)
    m.shape(raw, 'schema spec_rev contract_rev request_fingerprint plan_id plan_version status results error')
    version(raw, 'emoblocks.connection-raw-outcome.v1'); m.integer(raw['plan_version'], 1)
    if (raw['request_fingerprint'], raw['plan_id'], raw['plan_version']) != (request_fingerprint(request), plan['id'], plan['version']):
        m.reject('连接集合计划或输入版本错误。', 'PLAN_VERSION_MISMATCH')
    ids = [r['connection_id'] for r in m.objects(raw['results'])]
    if len(ids) != len(set(ids)) or set(ids) != {w['id'] for w in plan['windows']}:
        m.reject('连接集合缺失、重复或有额外结果。', 'INVALID_CONNECTION')
    for result in raw['results']: validate_result(request, plan, result)
    if raw['status'] == 'SUCCEEDED':
        if raw['error'] is not None or any(r['status'] != 'READY' for r in raw['results']): m.reject('连接尚未全部就绪。', 'INVALID_CONNECTION')
        notes = splice(request, plan, raw['results'])
        m.notes_check(notes, request['actual_layout']['total_ticks'], m.source_index(request['actual_layout']['base_project']['sources'])); b.monotone_notes(notes)
        before = request['actual_layout']['notes']
        protected = request['protection_summary']['ranges']
        def inside(values): return ordered([n for n in values if any(m.intersects(support(n), r) for r in protected)])
        if inside(before) != inside(notes): m.reject('连接实际拼接改变保护发声或保护休止。', 'PROTECTION_CONFLICT')
        for lock in request['actual_layout']['protections']:
            if lock['kind'] == 'bridge': m.validate_protected_notes([lock], notes)
        writable = plan['windows']
        def outside(values): return ordered([n for n in values if not any(m.intersects(support(n), w) for w in writable)])
        if outside(before) != outside(notes): m.reject('连接实际改写超出允许影响范围。', 'PROTECTION_CONFLICT')
    elif raw['status'] in ('FAILED', 'CANCELLED'): b.warning_check(raw['error'])
    else: m.reject('连接终态无效。', 'INVALID_CONNECTION')


@guard
def validate_outcome(request, plan, outcome):
    m.shape(outcome, OUTCOME_FIELDS); version(outcome, 'emoblocks.connection-outcome.v1'); m.integer(outcome['plan_version'], 1)
    if plan is None:
        if outcome['status'] not in ('FAILED', 'CANCELLED') or outcome['results'] != []: m.reject('未发布连接计划不能就绪。', 'INVALID_CONNECTION')
        b.warning_check(outcome['error'])
    else:
        validate_raw(request, plan, raw_outcome(request, plan, outcome['results'], outcome['status'], outcome['error']))
    if outcome != make_outcome(request, plan, outcome['results'], outcome['status'], outcome['error']):
        m.reject('连接拼接、能力或持久化摘要错误。', 'INVALID_CONNECTION')


def preview(request, plan, results, outcome=None):
    if plan is None: return None
    ref = request['bridge_ref']; view = b.preview(ref['request'], ref['plan'], ref['protections'], ref['results'], ref['outcome'])
    view['notes'] = copy.deepcopy(outcome['notes'] if outcome and outcome['status'] == 'SUCCEEDED' else request['actual_layout']['notes'])
    rows = {r['connection_id']: r for r in results}; overlays = []
    for win in plan['windows']:
        result = rows.get(win['id']); ready = result is not None and result['status'] == 'READY'
        overlays.append(dict(id=win['id'], range={k: win[k] for k in ('start_tick', 'end_tick')},
            status='CONTENT_READY' if ready else 'ALLOCATED', result_status=result['status'] if result else None,
            notes=copy.deepcopy(result['notes']) if ready else [], reasons=copy.deepcopy(win['reasons']),
            error=copy.deepcopy(result['error']) if result else None))
    view['connection_overlays'] = overlays
    return view


@guard
def validate_attempt(attempt, snapshots, attempts):
    m.shape(attempt, 'id snapshot_id input_fingerprint state records protections staged_materials error connection')
    stage = attempt['connection']; m.shape(stage, 'schema spec_rev contract_rev request phase plan results outcome')
    version(stage, 'emoblocks.connection-attempt.v1'); request = stage['request']; validate_request(request)
    snap = snapshots.get(attempt['snapshot_id']); ref = request['bridge_ref']; parent = attempts.get(ref['attempt_id'])
    if (snap is None or snap['project'] != request['input_project'] or snap['id'] != request['snapshot_id']
            or attempt['id'] != request['request_id'] or attempt['input_fingerprint'] != request['input_fingerprint']
            or snap['content_fingerprint'] != request['input_fingerprint']): m.reject('连接缺少匹配输入快照。', 'STALE_SNAPSHOT')
    if (parent is None or 'bridge' not in parent or any(ref[k] != parent['bridge'][k] for k in ('request', 'plan', 'results', 'outcome'))
            or ref['protections'] != parent['protections']): m.reject('连接依赖的真实父bridge不可解析。', 'STALE_SNAPSHOT')
    state = attempt['state']; plan = stage['plan']; rows = m.objects(stage['results']); outcome = stage['outcome']
    if state not in ('RUNNING', 'READY', 'FAILED', 'CANCELLED', 'INTERRUPTED', 'STALE'): m.reject('连接不能当作最终应用。', 'INVALID_CONNECTION')
    if state in ('RUNNING', 'READY') and parent['state'] != 'READY': m.reject('连接的父bridge已失效。', 'STALE_SNAPSHOT')
    if attempt['protections'] != ref['protections'] or attempt['records'] != [] or attempt['staged_materials'] != []:
        m.reject('连接暂存改变bridge保护或污染库。', 'PROTECTION_CONFLICT')
    if stage['phase'] not in ('CONNECTION_PLANNING', 'CONNECTION_PLANNED', 'CONNECTION_GENERATION', 'CONNECTIONS_READY'):
        m.reject('连接阶段状态无效。', 'INVALID_CONNECTION')
    if plan is None:
        if stage['phase'] != 'CONNECTION_PLANNING' or rows: m.reject('连接未发布计划却声称已生成。', 'INVALID_CONNECTION')
    else:
        validate_plan(request, plan)
        if stage['phase'] == 'CONNECTION_PLANNING': m.reject('连接计划不能退回规划阶段。', 'INVALID_CONNECTION')
        ids = []
        for result in m.objects(rows): validate_result(request, plan, result); ids.append(result['connection_id'])
        if len(ids) != len(set(ids)): m.reject('连接暂存实际结果重复。', 'INVALID_CONNECTION')
    if outcome is not None:
        validate_outcome(request, plan, outcome)
        if outcome['results'] != rows: m.reject('连接终态与流式事实不符。', 'INVALID_CONNECTION')
    if state in ('RUNNING', 'INTERRUPTED'):
        valid = outcome is None and attempt['error'] is None and stage['phase'] != 'CONNECTIONS_READY'
    elif state == 'READY':
        valid = plan is not None and outcome is not None and outcome['status'] == 'SUCCEEDED' and stage['phase'] == 'CONNECTIONS_READY' and attempt['error'] is None
    elif state in ('FAILED', 'CANCELLED'):
        valid = outcome is not None and outcome['status'] == state and attempt['error'] == outcome['error'] and stage['phase'] != 'CONNECTIONS_READY'
    else: valid = attempt['error'] == (outcome['error'] if outcome else None)
    if not valid: m.reject('连接状态、错误与实际音乐不一致。', 'INVALID_CONNECTION')


def plan_connection_blocks(request, should_cancel=None, on_progress=None):
    import story_engine
    return story_engine.plan_connection_request(request, should_cancel=should_cancel, on_progress=on_progress)


def generate_connection_blocks(request, plan, actual_layout, should_cancel=None, on_progress=None, on_result=None):
    import story_engine
    return story_engine.generate_connection_request(request, plan, actual_layout, should_cancel=should_cancel,
                                                    on_progress=on_progress, on_result=on_result)
