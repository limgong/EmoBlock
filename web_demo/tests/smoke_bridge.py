"""Positive global-bridge case with real LMMS; no renderer or planner mocks."""
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from web_demo.api.core import model, workflow, recommendations
import curve_final_render as audio


def project():
    value = model.new_project(4); sources = []
    for index in range(4):
        notes = []
        for j in range(8):
            source_id = f'source:{index}:{j}'
            note = dict(id=f'note:{index}:{j}', pitch=60 if j % 2 == 0 else 84,
                start_tick=j*240, duration_tick=240, velocity=80,
                origin=dict(source_id='S', track_id='track', source_note_id=source_id), lineage=[], slice=None)
            notes.append(note); sources.append(dict(copy.deepcopy(note), id=source_id, start_tick=index*1920+j*240))
        material = dict(id=f'material:{index}', label='bridge-positive-fixture', kind='phrase', length_ticks=1920,
            notes=notes, provenance=dict(source_id='S', source_start_tick=index*1920,
                key_context=dict(tonic=0, mode='major', confidence=1., method='explicit-fixture')),
            generation=None, phrase_id=None, children=[])
        value['materials'].append(material)
        value['placements'].append(dict(id=f'place:{index}', material_id=material['id'], base_snapshot=copy.deepcopy(material),
            start_tick=index*1920, length_ticks=1920, emotion='calm', emotion_variant=None))
    value['sources'] = [dict(id='S', label='bridge-positive-fixture', length_ticks=value['total_ticks'], notes=sources, provenance=dict(track_id='track'))]
    model.validate(value)
    return value


if __name__ == '__main__':
    controller = workflow.Controller(project()); before = controller.project
    captured = controller.capture_recommendations(mode='arranged')
    outcome = recommendations.prepare_recommendations(captured['request'], source_facts=captured['source_facts'])
    assert outcome['candidates'], outcome['failures']
    assert controller.finish_recommendations(captured['token'], outcome)
    candidate = outcome['candidates'][0]
    request = recommendations.resolve(outcome['facts'], next(f for f in outcome['facts'] if f['id'] == candidate['stage_refs']['boundary_request_id']), 'boundary_request')
    bridge = request['connection_ref']['request']['bridge_ref']
    assert bridge['plan']['decision'] == 'selected' and bridge['results'], 'positive fixture must actually generate bridges'
    score = recommendations.resolve(outcome['facts'], candidate['final_score_ref'], 'final_score')
    for result in bridge['results']:
        for note in result['notes']:
            assert any(all(n[k] == note[k] for k in ('id', 'pitch', 'start_tick', 'duration_tick')) for n in score['notes']), 'later connection/boundary processing changed a protected bridge note'
    audio.validate_asset(candidate['assets']['final'], score)
    assert score['total_ticks'] == before['total_ticks']
    controller.apply_recommendation(candidate['id'], confirmation_ref=controller.confirmation_ref(candidate['id']))
    guards = [p for p in controller.project['protections'] if p['kind'] == 'bridge']
    assert guards
    accepted = controller.project
    assert controller.undo() and controller.project == before
    assert controller.redo() and controller.project == accepted
    report = dict(bridge_count=len(bridge['results']), protected_note_count=sum(len(r['notes']) for r in bridge['results']),
        actual_lmms=True, protections_retained=True, fixed_duration=True, undo_redo=True)
    output = Path(os.environ.get('SMOKE_OUTPUT', 'data/bridge-smoke')); output.mkdir(parents=True, exist_ok=True)
    (output/'bridge-positive-report.json').write_text(json.dumps(report, indent=2))
    print('REAL_BRIDGE_SMOKE_PASS', json.dumps(report))
