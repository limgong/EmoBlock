"""P4 pure proposals: real coverage, bounded search, ancestry and replay.

Request fixtures implement the frozen public data shape, independently of the
lead's in-progress service. They do not claim post-emotion completion readiness.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import curve_completion as completion
import curve_project as model


def note(ident, pitch=60, start=0, duration=120, source_note='n0'):
    return dict(id=ident, pitch=pitch, start_tick=start, duration_tick=duration, velocity=80,
        origin=dict(source_id='S', track_id='track', source_note_id=source_note), lineage=[], slice=None)


def material(ident='B', length=240):
    return dict(id=ident, label=ident, kind='phrase', length_ticks=length,
        notes=[note(ident + ':0', duration=min(120, length))] + (
            [note(ident + ':1', 62, 120, length - 120, 'n1')] if length > 120 else []),
        provenance=dict(source_id='S', source_start_tick=0,
            key_context=dict(tonic=0, mode='major', confidence=.8, method='fixture-explicit')),
        generation=None, phrase_id=None, children=[])


def project(gap_length=240, tail_blank=True):
    p = model.new_project(4); p['project_id'] = 'completion-fixture'
    p['sources'] = [dict(id='S', label='source', length_ticks=4080,
        notes=[note('n0'), note('n1', 62, 120, 120, 'n1'), note('n2', 64, 360, 240, 'n2')],
        provenance=dict(track_id='track', file_fingerprint='fixture'))]
    left = material('L', 1200); right = material('R', 1920)
    p['materials'] = [material(), left, right]
    p['placements'] = [dict(id=ident, material_id=m['id'], base_snapshot=copy.deepcopy(m),
        start_tick=start, length_ticks=m['length_ticks'], emotion='calm', emotion_variant=None)
        for ident, m, start in [('left', left, 0), ('right', right, 1200 + gap_length)]]
    if tail_blank:
        p['blank_regions'] = [dict(id='blank', start_tick=3120 + gap_length,
                                    end_tick=p['total_ticks'], reason='用户主动留白')]
    model.validate(p)
    return p


def request(p=None, selected=True, budget=None, seed=31):
    p = copy.deepcopy(project() if p is None else p)
    fingerprint = model.fingerprint(p)
    gaps = [dict(id=model.digest('emoblocks.gap.v1', dict(input_fingerprint=fingerprint, range=r)), **r)
            for r in model.gaps(p)]
    if selected:
        gaps = gaps[:1]
    contexts = []
    for gap in gaps:
        lefts = [v for v in p['placements'] if v['start_tick'] + v['length_ticks'] <= gap['start_tick']]
        rights = [v for v in p['placements'] if v['start_tick'] >= gap['end_tick']]
        left = max(lefts, key=lambda v: v['start_tick']) if lefts else None
        right = min(rights, key=lambda v: v['start_tick']) if rights else None
        contexts.append(dict(gap_id=gap['id'], left=left, right=right,
            left_notes=model.placed_notes(left) if left else [], right_notes=model.placed_notes(right) if right else []))
    ranges = sorted({(r['start_tick'], r['end_tick']) for protection in p['protections']
                     for r in model.protection_ranges(protection)})
    def permitted(m):
        return m['kind'] != 'bridge' and all(permitted(c['snapshot']) for c in m['children'])
    return dict(schema='emoblocks.completion-request.v1', spec_rev=model.SPEC_REV,
        contract_rev=completion.CONTRACT_REV, input_contract_rev=p['contract_rev'],
        request_id='request', snapshot_id='snapshot', input_fingerprint=fingerprint,
        project=p, scope='selected' if selected else 'all', target_gaps=gaps,
        library_ids=sorted(m['id'] for m in p['materials'] if permitted(m)), contexts=contexts,
        protection_summary=dict(fingerprint=model.protection_summary(p['protections']),
            ranges=[dict(start_tick=a, end_tick=b) for a, b in ranges]),
        blank_regions=copy.deepcopy(p['blank_regions']), seed=seed,
        algorithm_version=completion.ALGORITHM_VERSION,
        budget=dict(completion.DEFAULT_BUDGET, **(budget or {})))


def music(proposal):
    return sorted((n['pitch'], s['start_tick'] + n['start_tick'], n['duration_tick'])
        for s in proposal['placements'] for n in s['material']['notes'])


def combination(ident, children):
    parts = []; notes = []; offset = 0
    for index, child in enumerate(children):
        parts.append(dict(occurrence_id=ident + ':part:' + str(index), offset_tick=offset,
                          snapshot=copy.deepcopy(child)))
        count = len(notes)
        notes.extend(dict(copy.deepcopy(n), id=ident + ':note:' + str(count + i),
                          start_tick=n['start_tick'] + offset) for i, n in enumerate(child['notes']))
        offset += child['length_ticks']
    return dict(id=ident, label=ident, kind='combination', length_ticks=offset,
        notes=notes, provenance={}, generation=None, phrase_id=None, children=parts)


class CompletionTests(unittest.TestCase):
    def assert_complete(self, req, result):
        self.assertTrue(result['proposals'], result)
        self.assertNotIn('ENOUGH_CANDIDATES', (result['search']['termination'], result['search']['raw_termination']))
        self.assertLessEqual(len(result['proposals']), min(32, max(req['budget']['beam_width'], 4 * req['budget']['max_candidates'])))
        self.assertLessEqual(result['search']['expansions'], req['budget']['max_expansions'])
        self.assertLessEqual(result['search']['generated_notes'], req['budget']['max_new_notes'])
        self.assertLessEqual(sum(len(s['material']['notes']) for p in result['proposals'] for s in p['placements']), 65536)
        sources = model.source_index(req['project']['sources'])
        for proposal in result['proposals']:
            for target in req['target_gaps']:
                selections = [s for s in proposal['placements'] if s['gap_id'] == target['id']]
                cursor = target['start_tick']
                self.assertTrue(selections)
                for selection in selections:
                    self.assertEqual(selection['start_tick'], cursor)
                    m = selection['material']; self.assertTrue(m['notes'])
                    model.material_check(m, sources)
                    self.assertIn(selection['emotion'], model.EMOTIONS)
                    cursor += m['length_ticks']
                self.assertEqual(cursor, target['end_tick'])

    def test_240_reuse_and_real_exact_motifs_no_input_edits(self):
        req = request(); before = copy.deepcopy(req)
        result = completion.propose(req)
        self.assert_complete(req, result)
        self.assertGreaterEqual(len(result['proposals']), 3)
        self.assertEqual(req, before)
        materials = [s['material'] for p in result['proposals'] for s in p['placements']]
        self.assertTrue(any(m['id'] == 'B' for m in materials))
        self.assertTrue(any(m['generation'] and m['generation']['method'] == 'completion_exact' for m in materials))
        self.assertEqual((req['project']['placements'][1]['start_tick'], req['project']['total_ticks']), (1440, 7680))

    def test_exact_one_tick_239_and_short_tail_4080(self):
        for length in (1, 239, 240, 4080):
            with self.subTest(length=length):
                req = request(project(length)); result = completion.propose(req)
                self.assert_complete(req, result)
                self.assertTrue(any(s['material']['length_ticks'] == length
                    for p in result['proposals'] for s in p['placements']))
                if length == 1:
                    self.assertGreaterEqual(len({tuple(music(p)) for p in result['proposals']}), 2)
                    self.assertTrue(all(n['duration_tick'] == 1 for p in result['proposals']
                                        for s in p['placements'] for n in s['material']['notes']))

    def test_joint_all_gaps_and_selected_does_not_touch_tail(self):
        p = project(tail_blank=False)
        req = request(p, selected=False); result = completion.propose(req)
        self.assert_complete(req, result)
        self.assertEqual(len(req['target_gaps']), 2)
        selected = request(p); one = completion.propose(selected)
        self.assert_complete(selected, one)
        self.assertTrue(all(s['start_tick'] < 1440 for proposal in one['proposals'] for s in proposal['placements']))

    def test_repeated_music_penalty_changes_ranking(self):
        p = project(480)
        req = request(p, budget=dict(material_limit=1, max_new_notes=1))
        result = completion.propose(req); self.assert_complete(req, result)
        reused = next(p for p in result['proposals'] if len(p['placements']) == 2
                      and all(s['material']['id'] == 'B' for s in p['placements']))
        self.assertEqual(reused['score']['repeat_penalty'], .5)
        self.assertAlmostEqual(reused['score']['total'], sum(
            reused['score'][key] * weight for key, weight in completion.WEIGHTS.items()))

    def test_deterministic_replay_and_random_request_identity_not_music(self):
        req = request(project(tail_blank=False), selected=False)
        first = completion.propose(req); self.assertEqual(first, completion.propose(req))
        other = copy.deepcopy(req); other.update(request_id='different', snapshot_id='different')
        self.assertEqual(first, completion.propose(other))
        changed = completion.propose(request(project(), seed=99))
        self.assert_complete(request(project(), seed=99), changed)
        self.assertTrue(all(-.1 <= p['score']['total'] <= .9 for p in first['proposals']))

    def test_returned_snapshots_independent_between_occurrences_and_calls(self):
        req = request(project(480), budget=dict(material_limit=1, max_new_notes=1))
        result = completion.propose(req); before = copy.deepcopy(req)
        proposal = next(p for p in result['proposals'] if len(p['placements']) == 2)
        proposal['placements'][0]['material']['notes'][0]['pitch'] = 100
        self.assertEqual(proposal['placements'][1]['material']['notes'][0]['pitch'], 60)
        self.assertEqual(req, before)
        self.assertNotEqual(result, completion.propose(req))

    def test_extreme_pitches_and_source_slices_get_fresh_identity(self):
        for pitch in (0, 127):
            p = project(1)
            for n in p['materials'][0]['notes']:
                n.update(pitch=pitch, slice=dict(parent_emission_id='source-emission',
                    offset_tick=n['start_tick'], parent_duration_tick=240))
            req = request(p, budget=dict(material_limit=1)); result = completion.propose(req)
            self.assert_complete(req, result)
            self.assertGreaterEqual(len(result['proposals']), 2)
            for proposal in result['proposals']:
                for n in proposal['placements'][0]['material']['notes']:
                    self.assertIsNone(n['slice']); self.assertTrue(0 <= n['pitch'] <= 127)

    def test_single_sided_context_and_internal_rest_are_not_gaps(self):
        p = project()
        p['placements'].pop(0)
        # The right phrase's own natural rest remains occupied, not a target.
        p['placements'][0]['base_snapshot']['notes'][1]['start_tick'] = 1440
        p['placements'][0]['base_snapshot']['notes'][1]['duration_tick'] = 480
        req = request(p); self.assertIsNone(req['contexts'][0]['left'])
        self.assertEqual(req['target_gaps'][0]['end_tick'], 1440)
        self.assert_complete(req, completion.propose(req))

    def test_original_source_registry_and_malformed_requests(self):
        req = request(); req['project']['materials'][0]['notes'][0]['origin']['source_note_id'] = 'missing'
        result = completion.propose(req); self.assertIsNotNone(result['error'])
        for value in ({}, None, [], {'budget': {}}):
            self.assertIsNotNone(completion.propose(value)['error'])

    def test_duplicate_ids_labels_velocity_not_different_music(self):
        p = project(); clone = copy.deepcopy(p['materials'][0])
        clone.update(id='B-alias', label='fake difference')
        for n in clone['notes']: n.update(id=n['id'] + '-alias', velocity=110)
        p['materials'].append(clone)
        result = completion.propose(request(p)); projections = [tuple(music(p)) for p in result['proposals']]
        self.assertEqual(len(projections), len(set(projections)))

    def test_generated_metadata_ancestry_and_exact_playable_domain(self):
        req = request(project(960)); result = completion.propose(req)
        self.assert_complete(req, result)
        original = {m['id']: m for m in req['project']['materials']}
        generated = [s['material'] for p in result['proposals'] for s in p['placements'] if s['material']['generation']]
        self.assertTrue(generated)
        for item in generated:
            gen = item['generation']; base = item['provenance']['completion']['base_snapshot']
            self.assertEqual(base, original[item['provenance']['completion']['base_material_id']])
            self.assertEqual(gen['base_notes'], base['notes'])
            self.assertEqual(gen['input_material_ids'], [base['id']])
            self.assertEqual(gen['parameters']['target_ticks'], item['length_ticks'])
            self.assertEqual(gen['algorithm_version'], 'curve-completion-v1')
            self.assertIsNone(item['phrase_id'])
            self.assertEqual(item['children'], [])
            for n in item['notes']:
                self.assertIsNone(n['slice']); self.assertTrue(n['lineage'])
                self.assertEqual(n['start_tick'] % 10, 0); self.assertEqual(n['duration_tick'] % 10, 0)

    def test_exact_original_ticks_not_quantized(self):
        p = project(239); p['materials'][0]['notes'][0]['duration_tick'] = 119
        p['materials'][0]['notes'][1]['start_tick'] = 121
        p['materials'][0]['notes'][1]['duration_tick'] = 119
        req = request(p); before = copy.deepcopy(req)
        result = completion.propose(req); self.assert_complete(req, result)
        self.assertEqual(req, before)
        self.assertTrue(any(s['material']['generation']['parameters']['rule_unit_ticks'] == 1
            for proposal in result['proposals'] for s in proposal['placements'] if s['material']['generation']))

    def test_nested_combination_new_phrase_keeps_complete_components(self):
        p = project(239)
        inner = combination('combo', [p['materials'][0], p['materials'][0]])
        outer = combination('A-nested', [inner, p['materials'][0]])
        p['materials'].append(outer); req = request(p, budget=dict(material_limit=1))
        before = copy.deepcopy(req); result = completion.propose(req)
        self.assert_complete(req, result); self.assertEqual(req, before)
        for proposal in result['proposals']:
            for selection in proposal['placements']:
                m = selection['material']; self.assertEqual(m['kind'], 'phrase')
                self.assertEqual(m['provenance']['component_snapshots'], outer['children'])
                self.assertTrue(m['provenance']['component_paths'])

    def test_note_budget_partial_attempt_counted_and_reuse_continues(self):
        req = request(project(480), budget=dict(material_limit=1, max_new_notes=1))
        result = completion.propose(req); self.assert_complete(req, result)
        self.assertEqual(result['search']['generated_notes'], 1)
        self.assertTrue(any(all(s['material']['id'] == 'B' for s in p['placements']) for p in result['proposals']))

    def test_expansion_budget_never_returns_partial_all_targets(self):
        req = request(project(tail_blank=False), selected=False, budget=dict(max_expansions=1))
        result = completion.propose(req)
        self.assertEqual(result['proposals'], [])
        self.assertEqual(result['search']['expansions'], 1)
        self.assertEqual(result['search']['termination'], 'BUDGET_EXHAUSTED')

    def test_cancel_before_work_and_after_complete_pool_discards_everything(self):
        immediate = completion.propose(request(), should_cancel=lambda: True)
        self.assertEqual(immediate['search']['generated_notes'], 0)
        self.assertEqual(immediate['proposals'], [])
        cancelled = False; events = []
        def progress(event):
            nonlocal cancelled
            events.append(event)
            cancelled = '原始备选池完成' in event['message']
        result = completion.propose(request(), should_cancel=lambda: cancelled, on_progress=progress)
        self.assertEqual(result['proposals'], [])
        self.assertEqual(result['search']['termination'], 'CANCELLED')
        self.assertGreater(result['search']['expansions'], 0)
        self.assertGreater(result['search']['generated_notes'], 0)
        self.assertEqual([e['event_seq'] for e in events], list(range(1, len(events) + 1)))
        self.assertTrue(all(e['phase'] == 'BASE_COMPLETION' for e in events))

    def test_callback_exception_propagates_for_lead_failure_transaction(self):
        def fail(event): raise RuntimeError('callback failed')
        with self.assertRaisesRegex(RuntimeError, 'callback failed'):
            completion.propose(request(), on_progress=fail)

    def test_no_targets_has_zero_search(self):
        p = project(); p['blank_regions'].append(dict(id='gap-blank', start_tick=1200, end_tick=1440, reason='主动留白'))
        result = completion.propose(request(p, selected=False))
        self.assertEqual(result['search']['termination'], 'NO_TARGETS')
        self.assertEqual(result['search']['expansions'], 0)
        self.assertEqual(result['search']['generated_notes'], 0)
        self.assertIsNone(result['error'])

    def test_actual_context_variant_and_tampered_context_rejected(self):
        p = project(); variant = copy.deepcopy(p['placements'][0]['base_snapshot'])
        variant['id'] = 'old-variant'
        for n in variant['notes']: n['pitch'] += 1
        p['placements'][0].update(emotion='hope', emotion_variant=variant)
        req = request(p); self.assert_complete(req, completion.propose(req))
        req['contexts'][0]['left_notes'][0]['pitch'] -= 1
        self.assertEqual(completion.propose(req)['error']['code'], 'STALE_SNAPSHOT')

    def test_half_gap_bad_version_ids_fingerprint_and_bool_budget(self):
        changes = [lambda r: r['target_gaps'][0].update(end_tick=1320),
            lambda r: r.update(input_contract_rev='wrong'),
            lambda r: r.update(input_fingerprint='wrong'),
            lambda r: r.update(library_ids=[]),
            lambda r: r['budget'].update(max_expansions=True),
            lambda r: r.update(seed=True)]
        for change in changes:
            req = request(); change(req); result = completion.propose(req)
            self.assertFalse(result['proposals']); self.assertIsNotNone(result['error'])

    def test_empty_notes_not_usable_and_no_fake_completion(self):
        p = project(); p['materials'][0]['notes'] = []
        result = completion.propose(request(p, budget=dict(material_limit=1)))
        self.assertEqual(result['proposals'], [])
        self.assertEqual(result['search']['termination'], 'NO_VALID_MATERIAL')

    def test_no_library_no_solution(self):
        p = model.new_project(1); p['project_id'] = 'empty'
        result = completion.propose(request(p, selected=False))
        self.assertEqual(result['proposals'], [])
        self.assertEqual(result['search']['termination'], 'NO_VALID_MATERIAL')

    def test_phase_isolation_no_emotion_memory_or_old_planner(self):
        with (patch('curve_memory.recompute', side_effect=AssertionError('memory generation')),
              patch('curve_emotion.emotion_variant', side_effect=AssertionError('emotion generation')),
              patch('story_engine.plan', side_effect=AssertionError('legacy planner'))):
            req = request(); self.assert_complete(req, completion.propose(req))

    def test_failed_range_lock_conflict_and_manual_bridge_exclusion(self):
        p = project(); protection = dict(id='fixed', kind='manual', owner_id='user', placement_id=None,
            component_path=[], start_tick=1200, end_tick=1440, status='RANGE_LOCKED', origin='manual',
            plan_id=None, plan_version=None, input_fingerprint=model.fingerprint(p), notes=[],
            structure_fingerprint=None, blank_mask=[])
        p['protections'] = [protection]
        result = completion.propose(request(p))
        self.assertEqual(result['search']['termination'], 'PROTECTION_CONFLICT')
        self.assertEqual(result['error']['code'], 'PROTECTION_CONFLICT')
        p = project(); bridge = material('bridge'); bridge['kind'] = 'bridge'
        nested = combination('nested-bridge', [bridge, p['materials'][0]])
        p['materials'].extend([bridge, nested]); req = request(p)
        self.assertNotIn('bridge', req['library_ids']); self.assertNotIn('nested-bridge', req['library_ids'])
        self.assert_complete(req, completion.propose(req))

    def test_raw_note_limit_is_counted_even_for_reuse(self):
        with patch.object(completion, 'RAW_NOTE_LIMIT', 2):
            result = completion.propose(request())
        self.assertEqual(result['search']['termination'], 'RAW_POOL_LIMIT')
        self.assertLessEqual(sum(len(s['material']['notes']) for p in result['proposals'] for s in p['placements']), 2)


class RealCompletionIntegrationTests(unittest.TestCase):
    """Real lead dependency 7014f51, not the proposal substitutes in gate tests."""
    def test_real_post_gate_all_input_versions_exact_tail_and_shortage(self):
        import curve_candidates as candidates
        for rev in ('curve-workflow-v2-r3-p0', 'curve-workflow-v2-r3-p23', completion.CONTRACT_REV):
            for length in (1, 239, 240, 4080):
                with self.subTest(version=rev, length=length):
                    p = project(length); p['contract_rev'] = rev; before = copy.deepcopy(p)
                    req = candidates.make_request(p, candidates.gap_items(p)[0]['id'])
                    result = candidates.prepare_completion(req)
                    candidates.validate_outcome(req, result)
                    self.assertEqual(result['status'], 'SUCCEEDED', result)
                    self.assertEqual(len(result['candidates']), 2)
                    self.assertEqual(p, before)
                    self.assertEqual(req['input_contract_rev'], rev)
                    for candidate in result['candidates']:
                        self.assertEqual(candidate['project']['placements'][:2], p['placements'])
                        self.assertFalse(candidate['capabilities']['can_audition'])
                        self.assertFalse(candidate['capabilities']['can_apply'])
        req = candidates.make_request(project(), budget=dict(max_candidates=1))
        result = candidates.prepare_completion(req)
        self.assertEqual(result['status'], 'INSUFFICIENT')
        self.assertTrue(result['shortage_reasons'])

    def test_real_old_custom_variant_preserved_peak_new_base_protected(self):
        import curve_candidates as candidates
        import curve_emotion
        p = project()
        p['intensity_points'] = [dict(tick=0, level=.2), dict(tick=1320, level=.95),
                                 dict(tick=7680, level=.1)]
        old = p['placements'][0]
        old['emotion'] = 'hope'
        old['emotion_variant'] = curve_emotion.emotion_variant(old['base_snapshot'], 'hope',
            p['intensity_points'], 0, [], protected_ranges=[], seed=99, parameters=dict(max_changes=1))
        before = copy.deepcopy(p)
        req = candidates.make_request(p, candidates.gap_items(p)[0]['id'])
        result = candidates.prepare_completion(req)
        self.assertEqual(result['status'], 'SUCCEEDED', result)
        self.assertEqual(p, before)
        for candidate in result['candidates']:
            self.assertEqual(candidate['project']['placements'][0], old)
            self.assertEqual(candidate['memory_info']['state'], 'BOUND')
            self.assertEqual(candidate['memory_info']['range'], dict(start_tick=1200, end_tick=1440))
            memory = next(lock for lock in candidate['project']['protections'] if lock['kind'] == 'memory')
            new = next(v for v in candidate['project']['placements'] if v['id'] == memory['placement_id'])
            actual = model.placed_notes(new)
            self.assertEqual(model.structural_notes(actual), model.structural_notes(memory['notes']))

    def test_real_controller_stage_save_reload_cancel_and_late_result(self):
        import curve_candidates as candidates
        import curve_workflow
        controller = curve_workflow.Controller(project())
        with tempfile.TemporaryDirectory() as tmp:
            controller.save_snapshot(Path(tmp) / 'input.json')
            before = controller.project; before_state = controller.state()
            job = controller.capture_completion(controller.gap_items()[0]['id'])
            outcome = candidates.prepare_completion(job['request'])
            self.assertTrue(controller.finish_completion(job['token'], outcome))
            self.assertFalse(controller.finish_completion(job['token'], outcome))
            self.assertEqual(controller.project, before)
            self.assertTrue(controller.state()['is_saved']); self.assertTrue(controller.state()['staging_dirty'])
            self.assertEqual(controller.state()['can_undo'], before_state['can_undo'])
            ready = controller.save_snapshot(Path(tmp) / 'ready.json')
            loaded = curve_workflow.Controller(); loaded.load(ready)
            self.assertEqual(loaded.completion_state()['status'], 'READY')
            self.assertEqual(loaded.project, before)
            serialized = json.loads(ready.read_text())
            self.assertEqual(serialized['project']['materials'], before['materials'])
            self.assertEqual(serialized['attempts'][0]['completion']['outcome'], outcome)
            late = loaded.capture_completion(loaded.gap_items()[0]['id'])
            self.assertTrue(loaded.cancel_completion(late['token']))
            newer = loaded.capture_completion(loaded.gap_items()[0]['id'])
            cancelled = candidates.prepare_completion(late['request'],
                should_cancel=lambda: not loaded.accepts(late['token']))
            self.assertEqual(cancelled['status'], 'CANCELLED')
            self.assertFalse(loaded.finish_completion(late['token'], outcome))
            self.assertTrue(loaded.accepts(newer['token']))
            self.assertEqual(loaded.project, before)
            running = loaded.save_snapshot(Path(tmp) / 'running.json')
            reopened = curve_workflow.Controller(); reopened.load(running)
            self.assertEqual(reopened.completion_state()['status'], 'INTERRUPTED')
            self.assertFalse(reopened.accepts(newer['token']))


if __name__ == '__main__':
    unittest.main()
