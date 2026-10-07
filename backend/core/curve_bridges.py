"""P5 private bridge facts and independent gates. Validators never compose music."""
import copy
import math
from functools import wraps

import curve_project as m
import curve_candidates as completion
import curve_memory as memory

REV = 'curve-workflow-v2-r3-p5'
ALGORITHM = 'curve-bridge-v1'
GLOBAL_ALGORITHM = 'curve-bridge-global-v2'
DEFAULTS = dict(policy='auto', max_windows=2, max_window_blocks=8, max_window_tests=128, max_notes=512)
LIMITS = dict(max_windows=8, max_window_blocks=32, max_window_tests=2048, max_notes=4096)
REQUEST_FIELDS = ('schema spec_rev contract_rev request_id snapshot_id session_id edit_revision input_contract_rev '
                  'input_fingerprint input_project input_kind completion_ref base_project base_fingerprint '
                  'resolved_ranges remaining_gaps base_notes protection_summary blank_regions plan_id plan_version '
                  'seed algorithm_version parameters')
PLAN_FIELDS = ('schema spec_rev contract_rev id version request_id snapshot_id input_fingerprint base_fingerprint '
               'candidate_id request_fingerprint decision windows inherited_bridge_ids protection_refs reasons '
               'assessments joint_boundary_conditions search range_lock_fingerprint plan_fingerprint')
RESULT_FIELDS = ('schema spec_rev contract_rev request_id snapshot_id request_fingerprint base_fingerprint '
                 'plan_id plan_version plan_fingerprint bridge_id protection_id origin range status base_material '
                 'material children emotion_processing operations notes content_fingerprint error')
OUTCOME_FIELDS = ('schema spec_rev contract_rev request_fingerprint plan_id plan_version plan_fingerprint status '
                  'results base_fingerprint notes content_fingerprint protection_summary remaining_gaps error capabilities')


def decide_bridge(request, should_cancel=None, on_progress=None):
    """Explicit background provider; never called by restoration or validators."""
    import story_engine
    return story_engine.decide_bridge_request(request, should_cancel=should_cancel, on_progress=on_progress)


def generate_bridges(request, plan, should_cancel=None, on_progress=None, on_result=None):
    import story_engine
    return story_engine.generate_bridge_request(request, plan, should_cancel=should_cancel,
                                               on_progress=on_progress, on_result=on_result)


def guard(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            if fn.__name__.startswith('validate_'):return m.cached_validation(fn,args,kwargs)
            return fn(*args, **kwargs)
        except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
            raise m.ProjectError('INVALID_BRIDGE', '桥接数据字段缺失或结构无效。') from exc
    return wrapped


def error(code, message, **details):
    return dict(code=code, message=message, details=details)


def warning_check(value):
    m.shape(value, 'code message details'); m.ident(value['code']); m.text(value['message'])
    if not isinstance(value['details'], dict): m.reject('桥接提示详情必须是对象。', 'INVALID_BRIDGE')
    m.canonical(value)


def version(value, schema):
    if (value['schema'], value['spec_rev'], value['contract_rev']) != (schema, m.SPEC_REV, REV):
        m.reject('桥接阶段版本不匹配。', 'UNSUPPORTED_VERSION')


def extent(p):
    return dict(start_tick=p['start_tick'], end_tick=p['start_tick'] + p['length_ticks'])


def support(n):
    return dict(start_tick=n['start_tick'], end_tick=n['start_tick'] + n['duration_tick'])


def ordered(notes):
    return sorted(copy.deepcopy(notes), key=lambda n: (n['start_tick'], n['pitch'], n['duration_tick'], n['id']))


def union(ranges):
    result = []
    for r in sorted(ranges, key=lambda v: (v['start_tick'], v['end_tick'])):
        if result and r['start_tick'] <= result[-1]['end_tick']:
            result[-1]['end_tick'] = max(result[-1]['end_tick'], r['end_tick'])
        else: result.append(copy.deepcopy(r))
    return result


def complement(ranges, total):
    cursor = 0; result = []
    for r in union(ranges):
        if cursor < r['start_tick']: result.append(dict(start_tick=cursor, end_tick=r['start_tick']))
        cursor = r['end_tick']
    if cursor < total: result.append(dict(start_tick=cursor, end_tick=total))
    return result


def actual_notes(project):
    result = ordered(m.current_notes(project))
    m.indexed(result)
    return result


def request_fingerprint(request):
    return m.digest('emoblocks.bridge-request.v1', request)


def plan_fingerprint(plan):
    return m.digest('emoblocks.bridge-plan.v1', {k: v for k, v in plan.items() if k != 'plan_fingerprint'})


def content_fingerprint(region, blank_mask, notes):
    return m.digest('emoblocks.bridge-content.v1', dict(range=region,
        blank_mask=sorted(blank_mask, key=lambda r: (r['start_tick'], r['end_tick'])), notes=ordered(notes)))


def splice_fingerprint(total, notes):
    return m.digest('emoblocks.bridge-splice.v1', dict(total_ticks=total, notes=ordered(notes)))


def parameters(values=None):
    if values is not None and (not isinstance(values, dict) or not set(values) <= set(DEFAULTS)):
        m.reject('未知bridge参数。', 'INVALID_PARAMETERS')
    result = dict(DEFAULTS, **(values or {}))
    if result['policy'] not in ('auto', 'none'): m.reject('桥接策略无效。', 'INVALID_PARAMETERS')
    for k, upper in LIMITS.items(): m.integer(result[k], 1, upper)
    return result


def inherited_locks(request):
    result = [p for p in request['base_project']['protections'] if p['kind'] == 'bridge']
    owners = [p['owner_id'] for p in result]
    if len(owners) != len(set(owners)): m.reject('同一桥身份存在多个活动保护。', 'PROTECTION_CONFLICT')
    return sorted(result, key=lambda p: p['owner_id'])


@guard
def make_request(project, completion_ref=None, token=None, seed=31, values=None, plan_id=None, plan_version=1,
                 *, algorithm_version=ALGORITHM):
    if algorithm_version not in (ALGORITHM, GLOBAL_ALGORITHM):
        m.reject('Unsupported bridge analysis version.', 'UNSUPPORTED_VERSION')
    m.validate(project); m.integer(seed, 0, 2**32-1); m.integer(plan_version, 1)
    if completion_ref is not None:
        m.shape(completion_ref, 'attempt_id candidate_id request candidate')
        m.ident(completion_ref['attempt_id']); m.ident(completion_ref['candidate_id'])
        previous = completion_ref['request']; candidate = completion_ref['candidate']
        completion.validate_request(previous); completion.validate_candidate(previous, candidate)
        if (previous['project'] != project or completion_ref['attempt_id'] != previous['request_id']
                or completion_ref['candidate_id'] != candidate['id']):
            m.reject('基础候选与当前输入或所属请求不匹配。', 'STALE_SNAPSHOT')
        base = candidate['project']; kind = 'completed_candidate'
    else:
        if m.gaps(project): m.reject('请先补全基础空缺或选择有效基础候选。', 'TARGET_GAPS_UNRESOLVED')
        base = project; kind = 'current_complete'
    if token is None:
        token = dict(request_id=m.uid(), snapshot_id=m.uid(), session_id=m.uid(), edit_revision=0,
                     input_fingerprint=m.fingerprint(project))
    for name in ('request_id', 'snapshot_id', 'session_id'): m.ident(token[name])
    m.integer(token['edit_revision'])
    if token['input_fingerprint'] != m.fingerprint(project): m.reject('捕获输入指纹不匹配。', 'STALE_SNAPSHOT')
    gaps = completion.gap_items(base)
    request = dict(schema='emoblocks.bridge-request.v1', spec_rev=m.SPEC_REV, contract_rev=REV,
        request_id=token['request_id'], snapshot_id=token['snapshot_id'], session_id=token['session_id'],
        edit_revision=token['edit_revision'], input_contract_rev=project['contract_rev'],
        input_fingerprint=token['input_fingerprint'], input_project=copy.deepcopy(project), input_kind=kind,
        completion_ref=copy.deepcopy(completion_ref), base_project=copy.deepcopy(base), base_fingerprint=m.fingerprint(base),
        resolved_ranges=complement(gaps, base['total_ticks']), remaining_gaps=gaps, base_notes=actual_notes(base),
        protection_summary=dict(fingerprint=m.protection_summary(base['protections']),
            ranges=[dict(start_tick=a, end_tick=b) for a, b in memory.protected_ranges(base['protections'])]),
        blank_regions=copy.deepcopy(base['blank_regions']), plan_id=m.uid() if plan_id is None else plan_id,
        plan_version=plan_version, seed=seed, algorithm_version=algorithm_version, parameters=parameters(values))
    m.ident(request['plan_id']); inherited_locks(request)
    return request


@guard
def validate_request(request):
    m.canonical(request); m.shape(request, REQUEST_FIELDS); version(request, 'emoblocks.bridge-request.v1')
    if request['algorithm_version'] not in (ALGORITHM, GLOBAL_ALGORITHM): m.reject('桥接算法版本不受支持。', 'UNSUPPORTED_VERSION')
    token = {k: request[k] for k in ('request_id', 'snapshot_id', 'session_id', 'edit_revision', 'input_fingerprint')}
    expected = make_request(request['input_project'], request['completion_ref'], token, request['seed'],
                            request['parameters'], request['plan_id'], request['plan_version'],
                            algorithm_version=request['algorithm_version'])
    if request != expected: m.reject('桥接请求与真实输入、基础候选或保护不一致。', 'STALE_SNAPSHOT')


def blank_mask(request, window):
    return [dict(start_tick=max(window['start_tick'], b['start_tick']), end_tick=min(window['end_tick'], b['end_tick']))
            for b in sorted(request['blank_regions'], key=lambda b: b['start_tick']) if m.intersects(b, window)]


def emotion_segments(request, window):
    return [dict(start_tick=max(window['start_tick'], p['start_tick']),
                 end_tick=min(window['end_tick'], extent(p)['end_tick']), emotion=p['emotion'])
            for p in sorted(request['base_project']['placements'], key=lambda p: (p['start_tick'], p['id']))
            if m.intersects(extent(p), window)]


def context_sides(request, window, windows):
    placements = [p for p in request['base_project']['placements']
                  if not any(m.intersects(extent(p), w) for w in windows)]
    lefts = [p for p in placements if extent(p)['end_tick'] <= window['start_tick']]
    rights = [p for p in placements if p['start_tick'] >= window['end_tick']]
    left = max(lefts, key=lambda p: (extent(p)['end_tick'], p['id'])) if lefts else None
    right = min(rights, key=lambda p: (p['start_tick'], p['id'])) if rights else None
    return tuple(dict(placement_id=p['id'], notes=__import__('curve_application').context_notes(request['base_project'],p)) if p else None for p in (left, right))


def parent_ref(request, emission_id):
    if request['base_project']['contract_rev'] == 'curve-workflow-v2-r3-p7':
        from curve_application import accepted_overlay, accepted_parent_ref
        active = accepted_overlay(request['base_project'])
        carry = any(r['kind']=='captured_music' and r['status']=='READY' for r in request['base_project']['records'])
        physical={n['id']:n for p in request['base_project']['placements'] for n in m.placed_notes(p)}
        actual={n['id']:n for n in m.current_notes(request['base_project'])}
        if (active or carry) and physical.get(emission_id)!=actual.get(emission_id):
            if any(r['kind']=='final_score' and r['payload'].get('p7') and any(n['id']==emission_id for n in r['payload']['p7']['final_score']['notes']) for r in request['base_project']['records']):
                return accepted_parent_ref(request['base_project'], emission_id)
    for place in request['base_project']['placements']:
        material = place['emotion_variant'] or place['base_snapshot']
        for n in material['notes']:
            if place['id'] + ':' + n['id'] != emission_id: continue
            base = place['base_snapshot']; path = []
            if base['kind'] == 'combination':
                ids = {n['id'], *n['lineage']}
                parent = next((v for v in base['notes'] if v['id'] in ids), None)
                if parent is None: m.reject('组合变体缺少具体基础发声。', 'INVALID_BRIDGE')
                current = base; offset = 0
                while current['kind'] == 'combination':
                    child = next((c for c in current['children']
                        if offset+c['offset_tick']<=parent['start_tick']
                        <offset+c['offset_tick']+c['snapshot']['length_ticks']),None)
                    if child is None: m.reject('组合动机路径不可解析。', 'INVALID_BRIDGE')
                    path.append(child['occurrence_id']);offset+=child['offset_tick']
                    current = child['snapshot']
            return dict(placement_id=place['id'], component_path=path, material_snapshot_id=material['id'], note_id=n['id'])
    m.reject('动机父音符不属于实际基础排布。', 'INVALID_BRIDGE')


@guard
def validate_proposal(request, proposal):
    validate_request(request)
    m.shape(proposal, 'schema spec_rev contract_rev request_fingerprint decision windows reasons assessments joint_boundary_conditions search')
    version(proposal, 'emoblocks.bridge-proposal.v1')
    if proposal['request_fingerprint'] != request_fingerprint(request): m.reject('选位输入已失效。', 'STALE_SNAPSHOT')
    if proposal['decision'] not in ('none', 'selected'): m.reject('需要明确桥决策。', 'INVALID_BRIDGE')
    windows = m.indexed(proposal['windows'])
    if (bool(windows) != (proposal['decision'] == 'selected') or len(windows) > request['parameters']['max_windows']
            or (request['parameters']['policy'] == 'none' and windows)):
        m.reject('桥决策与完整窗口集合不一致。', 'INVALID_BRIDGE')
    if not m.objects(proposal['reasons']): m.reject('桥决策缺少理由。', 'INVALID_BRIDGE')
    for reason in proposal['reasons']: warning_check(reason)
    for item in m.objects(proposal['assessments']):
        if not isinstance(item, dict): m.reject('选位评价必须是对象。', 'INVALID_BRIDGE')
        m.canonical(item)
    m.shape(proposal['search'], 'tested_windows termination')
    m.integer(proposal['search']['tested_windows'], 0, request['parameters']['max_window_tests'])
    m.ident(proposal['search']['termination'])
    parents = m.indexed(request['base_notes']); total = request['base_project']['total_ticks']
    for w in windows.values():
        m.shape(w, 'id start_tick end_tick placement_ids context emotion_segments blank_mask')
        m.range_check({k: w[k] for k in ('start_tick','end_tick')}, total)
        if w['end_tick']-w['start_tick'] > request['parameters']['max_window_blocks']*m.BAR:
            m.reject('桥窗口超出本次范围预算。','INVALID_PARAMETERS')
        if not any(r['start_tick'] <= w['start_tick'] and w['end_tick'] <= r['end_tick'] for r in request['resolved_ranges']):
            m.reject('桥窗口跨越未解决空缺。', 'TARGET_GAPS_UNRESOLVED')
        if any(m.intersects(w, r) for r in request['protection_summary']['ranges']):
            m.reject('桥窗口侵入记忆、主题、手工或既有桥保护。', 'PROTECTION_CONFLICT')
        if any(m.intersects(w,support(n)) for p in request['base_project']['protections'] for n in p['notes']):
            m.reject('桥窗口侵入保护音符的完整支撑。','PROTECTION_CONFLICT')
        if any(m.intersects(w, other) for other in windows.values() if other['id'] != w['id']):
            m.reject('桥窗口互相覆盖。', 'PROTECTION_CONFLICT')
        for n in parents.values():
            r = support(n)
            if m.intersects(w, r) and not (w['start_tick'] <= r['start_tick'] and r['end_tick'] <= w['end_tick']):
                m.reject('桥窗口切断完整跨界音符。', 'PROTECTION_CONFLICT')
        expected_ids = [p['id'] for p in sorted(request['base_project']['placements'], key=lambda p: (p['start_tick'],p['id'])) if m.intersects(extent(p),w)]
        if (w['placement_ids'] != expected_ids or w['blank_mask'] != blank_mask(request,w)
                or w['emotion_segments'] != emotion_segments(request,w) or not expected_ids):
            m.reject('桥窗口覆盖对象、情绪位置或留白不匹配。', 'INVALID_BRIDGE')
        m.shape(w['context'], 'left right motif_note_ids key_context')
        left, right = context_sides(request,w,list(windows.values()))
        if w['context']['left'] != left or w['context']['right'] != right:
            m.reject('桥上下文必须来自未覆盖的实际邻接排布。', 'INVALID_BRIDGE')
        allowed = {n['id'] for n in parents.values() if m.intersects(support(n),w)}
        for side in (left,right):
            if side: allowed.update(n['id'] for n in side['notes'])
        motifs = m.objects(w['context']['motif_note_ids'])
        if not motifs or len(motifs) != len(set(motifs)) or not set(motifs) <= allowed:
            m.reject('桥动机引用未知或无关的实际音符。', 'INVALID_BRIDGE')
        key = w['context']['key_context']
        if not isinstance(key,dict) or not {'tonic','mode','confidence','method'} <= set(key): m.reject('桥调性记录不完整。', 'INVALID_BRIDGE')
        m.integer(key['tonic'],0,11); m.ident(key['method'])
        if key['mode'] not in ('major','minor') or isinstance(key['confidence'],bool) or not isinstance(key['confidence'],(int,float)) or not math.isfinite(key['confidence']) or key['confidence']<0:
            m.reject('桥调性记录无效。', 'INVALID_BRIDGE')
    seen = set()
    for joint in m.objects(proposal['joint_boundary_conditions']):
        m.shape(joint, 'id left_bridge_id right_bridge_id tick relation reasons left_endpoint right_endpoint')
        m.ident(joint['id']); m.ident(joint['relation'])
        if joint['id'] in seen: m.reject('共同边界重复。', 'INVALID_BRIDGE')
        seen.add(joint['id'])
        a,b = windows.get(joint['left_bridge_id']), windows.get(joint['right_bridge_id'])
        if a is None or b is None or a['end_tick'] != b['start_tick'] or joint['tick'] != b['start_tick']:
            m.reject('共同边界必须绑定真实相邻桥。', 'INVALID_BRIDGE')
        for reason in m.objects(joint['reasons']): warning_check(reason)
        for name,w in (('left_endpoint',a),('right_endpoint',b)):
            ep = joint[name]
            if ep is None: continue
            m.shape(ep,'pitch start_tick duration_tick'); m.integer(ep['pitch'],0,127)
            m.integer(ep['start_tick'],w['start_tick'],w['end_tick']-1); m.integer(ep['duration_tick'],1)
            if ep['start_tick']+ep['duration_tick']>w['end_tick'] or any(m.intersects(support(ep),mask) for mask in w['blank_mask']):
                m.reject('共同边界端点越界或进入留白。', 'PROTECTION_CONFLICT')
    adjacent = {(a['id'],b['id']) for a in windows.values() for b in windows.values() if a['end_tick']==b['start_tick']}
    declared = [(j['left_bridge_id'],j['right_bridge_id']) for j in proposal['joint_boundary_conditions']]
    if len(declared)!=len(set(declared)) or set(declared)!=adjacent:
        m.reject('相邻桥缺少唯一冻结共同边界。', 'INVALID_BRIDGE')


def initial_locks(request, plan):
    refs = {r['bridge_id']:r['protection_id'] for r in plan['protection_refs']}
    locks = copy.deepcopy(request['base_project']['protections'])
    for w in plan['windows']:
        locks.append(dict(id=refs[w['id']],kind='bridge',owner_id=w['id'],placement_id=None,component_path=[],
            start_tick=w['start_tick'],end_tick=w['end_tick'],status='RANGE_LOCKED',origin='automatic',
            plan_id=plan['id'],plan_version=plan['version'],input_fingerprint=request['input_fingerprint'],
            notes=[],structure_fingerprint=None,blank_mask=copy.deepcopy(w['blank_mask'])))
    return locks


@guard
def make_plan(request, proposal):
    validate_proposal(request,proposal)
    inherited = inherited_locks(request)
    refs = [dict(bridge_id=p['owner_id'],protection_id=p['id']) for p in inherited]
    refs += [dict(bridge_id=w['id'],protection_id=m.digest('emoblocks.bridge-lock.v1',
                [request_fingerprint(request),request['plan_id'],request['plan_version'],w['id']])) for w in proposal['windows']]
    plan = dict(schema='emoblocks.bridge-plan.v1',spec_rev=m.SPEC_REV,contract_rev=REV,
        id=request['plan_id'],version=request['plan_version'],request_id=request['request_id'],snapshot_id=request['snapshot_id'],
        input_fingerprint=request['input_fingerprint'],base_fingerprint=request['base_fingerprint'],
        candidate_id=request['completion_ref']['candidate_id'] if request['completion_ref'] else None,
        request_fingerprint=request_fingerprint(request),decision=proposal['decision'],windows=copy.deepcopy(proposal['windows']),
        inherited_bridge_ids=[p['owner_id'] for p in inherited],protection_refs=refs,reasons=copy.deepcopy(proposal['reasons']),
        assessments=copy.deepcopy(proposal['assessments']),joint_boundary_conditions=copy.deepcopy(proposal['joint_boundary_conditions']),
        search=copy.deepcopy(proposal['search']),range_lock_fingerprint=None,plan_fingerprint=None)
    plan['range_lock_fingerprint']=m.protection_summary(initial_locks(request,plan))
    plan['plan_fingerprint']=plan_fingerprint(plan)
    validate_plan(request,plan)
    return plan


@guard
def validate_plan(request, plan):
    m.shape(plan,PLAN_FIELDS); version(plan,'emoblocks.bridge-plan.v1')
    expected = dict(id=request['plan_id'],version=request['plan_version'],request_id=request['request_id'],snapshot_id=request['snapshot_id'],
        input_fingerprint=request['input_fingerprint'],base_fingerprint=request['base_fingerprint'],request_fingerprint=request_fingerprint(request),
        candidate_id=request['completion_ref']['candidate_id'] if request['completion_ref'] else None)
    if any(plan[k]!=v for k,v in expected.items()): m.reject('桥计划输入、身份或版本不一致。','PLAN_VERSION_MISMATCH')
    proposal={k:copy.deepcopy(plan[k]) for k in ('spec_rev','contract_rev','request_fingerprint','decision','windows','reasons','assessments','joint_boundary_conditions','search')}
    proposal['schema']='emoblocks.bridge-proposal.v1'; validate_proposal(request,proposal)
    inherited=inherited_locks(request)
    if plan['inherited_bridge_ids']!=[p['owner_id'] for p in inherited]: m.reject('桥计划遗漏原保护。','PROTECTION_CONFLICT')
    refs={}
    for ref in m.objects(plan['protection_refs']):
        m.shape(ref,'bridge_id protection_id'); m.ident(ref['bridge_id']);m.ident(ref['protection_id'])
        if ref['bridge_id'] in refs: m.reject('桥保护映射重复。','PROTECTION_CONFLICT')
        refs[ref['bridge_id']]=ref['protection_id']
    if set(refs)!={w['id'] for w in plan['windows']}|set(plan['inherited_bridge_ids']) or len(set(refs.values()))!=len(refs):
        m.reject('桥保护映射不完整或有额外项。','PROTECTION_CONFLICT')
    originals=m.indexed(request['base_project']['protections'])
    if any(refs[p['owner_id']]!=p['id'] for p in inherited) or any(refs[w['id']] in originals for w in plan['windows']):
        m.reject('新桥改写原锁或继承映射错误。','PROTECTION_CONFLICT')
    if plan['range_lock_fingerprint']!=m.protection_summary(initial_locks(request,plan)) or plan['plan_fingerprint']!=plan_fingerprint(plan):
        m.reject('桥计划或初始范围锁指纹不匹配。','PROTECTION_CONFLICT')


def bridge_info(request, plan, bridge_id):
    ref = next((r for r in plan['protection_refs'] if r['bridge_id']==bridge_id),None)
    if ref is None: m.reject('结果包含未知或额外桥。','PLAN_VERSION_MISMATCH')
    window = next((w for w in plan['windows'] if w['id']==bridge_id),None)
    lock = next((p for p in initial_locks(request,plan) if p['id']==ref['protection_id']),None)
    return window, lock


def result_header(request, plan, bridge_id):
    window,lock = bridge_info(request,plan,bridge_id)
    return dict(schema='emoblocks.bridge-result.v1',spec_rev=m.SPEC_REV,contract_rev=REV,
        request_id=request['request_id'],snapshot_id=request['snapshot_id'],request_fingerprint=request_fingerprint(request),
        base_fingerprint=request['base_fingerprint'],plan_id=plan['id'],plan_version=plan['version'],
        plan_fingerprint=plan['plan_fingerprint'],bridge_id=bridge_id,protection_id=lock['id'],
        origin='automatic' if window else 'inherited',range={k:lock[k] for k in ('start_tick','end_tick')})


def failure_result(request, plan, bridge_id, failure, status='FAILED'):
    return dict(result_header(request,plan,bridge_id),status=status,base_material=None,material=None,children=[],
                emotion_processing=None,operations=[],notes=[],content_fingerprint=None,error=copy.deepcopy(failure))


def inherited_result(request, plan, bridge_id):
    _,lock=bridge_info(request,plan,bridge_id)
    if lock['status']!='CONTENT_READY':
        return failure_result(request,plan,bridge_id,error('BRIDGE_NOT_READY','已有桥范围仍未就绪，保护保留。'))
    project=request['base_project']; base=None; final=None
    if lock['origin']=='manual':
        place=next((p for p in project['placements'] if p['id']==lock['placement_id']),None)
        if place is not None:
            base=place['base_snapshot']; final=place['emotion_variant'] or base
            notes=(__import__('curve_application').context_notes(project,place) if project['contract_rev']=='curve-workflow-v2-r3-p7' else m.placed_notes(place))
    else:
        records=[r for r in project['records'] if r['kind']=='bridge_result' and r['status']=='READY'
            and r['payload']['bridge_id']==bridge_id and r['payload']['protection_id']==lock['id']
            and r['payload']['plan_id']==lock['plan_id'] and r['payload']['plan_version']==lock['plan_version']]
        parents=[r for r in project['records'] if r['id']==lock['plan_id'] and r['kind']=='bridge_plan'
            and r['status']=='READY' and r['version']==lock['plan_version']]
        if len(records)==1 and len(parents)==1:
            final=base=records[0]['payload']['material_snapshot']
            original=[dict(n,id=bridge_id+':'+n['id'],start_tick=lock['start_tick']+n['start_tick']) for n in final['notes']]
            if m.structural_notes(original)!=m.structural_notes(lock['notes']):
                m.reject('继承桥原记录与结构保护不匹配。','PROTECTION_CONFLICT')
            # The record and structural lock stay immutable. Current actual
            # performance may legally differ in velocity without rewriting melody.
            notes=[n for n in request['base_notes'] if m.intersects(support(n),lock)]
    if final is None:
        return failure_result(request,plan,bridge_id,error('BRIDGE_NOT_READY','已有桥没有可认证的就绪素材和原计划。'))
    if m.structural_notes(notes)!=m.structural_notes(lock['notes']):
        m.reject('继承桥与原保护实际音乐不符。','PROTECTION_CONFLICT')
    return dict(result_header(request,plan,bridge_id),status='READY',base_material=copy.deepcopy(base),material=copy.deepcopy(final),
        children=[],emotion_processing=None,operations=[],notes=ordered(notes),
        content_fingerprint=content_fingerprint({k:lock[k] for k in ('start_tick','end_tick')},lock['blank_mask'],notes),error=None)


def monotone_notes(notes):
    ordered_notes=ordered(notes)
    if any(a['start_tick']+a['duration_tick']>b['start_tick'] for a,b in zip(ordered_notes,ordered_notes[1:])):
        m.reject('桥接结果必须是合法单旋律。','INVALID_BRIDGE')


def joint_endpoints(plan, window):
    result=[]
    for j in plan['joint_boundary_conditions']:
        if j['left_bridge_id']==window['id']: result.append(('last',j['left_endpoint']))
        if j['right_bridge_id']==window['id']: result.append(('first',j['right_endpoint']))
    return result


def segment_protection_ranges(request, plan, window, segment, base):
    regions=[dict(start_tick=a,end_tick=b) for a,b in memory.protected_ranges(request['base_project']['protections'])
             if m.intersects(dict(start_tick=a,end_tick=b),window)]
    if window['start_tick']<segment['start_tick']:
        regions.append(dict(start_tick=window['start_tick'],end_tick=segment['start_tick']))
    if segment['end_tick']<window['end_tick']:
        regions.append(dict(start_tick=segment['end_tick'],end_tick=window['end_tick']))
    regions += copy.deepcopy(window['blank_mask'])
    for _,ep in joint_endpoints(plan,window):
        if ep: regions.append(support(ep))
    return union(regions)


def _emotion_result(request, plan, window, result):
    base=result['base_material']; final=result['material']; processing=result['emotion_processing']
    m.shape(processing,'pass_count algorithm_version segments')
    if type(processing['pass_count']) is not int or processing['pass_count']!=1 or processing['algorithm_version']!='curve-emotion-rules-v1':
        m.reject('桥情绪必须从基础快照处理一次。','INVALID_BRIDGE')
    entries=m.objects(processing['segments'])
    if len(entries)!=len(window['emotion_segments']): m.reject('桥情绪位置集合不完整。','INVALID_BRIDGE')
    picked=[]
    for entry,segment in zip(entries,window['emotion_segments']):
        m.shape(entry,'range emotion seed variant')
        if entry['range']!={k:segment[k] for k in ('start_tick','end_tick')} or entry['emotion']!=segment['emotion']:
            m.reject('桥情绪不能改写原情绪位置。','INVALID_BRIDGE')
        ranges=segment_protection_ranges(request,plan,window,segment,base)
        # Reuse the persisted P3 ledger gate with a private validation context;
        # these temporary authorisation ranges are not Project or saved locks.
        context=dict(sources=request['base_project']['sources'],intensity_points=request['base_project']['intensity_points'],
                     protections=[dict(kind='manual',start_tick=r['start_tick'],end_tick=r['end_tick']) for r in ranges])
        placement=dict(id=window['id'],base_snapshot=base,start_tick=window['start_tick'],length_ticks=base['length_ticks'],emotion=entry['emotion'])
        variant=entry['variant']; m.integer(entry['seed'],0,2**32-1)
        seed=int(m.digest('emoblocks.bridge-emotion-seed.v1',dict(music_seed=base['generation']['seed'],
                 range=entry['range'],emotion=entry['emotion']))[:8],16)
        if entry['seed']!=seed or variant.get('generation',{}).get('seed')!=entry['seed']:
            m.reject('桥情绪种子记录不匹配。','INVALID_BRIDGE')
        completion._variant_check(context,placement,variant,allow_calm_snapshot=True)
        notes=m.indexed(variant['notes'])
        for n in base['notes']:
            start=window['start_tick']+n['start_tick']
            if not segment['start_tick']<=start<segment['end_tick']: continue
            changed_id=m.digest('emoblocks.emotion-note.v1',[variant['id'],n['id']])
            selected=notes.get(n['id']) or notes.get(changed_id)
            if selected is None: m.reject('桥情绪遗漏实际基础发声。','INVALID_BRIDGE')
            picked.append(copy.deepcopy(selected))
    if ordered(picked)!=ordered(final['notes']) or len(final['notes'])!=len(base['notes']):
        m.reject('最终桥不是一次情绪段处理的真实结果。','INVALID_BRIDGE')
    gen=final['generation']
    expected=dict(method='bridge_emotion_once',parameters=dict(pass_count=1,
            segments=[dict(range=e['range'],emotion=e['emotion'],seed=e['seed'],input_material_id=base['id']) for e in entries]),
        seed=base['generation']['seed'],rng_version='python.random-v3',algorithm_version=ALGORITHM,
        input_fingerprint=m.digest('emoblocks.bridge-emotion-input.v1',dict(base=base,segments=entries)),
        input_material_ids=[base['id']],base_notes=base['notes'],key_context=base['generation']['key_context'],
        operations=[dict(range=e['range'],emotion=e['emotion'],operations=e['variant']['generation']['operations']) for e in entries])
    if gen!=expected or final['id']!=m.digest('emoblocks.bridge-final-material.v1',dict(base=base,segments=entries)):
        m.reject('最终桥缺少未处理基础和一次情绪记录。','INVALID_BRIDGE')


def _children(parent, children, sources):
    if len(children)!=math.ceil(parent['length_ticks']/m.BAR): m.reject('桥乐句子块集合不完整。','INVALID_BRIDGE')
    m.indexed(children)
    for i,child in enumerate(children):
        m.material_check(child,sources)
        a=i*m.BAR;b=min(a+m.BAR,parent['length_ticks'])
        if (child['kind']!='block' or child['phrase_id']!=parent['id'] or child['length_ticks']!=b-a
                or child['id']!=m.digest('emoblocks.melody.phrase-block.v1',[parent['id'],a,b])
                or child['generation']!=parent['generation']
                or child['provenance'].get('relative_start_tick')!=a or child['children']):
            m.reject('桥子块必须来自实际完整母句，短尾不补长。','INVALID_BRIDGE')
        expected=[]
        for n in parent['notes']:
            left=max(a,n['start_tick']);right=min(b,n['start_tick']+n['duration_tick'])
            if right>left: expected.append((n,left,right))
        if len(child['notes'])!=len(expected): m.reject('桥子块遗漏或增加发声。','INVALID_BRIDGE')
        for n,(original,left,right) in zip(sorted(child['notes'],key=lambda n:n['start_tick']),expected):
            slice_ = original['slice']
            if left!=original['start_tick'] or right!=original['start_tick']+original['duration_tick']:
                slice_=dict(parent_emission_id=m.digest('emoblocks.melody.emission.v1',[parent['id'],original['id']]),
                            offset_tick=left-original['start_tick'],parent_duration_tick=original['duration_tick'])
            if (n['pitch']!=original['pitch'] or n['start_tick']!=left-a or n['duration_tick']!=right-left
                    or n['velocity']!=original['velocity'] or n['origin']!=original['origin']
                    or n['slice']!=slice_ or n['lineage']!=list(dict.fromkeys(original['lineage']+[original['id']]))
                    or n['id']!=m.digest('emoblocks.melody.slice-note.v1',[child['id'],original['id']])):
                m.reject('桥子块与真实母句音符或发声切片不符。','INVALID_BRIDGE')


@guard
def validate_result(request, plan, result):
    validate_plan(request,plan); m.canonical(result); m.shape(result,RESULT_FIELDS);version(result,'emoblocks.bridge-result.v1')
    header=result_header(request,plan,result['bridge_id'])
    if any(result[k]!=v for k,v in header.items()): m.reject('桥结果身份、输入、计划或保护不匹配。','PLAN_VERSION_MISMATCH')
    window,lock=bridge_info(request,plan,result['bridge_id'])
    if result['status'] not in ('READY','FAILED','CANCELLED'): m.reject('桥结果状态无效。','INVALID_BRIDGE')
    if result['status']!='READY':
        warning_check(result['error'])
        if any(result[k] is not None for k in ('base_material','material','emotion_processing','content_fingerprint')) or any(result[k]!=[] for k in ('children','operations','notes')):
            m.reject('失败桥不能冒充实际音乐。','INVALID_BRIDGE')
        return
    if result['error'] is not None: m.reject('就绪桥不能带失败错误。','INVALID_BRIDGE')
    if window is None:
        if result!=inherited_result(request,plan,result['bridge_id']): m.reject('继承桥不得被重新生成或改写。','PROTECTION_CONFLICT')
        return
    source_index=m.source_index(request['base_project']['sources'])
    base,final=result['base_material'],result['material']
    for material in (base,final):
        m.material_check(material,source_index); monotone_notes(material['notes'])
        if material['kind']!='phrase' or material['phrase_id'] is not None or material['children'] or material['length_ticks']!=window['end_tick']-window['start_tick'] or not material['notes']:
            m.reject('新桥必须有精确长度的完整非空母句。','INVALID_BRIDGE')
    if len(base['notes'])>request['parameters']['max_notes']: m.reject('桥音符超出生成预算。','INVALID_BRIDGE')
    gen=base['generation']
    required={'method','parameters','seed','rng_version','algorithm_version','input_fingerprint','input_material_ids','base_notes','key_context','operations'}
    if not isinstance(gen,dict) or not required<=set(gen) or gen['method']!='bridge_phrase' or gen['algorithm_version']!=ALGORITHM:
        m.reject('基础桥缺少真实作曲记录。','INVALID_BRIDGE')
    musical_joints=[dict(tick=j['tick'],relation=j['relation'],left_endpoint=j['left_endpoint'],right_endpoint=j['right_endpoint'])
                    for j in plan['joint_boundary_conditions'] if window['id'] in (j['left_bridge_id'],j['right_bridge_id'])]
    musical_joints.sort(key=m.canonical)
    seed=int(m.digest('emoblocks.bridge-music-seed.v1',dict(base_fingerprint=request['base_fingerprint'],seed=request['seed'],
             range=result['range'],joints=musical_joints))[:8],16)
    if gen['parameters'].get('target_ticks')!=base['length_ticks'] or gen['seed']!=seed or gen['key_context']!=window['context']['key_context']:
        m.reject('桥作曲参数、种子或调性与计划不匹配。','INVALID_BRIDGE')
    m.ident(gen['input_fingerprint']);m.ident(gen['rng_version'])
    parents=m.indexed(request['base_notes'])
    motifs=[parents[n] for n in window['context']['motif_note_ids']]
    endpoints=[None,None]
    for which,ep in joint_endpoints(plan,window):endpoints[0 if which=='first' else 1]=ep
    compose_input=dict(base_fingerprint=request['base_fingerprint'],range=result['range'],motif=motifs,
                       key=gen['key_context'],blank_mask=window['blank_mask'],endpoints=tuple(endpoints),
                       seed=seed,algorithm_version=ALGORITHM)
    if gen['input_fingerprint']!=m.digest('emoblocks.bridge-compose-input.v1',compose_input):
        m.reject('桥作曲输入指纹不匹配实际音乐上下文。','INVALID_BRIDGE')
    if base['id']!=m.digest('emoblocks.melody.bridge-phrase.v1',gen['input_fingerprint']) or gen['rng_version']!='python.random-v3':
        m.reject('桥母句身份或随机规则与捕获音乐输入不匹配。','INVALID_BRIDGE')
    if gen['base_notes']!=motifs or result['operations']!=gen['operations'] or len(result['operations'])!=len(base['notes']):
        m.reject('桥作曲账本必须回指实际动机父快照。','INVALID_BRIDGE')
    material_ids=set()
    for n,op in zip(base['notes'],result['operations']):
        m.shape(op,'operation input_note_id parent_ref output_note_id motif_index cycle_index rule from_pitch to_pitch start_tick duration_tick')
        if op['operation']!='bridge-motif-cell' or op['rule'] not in ('opening','sequence','answer','rhythm','arrival'):
            m.reject('桥音符缺少明确动机发展规则。','INVALID_BRIDGE')
        parent=parents.get(op['input_note_id']);m.integer(op['motif_index'],0,len(motifs)-1);m.integer(op['cycle_index'])
        if parent is None or window['context']['motif_note_ids'][op['motif_index']]!=parent['id'] or op['parent_ref']!=parent_ref(request,parent['id']):
            m.reject('桥父音符或重复组合路径错误。','INVALID_BRIDGE')
        material_ids.add(op['parent_ref'].get('material_snapshot_id') or op['parent_ref'].get('owner_id'))
        if (op['output_note_id']!=n['id'] or op['from_pitch']!=parent['pitch'] or op['to_pitch']!=n['pitch']
                or any(op[k]!=n[k] for k in ('start_tick','duration_tick'))
                or n['origin']!=parent['origin'] or n['lineage']!=list(dict.fromkeys(parent['lineage']+[parent['id']])) or n['slice'] is not None):
            m.reject('桥实际音高时间来源与具体父音符账本不符。','INVALID_BRIDGE')
    captured={parent_ref(request,n['id']).get('material_snapshot_id') or parent_ref(request,n['id']).get('owner_id') for n in motifs}
    if set(gen['input_material_ids'])!=captured: m.reject('桥生成素材来源集合错误。','INVALID_BRIDGE')
    placements=m.indexed(request['base_project']['placements']);snapshots={}
    for n in motifs:
        ref=parent_ref(request,n['id'])
        if ref.get('kind')=='accepted_score':
            from curve_application import source_score
            snapshots[ref['owner_id']]=source_score(request['base_project'],n['id'])
        else:
            place=placements[ref['placement_id']]
            snapshots[place['id']]=place['emotion_variant'] or place['base_snapshot']
    if base['provenance'].get('parent_snapshots')!=snapshots or final['provenance']!=base['provenance']:
        m.reject('桥来源快照不是实际动机放置。','INVALID_BRIDGE')
    _emotion_result(request,plan,window,result); _children(final,result['children'],source_index)
    notes=ordered([dict(n,id=window['id']+':'+n['id'],start_tick=n['start_tick']+window['start_tick']) for n in final['notes']])
    if result['notes']!=notes: m.reject('桥绝对音符与真实母句不符。','INVALID_BRIDGE')
    if any(m.intersects(support(n),mask) for n in notes for mask in window['blank_mask']):
        m.reject('桥主旋律或延音进入主动留白。','PROTECTION_CONFLICT')
    for which,ep in joint_endpoints(plan,window):
        actual=notes[-1] if which=='last' else notes[0]
        if ep is not None and {k:actual[k] for k in ('pitch','start_tick','duration_tick')}!=ep:
            m.reject('桥情绪后端点没有兑现冻结共同边界。','PROTECTION_CONFLICT')
        if ep is None and (actual['start_tick']+actual['duration_tick']>=window['end_tick'] if which=='last' else actual['start_tick']==window['start_tick']):
            m.reject('共同边界声明休止但实际存在边界发声。','PROTECTION_CONFLICT')
    if result['content_fingerprint']!=content_fingerprint(result['range'],window['blank_mask'],notes):
        m.reject('桥内容指纹与实际音符不匹配。','PROTECTION_CONFLICT')


def locks_with_results(request,plan,results):
    locks=initial_locks(request,plan);refs={r['bridge_id']:r for r in results}
    for lock in locks:
        result=refs.get(lock['owner_id']) if lock['kind']=='bridge' else None
        if result is not None and result['status']=='READY' and result['origin']=='automatic':
            lock['status']='CONTENT_READY';lock['notes']=copy.deepcopy(result['notes'])
            lock['structure_fingerprint']=m.structure_fingerprint(lock)
    return locks


def staged_materials(results):
    items=[]
    for r in results:
        if r['status']=='READY' and r['origin']=='automatic': items.extend([r['material']]+r['children'])
    m.indexed(items)
    return copy.deepcopy(items)


def splice(request,plan,results):
    notes=[n for n in request['base_notes'] if not any(m.intersects(support(n),w) for w in plan['windows'])]
    for r in results:
        if r['origin']=='automatic' and r['status']=='READY': notes.extend(copy.deepcopy(r['notes']))
    return ordered(notes)


def capabilities(ready=False):
    return dict(score_scope='BRIDGE_STAGE',can_plan_connections=bool(ready),can_audition=False,can_apply=False,can_export_final=False)


def make_outcome(request,plan,results,status,failure=None):
    ready=status=='SUCCEEDED'
    notes=splice(request,plan,results) if ready else None
    protections=locks_with_results(request,plan,results) if plan else request['base_project']['protections']
    return dict(schema='emoblocks.bridge-outcome.v1',spec_rev=m.SPEC_REV,contract_rev=REV,
        request_fingerprint=request_fingerprint(request),plan_id=request['plan_id'],plan_version=request['plan_version'],
        plan_fingerprint=plan['plan_fingerprint'] if plan else None,status=status,results=copy.deepcopy(results),
        base_fingerprint=request['base_fingerprint'],notes=notes,
        content_fingerprint=splice_fingerprint(request['base_project']['total_ticks'],notes) if ready else None,
        protection_summary=m.protection_summary(protections),remaining_gaps=copy.deepcopy(request['remaining_gaps']),
        error=copy.deepcopy(failure),capabilities=capabilities(ready))


@guard
def validate_raw(request,plan,raw):
    m.shape(raw,'schema spec_rev contract_rev request_fingerprint plan_id plan_version status results error')
    version(raw,'emoblocks.bridge-raw-outcome.v1')
    if raw['request_fingerprint']!=request_fingerprint(request) or raw['plan_id']!=plan['id'] or raw['plan_version']!=plan['version']:
        m.reject('桥集合输入或计划版本不匹配。','PLAN_VERSION_MISMATCH')
    ids=[r['bridge_id'] for r in m.objects(raw['results'])]
    required={r['bridge_id'] for r in plan['protection_refs']}
    if len(ids)!=len(set(ids)) or set(ids)!=required: m.reject('桥集合缺项、重复或包含额外结果。','BRIDGE_NOT_READY')
    for result in raw['results']: validate_result(request,plan,result)
    if raw['status']=='SUCCEEDED':
        if raw['error'] is not None or any(r['status']!='READY' for r in raw['results']): m.reject('桥尚未全部就绪。','BRIDGE_NOT_READY')
        notes=splice(request,plan,raw['results']);monotone_notes(notes)
        originals=ordered(request['base_notes'])
        for lock in request['base_project']['protections']:
            ranges=m.protection_ranges(lock)
            def inside(values): return [n for n in values if any(m.intersects(support(n),r) for r in ranges)]
            if m.structural_notes(inside(originals))!=m.structural_notes(inside(notes)):
                m.reject('桥覆盖改变原保护内容或休止。','PROTECTION_CONFLICT')
        for lock in locks_with_results(request,plan,raw['results']):
            if lock['kind']=='bridge' and lock['status']=='CONTENT_READY': m.validate_protected_notes([lock],notes)
    elif raw['status'] in ('FAILED','CANCELLED'): warning_check(raw['error'])
    else: m.reject('桥集合终态不受支持。','INVALID_BRIDGE')


@guard
def validate_outcome(request,plan,value):
    m.shape(value,OUTCOME_FIELDS); version(value,'emoblocks.bridge-outcome.v1')
    if plan is None:
        if value['status'] not in ('FAILED','CANCELLED') or value['results']!=[]: m.reject('未登记位置不能产生就绪计划。','INVALID_BRIDGE')
        warning_check(value['error'])
    else:
        validate_raw(request,plan,dict(schema='emoblocks.bridge-raw-outcome.v1',spec_rev=m.SPEC_REV,contract_rev=REV,
            request_fingerprint=value['request_fingerprint'],plan_id=value['plan_id'],plan_version=value['plan_version'],
            status=value['status'],results=value['results'],error=value['error']))
    if value!=make_outcome(request,plan,value['results'],value['status'],value['error']):
        m.reject('桥终态、实际拼接、保护摘要或能力声明不一致。','INVALID_BRIDGE')


def preview(request,plan,protections,results,outcome=None):
    if plan is None: return None
    refs={r['bridge_id']:r for r in results};locks=m.indexed(protections);overlays=[]
    for ref in plan['protection_refs']:
        lock=locks[ref['protection_id']];r=refs.get(ref['bridge_id'])
        overlays.append(dict(id=ref['bridge_id'],range={k:lock[k] for k in ('start_tick','end_tick')},protection_id=lock['id'],
            status=lock['status'],result_status=r['status'] if r else None,material=copy.deepcopy(r['material']) if r else None,
            error=copy.deepcopy(r['error']) if r else None))
    return dict(project=copy.deepcopy(request['base_project']),overlays=overlays,protections=copy.deepcopy(protections),
                memory_info=memory.memory_info(request['base_project']),notes=copy.deepcopy(outcome['notes']) if outcome else None)


@guard
def validate_attempt(attempt, snapshots, attempts):
    m.shape(attempt,'id snapshot_id input_fingerprint state records protections staged_materials error bridge')
    stage=attempt['bridge'];m.shape(stage,'schema spec_rev contract_rev request phase plan results outcome')
    version(stage,'emoblocks.bridge-attempt.v1');request=stage['request'];validate_request(request)
    snap=snapshots.get(attempt['snapshot_id'])
    if (snap is None or snap['id']!=request['snapshot_id'] or snap['project']!=request['input_project']
            or snap['content_fingerprint']!=request['input_fingerprint'] or attempt['id']!=request['request_id']
            or attempt['input_fingerprint']!=request['input_fingerprint'] or attempt['records']!=[]):
        m.reject('桥尝试缺少匹配原版本输入快照。','STALE_SNAPSHOT')
    ref=request['completion_ref']
    if ref:
        parent=attempts.get(ref['attempt_id']);payload=parent.get('completion') if parent else None
        outcome=payload.get('outcome') if payload else None
        if (payload is None or payload['request']!=ref['request'] or outcome is None
                or not any(c==ref['candidate'] for c in outcome['candidates'])):
            m.reject('桥输入的基础候选所属尝试或实际快照不可解析。','STALE_SNAPSHOT')
        if attempt['state'] in ('RUNNING','READY') and parent['state']!='READY':
            m.reject('桥不能消费失效的基础候选。','STALE_SNAPSHOT')
    state=attempt['state'];plan=stage['plan'];results=stage['results'];outcome=stage['outcome']
    if state not in ('RUNNING','READY','FAILED','CANCELLED','INTERRUPTED','STALE'):
        m.reject('桥阶段不能被当作已应用或最终作品。','INVALID_BRIDGE')
    if stage['phase'] not in ('BRIDGE_DECISION','BRIDGE_LOCKED','BRIDGE_GENERATION','BRIDGES_READY'):
        m.reject('桥阶段状态无效。','INVALID_BRIDGE')
    if plan is None:
        if stage['phase']!='BRIDGE_DECISION' or results!=[]:
            m.reject('位置尚未登记，不能声称生成或就绪。','INVALID_BRIDGE')
        expected_locks=request['base_project']['protections']
    else:
        validate_plan(request,plan)
        if stage['phase']=='BRIDGE_DECISION': m.reject('已锁计划不能退回决策状态。','INVALID_BRIDGE')
        ids=[]
        for result in m.objects(results):
            validate_result(request,plan,result);ids.append(result['bridge_id'])
        if len(ids)!=len(set(ids)):m.reject('桥实际结果重复。','INVALID_BRIDGE')
        expected_locks=locks_with_results(request,plan,results)
    if attempt['protections']!=expected_locks or attempt['staged_materials']!=staged_materials(results):
        m.reject('桥范围保护或私有素材与已认证结果不一致。','PROTECTION_CONFLICT')
    if outcome is not None:
        validate_outcome(request,plan,outcome)
        if outcome['results']!=results or attempt['error']!=outcome['error']:
            m.reject('桥暂存结果、终态或错误不一致。','INVALID_BRIDGE')
    if state in ('RUNNING','INTERRUPTED') and (outcome is not None or attempt['error'] is not None):
        m.reject('运行桥不能伪造终态。','INVALID_BRIDGE')
    if state=='READY' and (plan is None or outcome is None or outcome['status']!='SUCCEEDED'
                           or stage['phase']!='BRIDGES_READY' or attempt['error'] is not None):
        m.reject('桥并未完成独立就绪认证。','BRIDGE_NOT_READY')
    if state in ('FAILED','CANCELLED') and (outcome is None or outcome['status']!=state or attempt['error'] is None):
        m.reject('桥失败或取消缺少完整可恢复事实。','INVALID_BRIDGE')
    if state=='STALE' and outcome is None and attempt['error'] is not None:
        m.reject('失效的运行桥不能伪造失败详情。','INVALID_BRIDGE')
