"""Backend-only entrypoint. Does not configure or import the desktop UI."""
import sys
import json
import copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for part in ('backend/step1', 'backend/step2', 'backend/core'):
    sys.path.insert(0, str(ROOT / part))
import curve_project as model
import curve_workflow as workflow
import curve_recommendations as recommendations
import curve_store
from curve_material_names import short_name
SAMPLE_CATALOG = json.loads((ROOT / 'assets/samples/classical-catalog.json').read_text(encoding='utf-8'))
SAMPLES = {item['id']: (item['label'], item['file']) for item in SAMPLE_CATALOG}

def controller(sample='joy', example=False):
    value = workflow.Controller(model.new_project(8))
    job = value.capture_job('IMPORT')
    value.apply_batch(workflow.prepare_import(ROOT / 'assets/samples' / SAMPLES[sample][1]), job['token'])
    if example:
        # An explicitly requested new experience; never modifies an existing project.
        originals = [m for m in value.project['materials']
                     if m['kind'] == 'block' and not m['phrase_id'] and not m['generation']]
        positions = (0, 1, 2, 4, 5, 6, 7)
        emotions = ('calm', 'hope', 'crisis', 'resolve', 'resolve', 'hope', 'calm')
        for index, emotion in zip(positions, emotions):
            value.edit('place', material_id=originals[index]['id'], start_tick=index * model.BAR)
            value.edit('set_emotion', placement_ids=[value.project['placements'][-1]['id']], emotion=emotion)
        value.edit('set_intensity', points=[dict(tick=0,level=.2),dict(tick=3840,level=.45),
            dict(tick=7680,level=.85),dict(tick=8640,level=.95),dict(tick=11520,level=.6),
            dict(tick=value.project['total_ticks'],level=.2)])
    return value

def edit_board(value, action, grid_count=None):
    """Browser-only, undoable board operations; desktop resize rules stay intact."""
    import curve_memory
    value._editable()
    before = value.project
    if action == 'resize' and grid_count >= before['grid_count']:
        return value.edit('resize', grid_count=grid_count)
    prepared = copy.deepcopy(before)
    if action == 'clear_canvas':
        prepared.update(placements=[], blank_regions=[], protections=[], accepted_candidate_id=None,
            intensity_points=[dict(tick=0, level=.25), dict(tick=before['total_ticks'], level=.25)])
    else:
        total = grid_count * model.BAR
        if (any(p['start_tick'] + p['length_ticks'] > total for p in before['placements'])
                or any(b['end_tick'] > total for b in before['blank_regions'])
                or any(r['end_tick'] > total for p in before['protections']
                       if not model.managed_memory(before, p) for r in model.protection_ranges(p))):
            model.reject('末尾仍有积木、留白或保护区域；请先移除，或清空画板后缩短。', 'OUT_OF_BOUNDS')
        points = [p for p in before['intensity_points'] if p['tick'] < total]
        prepared.update(grid_count=grid_count, total_ticks=total,
            intensity_points=points + [dict(tick=total, level=model.intensity_at(before, total))])
    if prepared == before:
        return False
    model.invalidate_records(prepared, before)
    model.apply_recompute(before, prepared, curve_memory.recompute)
    changed = value.session.apply_prepared(prepared, value.session._revision, model.fingerprint(before))
    if changed:
        value._stale_completions()
        value._jobs.clear()
        value._untouched_new = False
    return changed
