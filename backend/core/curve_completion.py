"""P4 bounded, pure base-completion proposals; never a completed/final score.

The lead validates and applies memory/emotion to this finite raw pool. No
project edits, renderer, controller, memory rules or later pipeline stages.
"""
import copy
import math
import random
from collections import Counter

import curve_melody as melody
import curve_project as model

ALGORITHM_VERSION = 'curve-completion-v1'
CONTRACT_REV = 'curve-workflow-v2-r3-p4'
RNG_VERSION = 'python.random-v3'
DEFAULT_BUDGET = dict(max_expansions=256, beam_width=8, material_limit=24,
                      max_new_notes=256, max_candidates=2)
LIMITS = dict(max_expansions=4096, beam_width=32, material_limit=128,
              max_new_notes=2048, max_candidates=8)
RAW_NOTE_LIMIT = 65536
POLICIES = ('motif_echo', 'motif_answer', 'rhythmic_development')
WEIGHTS = dict(left_fit=.20, right_fit=.20, key_fit=.12, rhythm_fit=.08,
               motif_fit=.10, emotion_fit=.10, intensity_fit=.10,
               repeat_penalty=-.10)


def _issue(code, message, **details):
    return dict(code=code, message=message, details=details)


def _fail(code, message):
    raise model.ProjectError(code, message)


def _bridge(material):
    return material['kind'] == 'bridge' or any(_bridge(c['snapshot']) for c in material['children'])


def _gap_items(project):
    fingerprint = model.fingerprint(project)
    return [dict(id=model.digest('emoblocks.gap.v1', dict(input_fingerprint=fingerprint, range=r)), **r)
            for r in model.gaps(project)]


def _validate(request):
    model.canonical(request)
    model.shape(request, 'schema spec_rev contract_rev input_contract_rev request_id snapshot_id '
                'input_fingerprint project scope target_gaps library_ids contexts protection_summary '
                'blank_regions seed algorithm_version budget')
    if (request['schema'] != 'emoblocks.completion-request.v1'
            or request['spec_rev'] != model.SPEC_REV or request['contract_rev'] != CONTRACT_REV
            or request['algorithm_version'] != ALGORITHM_VERSION):
        _fail('UNSUPPORTED_VERSION', '补全请求的规格或处理版本不匹配。')
    for field in ('request_id', 'snapshot_id'):
        model.ident(request[field])
    project = request['project']
    model.validate(project)
    if (request['input_contract_rev'] != project['contract_rev']
            or request['input_fingerprint'] != model.fingerprint(project)):
        _fail('STALE_SNAPSHOT', '补全输入版本或内容指纹不匹配。')
    model.integer(request['seed'], 0, 2**32 - 1)
    model.shape(request['budget'], ' '.join(DEFAULT_BUDGET))
    for name, limit in LIMITS.items():
        model.integer(request['budget'][name], 1, limit)
    gaps = _gap_items(project)
    targets = model.objects(request['target_gaps'])
    if request['scope'] == 'all':
        valid_targets = targets == gaps
    elif request['scope'] == 'selected':
        valid_targets = len(targets) == 1 and targets[0] in gaps
    else:
        valid_targets = False
    if not valid_targets:
        _fail('STALE_GAP', '目标必须等于当前完整空缺，不能只补其子范围。')
    materials = model.indexed(project['materials'])
    allowed = sorted(m['id'] for m in materials.values() if not _bridge(m))
    if request['library_ids'] != allowed:
        _fail('INVALID_PARAMETERS', '补全素材身份必须是完整允许集合。')
    if request['blank_regions'] != project['blank_regions']:
        _fail('STALE_SNAPSHOT', '主动留白与输入工程不匹配。')
    model.shape(request['protection_summary'], 'fingerprint ranges')
    ranges = sorted({(r['start_tick'], r['end_tick']) for p in project['protections']
                     for r in model.protection_ranges(p)})
    expected_ranges = [dict(start_tick=a, end_tick=b) for a, b in ranges]
    if (request['protection_summary']['fingerprint'] != model.protection_summary(project['protections'])
            or request['protection_summary']['ranges'] != expected_ranges):
        _fail('STALE_SNAPSHOT', '保护摘要或完整音符支撑与输入不匹配。')
    if any(model.intersects(g, r) for g in targets for r in expected_ranges):
        _fail('PROTECTION_CONFLICT', '目标空缺与已有不可写保护相交。')
    expected_contexts = []
    for gap in targets:
        lefts = [p for p in project['placements'] if p['start_tick'] + p['length_ticks'] <= gap['start_tick']]
        rights = [p for p in project['placements'] if p['start_tick'] >= gap['end_tick']]
        left = max(lefts, key=lambda p: p['start_tick']) if lefts else None
        right = min(rights, key=lambda p: p['start_tick']) if rights else None
        expected_contexts.append(dict(gap_id=gap['id'], left=left, right=right,
            left_notes=__import__('curve_application').context_notes(project,left),
            right_notes=__import__('curve_application').context_notes(project,right)))
    if request['contexts'] != expected_contexts:
        _fail('STALE_SNAPSHOT', '左右上下文必须来自实际放置变体及绝对音符。')
    return materials


def _key(material):
    context = material['provenance'].get('key_context')
    if context is None and material['generation']:
        context = material['generation'].get('key_context')
    if context is not None:
        if not isinstance(context, dict) or not {'tonic', 'mode', 'confidence', 'method'} <= set(context):
            _fail('INVALID_PARAMETERS', '动机调性上下文缺少字段。')
        model.integer(context['tonic'], 0, 11)
        confidence = context['confidence']
        if (context['mode'] not in ('major', 'minor') or isinstance(confidence, bool)
                or not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
                or not 0 <= confidence <= 1 or not isinstance(context['method'], str)):
            _fail('INVALID_PARAMETERS', '动机调性上下文无效。')
        return copy.deepcopy(context)
    weights = Counter()
    for note in material['notes']:
        weights[note['pitch'] % 12] += note['duration_tick']
    choices = []
    for mode, degrees in (('major', (0, 2, 4, 5, 7, 9, 11)), ('minor', (0, 2, 3, 5, 7, 8, 10))):
        for tonic in range(12):
            choices.append((sum(weights[(tonic + d) % 12] for d in degrees),
                            weights[tonic], tonic, mode))
    choices.sort(reverse=True)
    best = choices[0]
    return dict(tonic=best[2], mode=best[3], confidence=(best[0] - choices[1][0]) / sum(weights.values()),
                method='completion-duration-scale-v1')


def _scale(key):
    degrees = (0, 2, 4, 5, 7, 9, 11) if key['mode'] == 'major' else (0, 2, 3, 5, 7, 8, 10)
    return [pitch for pitch in range(128) if (pitch - key['tonic']) % 12 in degrees]


def _component_paths(material, path=()):
    result = []
    for child in material['children']:
        current = path + (child['occurrence_id'],)
        result.append(dict(component_path=list(current), material_id=child['snapshot']['id'],
                           offset_tick=child['offset_tick']))
        result.extend(_component_paths(child['snapshot'], current))
    return result


class _Cancelled(Exception):
    pass


class _NoteBudget(Exception):
    pass


class _Search:
    def __init__(self, request, should_cancel, on_progress):
        self.request = request
        self.budget = DEFAULT_BUDGET
        self.should_cancel = should_cancel
        self.on_progress = on_progress
        self.expansions = 0
        self.generated_notes = 0
        self.event_seq = 0
        self.rejections = []
        self.note_exhausted = False

    def check(self):
        if self.should_cancel is not None and self.should_cancel():
            raise _Cancelled()

    def progress(self, message):
        self.check()
        self.event_seq += 1
        if self.on_progress is not None:
            self.on_progress(dict(event_seq=self.event_seq, phase='BASE_COMPLETION',
                                  message=message, expansions=self.expansions))
        self.check()

    def expand(self):
        self.check()
        if self.expansions >= self.budget['max_expansions']:
            return False
        self.expansions += 1
        return True

    def note(self):
        self.check()
        if self.generated_notes >= self.budget['max_new_notes']:
            self.note_exhausted = True
            raise _NoteBudget()
        self.generated_notes += 1

    def info(self, termination):
        return dict(expansions=self.expansions, generated_notes=self.generated_notes,
                    termination=termination, raw_termination=termination, rejections=self.rejections)


def _compose(base, length, policy, seed, search):
    """Construct fresh motif cells, not a resized/cropped source emission."""
    source = sorted(base['notes'], key=lambda n: n['start_tick'])
    key = _key(base)
    scale = _scale(key)
    # The grammar preserves the renderer's existing exact 10-tick domain when
    # possible. Arbitrary target/source ticks use unit 1, never output rounding.
    unit = 10 if length % 10 == 0 and all(n['start_tick'] % 10 == n['duration_tick'] % 10 == 0
                                        for n in source) else 1
    durations = sorted(n['duration_tick'] for n in source)
    pulse = max(unit, durations[len(durations) // 2], math.ceil(length / 16))
    pulse = ((pulse + unit - 1) // unit) * unit
    rng = random.Random(seed)
    phase = rng.randrange(len(source)) if policy == 2 else 0
    ident = model.digest('emoblocks.completion-material.v1', dict(base=base, target_ticks=length,
        policy=POLICIES[policy], seed=seed, algorithm_version=ALGORITHM_VERSION))
    notes = []; operations = []; cursor = 0; index = 0
    while cursor < length:
        search.check()
        parent = source[(index + phase) % len(source)]
        cell = pulse
        if policy == 2:
            cell = max(unit, (pulse * (1, 3, 2)[index % 3] // 2 // unit) * unit)
        cell = min(cell, length - cursor)
        degree = min(range(len(scale)), key=lambda i: (abs(scale[i] - parent['pitch']), scale[i]))
        shift = 0 if policy == 0 else (1 if policy == 1 else (-1 if index % 2 == 0 else 1))
        if index >= len(source) and policy != 0:
            shift += (index // len(source)) % 2
        shifted = degree + shift
        if not 0 <= shifted < len(scale):
            shifted = degree - shift
        pitch = parent['pitch'] if policy == 0 else scale[max(0, min(len(scale) - 1, shifted))]
        duration = cell
        if policy == 2 and cursor + cell < length and cell >= 3 * unit:
            duration -= unit  # A new articulated rest within the cell.
        search.note()
        note = copy.deepcopy(parent)
        note.update(id=model.digest('emoblocks.completion-note.v1', [ident, index]),
                    pitch=pitch, start_tick=cursor, duration_tick=duration, slice=None,
                    lineage=list(dict.fromkeys(parent['lineage'] + [parent['id']])))
        notes.append(note)
        operations.append(dict(type='motif_cell', source_note_id=parent['id'],
            start_tick=cursor, duration_tick=duration, pitch=pitch, cell_ticks=cell,
            degree_shift=shift, rule_unit_ticks=unit))
        cursor += cell; index += 1
    provenance = copy.deepcopy(base['provenance'])
    provenance.update(input_material_id=base['id'], input_kind=base['kind'],
        input_phrase_id=base['phrase_id'], key_context=copy.deepcopy(key),
        completion=dict(base_material_id=base['id'], base_snapshot=copy.deepcopy(base), target_ticks=length))
    if base['kind'] == 'combination':
        provenance.update(component_snapshots=copy.deepcopy(base['children']),
                          component_paths=_component_paths(base))
    return dict(id=ident, label=base['label'] + ' · 基础补全', kind='phrase', length_ticks=length,
        notes=notes, provenance=provenance, phrase_id=None, children=[],
        generation=dict(method='completion_exact', parameters=dict(target_ticks=length,
            rhythm_method=POLICIES[policy], pulse_ticks=pulse, rule_unit_ticks=unit),
            seed=seed, rng_version=RNG_VERSION, algorithm_version=ALGORITHM_VERSION,
            input_fingerprint=model.digest('emoblocks.completion-input.v1', base),
            input_material_ids=[base['id']], base_notes=copy.deepcopy(base['notes']),
            key_context=key, operations=operations))


def _emotion(request, gap, start, material):
    context = next(c for c in request['contexts'] if c['gap_id'] == gap['id'])
    length = material['length_ticks']
    first = model.intensity_at(request['project'], start)
    last = model.intensity_at(request['project'], start + length)
    level = model.intensity_at(request['project'], start + length // 2)
    neighbor = context['left'] or context['right']
    if neighbor and neighbor['emotion'] != 'calm' and abs(last - first) < .1:
        return neighbor['emotion']
    if last - first > .1:
        return 'hope' if _key(material)['mode'] == 'major' else 'suspense'
    if first - last > .1:
        return 'resolve'
    if level >= .75 and len(material['notes']) * 480 / length >= 1:
        return 'crisis'
    if _key(material)['mode'] == 'minor':
        return 'sad' if level < .6 else 'suspense'
    return 'calm' if level < .45 else 'hope'


def _music(selections):
    """Music-only projection; slice continuity belongs to one new occurrence."""
    emitted = []
    for selection in selections:
        offset = selection['start_tick']
        previous = None
        for note in sorted(selection['material']['notes'], key=lambda n: (n['start_tick'], n['pitch'])):
            row = [note['pitch'], offset + note['start_tick'], note['duration_tick']]
            slice_ = note['slice']
            same = (previous is not None and slice_ is not None and previous['slice'] is not None
                    and previous['origin'] == note['origin'] and previous['origin'] is not None
                    and previous['slice']['parent_emission_id'] == slice_['parent_emission_id']
                    and previous['slice']['parent_duration_tick'] == slice_['parent_duration_tick']
                    and previous['slice']['offset_tick'] + previous['duration_tick'] == slice_['offset_tick']
                    and emitted[-1][0] == row[0] and emitted[-1][1] + emitted[-1][2] == row[1])
            if same:
                emitted[-1][2] += row[2]
            else:
                emitted.append(row)
            previous = note
    return sorted(emitted, key=lambda n: (n[1], n[0], n[2]))


def _music_hash(selections):
    return model.digest('emoblocks.completion-raw-music.v1', _music(selections))


def _fit(a, b):
    return .5 if a is None or b is None else max(0., 1. - abs(a - b) / 12)


def _score(request, selections):
    if not selections:
        return dict.fromkeys(WEIGHTS, 0.) | {'total': 0.}
    accum = dict.fromkeys(WEIGHTS, 0.)
    existing = Counter(melody.music_signature(p['emotion_variant'] or p['base_snapshot'])
                       for p in request['project']['placements'])
    repeated = 0
    for selection in selections:
        material = selection['material']; notes = sorted(material['notes'], key=lambda n: n['start_tick'])
        context = next(c for c in request['contexts'] if c['gap_id'] == selection['gap_id'])
        earlier = [s for s in selections if s['gap_id'] == selection['gap_id']
                   and s['start_tick'] < selection['start_tick']]
        later = [s for s in selections if s['gap_id'] == selection['gap_id']
                 and s['start_tick'] > selection['start_tick']]
        left = (max(earlier, key=lambda s: s['start_tick'])['material']['notes'] if earlier else context['left_notes'])
        right = (min(later, key=lambda s: s['start_tick'])['material']['notes'] if later else context['right_notes'])
        left_pitch = max(left, key=lambda n: n['start_tick'])['pitch'] if left else None
        right_pitch = min(right, key=lambda n: n['start_tick'])['pitch'] if right else None
        accum['left_fit'] += _fit(left_pitch, notes[0]['pitch'])
        accum['right_fit'] += _fit(notes[-1]['pitch'], right_pitch)
        key = _key(material); scale = set(_scale(key))
        context_notes = context['left_notes'] + context['right_notes']
        accum['key_fit'] += (sum(n['pitch'] in scale for n in notes + context_notes)
                             / len(notes + context_notes))
        base = material['generation'].get('base_notes', notes) if material['generation'] else notes
        durations = {n['duration_tick'] for n in base}
        accum['rhythm_fit'] += sum(any(max(d, n['duration_tick']) <= 2 * min(d, n['duration_tick'])
                                      for d in durations) for n in notes) / len(notes)
        comparisons = min(len(notes), len(base)) - 1
        sign = lambda interval: (interval > 0) - (interval < 0)
        accum['motif_fit'] += (sum(sign(notes[i+1]['pitch'] - notes[i]['pitch'])
                                  == sign(base[i+1]['pitch'] - base[i]['pitch'])
                                  for i in range(comparisons)) / comparisons if comparisons > 0 else 1.)
        density = min(1., len(notes) * 120 / material['length_ticks'])
        level = model.intensity_at(request['project'], selection['start_tick'] + material['length_ticks'] // 2)
        accum['intensity_fit'] += 1 - abs(density - level)
        ideal = dict(calm=.25, hope=.5, sad=.3, suspense=.6, crisis=.9, resolve=.4)[selection['emotion']]
        neighbor_emotions = [c['emotion'] for c in (context['left'], context['right']) if c]
        accum['emotion_fit'] += .7 * (1 - abs(ideal - level)) + .3 * (
            sum(e == selection['emotion'] for e in neighbor_emotions) / len(neighbor_emotions)
            if neighbor_emotions else .5)
        signature = melody.music_signature(material)
        repeated += existing[signature] > 0
        existing[signature] += 1
    count = len(selections)
    score = {k: v / count for k, v in accum.items()}
    score['repeat_penalty'] = repeated / count
    score['total'] = sum(score[k] * weight for k, weight in WEIGHTS.items())
    return score


def _order(request, state):
    return (-_score(request, state[2])['total'], _music_hash(state[2]))


def _note_count(material):
    return len(material['notes']) + sum(_note_count(c['snapshot']) for c in material['children'])


def propose(request, should_cancel=None, on_progress=None):
    """Return only complete raw layouts, accurate counters and finite search.

    Bad input is a structured ProposalResult error. Callback exceptions propagate
    to the lead's fail_completion; a cancellation returns no partial proposals.
    """
    if should_cancel is not None and not callable(should_cancel):
        _fail('INVALID_PARAMETERS', '取消检查必须可调用。')
    if on_progress is not None and not callable(on_progress):
        _fail('INVALID_PARAMETERS', '进度回调必须可调用。')
    search = _Search(request, should_cancel, on_progress)
    try:
        materials = _validate(request)
    except (model.ProjectError, KeyError, TypeError) as exc:
        code = getattr(exc, 'code', 'INVALID_PARAMETERS')
        termination = 'PROTECTION_CONFLICT' if code == 'PROTECTION_CONFLICT' else 'ERROR'
        info = search.info(termination)
        if termination == 'ERROR':
            info['raw_termination'] = 'UNKNOWN'
        return dict(proposals=[], search=info, error=_issue(code, str(exc)))
    request = copy.deepcopy(request)
    search.request = request
    search.budget = request['budget']
    materials = model.indexed(request['project']['materials'])
    try:
        search.progress('核对实际空缺与可用动机')
        targets = request['target_gaps']
        if not targets:
            return dict(proposals=[], search=search.info('NO_TARGETS'), error=None)
        roots = [materials[i] for i in request['library_ids'][:search.budget['material_limit']]]
        usable = []
        for root in roots:
            search.check()
            try:
                melody.music_signature(root)
                if not root['notes']:
                    _fail('NO_VALID_MATERIAL', '整段休止不可作为独立补全素材或动机。')
                _key(root)
                usable.append(root)
            except model.ProjectError as exc:
                search.rejections.append(_issue(exc.code, str(exc), material_id=root['id']))
        if not usable:
            return dict(proposals=[], search=search.info('NO_VALID_MATERIAL'),
                        error=_issue('NO_VALID_MATERIAL', '有限素材根中没有有效单旋律动机。'))
        roots = usable
        pool_limit = min(32, max(search.budget['beam_width'], 4 * search.budget['max_candidates']))
        beam = [(0, targets[0]['start_tick'], [])]
        pool = {}; pool_notes = 0; generated = {}; termination = None
        while beam and termination is None:
            search.progress('联合搜索精确基础排布')
            next_states = {}
            for gap_index, cursor, selections in beam:
                gap = targets[gap_index]; remaining = gap['end_tick'] - cursor
                options = [('reuse', root, root['length_ticks'], None) for root in roots
                           if root['length_ticks'] <= remaining]
                # Complete remaining range or construct an actual fourbeat/tail
                # phrase. Reuse options stay available after note budget exhaustion.
                lengths = list(dict.fromkeys((remaining, min(model.BAR, remaining))))
                options += [('compose', root, length, policy) for root in roots
                            for length in lengths for policy in range(len(POLICIES))]
                for kind, root, length, policy in options:
                    if not search.expand():
                        termination = 'BUDGET_EXHAUSTED'; break
                    if kind == 'reuse':
                        material = root
                    else:
                        key = (root['id'], length, policy)
                        if key not in generated:
                            if search.note_exhausted:
                                continue
                            try:
                                generated[key] = _compose(root, length, policy, request['seed'], search)
                            except _NoteBudget:
                                search.rejections.append(_issue('BUDGET_EXHAUSTED', '新音符预算耗尽，继续有限复用搜索。'))
                                continue
                        material = generated[key]
                    selection = dict(gap_id=gap['id'], start_tick=cursor, material=material,
                                     emotion=_emotion(request, gap, cursor, material))
                    selected = selections + [selection]
                    end = cursor + material['length_ticks']
                    index = gap_index
                    if end == gap['end_tick']:
                        index += 1
                        end = targets[index]['start_tick'] if index < len(targets) else end
                    if index == len(targets):
                        signature = _music_hash(selected)
                        score = _score(request, selected)
                        prior = pool.get(signature)
                        if prior is not None and prior['score']['total'] >= score['total']:
                            continue
                        count = sum(_note_count(s['material']) for s in selected)
                        old_count = sum(_note_count(s['material']) for s in prior['placements']) if prior else 0
                        if pool_notes - old_count + count > RAW_NOTE_LIMIT:
                            termination = 'RAW_POOL_LIMIT'; break
                        reasons = [_issue('COMPLETION_SCORE', '基础音程、调性、节奏、动机与重复评价；未经连接或听感验收。',
                            score=score, source_material_ids=[s['material']['provenance'].get('completion', {}).get(
                                'base_material_id', s['material']['id']) for s in selected],
                            repeated_fraction=score['repeat_penalty'], score_version=ALGORITHM_VERSION)]
                        pool[signature] = dict(id=model.digest('emoblocks.raw-proposal.v1',
                            dict(input_fingerprint=request['input_fingerprint'], music=signature)),
                            placements=selected, score=score, reasons=reasons)
                        pool_notes += count - old_count
                        if len(pool) >= pool_limit:
                            termination = 'RAW_POOL_LIMIT'; break
                    else:
                        signature = (index, end, _music_hash(selected))
                        state = (index, end, selected)
                        prior = next_states.get(signature)
                        if prior is None or _order(request, state) < _order(request, prior):
                            next_states[signature] = state
                if termination is not None:
                    break
            beam = sorted(next_states.values(), key=lambda state: _order(request, state))[:search.budget['beam_width']]
        if termination is None:
            termination = 'BUDGET_EXHAUSTED' if search.note_exhausted else 'RAW_POOL_EXHAUSTED'
        search.progress('原始备选池完成；等待正式记忆与情绪门禁')
        proposals = sorted(pool.values(), key=lambda p: (-p['score']['total'], _music_hash(p['placements'])))
        error = None if proposals else _issue('BUDGET_EXHAUSTED' if termination == 'BUDGET_EXHAUSTED'
                                              else 'NO_SOLUTION', '有限搜索未找到覆盖全部目标的有效提案。',
                                              target_gaps=copy.deepcopy(targets), finite_pool=True)
        independent = []
        for proposal in proposals:
            owned = copy.deepcopy(proposal)
            owned['placements'] = [copy.deepcopy(s) for s in proposal['placements']]
            independent.append(owned)
        return dict(proposals=independent, search=copy.deepcopy(search.info(termination)), error=error)
    except _Cancelled:
        return dict(proposals=[], search=search.info('CANCELLED'), error=_issue('CANCELLED', '基础补全已取消。'))
