"""P7 local boundary proposals over an authenticated actual P6 layout.

This provider writes no project, lock or asset. All edits read the same input
notes; the independent backend publishes and applies the complete proposal.
"""
import copy
import random

import curve_project as m

REV = 'curve-workflow-v2-r3-p7'
ALGORITHM = 'curve-boundary-v1'
DEFAULTS = dict(policy='auto', max_boundary_ticks=240, max_operations=64,
                max_pitch_shift=2, max_time_shift=120, max_modified_notes=2, max_added_notes=1)
LIMITS = dict(max_boundary_ticks=240, max_operations=256, max_pitch_shift=2,
              max_time_shift=120, max_modified_notes=2, max_added_notes=1)
METHODS = ('natural_continuation', 'motif_reply', 'gradual_build', 'blank_entry', 'resolve_close', 'none')
REQUEST_FIELDS = ('schema spec_rev contract_rev id token input_contract_rev input_fingerprint candidate_ref '
                  'connection_ref actual_layout layout_fingerprint protection_summary plan_id plan_version seed algorithm_version parameters')
LAYOUT_FIELDS = ('total_ticks bpm base_project notes segments coverage_ranges remaining_gaps protections blank_regions emission_ledger')
SEGMENT_FIELDS = ('id performance_id owner_ref start_tick end_tick phrase_id component_path emotion key_context intensity_start intensity_end kind')
REF_FIELDS = 'stage owner_id note_id component_path material_snapshot_id content_fingerprint'


def _fail(code, message):
    raise m.ProjectError(code, message)


def _check(cancel):
    if cancel is not None and cancel():
        _fail('CANCELLED', '最终边界计算已取消，原音乐和保护保持。')


def _warning(code, message):
    return dict(code=code, message=message, details={})


def _range(a, b):
    return dict(start_tick=a, end_tick=b)


def _support(note):
    return _range(note['start_tick'], note['start_tick'] + note['duration_tick'])


def _ordered(notes):
    return sorted(copy.deepcopy(notes), key=lambda n: (n['start_tick'], n['pitch'], n['duration_tick'], n['id']))


def _union(ranges):
    result = []
    for r in sorted(ranges, key=lambda r: (r['start_tick'], r['end_tick'])):
        if result and r['start_tick'] <= result[-1]['end_tick']:
            result[-1]['end_tick'] = max(result[-1]['end_tick'], r['end_tick'])
        else:
            result.append(_range(r['start_tick'], r['end_tick']))
    return result


def _subtract(ranges, guards):
    for guard in guards:
        remaining = []
        for r in ranges:
            a, b = r['start_tick'], r['end_tick']; x, y = guard['start_tick'], guard['end_tick']
            if y <= a or b <= x:
                remaining.append(r)
            else:
                if a < x: remaining.append(_range(a, x))
                if y < b: remaining.append(_range(y, b))
        ranges = remaining
    return ranges


def _contained(region, ranges):
    return any(r['start_tick'] <= region['start_tick'] < region['end_tick'] <= r['end_tick'] for r in ranges)


def _guards(request):
    layout = request['actual_layout']
    locks = [_range(p['start_tick'], p['end_tick']) for p in layout['protections']]
    locks.extend(_support(n) for p in layout['protections'] for n in p['notes'])
    return _union(locks)


def _monotone(notes):
    return all(a['start_tick'] + a['duration_tick'] <= b['start_tick'] for a, b in zip(notes, notes[1:]))


def _ref(value):
    m.shape(value, 'id version fingerprint'); m.ident(value['id']); m.integer(value['version'], 1); m.ident(value['fingerprint'])


def _validate(request):
    """Check the musical input and ledger; backend owns full registry authority."""
    m.canonical(request); m.shape(request, REQUEST_FIELDS)
    if ((request['schema'], request['spec_rev'], request['contract_rev']) != (
            'emoblocks.boundary-request.v1', m.SPEC_REV, REV)
            or request['algorithm_version'] not in (ALGORITHM, 'curve-boundary-v2-deterministic-layout')):
        _fail('UNSUPPORTED_VERSION', '最终边界请求版本不匹配。')
    token = request['token']
    m.shape(token, 'project_id session_id request_id snapshot_id spec_rev contract_rev edit_revision input_fingerprint')
    for key in ('project_id', 'session_id', 'request_id', 'snapshot_id'): m.ident(token[key])
    m.integer(token['edit_revision']); m.ident(request['plan_id']); m.integer(request['plan_version'], 1)
    m.integer(request['seed'], 0, 2**32-1)
    if token['spec_rev'] != m.SPEC_REV or token['contract_rev'] != REV or token['input_fingerprint'] != request['input_fingerprint']:
        _fail('STALE_SNAPSHOT', '最终边界Token与原输入不匹配。')
    if request['candidate_ref'] is not None: _ref(request['candidate_ref'])
    params = request['parameters']; m.shape(params, ' '.join(DEFAULTS))
    if params['policy'] not in ('auto', 'none'): _fail('INVALID_PARAMETERS', '未知边界策略。')
    for key, upper in LIMITS.items(): m.integer(params[key], 0 if key == 'max_added_notes' else 1, upper)
    connection = request['connection_ref']; m.shape(connection, 'attempt_id request plan results outcome')
    m.ident(connection['attempt_id'])
    expected_id = m.digest('emoblocks.boundary-request-id.v1', dict(
        recommendation_request_id=token['request_id'], candidate_ref=request['candidate_ref'],
        connection_attempt_id=connection['attempt_id'], plan_id=request['plan_id'], plan_version=request['plan_version']))
    if request['id'] != expected_id: _fail('STALE_SNAPSHOT', '最终边界请求身份没有绑定真实候选与计划。')
    previous = connection['request']; plan = connection['plan']; outcome = connection['outcome']
    project = previous['input_project']; layout = request['actual_layout']; m.shape(layout, LAYOUT_FIELDS)
    if (token['project_id'] != project['project_id'] or request['input_contract_rev'] != project['contract_rev']
            or request['input_fingerprint'] != m.digest('emoblocks.project.v2.1', project)):
        _fail('STALE_SNAPSHOT', '边界原编辑快照不匹配。')
    if (connection['attempt_id'] != previous['request_id'] or outcome['status'] != 'SUCCEEDED'
            or connection['results'] != outcome['results']
            or sorted(r['connection_id'] for r in connection['results']) != sorted(w['id'] for w in plan['windows'])
            or any(r['status'] != 'READY' for r in connection['results'])):
        _fail('CONNECTION_NOT_READY', '必须有完整真实P6结果，none也需对应计划。')
    old = previous['bridge_ref']; base = old['request']['base_project']
    if (layout['base_project'] != base or layout['notes'] != outcome['notes']
            or layout['protections'] != old['protections'] or layout['blank_regions'] != base['blank_regions']
            or layout['remaining_gaps'] != outcome['remaining_gaps']
            or layout['total_ticks'] != base['total_ticks'] or layout['bpm'] != base['bpm']):
        _fail('STALE_SNAPSHOT', '实际布局不是当前P6拼接。')
    if any(p['kind'] == 'bridge' and p['status'] != 'CONTENT_READY' for p in layout['protections']):
        _fail('BRIDGE_NOT_READY', '范围锁仍未实际就绪，不能最终处理。')
    m.integer(layout['total_ticks'], 1); m.integer(layout['bpm'], 120, 120)
    if request['layout_fingerprint'] != m.digest('emoblocks.final-layout.v1', layout):
        _fail('STALE_SNAPSHOT', '实际最终布局摘要不匹配。')
    m.shape(request['protection_summary'], 'fingerprint ranges')
    if request['protection_summary'] != dict(fingerprint=m.protection_summary(layout['protections']), ranges=_guards(request)):
        _fail('PROTECTION_CONFLICT', '完整保护及长音支撑摘要不匹配。')
    sources = m.source_index(base['sources']); m.notes_check(layout['notes'], layout['total_ticks'], sources)
    notes = _ordered(layout['notes'])
    if not _monotone(notes): _fail('INVALID_BOUNDARY', '实际输入不是单旋律。')
    for n in notes:
        m.integer(n['pitch'], 12, 119)
        if n['origin'] is not None:
            source=sources[n['origin']['source_id']]
            if 'track_id' in source['provenance'] and n['origin']['track_id']!=source['provenance']['track_id']:
                _fail('INVALID_SOURCE', '已知来源的音轨身份不匹配。')
        if any(m.intersects(_support(n), r) for r in layout['blank_regions'] + layout['remaining_gaps']):
            _fail('PROTECTION_CONFLICT', '实际主旋律进入主动留白或剩余gap。')
    for r in layout['coverage_ranges']: m.shape(r, 'start_tick end_tick'); m.range_check(r, layout['total_ticks'])
    if _union(layout['coverage_ranges']) != _union(old['request']['resolved_ranges']):
        _fail('INCOMPLETE_TARGET', '实际已解决范围不匹配。')
    ledger = {}; by_note = m.indexed(notes); performance_owners = {}; owner_performances = {}
    for entry in m.objects(layout['emission_ledger']):
        m.shape(entry, 'note_id parent_ref performance_id'); m.ident(entry['performance_id'])
        if entry['note_id'] in ledger or entry['note_id'] not in by_note: _fail('INVALID_SOURCE', '发声来源账本重复或多余。')
        parent = entry['parent_ref']; m.shape(parent, REF_FIELDS)
        if parent['stage'] not in ('placement', 'bridge', 'connection', 'final_score'): _fail('INVALID_SOURCE', '未知真实父类型。')
        for key in ('owner_id', 'note_id', 'content_fingerprint'): m.ident(parent[key])
        for part in m.objects(parent['component_path']): m.ident(part)
        if parent['material_snapshot_id'] is not None: m.ident(parent['material_snapshot_id'])
        if parent['stage'] == 'placement':
            place = next((p for p in base['placements'] if p['id'] == parent['owner_id']), None)
            material = None if place is None else place['emotion_variant'] or place['base_snapshot']
            if material is None or material['id'] != parent['material_snapshot_id'] or parent['content_fingerprint'] != m.digest('emoblocks.material-snapshot.v1', material):
                _fail('INVALID_SOURCE', '父快照不是实际该次放置。')
            actual = next((n for n in m.placed_notes(place) if n['id'] == entry['note_id']), None)
            if actual != by_note[entry['note_id']] or parent['note_id'] not in (entry['note_id'], actual['id'][len(place['id'])+1:]):
                _fail('INVALID_SOURCE', '音符没有对应真实放置父。')
            # Emotion variants flatten combinations into phrases; occurrence
            # ownership still comes from the unchanged placement base tree.
            path = []; leaf = place['base_snapshot']; onset = actual['start_tick']-place['start_tick']
            while leaf['kind']=='combination':
                child = next((c for c in leaf['children'] if c['offset_tick']<=onset<c['offset_tick']+c['snapshot']['length_ticks']),None)
                if child is None: _fail('INVALID_SOURCE', '音符不属于实际组合子使用。')
                path.append(child['occurrence_id']);onset-=child['offset_tick'];leaf=child['snapshot']
            if parent['component_path']!=path: _fail('INVALID_SOURCE', '父路径不是该音符实际子使用。')
        elif parent['stage'] in ('bridge', 'connection'):
            rows = old['results'] if parent['stage'] == 'bridge' else connection['results']
            key = 'bridge_id' if parent['stage'] == 'bridge' else 'connection_id'
            row = next((r for r in rows if r[key] == parent['owner_id']), None)
            if row is None or row['content_fingerprint'] != parent['content_fingerprint'] or by_note[entry['note_id']] not in row['notes']:
                _fail('INVALID_SOURCE', '来源不是实际桥/连接的发声。')
        else:
            if parent['material_snapshot_id'] is not None: _fail('INVALID_SOURCE', '旧接受谱父不能假扮Material。')
            leaves = [r['payload']['p7']['final_score'] for r in base['records']
                      if r['kind']=='final_score' and 'p7' in r['payload']]
            captured = [r['payload'] for r in base['records'] if r['kind']=='captured_music']
            actual = by_note[entry['note_id']]
            if not (any(s['id']==parent['owner_id'] and s['score_fingerprint']==parent['content_fingerprint'] and actual in s['notes'] for s in leaves)
                    or any(s['source_score_ref']['id']==parent['owner_id'] and s['source_score_ref']['fingerprint']==parent['content_fingerprint']
                           and actual in s['source_notes'] for s in captured)) or parent['note_id']!=actual['id']:
                _fail('INVALID_SOURCE', '旧接受父没有在实际捕获音乐中解析。')
        if parent['stage'] != 'final_score':
            owner = (parent['stage'],parent['owner_id'],tuple(parent['component_path']) if parent['stage']=='placement' else ())
            performance = entry['performance_id']
            if performance_owners.get(performance,owner)!=owner or owner_performances.get(owner,performance)!=performance:
                _fail('INVALID_SOURCE', '独立子使用不能共享演奏身份，同一演奏不能伪拆。')
            performance_owners[performance]=owner;owner_performances[owner]=performance
        ledger[entry['note_id']] = entry
    if set(ledger) != set(by_note): _fail('INVALID_SOURCE', '来源账本没有完整覆盖真实发声。')
    for protection in layout['protections']:
        if protection['status']!='CONTENT_READY': continue
        domains=[_range(protection['start_tick'],protection['end_tick'])]+[_support(n) for n in protection['notes']]
        captured=[n for n in notes if any(m.intersects(_support(n),r) for r in domains)]
        if m.structural_notes(captured)!=m.structural_notes(protection['notes']):
            _fail('PROTECTION_CONFLICT', '实际受保护音乐或名义休止不等于已就绪内容。')
    for segment in m.indexed(layout['segments']).values():
        m.shape(segment, SEGMENT_FIELDS); m.range_check(_range(segment['start_tick'],segment['end_tick']), layout['total_ticks'])
        if segment['kind'] not in ('placement', 'bridge', 'connection', 'blank'): _fail('INVALID_BOUNDARY', '未知真实段类型。')
        if segment['kind'] != 'blank': m.ident(segment['performance_id'])
        if segment['owner_ref'] is not None: _ref(segment['owner_ref'])
        if segment['emotion'] not in m.EMOTIONS: _fail('INVALID_BOUNDARY', '未知情绪。')
        key = segment['key_context']; m.shape(key, 'tonic mode confidence method'); m.integer(key['tonic'], 0, 11)
        if key['mode'] not in ('major', 'minor'): _fail('INVALID_BOUNDARY', '未知调式。')
        m.ident(key['method'])
        if type(key['confidence']) not in (int,float) or not 0<=key['confidence']<=1: _fail('INVALID_BOUNDARY', '调性置信度无效。')
        for field in ('intensity_start', 'intensity_end'):
            if type(segment[field]) not in (int, float) or not 0 <= segment[field] <= 1: _fail('INVALID_BOUNDARY', '强度无效。')
    segments=sorted(layout['segments'],key=lambda s:(s['start_tick'],s['end_tick'],s['id']))
    if any(a['end_tick']>b['start_tick'] for a,b in zip(segments,segments[1:])): _fail('INVALID_BOUNDARY', '实际演奏段重复覆盖。')
    for n in notes:
        if not any(s['performance_id']==ledger[n['id']]['performance_id'] and s['start_tick']<=n['start_tick']<s['end_tick'] for s in segments):
            _fail('INVALID_SOURCE', '发声没有对应的真实演奏所有者。')
    return ledger


def _endpoints(notes, tick):
    left = [n for n in notes if n['start_tick'] + n['duration_tick'] <= tick]
    right = [n for n in notes if n['start_tick'] >= tick]
    return (max(left, key=lambda n: (n['start_tick']+n['duration_tick'], n['id'])) if left else None,
            min(right, key=lambda n: (n['start_tick'], n['id'])) if right else None)


def _endpoint(note):
    return None if note is None else dict(note_id=note['id'], **{k: note[k] for k in ('pitch', 'start_tick', 'duration_tick')})


def _splice(notes, operations):
    consumed = {i for op in operations for i in op['consumed_note_ids']}
    return _ordered([n for n in notes if n['id'] not in consumed] + [o['note'] for op in operations for o in op['outputs']])


def _joins(notes, ledger, cancel):
    runs = []; current = []
    for note in _ordered(notes):
        _check(cancel); prior = current[-1] if current else None
        a = prior['slice'] if prior else None; b = note['slice']
        tie = (a and b and ledger[prior['id']]['performance_id'] == ledger[note['id']]['performance_id']
               and prior['origin'] == note['origin'] and prior['pitch'] == note['pitch']
               and a['parent_emission_id'] == b['parent_emission_id'] and a['parent_duration_tick'] == b['parent_duration_tick']
               and prior['start_tick'] + prior['duration_tick'] == note['start_tick']
               and a['offset_tick'] + prior['duration_tick'] == b['offset_tick'])
        if not tie:
            if len(current) > 1: runs.append(current)
            current = []
        current.append(note)
    if len(current) > 1: runs.append(current)
    groups = []
    for run in runs:
        performance = ledger[run[0]['id']]['performance_id']; source = run[0]['slice']['parent_emission_id']; ids = [n['id'] for n in run]
        event = dict(copy.deepcopy(run[0]), id=m.digest('emoblocks.final-emission.v1', dict(
            performance_id=performance, source_emission_id=source, input_note_ids=ids)),
            duration_tick=sum(n['duration_tick'] for n in run), slice=None,
            lineage=list(dict.fromkeys(i for n in run for i in n['lineage'] + [n['id']])))
        groups.append(dict(performance_id=performance, input_note_ids=ids, source_emission_id=source, render_event=event))
    return groups


def _boundaries(request):
    layout = request['actual_layout']; segments = sorted(layout['segments'], key=lambda s: (s['start_tick'], s['end_tick'], s['id']))
    events = []
    for index, right in enumerate(segments):
        left = segments[index-1] if index else None
        if left is None or left['end_tick'] != right['start_tick']:
            if left is not None: events.append((left['end_tick'], left, None))
            events.append((right['start_tick'], None, right))
        elif (left['performance_id'], left['kind']) != (right['performance_id'], right['kind']):
            events.append((right['start_tick'], left, right))
    if segments: events.append((segments[-1]['end_tick'], segments[-1], None))
    return sorted(events, key=lambda e: e[0])


def _method(tick, left, right, a, b, total):
    if right and right['kind'] != 'blank' and ((left is None and b and b['start_tick']>tick) or (left and left['kind']=='blank')
                                             or (a and b and b['start_tick']-a['start_tick']-a['duration_tick'] >= 60)):
        return 'blank_entry'
    if left and left['kind'] != 'blank' and (right is None or right['kind'] == 'blank'):
        key = left['key_context']
        if a and (a['pitch'] % 12 != key['tonic'] or left['intensity_end'] < left['intensity_start']-.1): return 'resolve_close'
        return 'none'
    if left and right and left['kind'] != 'blank' and right['kind'] != 'blank':
        if right['intensity_end'] > left['intensity_start']+.1: return 'gradual_build'
        if right['intensity_end'] < left['intensity_start']-.1: return 'resolve_close'
        if a and b and (abs(a['pitch']-b['pitch']) > 2 or abs(a['duration_tick']-b['duration_tick']) >= 120): return 'motif_reply'
        if a and b and (abs(a['velocity']-b['velocity']) > 8 or left['emotion'] != right['emotion']): return 'natural_continuation'
    return 'none'


def _candidate(request, boundary, method, a, b, left, right, ledger, rng):
    p = request['parameters']; ranges = boundary['editable_ranges']; total = request['actual_layout']['total_ticks']
    note = b if method in ('motif_reply', 'blank_entry') else a
    if note is None or not _contained(_support(note), ranges): return None
    kind = 'replace'; output = copy.deepcopy(note); unit = 10 if note['start_tick'] % 10 == 0 and note['duration_tick'] % 10 == 0 else 1
    delta = min(p['max_time_shift'], 60); delta = delta//unit*unit
    if method == 'blank_entry':
        if note['start_tick'] > boundary['tick'] and p['max_added_notes']:
            start = max(boundary['tick'], note['start_tick']-min(120, delta or unit)); duration = note['start_tick']-start
            if duration <= 0: return None
            kind = 'add'; output.update(start_tick=start, duration_tick=duration)
            degrees = (0,2,4,5,7,9,11) if right['key_context']['mode']=='major' else (0,2,3,5,7,8,10)
            pickups = [x for x in range(max(12,note['pitch']-p['max_pitch_shift']),min(119,note['pitch']+p['max_pitch_shift'])+1)
                       if x!=note['pitch'] and (x-right['key_context']['tonic'])%12 in degrees]
            if not pickups: return None
            output['pitch'] = min(pickups,key=lambda x:(abs(x-note['pitch']),x))
        elif delta and note['duration_tick'] > delta:
            output.update(start_tick=note['start_tick']+delta, duration_tick=note['duration_tick']-delta)
        else: return None
    elif method == 'motif_reply':
        segment = right or left; degrees = (0,2,4,5,7,9,11) if segment['key_context']['mode'] == 'major' else (0,2,3,5,7,8,10)
        pitches = [x for x in range(max(12,note['pitch']-p['max_pitch_shift']), min(119,note['pitch']+p['max_pitch_shift'])+1)
                   if x != note['pitch'] and (x-segment['key_context']['tonic'])%12 in degrees]
        if pitches and a:
            pitch = min(pitches, key=lambda x: (abs(x-a['pitch']), abs(x-note['pitch']), x))
            if abs(pitch-a['pitch']) < abs(note['pitch']-a['pitch']): output['pitch'] = pitch
        if output['pitch'] == note['pitch']:
            shorten = min(delta, unit*rng.choice((1,2)))
            if not shorten or note['duration_tick'] <= shorten: return None
            output['duration_tick'] -= shorten
    elif method == 'gradual_build':
        if b is None: return None
        shift = max(-p['max_pitch_shift'], min(p['max_pitch_shift'], b['pitch']-note['pitch']))
        if shift == 0: return None
        output['pitch'] = note['pitch']+shift
    elif method == 'resolve_close':
        if (note['duration_tick'] <= 120 and note['velocity'] <= 80 and note['start_tick'] % 1920 != 0):
            kind = 'remove'; output = None
        else:
            tonic = (left or right)['key_context']['tonic']; pitches = [x for x in range(12,120) if x%12 == tonic and abs(x-note['pitch']) <= p['max_pitch_shift']]
            if pitches and note['pitch']%12 != tonic: output['pitch'] = min(pitches, key=lambda x:(abs(x-note['pitch']),x))
            elif delta and note['duration_tick'] > delta: output['duration_tick'] -= delta
            else: return None
    else: return None
    if output is not None and not 12 <= output['pitch'] <= 119: return None
    original = ledger[note['id']]; req_fp = m.digest('emoblocks.boundary-request.v1', request)
    ident = m.digest('emoblocks.boundary-operation.v1', dict(request_fingerprint=req_fp, boundary_id=boundary['id'], kind=kind,
        parent_id=note['id'], structure=None if output is None else {k:output[k] for k in ('pitch','start_tick','duration_tick')}))
    if output is not None:
        output.update(id=m.digest('emoblocks.boundary-note.v1', dict(request_id=request['id'], operation_id=ident,
            note={k:output[k] for k in ('pitch','start_tick','duration_tick')})), slice=None,
            lineage=list(dict.fromkeys(note['lineage']+[note['id']])))
    return dict(id=ident, boundary_ids=[boundary['id']], kind=kind, input_refs=[copy.deepcopy(original['parent_ref'])],
        consumed_note_ids=[] if kind == 'add' else [note['id']],
        outputs=[] if output is None else [dict(note=output, parent_note_ids=[note['id']], performance_id=original['performance_id'])],
        permitted_ranges=copy.deepcopy(ranges))


def _feasible(request, operation, accepted, ledger):
    layout = request['actual_layout']; notes = layout['notes']; p = request['parameters']; by_id = m.indexed(notes)
    consumed = operation['consumed_note_ids']; used = {i for op in accepted for i in op['consumed_note_ids']}
    if any(i in used for i in consumed): return False
    forbidden = _guards(request) + layout['blank_regions'] + layout['remaining_gaps'] + request['connection_ref']['plan']['windows']
    for i in consumed:
        if (not _contained(_support(by_id[i]), operation['permitted_ranges']) or
                any(m.intersects(_support(by_id[i]),r) for r in forbidden)): return False
    for out in operation['outputs']:
        n = out['note']; parent = by_id[out['parent_note_ids'][0]]
        if not _contained(_support(n), operation['permitted_ranges']): return False
        if operation['kind'] == 'replace' and any(abs(n[k]-parent[k]) > p[limit] for k, limit in (
                ('pitch','max_pitch_shift'),('start_tick','max_time_shift'),('duration_tick','max_time_shift'))): return False
        if n['origin'] != parent['origin'] or n['lineage'] != list(dict.fromkeys(parent['lineage']+[parent['id']])) or n['slice'] is not None: return False
    final = _splice(notes, accepted+[operation])
    if (len({n['id'] for n in final}) != len(final) or
            any(o['note']['id'] in by_id for op in accepted+[operation] for o in op['outputs']) or
            not _monotone(final) or (notes and not final)): return False
    if any(m.intersects(_support(n), r) for op in accepted+[operation] for n in [o['note'] for o in op['outputs']] for r in forbidden): return False
    completion = request['connection_ref']['request']['bridge_ref']['request']['completion_ref']
    if completion is not None:
        if any(not any(m.intersects(_support(n), gap) for n in final) for gap in completion['request']['target_gaps']): return False
    return True


def _hint(boundary, method, a, b, left, right, ledger):
    note = b if method in ('blank_entry', 'natural_continuation') else a
    if note is None: return None
    if method == 'natural_continuation':
        delta = max(-6, min(6, a['velocity']-b['velocity'])) if a and b else 0
        tone = {'calm':'soft','hope':'bell','sad':'dark','suspense':'pluck','crisis':'pluck','resolve':'brass'}[(right or left)['emotion']] if left and right and left['emotion'] != right['emotion'] else None
        accompaniment = 'sustain'
        if not delta and tone is None: return None
    else:
        delta = {'gradual_build':6,'blank_entry':3,'resolve_close':-6,'motif_reply':-3}.get(method,0)
        tone = None; accompaniment = {'gradual_build':'fade_in','blank_entry':'fade_in','resolve_close':'reduce','motif_reply':'sustain'}.get(method,'none')
    delta = max(1-note['velocity'], min(127-note['velocity'], delta))
    return dict(id=m.digest('emoblocks.boundary-hint.v1', [boundary['id'],note['id'],delta,tone,accompaniment]),
        boundary_id=boundary['id'], note_id=note['id'], performance_id=ledger[note['id']]['performance_id'],
        velocity_delta=delta, tone_hint=tone, accompaniment_hint=accompaniment)


def _joints(boundaries, before, after):
    endpoints = {b['id']:_endpoints(before,b['tick']) for b in boundaries}; shared = {}
    for ident, pair in endpoints.items():
        for n in pair:
            if n: shared.setdefault(n['id'],set()).add(ident)
    groups = []
    for owners in (owners for owners in shared.values() if len(owners)>1):
        overlapping = [g for g in groups if g & owners]
        merged = set(owners)
        for group in overlapping: merged |= group; groups.remove(group)
        groups.append(merged)
    result = []; by_id = {b['id']:b for b in boundaries}
    for group in sorted(groups,key=lambda g:tuple(sorted(g))):
        ids = sorted(group)
        def rows(notes):
            return [dict(boundary_id=i,left=_endpoint(_endpoints(notes,by_id[i]['tick'])[0]),right=_endpoint(_endpoints(notes,by_id[i]['tick'])[1])) for i in ids]
        result.append(dict(id=m.digest('emoblocks.boundary-joint.v1',ids),boundary_ids=ids,
            note_ids=sorted(i for i,owners in shared.items() if len(owners & group)>1),
            original_endpoints=rows(before),final_endpoints=rows(after)))
    return result


def plan_boundaries(request, should_cancel=None, on_progress=None):
    """Produce concrete local edits and performance handoffs, never a score."""
    # 无需过渡也是有效结果；不自动处理每一处四拍或情绪分界。
    try: ledger = _validate(request)
    except m.ProjectError: raise
    except (KeyError,TypeError,OverflowError,RecursionError) as exc:
        raise m.ProjectError('INVALID_BOUNDARY','最终边界请求缺少真实音乐或字段形状无效。') from exc
    _check(should_cancel)
    if on_progress is not None: on_progress('读取真实连接后音乐，核对完整保护与演奏来源。')
    layout = request['actual_layout']; original = _ordered(layout['notes']); params = request['parameters']
    operations = []; hints = []; boundaries = []; assessments = []; tested = attempted = 0; exhausted = False
    events = _boundaries(request) if params['policy'] == 'auto' else []
    forbidden = _guards(request) + layout['blank_regions'] + layout['remaining_gaps'] + request['connection_ref']['plan']['windows']
    hint_notes = set(); needs = False
    for tick, left, right in events:
        _check(should_cancel); tested += 1
        a, b = _endpoints(original,tick); method = _method(tick,left,right,a,b,layout['total_ticks'])
        needs |= method != 'none'
        if method != 'none' and attempted >= params['max_operations']: exhausted = True; break
        ident = m.digest('emoblocks.boundary.v1', dict(request_id=request['id'], tick=tick,
            left=None if left is None else left['performance_id'],right=None if right is None else right['performance_id']))
        span = params['max_boundary_ticks']; wanted = []
        if left is not None:
            wanted.append(_range(max(left['start_tick'],left['end_tick']-span),left['end_tick']))
        if right is not None:
            wanted.append(_range(right['start_tick'],min(right['end_tick'],right['start_tick']+span)))
        permitted = [_range(max(local['start_tick'],r['start_tick']),min(local['end_tick'],r['end_tick']))
                     for local in wanted for r in layout['coverage_ranges'] if m.intersects(local,r)]
        ranges = _subtract(_union(permitted),_union(forbidden))
        boundary = dict(id=ident,tick=tick,left_performance_id=None if left is None else left['performance_id'],
            right_performance_id=None if right is None else right['performance_id'],method=method,
            editable_ranges=ranges,operation_ids=[],reasons=[])
        semantic = dict(seed=request['seed'],tick=tick,method=method,
            notes=[{k:n[k] for k in ('pitch','start_tick','duration_tick','velocity')} for n in (a,b) if n])
        rng = random.Random(int(m.digest('emoblocks.boundary-musical-seed.v1',semantic)[:8],16))
        candidate = _candidate(request,boundary,method,a,b,left,right,ledger,rng)
        if candidate is not None:
            _check(should_cancel); attempted += 1
            if not any(i in hint_notes for i in candidate['consumed_note_ids']) and _feasible(request,candidate,operations,ledger):
                operations.append(candidate); boundary['operation_ids'].append(candidate['id'])
        # A hint cannot pretend that a removed/replaced original is still an
        # actual output. A single writer owns each input structure/performance.
        consumed = {i for op in operations for i in op['consumed_note_ids']}
        hint = _hint(boundary,method,a,b,left,right,ledger) if method != 'none' else None
        if hint:
            if attempted >= params['max_operations']: exhausted = True
            else:
                _check(should_cancel); attempted += 1
                if hint['note_id'] not in consumed and hint['note_id'] not in hint_notes:
                    hints.append(hint); hint_notes.add(hint['note_id'])
        accepted = bool(boundary['operation_ids'] or any(h['boundary_id']==ident for h in hints))
        reasons = ['从同一实际Layout完成有限局部处理；旋律保护不变，听感未验证。' if accepted else
                   '实际端点无需专门处理。' if method=='none' else '完整支撑、保护或冲突无结构空间，保留原发声。']
        assessments.append(dict(boundary_id=ident,method=method,accepted=accepted,reasons=reasons))
        boundary['method'] = method if accepted else 'none'
        boundary['reasons'] = [_warning('LOCAL_CHANGE' if accepted else 'PRESERVE',reasons[0])]
        boundaries.append(boundary)
        if exhausted: break
    if exhausted and not operations and not hints: _fail('SEARCH_BUDGET_EXHAUSTED','预算已耗尽且未找到合法操作，不能宣称无合法窗口。')
    final = _splice(original,operations); final_ledger = dict(ledger)
    velocities = {h['note_id']:h['velocity_delta'] for h in hints}
    final = [dict(n,velocity=n['velocity']+velocities.get(n['id'],0)) for n in final]
    for op in operations:
        for out in op['outputs']: final_ledger[out['note']['id']] = dict(performance_id=out['performance_id'])
    joins = _joins(final,final_ledger,should_cancel)
    joints = _joints(boundaries,original,final); _check(should_cancel)
    decision = 'selected' if operations or hints else 'none'
    reason = None if decision == 'selected' else 'POLICY_NONE' if params['policy']=='none' else 'NO_LEGAL_OPERATION' if needs else 'NOT_NEEDED'
    warnings = [_warning('SELECTED' if decision=='selected' else reason,'具体边界操作与真实播放账本已完成，等待独立统一认证。')]
    if exhausted: warnings.append(_warning('SEARCH_BUDGET_EXHAUSTED','仅提交预算内已检查的局部方案，未完成全部搜索。'))
    if on_progress is not None: on_progress('边界操作统一冲突检查完成；没有修改原工程、桥或连接结构。')
    return dict(schema='emoblocks.boundary-proposal.v1',spec_rev=m.SPEC_REV,contract_rev=REV,
        request_fingerprint=m.digest('emoblocks.boundary-request.v1',request),decision=decision,none_reason=reason,
        boundaries=boundaries,operations=operations,joints=joints,join_groups=joins,performance_hints=hints,
        assessments=assessments,reasons=warnings,search=dict(tested_boundaries=tested,attempted_operations=attempted,
            termination='POLICY_NONE' if params['policy']=='none' else 'BUDGET_EXHAUSTED' if exhausted else 'COMPLETE'))
