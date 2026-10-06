"""P3 placement-local emotion rules, always computed from a base snapshot.

No project edits, new voices, bridge generation, rendering or player access.
Source resolution belongs to the workflow; music_signature validates standalone
Material shape, ancestry shape, single melody and component consistency here.
"""
import copy
import math
import random

import curve_melody as melody
import curve_project as model
import intensity_curve

ALGORITHM_VERSION = 'curve-emotion-rules-v1'
RNG_VERSION = 'python.random-v3'
DEFAULTS = {'max_changes': 2, 'max_pitch_shift': 3}
STYLES = {
    'calm': dict(timbre='soft-piano', harmony='stable-open-voicing', density=.2, gain=.9),
    'hope': dict(timbre='warm-bell', harmony='open-consonant-support', density=.4, gain=1.),
    'sad': dict(timbre='dark-sustained', harmony='restrained-low-support', density=.2, gain=.85),
    'suspense': dict(timbre='muted-pluck', harmony='sparse-pedal-with-tension', density=.35, gain=.92),
    'crisis': dict(timbre='focused-pluck', harmony='rhythmic-pedal-support', density=.6, gain=1.12),
    'resolve': dict(timbre='warm-brass', harmony='tonic-support-and-release', density=.45, gain=1.05),
}


def _fail(code, message):
    raise model.ProjectError(code, message)


def _parameters(parameters):
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict) or not set(parameters) <= set(DEFAULTS):
        _fail('INVALID_PARAMETERS', '未知情绪规则参数。')
    result = dict(DEFAULTS, **parameters)
    if (type(result['max_changes']) is not int or not 1 <= result['max_changes'] <= 8
            or type(result['max_pitch_shift']) is not int or not 1 <= result['max_pitch_shift'] <= 4):
        _fail('INVALID_PARAMETERS', '轻改数量须为1–8，音高幅度须为1–4半音。')
    return result


def _points(points, start_tick, length):
    model.objects(points)
    if len(points) < 2:
        _fail('INVALID_PARAMETERS', '强度轨迹需要覆盖素材的至少两个控制点。')
    previous = -1; result = []
    for point in points:
        model.shape(point, 'tick level')
        model.integer(point['tick'])
        level = point['level']
        if (point['tick'] <= previous or isinstance(level, bool)
                or not isinstance(level, (int, float)) or not math.isfinite(level) or not 0 <= level <= 1):
            _fail('INVALID_PARAMETERS', '强度控制点须递增且程度在0–1。')
        previous = point['tick']
        result.append(dict(time=point['tick'], level=level))
    if points[0]['tick'] > start_tick or points[-1]['tick'] < start_tick + length:
        _fail('INVALID_PARAMETERS', '强度轨迹没有覆盖当前放置。')
    return result


def _ranges(ranges):
    result = []
    for region in model.objects([] if ranges is None else ranges):
        model.shape(region, 'start_tick end_tick')
        model.integer(region['start_tick']); model.integer(region['end_tick'], region['start_tick'] + 1)
        result.append(copy.deepcopy(region))
    merged = []
    for region in sorted(result, key=lambda r: (r['start_tick'], r['end_tick'])):
        if merged and region['start_tick'] <= merged[-1]['end_tick']:
            merged[-1]['end_tick'] = max(merged[-1]['end_tick'], region['end_tick'])
        else:
            merged.append(region)
    return merged


def _support(note, start_tick):
    return dict(start_tick=start_tick + note['start_tick'],
                end_tick=start_tick + note['start_tick'] + note['duration_tick'])


def _structure(note):
    return {k: v for k, v in note.items() if k != 'velocity'}


def _protected(base, protected_notes, start_tick):
    try:
        supplied = model.indexed(protected_notes)
        originals = model.indexed(base['notes'])
        for ident, note in supplied.items():
            model.shape(note, 'id pitch start_tick duration_tick velocity origin lineage slice')
            model.integer(note['velocity'], 1, 127)
            original = originals.get(ident)
            if original is None:
                _fail('PROTECTION_CONFLICT', '受保护音符不属于当前基础快照。')
            expected = dict(original, start_tick=original['start_tick'] + start_tick)
            if model.canonical(_structure(note)) != model.canonical(_structure(expected)):
                _fail('PROTECTION_CONFLICT', '保护音符必须是基础快照的完整绝对音符。')
        return supplied
    except model.ProjectError as exc:
        if exc.code == 'PROTECTION_CONFLICT':
            raise
        raise model.ProjectError('PROTECTION_CONFLICT', '保护音符数据无效。') from exc


def _components(material, path=(), offset=0):
    if material['kind'] != 'combination':
        return [dict(component_path=list(path), material_id=material['id'], kind=material['kind'],
                     start_tick=offset, length_ticks=material['length_ticks'],
                     provenance=copy.deepcopy(material['provenance']))]
    result = []
    for child in material['children']:
        result.extend(_components(child['snapshot'], path + (child['occurrence_id'],), offset + child['offset_tick']))
    return result


def _covered(region, ranges):
    return any(r['start_tick'] <= region['start_tick'] and r['end_tick'] >= region['end_tick'] for r in ranges)


def _key_context(base):
    context = base['provenance'].get('key_context')
    if context is None and base['generation']:
        context = base['generation'].get('key_context')
    if context is None:
        return None  # Use explicit local neighbors; never silently assume C.
    if not isinstance(context, dict) or not {'tonic', 'mode', 'confidence', 'method'} <= set(context):
        _fail('INVALID_PARAMETERS', '调性上下文缺少字段。')
    model.integer(context['tonic'], 0, 11); model.text(context['method'])
    confidence = context['confidence']
    if (context['mode'] not in ('major', 'minor') or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or confidence < 0):
        _fail('INVALID_PARAMETERS', '调性上下文无效。')
    return copy.deepcopy(context)


def _pitch_choices(pitch, emotion, key, limit, terminal):
    degrees = (0, 2, 4, 5, 7, 9, 11) if key and key['mode'] == 'major' else (0, 2, 3, 5, 7, 8, 10)
    candidates = [p for p in range(max(0, pitch - limit), min(127, pitch + limit) + 1) if p != pitch]
    if key and emotion != 'suspense':
        candidates = [p for p in candidates if (p - key['tonic']) % 12 in degrees]
    if emotion == 'sad':
        return sorted((p for p in candidates if p < pitch), reverse=True)
    if emotion == 'suspense':
        return sorted(candidates, key=lambda p: (abs(p - pitch), p < pitch))
    if emotion == 'resolve' and key:
        tonic = [p for p in candidates if p % 12 == key['tonic']]
        if tonic:
            return sorted(tonic, key=lambda p: (abs(p - pitch), p))
        if terminal:
            return []  # An already stable final note need not be rewritten.
    return sorted(p for p in candidates if p > pitch)


def _change_note(note, emotion, key, level, parameters, terminal):
    """Local pitch/short-articulation edit; never creates attacks or moves them."""
    result = copy.deepcopy(note)
    choices = _pitch_choices(note['pitch'], emotion, key, parameters['max_pitch_shift'], terminal)
    if choices:
        result['pitch'] = choices[0]
    if choices and emotion in ('suspense', 'crisis') and note['duration_tick'] % 10 == 0:
        # Reduction is an algorithm operation in whole 10tick units; exact
        # nonmultiple input durations stay untouched, not output-quantized.
        divisor = 10 if emotion == 'suspense' else (4 if level >= .75 else 5)
        reduction = (note['duration_tick'] // (divisor * 10)) * 10
        result['duration_tick'] -= reduction
    return result


def _guard(before, after, protected_ids, ranges, start_tick):
    """Independent structural check on actual events, not the operation claims."""
    originals = model.indexed(before); actual = model.indexed(after)
    if set(actual) != set(originals):
        _fail('PROTECTION_CONFLICT', '情绪轻改不能新增或删除主旋律发声。')
    for ident, note in actual.items():
        original = originals[ident]
        if ident in protected_ids or any(model.intersects(_support(original, start_tick), r) for r in ranges):
            if _structure(note) != _structure(original):
                _fail('PROTECTION_CONFLICT', '情绪处理改变了完整受保护音符。')
        elif any(model.intersects(_support(note, start_tick), r) for r in ranges):
            _fail('PROTECTION_CONFLICT', '情绪音符进入受保护休止或范围。')
        elif (note['start_tick'] != original['start_tick'] or not 0 < note['duration_tick'] <= original['duration_tick']
              or any(note[k] != original[k] for k in ('origin', 'lineage', 'slice'))):
            _fail('PROTECTION_CONFLICT', '局部情绪规则不得移动起音、延长时值或篡改来源。')


def emotion_variant(base, emotion, intensity_points, start_tick, protected_notes,
                    protected_ranges=None, seed=31, parameters=None):
    """Return a deterministic Material from this base, never a prior variant.

    Protected notes use base Note.id and absolute time. Ranges use absolute,
    half-open ticks, including empty protected regions and full sound supports.
    Calm can preserve the melody. Limitations live in generation.warnings.
    """
    melody.music_signature(base)
    if base['generation'] and base['generation'].get('method') == 'emotion_variant':
        _fail('INVALID_PARAMETERS', '请从放置基础快照重算，不能累计处理情绪变体。')
    if not isinstance(emotion, str) or emotion not in STYLES:
        _fail('INVALID_PARAMETERS', '未知情绪。')
    model.integer(start_tick)
    if type(seed) is not int:
        _fail('INVALID_PARAMETERS', '情绪种子须为整数。')
    parameters = _parameters(parameters)
    points = _points(intensity_points, start_tick, base['length_ticks'])
    ranges = _ranges(protected_ranges)
    supplied = _protected(base, protected_notes, start_tick)
    originals = sorted(copy.deepcopy(base['notes']), key=lambda n: (n['start_tick'], n['id']))
    frozen = set(supplied)
    frozen.update(n['id'] for n in originals if any(model.intersects(_support(n, start_tick), r) for r in ranges))
    components = _components(base)
    for component in components:
        if component['kind'] == 'bridge':
            region = dict(start_tick=start_tick + component['start_tick'],
                          end_tick=start_tick + component['start_tick'] + component['length_ticks'])
            bridge_ids = {n['id'] for n in originals if model.intersects(_support(n, start_tick), region)}
            if not _covered(region, ranges) or not bridge_ids <= set(supplied):
                _fail('PROTECTION_CONFLICT', '已有 bridge 必须有完整范围和实际音符保护。')
    key = _key_context(base)
    level = intensity_curve.evaluate(points, start_tick + base['length_ticks'] / 2)
    eligible = [i for i, n in enumerate(originals) if n['id'] not in frozen]
    if emotion == 'resolve':
        eligible.reverse()
    else:
        # Retain the opening motive when there is other editable material.
        opening = [i for i in eligible if i == 0]
        eligible = [i for i in eligible if i != 0]
        random.Random(seed).shuffle(eligible)
        eligible += opening
    budget = min(parameters['max_changes'], max(1, math.ceil(len(originals) * (.15 + .25 * level))))
    notes = copy.deepcopy(originals); operations = []; changed_ids = []
    if emotion != 'calm':
        for index in eligible:
            original = originals[index]
            changed = _change_note(original, emotion, key, level, parameters, index == len(originals) - 1)
            if (changed['pitch'], changed['start_tick'], changed['duration_tick']) != (original['pitch'], original['start_tick'], original['duration_tick']):
                notes[index] = changed; changed_ids.append(original['id'])
                operations.append(dict(operation='local-emotion-melody', emotion=emotion, input_note_id=original['id'],
                    from_pitch=original['pitch'], to_pitch=changed['pitch'], start_tick=original['start_tick'],
                    original_duration_tick=original['duration_tick'], output_duration_tick=changed['duration_tick'],
                    shortened_by_tick=original['duration_tick'] - changed['duration_tick'], rule_unit_ticks=10))
            if len(changed_ids) >= budget:
                break
    _guard(originals, notes, frozen, ranges, start_tick)
    warnings = []
    if not changed_ids:
        if not originals:
            code, message = 'PURE_REST', '素材为内部休止，未生成新旋律。'
        elif not eligible:
            code, message = 'FULLY_PROTECTED', '全部音符受保护，无法合法改变旋律。'
        elif emotion == 'calm':
            code, message = 'CALM_MELODY_PRESERVED', '平静保留基础旋律。'
        else:
            code, message = 'NO_LEGAL_MELODIC_CHANGE', '素材或音域不足，未找到合法局部旋律变化。'
        warnings.append(dict(code=code, message=message, details=dict(melody_changed=False)))
        operations.append(dict(operation='melody-preserved', reason=code, protected_note_ids=sorted(frozen)))
    input_fingerprint = model.digest('emoblocks.emotion-input.v1', dict(base=base, emotion=emotion,
        intensity_points=intensity_points, start_tick=start_tick,
        protected_notes=[supplied[k] for k in sorted(supplied)], protected_ranges=ranges,
        seed=seed, parameters=parameters, algorithm_version=ALGORITHM_VERSION))
    variant_id = model.digest('emoblocks.emotion-material.v1', input_fingerprint)
    performance = []
    for note in notes:
        note_level = intensity_curve.evaluate(points, start_tick + note['start_tick'])
        old_velocity = note['velocity']
        note['velocity'] = max(1, min(127, round(note['velocity'] * (.75 + .4 * note_level) * STYLES[emotion]['gain'])))
        performance.append(dict(input_note_id=note['id'], intensity=note_level,
                                original_velocity=old_velocity, output_velocity=note['velocity']))
        if note['id'] in changed_ids:
            old_id = note['id']
            note.update(id=model.digest('emoblocks.emotion-note.v1', [variant_id, old_id]), slice=None,
                        lineage=list(dict.fromkeys(note['lineage'] + [old_id])))
    operations.append(dict(operation='velocity-expression', melody_change=False,
                           emotion_gain=STYLES[emotion]['gain'], events=performance))
    provenance = copy.deepcopy(base['provenance'])
    provenance.update(input_material_id=base['id'], input_phrase_id=base['phrase_id'], input_kind=base['kind'])
    if base['kind'] == 'combination':
        provenance.update(component_snapshots=copy.deepcopy(base['children']), component_paths=components, source_start_tick=None)
    hints = dict(timbre=STYLES[emotion]['timbre'], harmony=STYLES[emotion]['harmony'],
                 density=round(STYLES[emotion]['density'] * (.5 + level), 4), key_context=key,
                 drums=dict(enabled=False, fill=False), status='suggested-not-rendered')
    result = dict(id=variant_id, label=base['label'] + ' · ' + emotion,
        kind='phrase' if base['kind'] == 'combination' else base['kind'], length_ticks=base['length_ticks'],
        notes=notes, provenance=provenance, phrase_id=None, children=[],
        generation=dict(method='emotion_variant', emotion=emotion, parameters=parameters, seed=seed,
            rng_version=RNG_VERSION, algorithm_version=ALGORITHM_VERSION, input_fingerprint=input_fingerprint,
            input_material_ids=[base['id']], base_notes=copy.deepcopy(base['notes']), key_context=key,
            operations=operations, warnings=warnings, melody_changed=bool(changed_ids),
            accompaniment_hints=hints,
            protection=dict(explicit_note_ids=sorted(supplied), frozen_note_ids=sorted(frozen), ranges=ranges)))
    melody.music_signature(result)  # Validate the actual output independently.
    return result
