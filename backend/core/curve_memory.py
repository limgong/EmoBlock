"""Pure peak lookup, full-note memory protection and bounded trace editing."""
import copy
import math

import curve_project as model


def managed_id(project):
    return 'memory:' + project['project_id']


def memory_input(project):
    return model.digest('emoblocks.memory-input.v1', dict(
        total_ticks=project['total_ticks'],
        placements=[{k: copy.deepcopy(p[k]) for k in ('id', 'base_snapshot', 'start_tick', 'length_ticks')}
                    for p in sorted(project['placements'], key=lambda p: p['id'])],
        intensity_points=project['intensity_points'], blank_regions=project['blank_regions']))


def _location(project):
    """Already validated geometry; usable by validation without recursion."""
    peak = min(project['intensity_points'], key=lambda p: (-p['level'], p['tick']))['tick']
    lookup = min(peak, project['total_ticks'] - 1)
    info = dict(peak_tick=peak, lookup_tick=lookup, state='PENDING_GAP',
                placement_id=None, component_path=[], range=None, protection_id=None)
    if any(b['start_tick'] <= lookup < b['end_tick'] for b in project['blank_regions']):
        info['state'] = 'PRESERVE_BLANK'
        return info
    placement = next((p for p in project['placements']
                      if p['start_tick'] <= lookup < p['start_tick'] + p['length_ticks']), None)
    if placement is None:
        return info
    component, offset, path = placement['base_snapshot'], placement['start_tick'], []
    while component['kind'] == 'combination':
        part = next(c for c in component['children']
                    if offset + c['offset_tick'] <= lookup < offset + c['offset_tick'] + c['snapshot']['length_ticks'])
        offset += part['offset_tick']; path.append(part['occurrence_id']); component = part['snapshot']
    start = offset + ((lookup - offset) // model.BAR) * model.BAR
    info.update(state='BOUND', placement_id=placement['id'], component_path=path,
                range=dict(start_tick=start, end_tick=min(start + model.BAR, offset + component['length_ticks'])))
    ident = managed_id(project)
    if any(p['id'] == ident for p in project['protections']):
        info['protection_id'] = ident
    return info


def memory_info(project):
    model.validate(project)
    return _location(project)


def base_notes(placement, ranges):
    return [dict(copy.deepcopy(n), id=placement['id'] + ':' + n['id'],
                 start_tick=n['start_tick'] + placement['start_tick'])
            for n in placement['base_snapshot']['notes']
            if any(model.intersects(r, dict(start_tick=n['start_tick'] + placement['start_tick'],
                                           end_tick=n['start_tick'] + placement['start_tick'] + n['duration_tick']))
                   for r in ranges)]


def expected_protection(project):
    """No mutation or full validation: the model independently calls this gate."""
    info = _location(project)
    if info['state'] != 'BOUND':
        return None
    placement = next(p for p in project['placements'] if p['id'] == info['placement_id'])
    ident = managed_id(project)
    result = dict(id=ident, kind='memory', owner_id=ident, placement_id=placement['id'],
        component_path=info['component_path'], **info['range'], status='CONTENT_READY', origin='automatic',
        plan_id=None, plan_version=None, input_fingerprint=memory_input(project),
        notes=base_notes(placement, [info['range']]), structure_fingerprint=None, blank_mask=[])
    result['structure_fingerprint'] = model.structure_fingerprint(result)
    return result


def protected_ranges(protections):
    """Rest in the nominal lock and full crossing note supports are immutable."""
    ranges = []
    for p in protections:
        ranges.append({k: p[k] for k in ('start_tick', 'end_tick')})
        if p['kind'] == 'memory':
            ranges.extend(dict(start_tick=n['start_tick'], end_tick=n['start_tick'] + n['duration_tick'])
                          for n in p['notes'])
    return sorted({(r['start_tick'], r['end_tick']) for r in ranges})


def recompute(before, edited):
    """Narrow, deterministic result; Session remains the only transaction owner."""
    memory = expected_protection(edited)
    ident = managed_id(edited)
    fixed = [p for p in edited['protections'] if p['id'] != ident]
    locks = fixed + ([memory] if memory else [])
    domains = [dict(start_tick=a, end_tick=b) for a, b in protected_ranges(locks)]
    variants = {}
    for placement in edited['placements']:
        if placement['emotion'] == 'calm':
            variants[placement['id']] = None
            continue
        import curve_emotion
        relevant = [r for r in domains if model.intersects(r, dict(start_tick=placement['start_tick'],
                                      end_tick=placement['start_tick'] + placement['length_ticks']))]
        notes = base_notes(placement, relevant)
        prefix = placement['id'] + ':'
        notes = [dict(n, id=n['id'][len(prefix):]) for n in notes]
        variants[placement['id']] = curve_emotion.emotion_variant(
            copy.deepcopy(placement['base_snapshot']), placement['emotion'],
            copy.deepcopy(edited['intensity_points']), placement['start_tick'], notes,
            protected_ranges=relevant)
    return dict(automatic_memory=memory, emotion_variants=variants)


def normalize_trace(points, total_ticks, tolerance=.02):
    model.integer(total_ticks, 1)
    if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance) or tolerance < 0 or tolerance > 1):
        model.reject('轨迹简化容差应在0到1之间。', 'INVALID_INTENSITY_TRACE')
    values = {}
    for point in model.objects(points):
        model.shape(point, 'tick level'); model.integer(point['tick'], 0, total_ticks)
        level = point['level']
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not math.isfinite(level) or not 0 <= level <= 1:
            model.reject('强度必须是0到1之间的有限数值。', 'INVALID_INTENSITY_TRACE')
        values[point['tick']] = float(level)
    if not values:
        model.reject('请先绘制强度轨迹。', 'INVALID_INTENSITY_TRACE')
    ordered = sorted(values.items())
    values.setdefault(0, ordered[0][1]); values.setdefault(total_ticks, ordered[-1][1])
    points = [dict(tick=tick, level=level) for tick, level in sorted(values.items())]
    # Keep plateau boundaries too: they define the earliest equal peak.
    anchors = [0]
    for i in range(1, len(points) - 1):
        left = points[i]['level'] - points[i-1]['level']
        right = points[i+1]['level'] - points[i]['level']
        if left * right < 0 or ((left == 0) != (right == 0)):
            anchors.append(i)
    anchors.append(len(points) - 1)
    keep = set(anchors)
    pending = list(zip(anchors, anchors[1:]))
    while pending:
        a, b = pending.pop()
        if b - a < 2:
            continue
        left, right = points[a], points[b]
        worst = max(range(a + 1, b), key=lambda i: abs(points[i]['level'] -
            (left['level'] + (right['level'] - left['level']) *
             (points[i]['tick'] - left['tick']) / (right['tick'] - left['tick']))))
        deviation = abs(points[worst]['level'] - (left['level'] + (right['level'] - left['level']) *
                      (points[worst]['tick'] - left['tick']) / (right['tick'] - left['tick'])))
        if deviation > tolerance:
            keep.add(worst); pending.extend(((a, worst), (worst, b)))
    return [points[i] for i in sorted(keep)]
