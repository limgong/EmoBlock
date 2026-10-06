"""Deterministic ordinary melody rules and P5 whole-phrase bridge composition.

Times are integer ticks at PPQ=480. Source references are resolved by the
workflow when applying a batch; standalone derivation checks their shape only.
All public functions leave their input unchanged and return independent data.
"""
import copy
import math
import random

import curve_project as model
import intensity_curve

PPQ = 480
BAR = 4 * PPQ
ALGORITHM_VERSION = 'curve-melody-rules-v1'
COUNTER_ALGORITHM_VERSION = 'curve-melody-counter-v2'
SEGMENTATION_VERSION = 'rest-phrases-v1'
RNG_VERSION = 'python.random-v3'
METHODS = ('variant', 'answer', 'counter', 'rhythm', 'develop', 'density')
DEFAULTS = {
    'variant': {'max_step': 2, 'fraction': .35},
    'answer': {'degree_shift': 1},
    'counter': {'degree_shift': 2},
    'rhythm': {'rotation': 1, 'unit_ticks': 120},
    'develop': {'sequence_step': 1},
    'density': {'direction': 'denser', 'max_splits': 2},
}

BRIDGE_VERSION = 'curve-bridge-v1'


def _bridge_parent_table(project):
    """Resolve actual emissions, including transformed combo notes, to captures."""
    table = {}
    for placement in project['placements']:
        actual = placement['emotion_variant'] or placement['base_snapshot']
        for local in actual['notes']:
            path = []; component = placement['base_snapshot']; offset = 0
            while component['kind'] == 'combination':
                child = next(c for c in component['children']
                    if offset + c['offset_tick'] <= local['start_tick']
                    < offset + c['offset_tick'] + c['snapshot']['length_ticks'])
                path.append(child['occurrence_id']); offset += child['offset_tick']
                component = child['snapshot']
            absolute = dict(copy.deepcopy(local), id=placement['id'] + ':' + local['id'],
                            start_tick=placement['start_tick'] + local['start_tick'])
            if absolute['id'] in table:
                _fail('INVALID_CANDIDATE', '实际发声身份重复，不能认证桥动机。')
            table[absolute['id']] = dict(note=absolute, snapshot=actual,
                parent_ref=dict(placement_id=placement['id'], component_path=path,
                    material_snapshot_id=actual['id'], note_id=local['id']))
    return table


def _bridge_seed(request, window, joints):
    musical_joints = [dict(tick=j['tick'], relation=j['relation'],
        left_endpoint=j['left_endpoint'], right_endpoint=j['right_endpoint']) for j in joints
        if window['id'] in (j['left_bridge_id'], j['right_bridge_id'])]
    musical_joints.sort(key=model.canonical)
    projection = dict(base_fingerprint=request['base_fingerprint'], seed=request['seed'],
        range={k: window[k] for k in ('start_tick', 'end_tick')}, joints=musical_joints)
    return int(model.digest('emoblocks.bridge-music-seed.v1', projection)[:8], 16)


def _bridge_endpoints(window, joints):
    entry = exit_ = None
    for joint in joints:
        if joint['right_bridge_id'] == window['id']:
            if entry is not None:
                _fail('PROTECTION_CONFLICT', '桥入口共同条件重复。')
            entry = joint['right_endpoint']
        if joint['left_bridge_id'] == window['id']:
            if exit_ is not None:
                _fail('PROTECTION_CONFLICT', '桥出口共同条件重复。')
            exit_ = joint['left_endpoint']
    return entry, exit_


def compose_bridge_phrase(request, window, joint_boundary_conditions, should_cancel=None):
    """P5 fresh motif/answer/sequence phrase with exact rests and joint anchors.

    No lock or project edits. Every emitted note has exactly one concrete
    captured parent. The per-bridge note budget fails rather than truncating.
    """
    def check():
        if should_cancel is not None and should_cancel():
            _fail('CANCELLED', '完整桥乐句构作已取消。')
    check()
    model.canonical(request); model.validate(request['base_project'])
    start, end = window['start_tick'], window['end_tick']
    length = end - start
    model.integer(length, 1)
    parents = _bridge_parent_table(request['base_project'])
    ids = window['context']['motif_note_ids']
    if not ids or len(ids) != len(set(ids)) or any(i not in parents for i in ids):
        _fail('BRIDGE_GENERATION_FAILED', '桥没有可追溯的实际动机父音符。')
    motif = [parents[i] for i in ids]
    if not any(r['start_tick'] <= start < end <= r['end_tick'] for r in request['resolved_ranges']):
        _fail('PROTECTION_CONFLICT', '完整桥句不能跨未解决范围。')
    for protection in request['base_project']['protections']:
        guards = model.protection_ranges(protection) + [dict(start_tick=n['start_tick'], end_tick=n['start_tick']+n['duration_tick']) for n in protection['notes']]
        if any(model.intersects(window, r) for r in guards):
            _fail('PROTECTION_CONFLICT', '完整桥句与原独立保护层冲突。')
    allowed = {i for i, p in parents.items() if model.intersects(window,
        dict(start_tick=p['note']['start_tick'], end_tick=p['note']['start_tick']+p['note']['duration_tick']))}
    for side in ('left', 'right'):
        allowed.update(n['id'] for n in (window['context'][side] or {}).get('notes', []))
    if not set(ids) <= allowed:
        _fail('INVALID_CANDIDATE', '完整句动机不能借无关实际来源。')
    key = _key(dict(provenance=dict(key_context=window['context']['key_context']), generation=None),
               [p['note'] for p in motif])
    scale = _scale(key)
    seed = _bridge_seed(request, window, joint_boundary_conditions)
    rng = random.Random(seed)
    masks = [dict(start_tick=r['start_tick'] - start, end_tick=r['end_tick'] - start)
             for r in window['blank_mask']]
    for mask in masks:
        model.range_check(mask, length)
    endpoints = _bridge_endpoints(window, joint_boundary_conditions)
    reserved = []
    for spec in endpoints:
        if spec is None:
            continue
        model.shape(spec, 'pitch start_tick duration_tick')
        model.integer(spec['pitch'], 0, 127); model.integer(spec['duration_tick'], 1)
        a = spec['start_tick'] - start; b = a + spec['duration_tick']
        if not 0 <= a < b <= length or any(model.intersects(dict(start_tick=a, end_tick=b), m) for m in masks):
            _fail('PROTECTION_CONFLICT', '共同端点越窗或进入主动留白。')
        if spec not in reserved:
            reserved.append(spec)
    if any(model.intersects(dict(start_tick=a['start_tick'], end_tick=a['start_tick']+a['duration_tick']),
                            dict(start_tick=b['start_tick'], end_tick=b['start_tick']+b['duration_tick']))
           for i, a in enumerate(reserved) for b in reserved[i+1:]):
        _fail('PROTECTION_CONFLICT', '共同入口与出口重叠。')
    exact_values = [start, end] + [v for m in window['blank_mask'] for v in m.values()]
    exact_values += [v for spec in reserved for k, v in spec.items() if k != 'pitch']
    exact_values += [v for p in motif for k, v in p['note'].items() if k in ('start_tick', 'duration_tick')]
    unit = 10 if all(v % 10 == 0 for v in exact_values) else 1
    rhythm = [max(unit, min(960, p['note']['duration_tick'])) for p in motif]
    input_projection = dict(base_fingerprint=request['base_fingerprint'], range=dict(start_tick=start, end_tick=end),
        motif=[p['note'] for p in motif], key=key, blank_mask=window['blank_mask'],
        endpoints=endpoints, seed=seed, algorithm_version=BRIDGE_VERSION)
    input_hash = model.digest('emoblocks.bridge-compose-input.v1', input_projection)
    ident = _id('bridge-phrase', input_hash)
    notes = []; cells = []
    budget = request['parameters']['max_notes']; model.integer(budget, 1, 4096)

    def emit(parent_index, pitch, onset, duration, rule, cycle):
        check()
        if len(notes) >= budget:
            _fail('BRIDGE_GENERATION_FAILED', '本桥作曲音符预算耗尽；不截短乐句。')
        parent = motif[parent_index % len(motif)]
        original = parent['note']; index = len(notes)
        note = dict(copy.deepcopy(original), id=_id('bridge-note', [ident, index]), pitch=pitch,
            start_tick=onset, duration_tick=duration, slice=None,
            lineage=list(dict.fromkeys(original['lineage'] + [original['id']])))
        notes.append(note)
        cells.append(dict(operation='bridge-motif-cell', input_note_id=original['id'],
            parent_ref=copy.deepcopy(parent['parent_ref']), output_note_id=note['id'],
            motif_index=parent_index % len(motif), cycle_index=cycle, rule=rule,
            from_pitch=original['pitch'], to_pitch=pitch, start_tick=onset, duration_tick=duration))

    # Reserve actual endpoint notes, including their whole supports, before
    # constructing the interior. This is not endpoint pitch interpolation.
    for spec in reserved:
        is_entry = spec == endpoints[0]
        emit(0 if is_entry else len(motif)-1, spec['pitch'], spec['start_tick']-start,
             spec['duration_tick'], 'opening' if is_entry else 'arrival', 0)
    blocked = masks + [dict(start_tick=s['start_tick']-start,
                            end_tick=s['start_tick']-start+s['duration_tick']) for s in reserved]
    entry, exit_ = endpoints
    has_following_music = bool(window['context']['right']) or any(p['note']['start_tick'] >= end for p in parents.values())
    low = entry['start_tick'] - start if entry else 0
    high = exit_['start_tick'] - start + exit_['duration_tick'] if exit_ else length
    if low > 0: blocked.append(dict(start_tick=0, end_tick=low))
    if high < length: blocked.append(dict(start_tick=high, end_tick=length))
    cursor = 0; step = 0
    while cursor < length:
        check()
        covering = [m['end_tick'] for m in blocked if m['start_tick'] <= cursor < m['end_tick']]
        if covering:
            cursor = max(covering); continue
        boundary = min([length] + [m['start_tick'] for m in blocked if m['start_tick'] > cursor])
        motif_index = step % len(motif); cycle = step // len(motif)
        parent_pitch = motif[motif_index]['note']['pitch']
        cell = rhythm[motif_index]
        rule = 'opening'
        if cursor >= length * 3 // 4:
            rule = 'arrival'
            stable = [p for p in scale if p % 12 in (key['tonic'], (key['tonic']+7)%12)]
            pitch = min(stable, key=lambda p: (abs(p-parent_pitch), p))
            cell = min(960, max(cell, 240))
        elif cycle or cursor >= length // 4:
            development = max(1, cycle, cursor*4//length)
            if cursor < length // 2 or development % 2:
                rule = 'answer'
                axis = _degree(scale, motif[0]['note']['pitch'])
                degree = 2*axis - _degree(scale, parent_pitch) + rng.choice((0, 1))
                pitch = scale[max(0, min(len(scale)-1, degree))]
            else:
                rule = 'sequence'
                level = intensity_curve.evaluate([dict(time=p['tick'], level=p['level']) for p in request['base_project']['intensity_points']], start+cursor)
                pitch = _step(scale, parent_pitch, (1 if level >= .5 else -1) * (1+development%3))
            if development % 3 == 0:
                rule = 'rhythm'; cell = max(unit, (cell//2//unit)*unit)
        else:
            pitch = parent_pitch
        cell = min(cell, boundary-cursor)
        duration = cell
        # Phrase-level reply articulation and the final entry space are
        # explicit rests. No changes are made at every fourbeat child edge.
        if rule in ('answer', 'rhythm') and cell >= 4*unit:
            duration -= unit * min(12, max(1, cell//(8*unit)))
        if exit_ is None and cursor+cell == length and has_following_music and cell >= 4*unit:
            duration = min(duration, cell-unit*min(12, max(1, cell//(4*unit))))
        emit(motif_index, pitch, cursor, duration, rule, cycle)
        cursor += cell; step += 1
    paired = sorted(zip(notes, cells), key=lambda pair: pair[0]['start_tick'])
    notes = [p[0] for p in paired]; cells = [p[1] for p in paired]
    if not notes:
        _fail('BRIDGE_GENERATION_FAILED', '桥没有实际音符，不能视为完成。')
    result = dict(id=ident, label='桥完整乐句', kind='phrase', length_ticks=length, notes=notes,
        provenance=dict(source_start_tick=None, key_context=key,
            parent_snapshots={p['parent_ref']['placement_id']:copy.deepcopy(p['snapshot']) for p in motif}),
        generation=dict(method='bridge_phrase', parameters=dict(target_ticks=length,
            rhythm_method='captured-motif-cells-with-reply-rests', motif_method='opening-answer-sequence-arrival',
            rule_unit_ticks=unit), seed=seed, rng_version=RNG_VERSION, algorithm_version=BRIDGE_VERSION,
            input_fingerprint=input_hash,
            input_material_ids=list(dict.fromkeys(p['snapshot']['id'] for p in motif)),
            base_notes=[copy.deepcopy(p['note']) for p in motif], key_context=key, operations=cells),
        phrase_id=None, children=[])
    music_signature(result)
    return result


def _fail(code, message):
    raise model.ProjectError(code, message)


def _id(domain, value):
    return model.digest('emoblocks.melody.' + domain + '.v1', value)


def _seed(seed):
    if type(seed) is not int:
        _fail('INVALID_PARAMETERS', '种子必须是整数。')


def _notes(notes, length):
    model.indexed(notes)
    for note in notes:
        model.shape(note, 'id pitch start_tick duration_tick velocity origin lineage slice')
        # There is no source registry in derive(Material). Do not invent or
        # resolve ancestry here; the complete batch is validated by the lead.
        model.note_check(dict(note, origin=None), length, {})
        if note['origin'] is not None:
            model.shape(note['origin'], 'source_id track_id source_note_id')
            for value in note['origin'].values():
                model.ident(value)
    ordered = sorted(notes, key=lambda n: (n['start_tick'], n['id']))
    if any(a['start_tick'] + a['duration_tick'] > b['start_tick']
           for a, b in zip(ordered, ordered[1:])):
        _fail('INVALID_PARAMETERS', '普通新旋律只接受无重叠的单旋律。')
    return ordered


def _material(material, depth=0, ancestors=()):
    model.canonical(material)
    model.shape(material, 'id label kind length_ticks notes provenance generation phrase_id children')
    model.ident(material['id']); model.text(material['label'])
    model.integer(material['length_ticks'], 1)
    if depth > 16 or material['id'] in ancestors:
        _fail('INVALID_PARAMETERS', '组合有环或超过16层。')
    if material['kind'] not in ('block', 'phrase', 'combination', 'bridge'):
        _fail('INVALID_PARAMETERS', '素材类型无效。')
    if not isinstance(material['provenance'], dict) or (material['generation'] is not None
                                                       and not isinstance(material['generation'], dict)):
        _fail('INVALID_PARAMETERS', '来源或生成记录无效。')
    if material['phrase_id'] is not None:
        model.ident(material['phrase_id'])
    ordered = _notes(material['notes'], material['length_ticks'])
    children = model.objects(material['children'])
    if material['kind'] != 'combination' and children:
        _fail('INVALID_PARAMETERS', '只有组合可包含组件。')
    if material['kind'] == 'combination':
        if not children:
            _fail('INVALID_PARAMETERS', '组合不能为空。')
        offset = 0; seen = set(); joined = []
        for child in children:
            model.shape(child, 'occurrence_id offset_tick snapshot')
            model.ident(child['occurrence_id'])
            if type(child['offset_tick']) is not int or child['offset_tick'] != offset or child['occurrence_id'] in seen:
                _fail('INVALID_PARAMETERS', '组合组件不连续或身份重复。')
            seen.add(child['occurrence_id'])
            _material(child['snapshot'], depth + 1, ancestors + (material['id'],))
            joined.extend(dict(n, start_tick=n['start_tick'] + offset) for n in child['snapshot']['notes'])
            offset += child['snapshot']['length_ticks']
        if offset != material['length_ticks'] or model.musical_notes(joined) != model.musical_notes(ordered):
            _fail('INVALID_PARAMETERS', '组合音符与组件快照不一致。')
    return ordered


def music_signature(material):
    """Actual length/pitch/onset/duration only, retaining event multiplicity."""
    notes = _material(material)
    return _id('music', {'length_ticks': material['length_ticks'],
                         'notes': [[n['pitch'], n['start_tick'], n['duration_tick']] for n in notes]})


def _window(notes, start, end, owner, child_id):
    result = []
    for note in notes:
        a = max(start, note['start_tick'])
        b = min(end, note['start_tick'] + note['duration_tick'])
        if b <= a:
            continue
        new = copy.deepcopy(note)
        new.update(id=_id('slice-note', [child_id, note['id']]), start_tick=a - start, duration_tick=b - a)
        new['lineage'] = list(dict.fromkeys(note['lineage'] + [note['id']]))
        if a != note['start_tick'] or b != note['start_tick'] + note['duration_tick']:
            prior = note['slice']
            new['slice'] = dict(parent_emission_id=prior['parent_emission_id'] if prior else _id('emission', [owner, note['id']]),
                                offset_tick=(prior['offset_tick'] if prior else 0) + a - note['start_tick'],
                                parent_duration_tick=prior['parent_duration_tick'] if prior else note['duration_tick'])
        result.append(new)
    return result


def split_phrase(phrase):
    """Fourbeat children of an unchanged, unsliced phrase, including rest/tail."""
    notes = _material(phrase)
    if phrase['kind'] != 'phrase':
        _fail('INVALID_PARAMETERS', 'split_phrase 只接受整句。')
    result = []
    source_start = phrase['provenance'].get('source_start_tick')
    for index, start in enumerate(range(0, phrase['length_ticks'], BAR)):
        end = min(start + BAR, phrase['length_ticks'])
        ident = _id('phrase-block', [phrase['id'], start, end])
        provenance = copy.deepcopy(phrase['provenance'])
        provenance.update(relative_start_tick=start,
                          source_start_tick=source_start + start if type(source_start) is int else None)
        result.append(dict(id=ident, label=phrase['label'] + f' · {index + 1}', kind='block',
            length_ticks=end - start, notes=_window(notes, start, end, phrase['id'], ident),
            provenance=provenance, generation=copy.deepcopy(phrase['generation']),
            phrase_id=phrase['id'], children=[]))
    return result


def _key(material, notes):
    context = material['provenance'].get('key_context')
    if context is None and material.get('generation'):
        context = material['generation'].get('key_context')
    if context is not None:
        if not isinstance(context, dict) or not {'tonic', 'mode', 'confidence', 'method'} <= set(context):
            _fail('INVALID_PARAMETERS', '调性上下文缺失字段。')
        model.integer(context['tonic'], 0, 11)
        model.text(context['method'])
        confidence = context['confidence']
        if (context['mode'] not in ('major', 'minor') or isinstance(confidence, bool)
                or not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
                or confidence < 0):
            _fail('INVALID_PARAMETERS', '调性上下文无效。')
        return copy.deepcopy(context)
    # A deterministic, explicitly labelled rule estimate, not an implicit C key.
    weights = [0] * 12
    for n in notes:
        weights[n['pitch'] % 12] += n['duration_tick']
    choices = []
    for mode, degrees in [('major', (0, 2, 4, 5, 7, 9, 11)), ('minor', (0, 2, 3, 5, 7, 8, 10))]:
        for tonic in range(12):
            coverage = sum(weights[(tonic + d) % 12] for d in degrees)
            choices.append((coverage, weights[tonic], tonic, mode))
    choices.sort(reverse=True)
    best = choices[0]
    return dict(tonic=best[2], mode=best[3], confidence=(best[0] - choices[1][0]) / max(1, sum(weights)),
                method='duration-weighted-scale-v1')


def _parameters(method, parameters):
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict) or not set(parameters) <= set(DEFAULTS[method]):
        _fail('INVALID_PARAMETERS', '未知生成参数。')
    result = dict(DEFAULTS[method], **parameters)
    for key, value in result.items():
        if key == 'fraction':
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1:
                _fail('INVALID_PARAMETERS', '变化比例必须在(0,1]。')
        elif key == 'direction':
            if value not in ('denser', 'sparser'):
                _fail('INVALID_PARAMETERS', '疏密方向无效。')
        elif type(value) is not int or (key == 'degree_shift' and not -7 <= value <= 7) or (key != 'degree_shift' and value < 1):
            _fail('INVALID_PARAMETERS', '生成整数参数无效。')
    if result.get('max_step', 1) > 7 or result.get('sequence_step', 1) > 7:
        _fail('INVALID_PARAMETERS', '音阶步进不得超过七级。')
    return result


def _scale(context):
    degrees = (0, 2, 4, 5, 7, 9, 11) if context['mode'] == 'major' else (0, 2, 3, 5, 7, 8, 10)
    return [pitch for pitch in range(128) if (pitch - context['tonic']) % 12 in degrees]


def _degree(scale, pitch):
    return min(range(len(scale)), key=lambda i: (abs(scale[i] - pitch), scale[i]))


def _step(scale, pitch, amount):
    index = _degree(scale, pitch)
    target = max(0, min(len(scale) - 1, index + amount))
    if scale[target] == pitch and amount:
        target = max(0, min(len(scale) - 1, index - amount))
    return scale[target]


def _rules(notes, length, method, parameters, scale, rng):
    out = copy.deepcopy(notes); operations = []
    if method == 'variant':
        indices = list(range(1 if len(out) > 1 else 0, len(out)))
        rng.shuffle(indices)
        for i in indices[:max(1, math.ceil(len(indices) * parameters['fraction']))]:
            amount = rng.choice((-1, 1)) * rng.randint(1, parameters['max_step'])
            out[i]['pitch'] = _step(scale, out[i]['pitch'], amount)
            operations.append(dict(operation='local-degree-change', input_note_ids=[notes[i]['id']],
                requested_degree_step=amount,
                degree_step=_degree(scale, out[i]['pitch']) - _degree(scale, notes[i]['pitch']),
                from_pitch=notes[i]['pitch'], to_pitch=out[i]['pitch']))
    elif method == 'answer':
        axis = _degree(scale, notes[0]['pitch'])
        for i, n in enumerate(out):
            degree = 2 * axis - _degree(scale, n['pitch']) + parameters['degree_shift']
            n['pitch'] = scale[max(0, min(len(scale) - 1, degree))]
        operations.append(dict(operation='motif-contour-answer', input_note_ids=[n['id'] for n in notes],
                               degree_shift=parameters['degree_shift']))
    elif method == 'counter':
        articulation = []
        for i, n in enumerate(out):
            motif_note = notes[(i + 1) % len(notes)]
            n['pitch'] = _step(scale, motif_note['pitch'], parameters['degree_shift'])
            n['lineage'] = list(dict.fromkeys(n['lineage'] + [motif_note['id']]))
            duration = n['duration_tick']
            # Shorten expressible durations by whole LMMS units, not the
            # rendered output. Preserve nonmultiple input ticks verbatim.
            reduction = (duration // 50) * 10 if duration % 10 == 0 else 0
            n['duration_tick'] = duration - reduction
            articulation.append(dict(input_note_id=notes[i]['id'], original_duration_tick=duration,
                shortened_by_tick=reduction, output_duration_tick=n['duration_tick'],
                preserved_exact_tick=bool(duration % 10)))
        operations.append(dict(operation='replacement-motif-rotation', input_note_ids=[n['id'] for n in notes],
            degree_shift=parameters['degree_shift'], target_articulation_ratio=.8, voices=1,
            rule_unit_ticks=10, duration_rule='floor-fifth-reduction-to-unit; preserve-nonmultiple-duration',
            articulation=articulation))
    elif method == 'rhythm':
        slots = [(n['duration_tick'], (notes[i + 1]['start_tick'] if i + 1 < len(notes) else length)
                  - n['start_tick'] - n['duration_tick']) for i, n in enumerate(notes)]
        rotation = parameters['rotation'] % len(slots)
        rotated = slots[rotation:] + slots[:rotation]
        cursor = notes[0]['start_tick']
        for n, (duration, gap) in zip(out, rotated):
            n.update(start_tick=cursor, duration_tick=duration)
            cursor += duration + gap
        if all((a['start_tick'], a['duration_tick']) == (b['start_tick'], b['duration_tick']) for a, b in zip(notes, out)):
            editable = [i for i, n in enumerate(out) if n['duration_tick'] > 1 or slots[i][1] > 0]
            if editable:
                i = rng.choice(editable); n = out[i]
                available = n['duration_tick'] - 1 if n['duration_tick'] > 1 else slots[i][1]
                delay = min(parameters['unit_ticks'], available)
                n['start_tick'] += delay
                if n['duration_tick'] > 1:
                    n['duration_tick'] -= delay
                operations.append(dict(operation='delayed-attack', input_note_ids=[notes[i]['id']], delay_tick=delay))
        operations.append(dict(operation='rotate-duration-rest-cells', rotation=rotation,
                               input_note_ids=[n['id'] for n in notes]))
    elif method == 'develop':
        if len(out) >= 3:
            motif = notes[:2]
            for i in range(2, len(out)):
                source = motif[i % 2]
                degree = _degree(scale, source['pitch']) + (i // 2) * parameters['sequence_step']
                out[i]['pitch'] = scale[max(0, min(len(scale) - 1, degree))]
                out[i]['lineage'] = list(dict.fromkeys(out[i]['lineage'] + [source['id']]))
            operations.append(dict(operation='motif-sequence', motif_note_ids=[n['id'] for n in motif],
                                   degree_step=parameters['sequence_step']))
        else:
            index = next((i for i, n in enumerate(out) if n['duration_tick'] >= 2), None)
            if index is not None:
                note = out[index]; first = copy.deepcopy(note); second = copy.deepcopy(note)
                first['duration_tick'] = note['duration_tick'] // 2
                second.update(start_tick=note['start_tick'] + first['duration_tick'],
                              duration_tick=note['duration_tick'] - first['duration_tick'],
                              pitch=_step(scale, note['pitch'], parameters['sequence_step']))
                out[index:index + 1] = [first, second]
                operations.append(dict(operation='motif-repeat-and-sequence', motif_note_ids=[note['id']],
                                       degree_step=parameters['sequence_step']))
    else:  # density
        if parameters['direction'] == 'sparser':
            if len(out) > 1:
                removed = [n['id'] for n in out[1::2]]
                out = out[::2]
                operations.append(dict(operation='thin-attacks', removed_input_note_ids=removed))
        else:
            expanded = []; count = 0
            for note in out:
                if note['duration_tick'] >= 2 and count < parameters['max_splits']:
                    first = copy.deepcopy(note); second = copy.deepcopy(note)
                    first['duration_tick'] = note['duration_tick'] // 2
                    second.update(start_tick=note['start_tick'] + first['duration_tick'],
                                  duration_tick=note['duration_tick'] - first['duration_tick'],
                                  pitch=_step(scale, note['pitch'], rng.choice((-1, 1))))
                    expanded.extend((first, second)); count += 1
                    operations.append(dict(operation='split-attack', input_note_ids=[note['id']], split_tick=second['start_tick']))
                else:
                    expanded.append(note)
            out = expanded
    return out, operations


def _component_paths(material, path=(), offset=0):
    if material['kind'] != 'combination':
        return [dict(component_path=list(path), material_id=material['id'], start_tick=offset,
                     length_ticks=material['length_ticks'], provenance=copy.deepcopy(material['provenance']))]
    result = []
    for child in material['children']:
        result.extend(_component_paths(child['snapshot'], path + (child['occurrence_id'],), offset + child['offset_tick']))
    return result


def derive(material, method, seed=31, parameters=None):
    """Ordinary rule variation with complete replay metadata.

    Accepted parameters and defaults are listed in DEFAULTS. Density accepts
    direction=denser/sparser; all methods preserve the input's actual length.
    """
    if not isinstance(method, str) or method not in METHODS:
        _fail('UNSUPPORTED_METHOD', 'P2 只支持六种普通新旋律规则。')
    _seed(seed)
    notes = _material(material)
    if material['kind'] == 'bridge':
        _fail('UNSUPPORTED_METHOD', 'P2 不处理 bridge 素材。')
    if not notes:
        _fail('EMPTY_MATERIAL', '没有可用于派生的实际音符。')
    parameters = _parameters(method, parameters)
    key = _key(material, notes)
    new_notes, operations = _rules(notes, material['length_ticks'], method, parameters, _scale(key), random.Random(seed))
    input_fingerprint = _id('input', material)
    algorithm_version = COUNTER_ALGORITHM_VERSION if method == 'counter' else ALGORITHM_VERSION
    ident = _id('derived-material', [input_fingerprint, method, seed, parameters, algorithm_version])
    for i, note in enumerate(new_notes):
        parent = note['id']
        note.update(id=_id('derived-note', [ident, i]), slice=None,
                    lineage=list(dict.fromkeys(note['lineage'] + [parent])))
    provenance = copy.deepcopy(material['provenance'])
    provenance.update(input_material_id=material['id'], input_kind=material['kind'], input_phrase_id=material['phrase_id'],
                      key_context=copy.deepcopy(key))
    if material['kind'] == 'combination':
        provenance.update(component_snapshots=copy.deepcopy(material['children']), component_paths=_component_paths(material),
                          source_start_tick=None)
    result = dict(id=ident, label=material['label'] + ' · ' + method,
        kind='phrase' if material['kind'] in ('phrase', 'combination') else 'block',
        length_ticks=material['length_ticks'], notes=new_notes, provenance=provenance,
        generation=dict(method=method, parameters=parameters, seed=seed, rng_version=RNG_VERSION,
            algorithm_version=algorithm_version, input_fingerprint=input_fingerprint,
            input_material_ids=[material['id']], base_notes=copy.deepcopy(material['notes']), key_context=key, operations=operations),
        phrase_id=None, children=[])
    if music_signature(result) == music_signature(material):
        _fail('NO_VALID_VARIATION', '该素材和参数未产生实际音高或节奏差异。')
    return result


def prepare_source(source, seed=31):
    """Prepare actual-tail blocks, conservative rest phrases and <=3 candidates."""
    _seed(seed)
    model.canonical(source)
    model.shape(source, 'id label length_ticks notes provenance')
    model.ident(source['id']); model.text(source['label']); model.integer(source['length_ticks'], 1)
    provenance = source['provenance']
    required = {'path', 'file_fingerprint', 'track_id', 'original_bpm', 'ppq_policy', 'key_context'}
    if not isinstance(provenance, dict) or not required <= set(provenance):
        _fail('INVALID_PARAMETERS', 'Source 缺少规范导入来源。')
    if provenance['key_context'] is None:
        _fail('INVALID_PARAMETERS', '规范 Source 必须提供明确调性上下文。')
    for field in ('path', 'file_fingerprint', 'track_id'):
        model.ident(provenance[field])
    bpm = provenance['original_bpm']
    if isinstance(bpm, bool) or not isinstance(bpm, (int, float)) or not math.isfinite(bpm) or bpm <= 0:
        _fail('INVALID_PARAMETERS', '来源速度无效。')
    notes = _notes(source['notes'], source['length_ticks'])
    if not notes:
        _fail('EMPTY_MATERIAL', '来源没有实际音符。')
    if notes[-1]['start_tick'] + notes[-1]['duration_tick'] != source['length_ticks']:
        _fail('INVALID_PARAMETERS', '规范来源长度必须是最后实际音符的终点。')
    for note in notes:
        if note['origin'] != dict(source_id=source['id'], track_id=provenance['track_id'], source_note_id=note['id']):
            _fail('INVALID_PARAMETERS', '来源音符身份必须引用自身来源和轨道。')
    source_meta = dict(source_id=source['id'], source_provenance=copy.deepcopy(provenance), key_context=copy.deepcopy(provenance['key_context']))
    _key({'provenance': source_meta}, notes)
    source_fingerprint = _id('source-input', source)
    materials = []; original_blocks = []
    for index, start in enumerate(range(0, source['length_ticks'], BAR)):
        end = min(source['length_ticks'], start + BAR)
        ident = _id('source-block', [source['id'], source_fingerprint, start, end])
        block = dict(id=ident, label=source['label'] + f' · 块{index + 1}', kind='block', length_ticks=end - start,
            notes=_window(notes, start, end, source['id'], ident),
            provenance=dict(copy.deepcopy(source_meta), source_start_tick=start, relative_start_tick=start),
            generation=None, phrase_id=None, children=[])
        original_blocks.append(block); materials.append(block)
    # Cut at the next attack after a >=halfbeat rest, never through a sound.
    edges = [0]; reasons = ['source-start']
    for previous, following in zip(notes, notes[1:]):
        if (following['start_tick'] - previous['start_tick'] - previous['duration_tick'] >= PPQ // 2
                and following['start_tick'] - edges[-1] >= BAR):
            edges.append(following['start_tick']); reasons.append('rest-at-least-240-ticks')
    edges.append(source['length_ticks']); reasons.append('source-end')
    phrases = []
    for index, (start, end) in enumerate(zip(edges, edges[1:])):
        ident = _id('source-phrase', [source['id'], source_fingerprint, start, end])
        # Boundaries are in silence; windowing cannot truncate a source note.
        phrase_notes = _window(notes, start, end, source['id'], ident)
        complete = end - start >= BAR and len(phrase_notes) >= 2
        phrase = dict(id=ident, label=source['label'] + f' · 句{index + 1}', kind='phrase',
            length_ticks=end - start, notes=phrase_notes,
            provenance=dict(copy.deepcopy(source_meta), source_start_tick=start, relative_start_tick=0,
                segmentation_version=SEGMENTATION_VERSION,
                segmentation_parameters=dict(rest_threshold_ticks=240, min_complete_ticks=BAR, min_complete_notes=2),
                segmentation_reasons=[reasons[index], reasons[index + 1]], phrase_complete=complete,
                heuristic=True), generation=None, phrase_id=None, children=[])
        phrases.append(phrase); materials.extend([phrase] + split_phrase(phrase))
    base = next((p for p in phrases if p['provenance']['phrase_complete'] and p['notes']), None)
    warnings = []
    if base is None:
        base = next(b for b in original_blocks if b['notes'])
        warnings.append(dict(code='PHRASE_FALLBACK', message='未确定完整启发式乐句，使用首个有音符块。', details={'material_id': base['id']}))
    seen = {music_signature(m) for m in materials}; candidates = []
    for method in ('variant', 'answer', 'rhythm'):
        try:
            candidate = derive(base, method, seed)
        except model.ProjectError as exc:
            if exc.code not in ('EMPTY_MATERIAL', 'NO_VALID_VARIATION'):
                raise
            warnings.append(dict(code=exc.code, message=str(exc), details={'method': method, 'base_material_id': base['id']}))
            continue
        signature = music_signature(candidate)
        if signature in seen:
            warnings.append(dict(code='DUPLICATE_CANDIDATE', message='实际音乐重复，未补足候选数量。', details={'method': method}))
            continue
        seen.add(signature); candidates.append(candidate['id']); materials.append(candidate)
        if candidate['kind'] == 'phrase':
            materials.extend(split_phrase(candidate))
    if len(candidates) < 3:
        warnings.append(dict(code='INSUFFICIENT_CANDIDATES', message='有效默认候选不足三条。', details={'actual_count': len(candidates), 'requested_count': 3}))
    return dict(materials=materials, candidates=candidates, warnings=warnings)
