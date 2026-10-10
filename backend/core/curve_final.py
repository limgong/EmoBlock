"""P7 final musical facts. Validation is pure and never calls a composer."""
import curve_copy as copy
from functools import wraps

import curve_project as m
import curve_bridges as b
import curve_connections as c
import curve_memory as memory

REV = 'curve-workflow-v2-r3-p7'
LEGACY_ALGORITHM = 'curve-boundary-v1'
ALGORITHM = 'curve-boundary-v2-deterministic-layout'
LEGACY_PROOF_BUDGET = dict(max_nodes=8192, max_cells=16384, max_edges=1000000)
REQUEST_FIELDS = ('schema spec_rev contract_rev id token input_contract_rev input_fingerprint candidate_ref '
                  'connection_ref actual_layout layout_fingerprint protection_summary plan_id plan_version '
                  'seed algorithm_version parameters')
PROPOSAL_FIELDS = ('schema spec_rev contract_rev request_fingerprint decision none_reason boundaries '
                   'operations joints join_groups performance_hints assessments reasons search')
PLAN_FIELDS = PROPOSAL_FIELDS + (' id version token layout_fingerprint protection_summary_fingerprint '
                               'connection_plan_ref original_notes plan_fingerprint')
RESULT_FIELDS = ('schema spec_rev contract_rev id request_fingerprint plan_ref notes emitted_notes join_groups '
                 'operations performance_hints remaining_gaps content_fingerprint')
SCORE_FIELDS = ('schema spec_rev contract_rev id boundary_request_ref boundary_plan_ref connection_plan_ref '
                'kind mode total_ticks bpm notes emitted_notes join_groups performance_map layers '
                'remaining_gaps target_resolution protection_summary_fingerprint source_fingerprint '
                'music_fingerprint score_fingerprint')
DEFAULTS = dict(policy='auto', max_boundary_ticks=240, max_operations=64, max_pitch_shift=2,
                max_time_shift=120, max_modified_notes=2, max_added_notes=1)
METHODS = ('natural_continuation', 'motif_reply', 'gradual_build', 'blank_entry', 'resolve_close', 'none')
PRESETS = dict(calm='soft', hope='bell', sad='dark', suspense='pluck', crisis='pluck', resolve='brass')
ordered = b.ordered
support = b.support


def guard(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            with m.validation_scope() as context:
                if fn.__name__.startswith('validate_'):
                    args,kwargs=m.curve_frozen.arguments(args,kwargs)
                    key=m.validation_key(fn,args,kwargs)
                else:key=None
                if key is not None and key in context['final_checks']:
                    result=context['final_checks'].pop(key);context['final_checks'][key]=result
                    return copy.deepcopy(result)
                result=fn(*args, **kwargs)
                if key is not None:
                    if len(context['final_checks'])>=32:context['final_checks'].pop(next(iter(context['final_checks'])))
                    context['final_checks'][key]=copy.deepcopy(result)
                return copy.deepcopy(result) if key is not None else result
        except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
            raise m.ProjectError('INVALID_FINAL_SCORE', '最终乐谱字段缺失或结构无效。') from exc
    return wrapped


def version(data, schema):
    if (data['schema'], data['spec_rev'], data['contract_rev']) != (schema, m.SPEC_REV, REV):
        m.reject('最终处理对象版本不匹配。', 'UNSUPPORTED_VERSION')


def header(schema):
    return dict(schema=schema, spec_rev=m.SPEC_REV, contract_rev=REV)


def parameters(values=None):
    out = dict(DEFAULTS)
    if values is not None:
        if not isinstance(values, dict) or set(values) - set(out):
            m.reject('最终边界参数不受支持。', 'INVALID_PARAMETERS')
        out.update(values)
    if out['policy'] not in ('auto', 'none'):
        m.reject('最终边界策略不受支持。', 'INVALID_PARAMETERS')
    for key, maximum in dict(max_boundary_ticks=240, max_operations=256, max_pitch_shift=2,
                             max_time_shift=120, max_modified_notes=2, max_added_notes=1).items():
        m.integer(out[key], 0 if key == 'max_added_notes' else 1, maximum)
    return out


def ref(data, kind=None):
    name = kind or data['schema']
    key = ('plan_fingerprint' if 'plan_fingerprint' in data else
           'score_fingerprint' if 'score_fingerprint' in data else
           'asset_fingerprint' if 'asset_fingerprint' in data else
           'content_fingerprint' if 'content_fingerprint' in data else None)
    fingerprint = data[key] if key else request_fingerprint(data)
    return dict(id=data['id'], version=data.get('version', 1), fingerprint=fingerprint)


def request_fingerprint(request):
    return m.digest('emoblocks.boundary-request.v1', request)


def plan_fingerprint(plan):
    return m.digest('emoblocks.boundary-plan.v1', {k: v for k, v in plan.items() if k != 'plan_fingerprint'})


def result_fingerprint(result):
    return m.digest('emoblocks.boundary-result.v1', {k: v for k, v in result.items() if k not in ('id', 'content_fingerprint')})


def score_fingerprint(score):
    return m.digest('emoblocks.final-score.v1', {k: v for k, v in score.items() if k not in ('id', 'score_fingerprint')})


def music_fingerprint(total, bpm, notes):
    return m.digest('emoblocks.final-music.v1', dict(total_ticks=total, bpm=bpm,
        notes=sorted([(n['start_tick'], n['pitch'], n['duration_tick']) for n in notes])))


def validate_connection_ref(value):
    m.shape(value, 'attempt_id request plan results outcome')
    m.ident(value['attempt_id'])
    request, plan, outcome = value['request'], value['plan'], value['outcome']
    c.validate_request(request); c.validate_plan(request, plan); c.validate_outcome(request, plan, outcome)
    if (value['attempt_id'] != request['request_id'] or value['results'] != outcome['results']
            or outcome['status'] != 'SUCCEEDED' or not outcome['capabilities']['can_plan_boundaries']):
        m.reject('连接结果尚未完整就绪或已失效。', 'CONNECTIONS_NOT_READY')


def _key(material, sources):
    context = (material.get('generation') or {}).get('key_context') or material['provenance'].get('key_context')
    if not context:
        for note in material['notes']:
            source = sources.get((note['origin'] or {}).get('source_id'))
            if source and source['provenance'].get('key_context'):
                context = source['provenance']['key_context']; break
    if not context:
        import engine
        tonic, mode, confidence = engine.infer_key([engine.Note(n['pitch'], n['start_tick'], n['duration_tick'], n['velocity'])
                                                    for n in material['notes']])
        context = dict(tonic=tonic, mode=mode, confidence=confidence, method='existing-note-key-inference')
    return copy.deepcopy(context)


def _performance(stage, owner, path=()):
    return m.digest('emoblocks.final-performance.v1', dict(stage=stage, owner_id=owner, component_path=list(path)))


def placement_segments(place):
    root=place['emotion_variant'] or place['base_snapshot'];rows=[]
    def visit(material,start,path):
        if material['kind']=='combination':
            for child in material['children']:visit(child['snapshot'],start+child['offset_tick'],path+[child['occurrence_id']])
        else:rows.append(dict(owner=place['id'],stage='placement',start_tick=start,end_tick=start+material['length_ticks'],
            emotion=place['emotion'],material=material,path=path,performance_id=_performance('placement',place['id'],path),priority=0))
    visit(place['base_snapshot'],place['start_tick'],[])
    # Parent capture/key are the actual variant; ownership remains each occurrence.
    if place['emotion_variant'] is not None:
        for row in rows:row['material']=dict(notes=root['notes'],provenance=root['provenance'],generation=root['generation'],phrase_id=root['phrase_id'])
    return rows


def _layout(value, retained_order=None, rows_capture=None):
    req = value['request']; bridge = req['bridge_ref']; base = bridge['request']['base_project']
    sources = m.source_index(base['sources']); place_by_id = m.indexed(base['placements'])
    bridge_by_note = {n['id']: r for r in bridge['results'] for n in r['notes']}
    connection_by_note = {n['id']: r for r in value['results'] for n in r['notes']}
    notes = copy.deepcopy(value['outcome']['notes']); ledger = []
    for note in notes:
        if note['id'] in connection_by_note:
            row = connection_by_note[note['id']]; stage, owner, path, snapshot = 'connection', row['connection_id'], [], None
            fingerprint = row['content_fingerprint']
        elif note['id'] in bridge_by_note:
            row = bridge_by_note[note['id']]; stage, owner, path = 'bridge', row['bridge_id'], []
            snapshot = row['material']['id']; fingerprint = row['content_fingerprint']
        else:
            old = b.parent_ref(bridge['request'], note['id'])
            if old.get('kind') == 'accepted_score':
                stage, owner, path, snapshot = 'final_score', old['owner_id'], old['component_path'], None
                from curve_application import source_score
                fingerprint = source_score(base, note['id'])['score_fingerprint']
            else:
                stage, owner, path = 'placement', old['placement_id'], old['component_path']
                place = place_by_id[owner]; material = place['emotion_variant'] or place['base_snapshot']
                snapshot = material['id']; fingerprint = m.digest('emoblocks.material-snapshot.v1', material)
        parent = dict(stage=stage, owner_id=owner, note_id=note['id'], component_path=path,
                      material_snapshot_id=snapshot, content_fingerprint=fingerprint)
        performance = _performance(stage, owner, path)
        if stage == 'final_score':
            original_score = source_score(base, note['id'])
            performance = next(r['performance_id'] for r in original_score['performance_map'] if note['id'] in r['logical_note_ids'])
        ledger.append(dict(note_id=note['id'], parent_ref=parent, performance_id=performance))
    raw_segments = []
    for place in base['placements']:
        raw_segments.extend(placement_segments(place))
    # Retained accepted music can have connection owners and local weak starts.
    # It is never relabelled as the underlying, no-longer-sounding old material.
    by_performance={row['performance_id']:row for row in raw_segments}
    for record in base['records']:
        prior=record['payload'].get('p7') if record['kind']=='final_score' else None
        if not prior:continue
        old_score=prior['final_score']
        for stage,key in (('connection','connection_overlays'),('bridge','bridge_overlays')):
            for overlay in prior[key]:
                pid=_performance(stage,overlay['id'])
                region=overlay['range'];key_context=next((e['key_context'] for layer in old_score['layers'] for e in layer['rules']['entries']
                    if e['rule']=='melody' and region['start_tick']<=e['start_tick']<region['end_tick']),None)
                by_performance[pid]=dict(owner=overlay['id'],stage=stage,**region,emotion=_emotion(base,region['start_tick']),
                    path=[],performance_id=pid,priority=1,material=dict(notes=overlay['notes'],provenance={},generation=dict(key_context=key_context)))
    retained={r['performance_id'] for r in ledger if r['parent_ref']['stage']=='final_score'}
    if retained_order is None:
        retained_order = sorted(retained, key=lambda pid: (
            0 if by_performance.get(pid, {}).get('stage') in ('bridge', 'connection') else 1, pid))
    elif len(retained_order) != len(retained) or set(retained_order) != retained:
        m.reject('历史演奏顺序证明无效。', 'SOURCE_CLOSURE_INVALID')
    for pid in retained_order:
        row=by_performance.get(pid)
        if row is None:m.reject('接受谱演奏缺少真实素材或覆盖层范围。','SOURCE_CLOSURE_INVALID')
        values=[n for n in notes if next(r for r in ledger if r['note_id']==n['id'])['performance_id']==pid]
        raw_segments.append(dict(copy.deepcopy(row),start_tick=min(row['start_tick'],min(n['start_tick'] for n in values)),
            end_tick=max(row['end_tick'],max(support(n)['end_tick'] for n in values)),priority=1))
    for row in bridge['results']:
        raw_segments.append(dict(owner=row['bridge_id'], stage='bridge', **row['range'],path=[],priority=2,
            emotion=_emotion(base, row['range']['start_tick']), material=row['material'],performance_id=_performance('bridge',row['bridge_id'])))
    for window in value['plan']['windows']:
        material = dict(notes=notes, provenance={}, generation=dict(key_context=window['key_context']))
        raw_segments.append(dict(owner=window['id'], stage='connection', start_tick=window['start_tick'],path=[],priority=3,
            end_tick=window['end_tick'], emotion=_emotion(base, window['start_tick']), material=material,performance_id=_performance('connection',window['id'])))
    for blank in base['blank_regions']:
        raw_segments.append(dict(owner=blank['id'], stage='blank', start_tick=blank['start_tick'],path=[],priority=4,performance_id=None,
            end_tick=blank['end_tick'], emotion='calm', material=dict(notes=[], provenance={}, generation=None)))
    if rows_capture is not None:
        rows_capture.extend(copy.deepcopy(raw_segments))
    breaks = sorted({x for r in raw_segments for x in (r['start_tick'], r['end_tick'])})
    spans = []
    for a, z in zip(breaks, breaks[1:]):
        rows = [s for s in raw_segments if s['start_tick'] <= a and z <= s['end_tick']]
        if not rows: continue
        row = max(rows, key=lambda r: r['priority'])
        if spans and spans[-1]['owner'] == row['owner'] and spans[-1]['stage'] == row['stage'] and spans[-1]['performance_id']==row['performance_id'] and spans[-1]['end_tick'] == a:
            spans[-1]['end_tick'] = z
        else: spans.append(dict(row, start_tick=a, end_tick=z))
    segments = []
    for span in spans:
        region = {k: span[k] for k in ('start_tick', 'end_tick')}
        owner_ref = dict(id=span['owner'], version=1, fingerprint=m.digest('emoblocks.final-segment-owner.v1', span['material']))
        ident = m.digest('emoblocks.final-segment.v1', dict(owner_ref=owner_ref, kind=span['stage'],path=span['path'], **region))
        segments.append(dict(id=ident, performance_id=span['performance_id'], owner_ref=owner_ref,
            **region, phrase_id=span['material'].get('phrase_id'), component_path=span['path'], emotion=span['emotion'],
            key_context=_key(span['material'], sources), intensity_start=m.intensity_at(base, region['start_tick']),
            intensity_end=m.intensity_at(base, region['end_tick']), kind=span['stage']))
    return dict(total_ticks=base['total_ticks'], bpm=base['bpm'], base_project=copy.deepcopy(base), notes=ordered(notes),
        segments=segments, coverage_ranges=b.complement(value['outcome']['remaining_gaps'], base['total_ticks']),
        remaining_gaps=copy.deepcopy(value['outcome']['remaining_gaps']), protections=copy.deepcopy(req['actual_layout']['protections']),
        blank_regions=copy.deepcopy(base['blank_regions']), emission_ledger=sorted(ledger, key=lambda r: r['note_id']))


def _legacy_layout(value, stored):
    """Prove one global ordering of authentic v1 retained rows, then replay it."""
    import heapq
    rows = []
    _layout(value, rows_capture=rows)
    nodes = {r['performance_id'] for r in rows if r['priority'] == 1}
    breaks = sorted({t for r in rows for t in (r['start_tick'], r['end_tick'])})
    budget = LEGACY_PROOF_BUDGET
    if len(nodes) > budget['max_nodes'] or max(0, len(breaks)-1) > budget['max_cells']:
        m.reject('历史布局顺序证明超过来源预算，原工程已保留。', 'SOURCE_CLOSURE_INVALID')
    edges = {pid:set() for pid in nodes}; indegree = {pid:0 for pid in nodes}; edge_count = 0
    for a, z in zip(breaks, breaks[1:]):
        eligible = [r for r in rows if r['start_tick'] <= a and z <= r['end_tick']]
        if not eligible:
            continue
        maximum = max(r['priority'] for r in eligible)
        best = [r for r in eligible if r['priority'] == maximum]
        spans = [s for s in stored['segments'] if s['start_tick'] <= a and z <= s['end_tick']]
        if len(spans) != 1:
            m.reject('历史布局缺少一致的原始演奏范围。', 'STALE_SNAPSHOT')
        selected = spans[0]
        matching = [r for r in best if (r['owner'], r['stage'], r['performance_id']) == (
            selected['owner_ref']['id'], selected['kind'], selected['performance_id'])]
        if len(matching) != 1:
            m.reject('历史布局选择不属于真实最高优先级演奏。', 'STALE_SNAPSHOT')
        if maximum != 1:
            if matching[0] is not best[0]:
                m.reject('历史布局改变了固定演奏顺序。', 'STALE_SNAPSHOT')
            continue
        winner = matching[0]['performance_id']
        for competitor in best:
            other = competitor['performance_id']
            if other != winner and other not in edges[winner]:
                edges[winner].add(other); indegree[other] += 1; edge_count += 1
                if edge_count > budget['max_edges']:
                    m.reject('历史布局顺序证明超过来源预算，原工程已保留。', 'SOURCE_CLOSURE_INVALID')
    ready = [pid for pid in nodes if not indegree[pid]]; heapq.heapify(ready); order = []
    while ready:
        pid = heapq.heappop(ready); order.append(pid)
        for other in sorted(edges[pid]):
            indegree[other] -= 1
            if not indegree[other]:heapq.heappush(ready, other)
    if len(order) != len(nodes):
        m.reject('历史布局不存在一致的全局演奏顺序。', 'STALE_SNAPSHOT')
    actual = _layout(value, retained_order=order)
    if actual != stored:
        m.reject('历史布局与完整原始演奏事实不一致。', 'STALE_SNAPSHOT')
    return actual


def _emotion(project, tick):
    p = next((p for p in project['placements'] if p['start_tick'] <= tick < p['start_tick'] + p['length_ticks']), None)
    return p['emotion'] if p else 'calm'


@guard
def make_request(connection_ref, token=None, candidate_ref=None, seed=31, values=None, plan_id=None, plan_version=1, algorithm_version=None):
    validate_connection_ref(connection_ref)
    parent = connection_ref['request']; m.integer(seed, 0, 2**32 - 1); m.integer(plan_version, 1)
    if token is None:
        token = dict(project_id=parent['input_project']['project_id'], session_id=parent['session_id'],
            request_id=m.uid(), snapshot_id=m.uid(), spec_rev=m.SPEC_REV, contract_rev=REV,
            edit_revision=parent['edit_revision'], input_fingerprint=parent['input_fingerprint'])
    m.shape(token, 'project_id session_id request_id snapshot_id spec_rev contract_rev edit_revision input_fingerprint')
    if (token['spec_rev'], token['contract_rev'], token['project_id'], token['input_fingerprint']) != (
            m.SPEC_REV, REV, parent['input_project']['project_id'], parent['input_fingerprint']):
        m.reject('最终处理输入快照身份不匹配。', 'STALE_SNAPSHOT')
    previous = parent['bridge_ref']['request']['completion_ref']
    expected = dict(id=previous['candidate_id'], version=1, fingerprint=previous['candidate']['content_fingerprint']) if previous else None
    if candidate_ref is None: candidate_ref = expected
    if candidate_ref != expected: m.reject('最终处理候选身份不匹配。', 'STALE_SNAPSHOT')
    layout = _layout(connection_ref); locks = layout['protections']; plan_id = m.uid() if plan_id is None else plan_id
    identity = dict(recommendation_request_id=token['request_id'], candidate_ref=candidate_ref,
                    connection_attempt_id=connection_ref['attempt_id'], plan_id=plan_id, plan_version=plan_version)
    algorithm_version = ALGORITHM if algorithm_version is None else algorithm_version
    if algorithm_version not in (LEGACY_ALGORITHM, ALGORITHM):
        m.reject('最终布局算法版本不受支持。', 'UNSUPPORTED_VERSION')
    return dict(header('emoblocks.boundary-request.v1'), id=m.digest('emoblocks.boundary-request-id.v1', identity),
        token=copy.deepcopy(token), input_contract_rev=parent['input_contract_rev'], input_fingerprint=parent['input_fingerprint'],
        candidate_ref=copy.deepcopy(candidate_ref), connection_ref=copy.deepcopy(connection_ref), actual_layout=layout,
        layout_fingerprint=m.digest('emoblocks.final-layout.v1', layout),
        protection_summary=dict(fingerprint=m.protection_summary(locks), ranges=c.protection_ranges(locks)),
        plan_id=plan_id, plan_version=plan_version, seed=seed, algorithm_version=algorithm_version, parameters=parameters(values))


@guard
def validate_request(request):
    m.canonical(request); m.shape(request, REQUEST_FIELDS); version(request, 'emoblocks.boundary-request.v1')
    if request['algorithm_version'] not in (LEGACY_ALGORITHM, ALGORITHM):
        m.reject('最终布局算法版本不受支持。', 'UNSUPPORTED_VERSION')
    expected = make_request(request['connection_ref'], request['token'], request['candidate_ref'], request['seed'],
                            request['parameters'], request['plan_id'], request['plan_version'], request['algorithm_version'])
    if request['algorithm_version'] == LEGACY_ALGORITHM:
        expected['actual_layout'] = _legacy_layout(request['connection_ref'], request['actual_layout'])
        expected['layout_fingerprint'] = m.digest('emoblocks.final-layout.v1', expected['actual_layout'])
    if request != expected:
        m.reject('最终处理布局、演奏账本或保护与实际输入不匹配。', 'STALE_SNAPSHOT')


def editable_ranges(request, left, right):
    """Complete note supports must fit; adjacency never opens a protected rest."""
    width = request['parameters']['max_boundary_ticks']
    wanted = []
    if left is not None:
        wanted.append(dict(start_tick=max(left['start_tick'], left['end_tick'] - width), end_tick=left['end_tick']))
    if right is not None:
        wanted.append(dict(start_tick=right['start_tick'], end_tick=min(right['end_tick'], right['start_tick'] + width)))
    forbidden = request['protection_summary']['ranges'] + request['actual_layout']['blank_regions'] + request['actual_layout']['remaining_gaps']
    forbidden += [{k: w[k] for k in ('start_tick', 'end_tick')} for w in request['connection_ref']['plan']['windows']]
    result = []
    for region in wanted:
        cursor = region['start_tick']
        for block in b.union(forbidden):
            if block['end_tick'] <= cursor or block['start_tick'] >= region['end_tick']: continue
            if cursor < block['start_tick']:
                result.append(dict(start_tick=cursor, end_tick=block['start_tick']))
            cursor = max(cursor, block['end_tick'])
        if cursor < region['end_tick']:
            result.append(dict(start_tick=cursor, end_tick=region['end_tick']))
    return b.union(result)


def boundary_sites(request):
    segments = sorted(request['actual_layout']['segments'], key=lambda s: (s['start_tick'], s['end_tick'], s['id']))
    pairs = []
    for index, right in enumerate(segments):
        left = segments[index - 1] if index else None
        if left is None or left['end_tick'] != right['start_tick']:
            if left is not None: pairs.append((left, None))
            pairs.append((None, right))
        elif (left['performance_id'], left['kind']) != (right['performance_id'], right['kind']):
            pairs.append((left, right))
    if segments: pairs.append((segments[-1], None))
    result = []
    for left, right in pairs:
        tick = right['start_tick'] if right else left['end_tick']
        ident = m.digest('emoblocks.final-boundary.v1', dict(left=left['id'] if left else None, right=right['id'] if right else None, tick=tick))
        result.append(dict(id=ident, tick=tick, left=left, right=right, editable_ranges=editable_ranges(request, left, right)))
    return result


def _near_notes(request, site):
    notes = request['actual_layout']['notes']; tick = site['tick']
    left_notes = [n for n in notes if support(n)['end_tick'] <= tick]
    right_notes = [n for n in notes if n['start_tick'] >= tick]
    return (max(left_notes, key=lambda n: (support(n)['end_tick'], n['id'])) if left_notes else None,
            min(right_notes, key=lambda n: (n['start_tick'], n['id'])) if right_notes else None)


def _endpoint(note):
    return {k: note[k] for k in ('id', 'pitch', 'start_tick', 'duration_tick')} | {'note_id': note['id']} if note else None


def _ep(note):
    return {('note_id' if k == 'id' else k): note[k] for k in ('id', 'pitch', 'start_tick', 'duration_tick')} if note else None


def joined_events(notes, ledger):
    """One physical voice, with explicit performance provenance for every tie."""
    by_id = {v['note_id']: v for v in ledger}; groups = []; events = []; paths = []
    for note in ordered(notes):
        row = by_id[note['id']]; previous = paths[-1][-1] if paths else None
        a, z = previous.get('slice') if previous else None, note['slice']
        same = (a is not None and z is not None and previous['pitch'] == note['pitch']
            and previous['origin'] == note['origin'] and by_id[previous['id']]['performance_id'] == row['performance_id']
            and a['parent_emission_id'] == z['parent_emission_id'] and a['parent_duration_tick'] == z['parent_duration_tick']
            and a['offset_tick'] + previous['duration_tick'] == z['offset_tick']
            and previous['start_tick'] + previous['duration_tick'] == note['start_tick'])
        if same: paths[-1].append(note)
        else: paths.append([note])
    for path in paths:
        first = path[0]
        if len(path) == 1: events.append(copy.deepcopy(first)); continue
        ids = [n['id'] for n in path]; performance = by_id[first['id']]['performance_id']
        source = first['slice']['parent_emission_id']
        ident = m.digest('emoblocks.final-emission.v1', dict(performance_id=performance, source_emission_id=source, input_note_ids=ids))
        event = dict(copy.deepcopy(first), id=ident, duration_tick=sum(n['duration_tick'] for n in path), slice=None,
                     lineage=list(dict.fromkeys(x for n in path for x in n['lineage'] + [n['id']])))
        groups.append(dict(performance_id=performance, input_note_ids=ids, source_emission_id=source, render_event=event))
        events.append(event)
    return ordered(events), groups


def _apply_operations(request, operations, hints):
    originals = m.indexed(request['actual_layout']['notes']); notes = copy.deepcopy(originals)
    ledger = {r['note_id']: copy.deepcopy(r) for r in request['actual_layout']['emission_ledger']}
    for operation in operations:
        for ident in operation['consumed_note_ids']:
            del notes[ident]; ledger.pop(ident)
        for row in operation['outputs']:
            note = copy.deepcopy(row['note']); notes[note['id']] = note
            parent = copy.deepcopy(next(r for r in request['actual_layout']['emission_ledger'] if r['note_id'] == row['parent_note_ids'][0]))
            ledger[note['id']] = dict(parent, note_id=note['id'], performance_id=row['performance_id'])
    for hint in hints:
        note = notes[hint['note_id']]; note['velocity'] += hint['velocity_delta']
    return ordered(list(notes.values())), sorted(ledger.values(), key=lambda r: r['note_id'])


def _inside(region, domains):
    return any(r['start_tick'] <= region['start_tick'] and region['end_tick'] <= r['end_tick'] for r in domains)


def _check_voice(notes, total, sources):
    m.notes_check(notes, total, sources)
    if any(not 12 <= n['pitch'] <= 119 for n in notes):
        m.reject('最终主旋律音高超出输出音域。', 'INVALID_FINAL_SCORE')
    sorted_ = ordered(notes)
    if any(support(a)['end_tick'] > z['start_tick'] for a, z in zip(sorted_, sorted_[1:])):
        m.reject('最终主旋律出现重叠或复声。', 'INVALID_FINAL_SCORE')


def _actual_protection(request, notes):
    original = request['actual_layout']['notes']; domains = request['protection_summary']['ranges']
    def protected(values):
        return m.structural_notes([n for n in values if any(m.intersects(support(n), r) for r in domains)])
    if protected(notes) != protected(original):
        m.reject('最终处理改变了完整保护音符或受保护休止。', 'PROTECTION_CONFLICT')
    if any(m.intersects(support(n), blank) for n in notes for blank in request['actual_layout']['blank_regions']):
        m.reject('最终主旋律进入主动留白。', 'PROTECTION_CONFLICT')


@guard
def validate_proposal(request, proposal):
    validate_request(request); m.canonical(proposal); m.shape(proposal, PROPOSAL_FIELDS)
    version(proposal, 'emoblocks.boundary-proposal.v1')
    if proposal['request_fingerprint'] != request_fingerprint(request): m.reject('边界请求已过期。', 'STALE_SNAPSHOT')
    params = request['parameters']; actual_sites = boundary_sites(request); sites = {}; boundaries = m.indexed(proposal['boundaries'])
    operations = m.indexed(proposal['operations']); hints = m.indexed(proposal['performance_hints'])
    if len(operations) > params['max_operations']: m.reject('最终边界操作超过有限预算。')
    if proposal['decision'] not in ('none', 'selected') or (proposal['decision'] == 'none' and (operations or hints)):
        m.reject('边界决策与真实操作不一致。')
    if proposal['decision'] == 'none' and proposal['none_reason'] not in ('NOT_NEEDED', 'NO_LEGAL_OPERATION', 'POLICY_NONE'):
        m.reject('无边界处理缺少真实理由。')
    if proposal['decision'] == 'selected' and (proposal['none_reason'] is not None or not (operations or hints)):
        m.reject('不能用类型标签冒充实际边界处理。')
    for boundary in boundaries.values():
        m.shape(boundary, 'id tick left_performance_id right_performance_id method editable_ranges operation_ids reasons')
        site = next((s for s in actual_sites if s['tick'] == boundary['tick']
            and (s['left']['performance_id'] if s['left'] else None) == boundary['left_performance_id']
            and (s['right']['performance_id'] if s['right'] else None) == boundary['right_performance_id']), None)
        if site is None or boundary['method'] not in METHODS or not boundary['reasons']: m.reject('边界不是实际乐句交接。')
        if any(s['id'] == site['id'] for s in sites.values()): m.reject('同一实际边界被重复声明。', 'BOUNDARY_CONFLICT')
        sites[boundary['id']] = site
        if (boundary['tick'] != site['tick'] or boundary['editable_ranges'] != site['editable_ranges']
            or boundary['left_performance_id'] != (site['left']['performance_id'] if site['left'] else None)
            or boundary['right_performance_id'] != (site['right']['performance_id'] if site['right'] else None)):
            m.reject('边界许可范围或演奏归属不符。')
        if sorted(boundary['operation_ids']) != sorted(op['id'] for op in operations.values() if boundary['id'] in op['boundary_ids']):
            m.reject('边界操作集合不一致。')
    parents = m.indexed(request['actual_layout']['notes']); raw_ledger = {r['note_id']: r for r in request['actual_layout']['emission_ledger']}
    consumed = set(); created = set(); impact = []; per_boundary = {i: [0, 0] for i in boundaries}
    for op in operations.values():
        m.shape(op, 'id boundary_ids kind input_refs consumed_note_ids outputs permitted_ranges')
        ids = op['boundary_ids']
        if not ids or len(ids) != len(set(ids)) or not set(ids) <= set(boundaries): m.reject('操作引用未知边界。')
        allowed = b.union([r for i in ids for r in boundaries[i]['editable_ranges']])
        if any(not _inside(r, allowed) for r in op['permitted_ranges']): m.reject('操作扩大了边界写域。', 'PROTECTION_CONFLICT')
        allowed = op['permitted_ranges']
        used = op['consumed_note_ids']; output = op['outputs']
        if len(used) != len(set(used)) or consumed & set(used) or not set(used) <= set(parents):
            m.reject('多个边界试图覆盖同一个原音符。', 'BOUNDARY_CONFLICT')
        expected_count = {'replace': (1, 1), 'remove': (1, 0), 'add': (0, 1)}.get(op['kind'])
        if expected_count != (len(used), len(output)): m.reject('实际操作不是限定局部变换。')
        referenced = [r['note_id'] for r in op['input_refs']]
        if not referenced or len(referenced) != len(set(referenced)) or not set(referenced) <= set(parents): m.reject('缺少真实父音符。')
        if op['input_refs'] != [raw_ledger[i]['parent_ref'] for i in referenced]: m.reject('音符父归属或快照被伪造。')
        if not set(used) <= set(referenced): m.reject('消耗的音符不在真实输入。')
        for ident in used:
            old = parents[ident]
            if not _inside(support(old), allowed): m.reject('边界改写跨出许可域。', 'PROTECTION_CONFLICT')
            if op['kind'] == 'remove' and (old['duration_tick'] > 120 or old['velocity'] > 80 or old['start_tick'] % m.BAR == 0):
                m.reject('收束不能删除重要或非局部弱音。')
            impact.append(support(old))
        for row in output:
            m.shape(row, 'note parent_note_ids performance_id'); note = row['note']; pids = row['parent_note_ids']
            if len(pids) != 1 or not set(pids) <= set(referenced): m.reject('局部变换必须回指具体实际父。')
            old = parents[pids[0]]
            if note['id'] in parents or note['id'] in created: m.reject('新发声沿用了原身份。')
            if (note['origin'] != old['origin'] or note['lineage'] != list(dict.fromkeys(old['lineage'] + [old['id']]))
                    or note['slice'] is not None or note['velocity'] != old['velocity']):
                m.reject('派生音符丢失具体来源或伪造发声切片。')
            if abs(note['pitch'] - old['pitch']) > params['max_pitch_shift']: m.reject('局部音高改写越界。')
            if op['kind'] == 'replace' and (pids != used or abs(note['start_tick'] - old['start_tick']) > params['max_time_shift']
                    or abs(note['duration_tick'] - old['duration_tick']) > params['max_time_shift']):
                m.reject('最终边界不能变成长片段重写。')
            if op['kind'] == 'add' and note['duration_tick'] > 120: m.reject('弱起新增时长越界。')
            if not _inside(support(note), allowed): m.reject('新增音符延伸进入保护。', 'PROTECTION_CONFLICT')
            if row['performance_id'] != raw_ledger[pids[0]]['performance_id']:
                m.reject('派生发声没有实际演奏所有者。')
            created.add(note['id']); impact.append(support(note))
        for ident in ids:
            per_boundary[ident][0] += len(used); per_boundary[ident][1] += int(op['kind'] == 'add')
        consumed.update(used)
    if any(a > params['max_modified_notes'] or z > params['max_added_notes'] for a, z in per_boundary.values()): m.reject('局部音符预算超限。')
    hinted = set()
    for hint in hints.values():
        m.shape(hint, 'id boundary_id note_id performance_id velocity_delta tone_hint accompaniment_hint')
        site = sites.get(hint['boundary_id']); note = parents.get(hint['note_id'])
        if site is None or hint['boundary_id'] not in boundaries or note is None or note['id'] in hinted or note['id'] in consumed:
            m.reject('表演交接存在重复/结构冲突。', 'BOUNDARY_CONFLICT')
        neighbours = _near_notes(request, site)
        if not (_inside(support(note), site['editable_ranges']) or note in neighbours): m.reject('表演变化不是局部交接。')
        m.integer(hint['velocity_delta'], -12, 12)
        if hint['tone_hint'] not in (None, 'soft', 'bell', 'dark', 'pluck', 'brass') or hint['accompaniment_hint'] not in ('none', 'fade_in', 'reduce', 'sustain'):
            m.reject('表演字段不受支持。')
        if hint['performance_id'] != raw_ledger[note['id']]['performance_id'] or not 1 <= note['velocity'] + hint['velocity_delta'] <= 127:
            m.reject('表演归属或力度无效。')
        hinted.add(note['id'])
    notes, ledger = _apply_operations(request, list(operations.values()), list(hints.values()))
    _check_voice(notes, request['actual_layout']['total_ticks'], m.source_index(request['actual_layout']['base_project']['sources']))
    _actual_protection(request, notes)
    events, groups = joined_events(notes, ledger)
    if proposal['join_groups'] != groups: m.reject('播放合并不属于同一次实际演奏。', 'INVALID_FINAL_SCORE')
    joint_ids = set()
    shared = {}
    for ident, site in sites.items():
        for note in _near_notes(request, site):
            if note is not None:
                shared.setdefault(note['id'], []).append(ident)
    expected_shared = {n: sorted(ids) for n, ids in shared.items() if len(ids) > 1}
    covered = {}
    for joint in m.objects(proposal['joints']):
        m.shape(joint, 'id boundary_ids note_ids original_endpoints final_endpoints')
        if joint['id'] in joint_ids or not set(joint['boundary_ids']) <= set(sites): m.reject('共同端点重复或无对应边界。')
        joint_ids.add(joint['id'])
        def endpoints(values):
            out = []
            for ident in joint['boundary_ids']:
                site = sites[ident]
                left, right = _near_notes(dict(request, actual_layout=dict(request['actual_layout'], notes=values)), site)
                out.append(dict(boundary_id=ident, left=_ep(left), right=_ep(right)))
            return out
        if (joint['original_endpoints'] != endpoints(request['actual_layout']['notes'])
                or joint['final_endpoints'] != endpoints(notes)):
            m.reject('共同边界未使用一次应用后的真实端点。', 'BOUNDARY_CONFLICT')
        for nid in joint['note_ids']:
            if nid in covered or not set(expected_shared.get(nid, [])) <= set(joint['boundary_ids']): m.reject('共同原端点集合不完整。')
            covered[nid] = expected_shared[nid]
    if covered != expected_shared: m.reject('缺失共同原端点，不能依次覆盖。', 'BOUNDARY_CONFLICT')
    for assessment in m.objects(proposal['assessments']):
        m.shape(assessment, 'boundary_id method accepted reasons')
        if assessment['boundary_id'] not in boundaries or assessment['method'] not in METHODS or type(assessment['accepted']) is not bool or not assessment['reasons']:
            m.reject('边界评价缺少实际判断。')
        for reason in assessment['reasons']: m.text(reason)
    if params['policy'] == 'none' and (operations or hints or proposal['none_reason'] != 'POLICY_NONE'):
        m.reject('显式无处理策略不能生成额外操作。')
    for gap in ((request['connection_ref']['request']['bridge_ref']['request']['completion_ref'] or {}).get('request') or {}).get('target_gaps', []):
        if not any(m.intersects(support(n), gap) for n in notes): m.reject('边界处理删除了目标唯一发声。', 'TARGET_GAPS_UNRESOLVED')
    m.shape(proposal['search'], 'tested_boundaries attempted_operations termination')
    m.integer(proposal['search']['tested_boundaries'], 0, len(actual_sites)); m.integer(proposal['search']['attempted_operations'], 0, params['max_operations'])
    if proposal['search']['termination'] not in ('COMPLETE', 'POLICY_NONE', 'BUDGET_EXHAUSTED'): m.reject('搜索终止原因无效。')
    if proposal['search']['termination'] == 'BUDGET_EXHAUSTED' and not (operations or hints): m.reject('预算耗尽不等于没有合法操作。', 'SEARCH_BUDGET_EXHAUSTED')
    for reason in proposal['reasons']:
        if isinstance(reason,dict): b.warning_check(reason)
        else: m.text(reason)


@guard
def make_plan(request, proposal):
    validate_proposal(request, proposal)
    plan = dict(copy.deepcopy(proposal), schema='emoblocks.boundary-plan.v1', id=request['plan_id'], version=request['plan_version'],
        token=copy.deepcopy(request['token']), layout_fingerprint=request['layout_fingerprint'],
        protection_summary_fingerprint=request['protection_summary']['fingerprint'],
        connection_plan_ref=ref(request['connection_ref']['plan']), original_notes=copy.deepcopy(request['actual_layout']['notes']))
    plan['plan_fingerprint'] = plan_fingerprint(plan)
    return plan


@guard
def validate_plan(request, plan):
    m.shape(plan, PLAN_FIELDS); version(plan, 'emoblocks.boundary-plan.v1')
    proposal = {k: copy.deepcopy(plan[k]) for k in PROPOSAL_FIELDS.split()}; proposal['schema'] = 'emoblocks.boundary-proposal.v1'
    if plan != make_plan(request, proposal): m.reject('最终边界计划身份或内容被改变。', 'PLAN_VERSION_MISMATCH')


@guard
def apply_boundaries(request, plan):
    validate_plan(request, plan)
    notes, ledger = _apply_operations(request, plan['operations'], plan['performance_hints'])
    events, groups = joined_events(notes, ledger)
    result = dict(header('emoblocks.boundary-result.v1'), request_fingerprint=request_fingerprint(request), plan_ref=ref(plan),
        notes=notes, emitted_notes=events, join_groups=groups, operations=copy.deepcopy(plan['operations']),
        performance_hints=copy.deepcopy(plan['performance_hints']), remaining_gaps=copy.deepcopy(request['actual_layout']['remaining_gaps']))
    result['content_fingerprint'] = result_fingerprint(result); result['id'] = result['content_fingerprint']
    return result


@guard
def validate_result(request, plan, result):
    m.shape(result, RESULT_FIELDS); version(result, 'emoblocks.boundary-result.v1')
    if result != apply_boundaries(request, plan): m.reject('最终音符与一次认证操作不符。', 'INVALID_FINAL_SCORE')


def base_ledger(request):
    bridge = request['connection_ref']['request']['bridge_ref']['request']
    base = bridge['base_project']; ledger = []
    for note in b.actual_notes(base):
        parent = b.parent_ref(bridge, note['id'])
        if parent.get('kind') == 'accepted_score':
            from curve_application import source_score
            owner = parent['owner_id']; stage = 'final_score'; snapshot = None
            fingerprint = source_score(base, note['id'])['score_fingerprint']
        else:
            owner = parent['placement_id']; stage = 'placement'
            place = m.indexed(base['placements'])[owner]
            material = place['emotion_variant'] or place['base_snapshot']; snapshot = material['id']
            fingerprint = m.digest('emoblocks.material-snapshot.v1', material)
        performance = _performance(stage, owner, parent['component_path'])
        if stage == 'final_score':
            original_score = source_score(base,note['id'])
            performance = next(r['performance_id'] for r in original_score['performance_map'] if note['id'] in r['logical_note_ids'])
        ledger.append(dict(note_id=note['id'], performance_id=performance,
            parent_ref=dict(stage=stage, owner_id=owner, note_id=note['id'], component_path=parent['component_path'],
                            material_snapshot_id=snapshot, content_fingerprint=fingerprint)))
    return ledger


def source_projection(request, plan, notes, kind):
    """Resolve every concrete parent from authenticated facts, never caller labels."""
    base = request['actual_layout']['base_project']
    original = b.actual_notes(base) if kind == 'comparison' else request['actual_layout']['notes']
    originals = m.indexed(original)
    ledger = {r['note_id']: r['parent_ref'] for r in (base_ledger(request) if kind == 'comparison' else request['actual_layout']['emission_ledger'])}
    operations = {v['note']['id']: v['parent_note_ids'] for op in plan['operations'] for v in op['outputs']}
    descriptors = []
    for note in notes:
        pids = [note['id']] if kind == 'comparison' or note['id'] in originals else operations.get(note['id'])
        if not pids or not set(pids) <= set(originals): m.reject('最终音符没有实际父音符。', 'SOURCE_CLOSURE_INVALID')
        descriptors.append(dict(id=note['id'], origin=copy.deepcopy(note['origin']), lineage=copy.deepcopy(note['lineage']),
                                slice=copy.deepcopy(note['slice']), parent_ids=sorted(set(pids))))
    parents = []; used_sources = set(); placements = m.indexed(base['placements'])
    bridges = {r['bridge_id']: r for r in request['connection_ref']['request']['bridge_ref']['results']}
    def collect(value):
        if isinstance(value, dict):
            origin = value.get('origin')
            if isinstance(origin, dict): used_sources.add(origin['source_id'])
            for v in value.values(): collect(v)
        elif isinstance(value, list):
            for v in value: collect(v)
    for ident in sorted({i for row in descriptors for i in row['parent_ids']}):
        parent = copy.deepcopy(ledger[ident]); snapshots = []; score_ref = source_fp = None
        if parent['stage'] == 'placement':
            place = placements[parent['owner_id']]
            snapshots = [place['base_snapshot']] + ([place['emotion_variant']] if place['emotion_variant'] is not None else [])
        elif parent['stage'] == 'bridge':
            result = bridges[parent['owner_id']]
            snapshots = [result[k] for k in ('base_material', 'material') if result.get(k) is not None]
        elif parent['stage'] == 'final_score':
            from curve_application import source_score
            score = source_score(base, ident); score_ref = ref(score); source_fp = score['source_fingerprint']
        unique = {}
        for snap in snapshots:
            if snap['id'] in unique and unique[snap['id']] != snap: m.reject('同一快照身份指向不同音乐。')
            unique[snap['id']] = copy.deepcopy(snap)
        snapshots = [unique[k] for k in sorted(unique)]
        row = dict(note=copy.deepcopy(originals[ident]), parent_ref=parent, material_snapshots=snapshots,
                   accepted_score_ref=score_ref, accepted_source_fingerprint=source_fp)
        collect(row); parents.append(row)
    collect(notes)
    sources = m.source_index(base['sources'])
    if not used_sources <= set(sources): m.reject('最终来源闭包缺失。', 'SOURCE_CLOSURE_INVALID')
    source_rows = []
    for ident in sorted(used_sources):
        source = copy.deepcopy(sources[ident]); source['notes'] = ordered(source['notes']); source_rows.append(source)
    return dict(kind=kind, notes=sorted(descriptors, key=lambda n: n['id']), parents=parents, sources=source_rows)


def _segments(request, kind):
    if kind == 'final': return copy.deepcopy(request['actual_layout']['segments'])
    base = request['actual_layout']['base_project']; sources = m.source_index(base['sources']); segments = []
    for place in base['placements']:
        material = place['emotion_variant'] or place['base_snapshot']; start = place['start_tick']; end = start + place['length_ticks']
        segments.append(dict(start_tick=start, end_tick=end, kind='placement', emotion=place['emotion'],
            performance_id=_performance('placement', place['id']), key_context=_key(material, sources)))
    segments.extend(dict(blank, kind='blank', emotion='calm', key_context=None, performance_id=None) for blank in base['blank_regions'])
    return sorted(segments, key=lambda s: s['start_tick'])


def _triad(key, notes):
    scale = [0, 2, 4, 5, 7, 9, 11] if key['mode'] == 'major' else [0, 2, 3, 5, 7, 8, 10]
    pcs = [(key['tonic'] + x) % 12 for x in scale]
    degree = max(range(7), key=lambda d: sum(n['duration_tick'] for n in notes if n['pitch'] % 12 in [pcs[(d+j)%7] for j in (0,2,4)]))
    chord = [48 + pcs[degree]]
    for j in (2, 4):
        pitch = pcs[(degree+j)%7]
        while pitch <= chord[-1]: pitch += 12
        chord.append(pitch)
    return chord


def arrange(request, plan, notes, events, groups, ledger, kind, mode):
    """Finite, auditable rule adapter; never transforms the planned melody."""
    if mode not in ('melody_only', 'arranged'): m.reject('输出模式不受支持。')
    base = request['actual_layout']['base_project']; segments = _segments(request, kind)
    by_note = {r['note_id']: r for r in ledger}; by_group = {g['render_event']['id']: g for g in groups}
    hints = {h['note_id']: h for h in plan['performance_hints']} if kind == 'final' else {}
    layers = {}; performance_map = []
    def emit(rule, note, parents, region, key, level, emotion, preset, volume, drum=None):
        owner = rule + ':' + preset
        layer = layers.setdefault(owner, dict(id=owner, role='melody' if rule == 'melody' else rule,
            name=owner, preset=preset, volume=volume, pan=0, drum=drum, notes=[], rules=dict(profile='curve-arrangement-v1', entries=[])))
        layer['notes'].append(note)
        layer['rules']['entries'].append(dict(note_id=note['id'], rule=rule, source_note_ids=list(parents),
            region=copy.deepcopy(region), start_tick=note['start_tick'], duration_tick=note['duration_tick'], pitch=note['pitch'],
            velocity=note['velocity'], key_context=copy.deepcopy(key), intensity=level, emotion=emotion))
    def companion(rule, tick, duration, pitch, velocity, parents, region, key, level, emotion, preset, volume, drum=None):
        if duration <= 0: return
        ident = m.digest('emoblocks.arrangement-note.v1', dict(rule=rule, start_tick=tick, duration_tick=duration,
            pitch=pitch, source_note_ids=parents, region=region))
        note = dict(id=ident, pitch=pitch, start_tick=tick, duration_tick=duration, velocity=velocity,
                    origin=None, lineage=list(parents), slice=None)
        emit(rule, note, parents, region, key, level, emotion, preset, volume, drum)
    for event in events:
        segment = next((s for s in segments if s['start_tick'] <= event['start_tick'] < s['end_tick'] and s['kind'] != 'blank'), None)
        if segment is None: m.reject('实际主旋律不属于音乐排布。')
        logical_ids = by_group[event['id']]['input_note_ids'] if event['id'] in by_group else [event['id']]
        performance = by_note[logical_ids[0]]['performance_id']; hint = hints.get(logical_ids[0], {})
        preset = 'soft' if mode == 'melody_only' else (hint.get('tone_hint') or PRESETS[segment['emotion']])
        note = dict(copy.deepcopy(event), velocity=80 if mode == 'melody_only' else event['velocity'])
        region = {k: segment[k] for k in ('start_tick','end_tick')}; level = m.intensity_at(base, event['start_tick'])
        emit('melody', note, [event['id']], region, segment['key_context'], level, segment['emotion'], preset, 35)
        performance_map.append(dict(emitted_note_id=event['id'], logical_note_ids=logical_ids, performance_id=performance, preset=preset))
    if mode == 'arranged':
        previous = None
        for segment in segments:
            region = {k: segment[k] for k in ('start_tick','end_tick')}; emotion = segment['emotion']
            if segment['kind'] == 'blank':
                if previous and previous[0]['end_tick'] == region['start_tick']:
                    old_region, chord, parents, key = previous; level = m.intensity_at(base, region['start_tick'])
                    span = min(m.PPQ, region['end_tick']-region['start_tick'])
                    for pitch in chord: companion('harmony', region['start_tick'], span, pitch, min(35, round(28+20*level)), parents, region, key, level, 'calm', 'pad', 14)
                previous = None; continue
            actual = [n for n in events if m.intersects(support(n), region)]
            if not actual: previous = None; continue
            key = segment['key_context']; chord = _triad(key, actual); parents = [n['id'] for n in actual]
            for tick in range(region['start_tick'], region['end_tick'], m.PPQ):
                span = min(m.PPQ, region['end_tick']-tick); level = m.intensity_at(base, tick); beat = tick//m.PPQ
                for pitch in chord: companion('harmony', tick, span, pitch, round(28+20*level), parents, region, key, level, emotion, 'dark' if emotion in ('sad','suspense') else 'pad', 14)
                companion('bass', tick, int(span*.8)//10*10, chord[0]-12, round(40+28*level), parents, region, key, level, emotion, 'bass', 20)
                if level > .35 and emotion != 'sad' and beat % 2:
                    stride = 120 if level > .8 else 240 if level > .6 else 480
                    for index, onset in enumerate(range(tick,tick+span,stride)):
                        if emotion == 'suspense' and index % 3 == 2: continue
                        duration = int(min(tick+span-onset,stride*.6))//10*10
                        companion('pulse', onset, duration, chord[index%3]+12, round(30+25*level), parents, region, key, level, emotion, 'pluck',15)
                if emotion in ('crisis','resolve') and level > .45:
                    rule, pitch, volume, drum = ('kick',36,20,'bassdrum01.ogg') if not beat%2 else ('snare',38,15,'snare01.ogg')
                    companion(rule,tick,min(100,span),pitch,round((50+25*level) if rule=='kick' else (45+20*level)),parents,region,key,level,emotion,'bass',volume,drum)
                    stride = 120 if emotion=='crisis' and level>.8 else 240
                    for onset in range(tick,tick+span,stride): companion('hat',onset,min(60,tick+span-onset),42,round(30+20*level),parents,region,key,level,emotion,'bass',10,'hihat_closed01.ogg')
            previous = (region, chord, parents, key)
    return [layers[k] for k in sorted(layers)], performance_map


@guard
def make_score(request, plan, result, mode='arranged', kind='final'):
    validate_result(request, plan, result)
    if kind not in ('comparison','final'): m.reject('乐谱对象类型不受支持。')
    if kind == 'final':
        notes = copy.deepcopy(result['notes']); events = copy.deepcopy(result['emitted_notes']); groups = copy.deepcopy(result['join_groups'])
        _, ledger = _apply_operations(request, plan['operations'], plan['performance_hints'])
        protection_fp = request['protection_summary']['fingerprint']
    else:
        notes = b.actual_notes(request['actual_layout']['base_project']); ledger = base_ledger(request)
        events, groups = joined_events(notes,ledger)
        protection_fp = m.protection_summary(request['actual_layout']['base_project']['protections'])
    layers, mapping = arrange(request,plan,notes,events,groups,ledger,kind,mode)
    bridge = request['connection_ref']['request']['bridge_ref']['request']
    completion = bridge['completion_ref']; targets = copy.deepcopy(completion['candidate']['target_resolution']) if completion else []
    score = dict(header('emoblocks.final-score.v1'), boundary_request_ref=ref(request), boundary_plan_ref=ref(plan),
        connection_plan_ref=ref(request['connection_ref']['plan']), kind=kind, mode=mode,
        total_ticks=request['actual_layout']['total_ticks'], bpm=request['actual_layout']['bpm'], notes=notes, emitted_notes=events,
        join_groups=groups, performance_map=mapping, layers=layers, remaining_gaps=copy.deepcopy(result['remaining_gaps']),
        target_resolution=targets, protection_summary_fingerprint=protection_fp,
        source_fingerprint=m.digest('emoblocks.final-source.v1', source_projection(request,plan,notes,kind)),
        music_fingerprint=music_fingerprint(request['actual_layout']['total_ticks'],request['actual_layout']['bpm'],events))
    score['score_fingerprint'] = score_fingerprint(score); score['id'] = score['score_fingerprint']
    return score


@guard
def validate_final_score(request, plan, score):
    """Check concrete data and finite slots; never invoke an arrangement/composer."""
    m.shape(score, SCORE_FIELDS); version(score, 'emoblocks.final-score.v1')
    result = apply_boundaries(request,plan)
    if score['kind'] not in ('comparison','final') or score['mode'] not in ('arranged','melody_only'):m.reject('最终乐谱类型或模式无效。')
    if score['kind']=='final':
        notes=result['notes'];events=result['emitted_notes'];groups=result['join_groups'];_,ledger=_apply_operations(request,plan['operations'],plan['performance_hints'])
        protection_fp=request['protection_summary']['fingerprint']
    else:
        notes=b.actual_notes(request['actual_layout']['base_project']);ledger=base_ledger(request);events,groups=joined_events(notes,ledger)
        protection_fp=m.protection_summary(request['actual_layout']['base_project']['protections'])
    bridge=request['connection_ref']['request']['bridge_ref']['request'];parent=bridge['completion_ref']
    expected_fields=dict(boundary_request_ref=ref(request),boundary_plan_ref=ref(plan),connection_plan_ref=ref(request['connection_ref']['plan']),
        total_ticks=request['actual_layout']['total_ticks'],bpm=request['actual_layout']['bpm'],notes=notes,emitted_notes=events,join_groups=groups,
        remaining_gaps=result['remaining_gaps'],target_resolution=parent['candidate']['target_resolution'] if parent else [],protection_summary_fingerprint=protection_fp,
        source_fingerprint=m.digest('emoblocks.final-source.v1',source_projection(request,plan,notes,score['kind'])),music_fingerprint=music_fingerprint(request['actual_layout']['total_ticks'],request['actual_layout']['bpm'],events))
    if any(score[k]!=v for k,v in expected_fields.items()) or score['score_fingerprint']!=score_fingerprint(score) or score['id']!=score['score_fingerprint']:
        m.reject('最终乐谱、来源或实际保护被改变。', 'INVALID_FINAL_SCORE')
    validate_layers(request,plan,score,ledger)
    return dict(status='VALID', score_fingerprint=score['score_fingerprint'], music_fingerprint=score['music_fingerprint'],
        layout_fingerprint=request['layout_fingerprint'], protection_summary_fingerprint=score['protection_summary_fingerprint'],
        checks=['dependencies','actual_note_protection','sources','targets','performance_ties','arrangement_rules','fixed_ticks'],
        remaining_gaps=copy.deepcopy(score['remaining_gaps']))


def validate_layers(request,plan,score,ledger):
    """Independent rule-slot verifier, including completeness and role authority."""
    base=request['actual_layout']['base_project'];segments=_segments(request,score['kind']);events=score['emitted_notes']
    hints={h['note_id']:h for h in plan['performance_hints']} if score['kind']=='final' else {}
    ledger={r['note_id']:r for r in ledger};groups={g['render_event']['id']:g for g in score['join_groups']}
    slots={};mapping=[]
    def slot(rule,tick,duration,pitch,velocity,parents,region,key,level,emotion,preset,volume,drum=None,event=None):
        if duration<=0:return
        ident=event['id'] if event else m.digest('emoblocks.arrangement-note.v1',dict(rule=rule,start_tick=tick,duration_tick=duration,pitch=pitch,source_note_ids=parents,region=region))
        fields=dict(note_id=ident,rule=rule,source_note_ids=parents,region=region,start_tick=tick,duration_tick=duration,pitch=pitch,velocity=velocity,key_context=key,intensity=level,emotion=emotion)
        slots[ident]=(fields,preset,volume,drum,event)
    for event in events:
        segment=next((s for s in segments if s['kind']!='blank' and s['start_tick']<=event['start_tick']<s['end_tick']),None)
        if segment is None:m.reject('主旋律没有实际音乐范围。')
        logical=groups[event['id']]['input_note_ids'] if event['id'] in groups else [event['id']]
        preset='soft' if score['mode']=='melody_only' else hints.get(logical[0],{}).get('tone_hint') or PRESETS[segment['emotion']]
        velocity=80 if score['mode']=='melody_only' else event['velocity'];region={k:segment[k] for k in ('start_tick','end_tick')}
        slot('melody',event['start_tick'],event['duration_tick'],event['pitch'],velocity,[event['id']],region,segment['key_context'],m.intensity_at(base,event['start_tick']),segment['emotion'],preset,35,event=event)
        mapping.append(dict(emitted_note_id=event['id'],logical_note_ids=logical,performance_id=ledger[logical[0]]['performance_id'],preset=preset))
    if mapping!=score['performance_map']:m.reject('播放事件被合并到另一次演奏或重复起音丢失。')
    if score['mode']=='arranged':
        previous=None
        for segment in segments:
            region={k:segment[k] for k in ('start_tick','end_tick')}
            if segment['kind']=='blank':
                if previous and previous[0]['end_tick']==region['start_tick']:
                    _,chord,parents,key=previous;level=m.intensity_at(base,region['start_tick']);duration=min(m.PPQ,region['end_tick']-region['start_tick'])
                    for pitch in chord:slot('harmony',region['start_tick'],duration,pitch,min(35,round(28+20*level)),parents,region,key,level,'calm','pad',14)
                previous=None;continue
            actual=[n for n in events if m.intersects(support(n),region)]
            if not actual:previous=None;continue
            key=segment['key_context'];chord=_triad(key,actual);parents=[n['id'] for n in actual];emotion=segment['emotion']
            for tick in range(region['start_tick'],region['end_tick'],m.PPQ):
                duration=min(m.PPQ,region['end_tick']-tick);level=m.intensity_at(base,tick);beat=tick//m.PPQ
                for pitch in chord:slot('harmony',tick,duration,pitch,round(28+20*level),parents,region,key,level,emotion,'dark' if emotion in ('sad','suspense') else 'pad',14)
                slot('bass',tick,int(duration*.8)//10*10,chord[0]-12,round(40+28*level),parents,region,key,level,emotion,'bass',20)
                if beat%2 and level>.35 and emotion!='sad':
                    stride=120 if level>.8 else 240 if level>.6 else 480
                    for index,onset in enumerate(range(tick,tick+duration,stride)):
                        if emotion=='suspense' and index%3==2:continue
                        span=int(min(tick+duration-onset,stride*.6))//10*10
                        slot('pulse',onset,span,chord[index%3]+12,round(30+25*level),parents,region,key,level,emotion,'pluck',15)
                if emotion in ('crisis','resolve') and level>.45:
                    if beat%2:slot('snare',tick,min(100,duration),38,round(45+20*level),parents,region,key,level,emotion,'bass',15,'snare01.ogg')
                    else:slot('kick',tick,min(100,duration),36,round(50+25*level),parents,region,key,level,emotion,'bass',20,'bassdrum01.ogg')
                    for onset in range(tick,tick+duration,120 if emotion=='crisis' and level>.8 else 240):
                        slot('hat',onset,min(60,tick+duration-onset),42,round(30+20*level),parents,region,key,level,emotion,'bass',10,'hihat_closed01.ogg')
            previous=(region,chord,parents,key)
    seen=set();layer_ids=set()
    for layer in score['layers']:
        m.shape(layer,'id role name preset volume pan drum notes rules');m.shape(layer['rules'],'profile entries')
        if layer['id'] in layer_ids or layer['rules']['profile']!='curve-arrangement-v1' or len(layer['notes'])!=len(layer['rules']['entries']):m.reject('编配层重复或规则数量错误。')
        layer_ids.add(layer['id'])
        for note,entry in zip(layer['notes'],layer['rules']['entries']):
            expected=slots.get(note['id'])
            if expected is None or note['id'] in seen:m.reject('新增音符不是允许伴奏或重复了主旋律。')
            fields,preset,volume,drum,event=expected
            if entry!=fields or (layer['preset'],layer['volume'],layer['pan'],layer['drum'])!=(preset,volume,0,drum) or layer['role']!=fields['rule'] or layer['id']!=fields['rule']+':'+preset or layer['name']!=layer['id']:
                m.reject('音色、层角色或真实伴奏规则被改变。')
            if event is not None:expected_note=dict(event,velocity=fields['velocity'])
            else:expected_note=dict(id=note['id'],pitch=fields['pitch'],start_tick=fields['start_tick'],duration_tick=fields['duration_tick'],velocity=fields['velocity'],origin=None,lineage=fields['source_note_ids'],slice=None)
            if note!=expected_note:m.reject('实际层音符与其有限规则不一致。')
            seen.add(note['id'])
    if seen!=set(slots):m.reject('编配遗漏主旋律或必需规则事件。')
