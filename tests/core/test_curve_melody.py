"""P2 actual music/data checks; no LMMS, Tk, devices or aesthetic verdict."""
import copy
import random
import unittest
from pathlib import Path
from unittest.mock import patch

import curve_melody as melody
import curve_project as model


def source(ident='S', events=None, length=4080):
    if events is None:
        events = [(60, 240, 240), (64, 720, 240), (67, 1200, 240),
                  (65, 1800, 300), (64, 2160, 240), (62, 2640, 240),
                  (64, 3360, 240), (60, 3840, 240)]
    return dict(id=ident, label='来源 ' + ident, length_ticks=length,
        notes=[dict(id=f'n{i}', pitch=pitch, start_tick=start, duration_tick=duration, velocity=80,
                    origin=dict(source_id=ident, track_id='track1', source_note_id=f'n{i}'), lineage=[], slice=None)
               for i, (pitch, start, duration) in enumerate(events)],
        provenance=dict(path='fixture.mid', file_fingerprint='fixture-' + ident, track_id='track1',
                        original_bpm=96, ppq_policy='round-to-480',
                        key_context=dict(tonic=0, mode='major', confidence=.7, method='fixture')))


def base(src=None):
    src = source() if src is None else src
    return dict(id='base-' + src['id'], label='测试句', kind='phrase', length_ticks=src['length_ticks'],
        notes=copy.deepcopy(src['notes']), provenance=dict(source_id=src['id'], source_start_tick=0,
            source_provenance=copy.deepcopy(src['provenance']), key_context=copy.deepcopy(src['provenance']['key_context'])),
        generation=None, phrase_id=None, children=[])


def combination(ident, items):
    offset = 0; children = []; notes = []
    for index, item in enumerate(items):
        children.append(dict(occurrence_id=f'occ-{index}', offset_tick=offset, snapshot=copy.deepcopy(item)))
        for i, n in enumerate(item['notes']):
            notes.append(dict(copy.deepcopy(n), id=f'{ident}:{index}:{i}', start_tick=offset + n['start_tick']))
        offset += item['length_ticks']
    return dict(id=ident, label='组合', kind='combination', length_ticks=offset, notes=notes,
                provenance=dict(key_context=copy.deepcopy(items[0]['provenance']['key_context'])),
                generation=None, phrase_id=None, children=children)


def prepared_project(*sources):
    project = model.new_project()
    for src in sources:
        project['sources'].append(copy.deepcopy(src))
        project['materials'].extend(melody.prepare_source(src)['materials'])
    model.validate(project)
    return project


class ImportTests(unittest.TestCase):
    def test_own_source_imports(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(Path(melody.__file__).resolve(), root / 'backend/core/curve_melody.py')
        self.assertEqual(Path(model.__file__).resolve(), root / 'backend/core/curve_project.py')

    def test_actual_4080_tail_leading_rest_and_full_batch(self):
        src = source(); before = copy.deepcopy(src)
        batch = melody.prepare_source(src)
        self.assertEqual(set(batch), {'materials', 'candidates', 'warnings'})
        original = [m for m in batch['materials'] if m['kind'] == 'block' and m['phrase_id'] is None and m['generation'] is None]
        self.assertEqual([m['length_ticks'] for m in original], [1920, 1920, 240])
        self.assertEqual(original[0]['notes'][0]['start_tick'], 240)
        self.assertEqual(original[2]['notes'][0]['duration_tick'], 240)
        self.assertEqual(src, before)
        ids = [m['id'] for m in batch['materials']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(batch['candidates']) <= set(ids))
        prepared_project(src)

    def test_cross_1920_source_slices_reconstruct_full_note(self):
        batch = melody.prepare_source(source())
        original = [m for m in batch['materials'] if m['kind'] == 'block' and m['phrase_id'] is None and m['generation'] is None]
        a = next(n for n in original[0]['notes'] if n['origin']['source_note_id'] == 'n3')
        b = next(n for n in original[1]['notes'] if n['origin']['source_note_id'] == 'n3')
        self.assertEqual((a['start_tick'], a['duration_tick'], b['start_tick'], b['duration_tick']), (1800, 120, 0, 180))
        self.assertEqual(a['slice']['parent_emission_id'], b['slice']['parent_emission_id'])
        self.assertEqual((a['slice']['offset_tick'], b['slice']['offset_tick']), (0, 120))
        self.assertEqual((a['slice']['parent_duration_tick'], b['slice']['parent_duration_tick']), (300, 300))
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(a['origin'], b['origin'])

    def test_phrase_full_note_and_children_independent_uses(self):
        project = prepared_project(source())
        phrase = next(m for m in project['materials'] if m['kind'] == 'phrase' and m['generation'] is None)
        self.assertEqual(phrase['children'], [])
        cross = next(n for n in phrase['notes'] if n['origin']['source_note_id'] == 'n3')
        self.assertEqual((cross['start_tick'], cross['duration_tick'], cross['slice']), (1800, 300, None))
        children = [m for m in project['materials'] if m['phrase_id'] == phrase['id']]
        self.assertEqual([m['provenance']['relative_start_tick'] for m in children], [0, 1920])
        self.assertEqual([m['length_ticks'] for m in children], [1920, 720])
        project = model.edit(project, 'place', material_id=phrase['id'], start_tick=0, placement_id='whole')
        project = model.edit(project, 'place', material_id=children[1]['id'], start_tick=4800, placement_id='child')
        project = model.edit(project, 'place', material_id=children[1]['id'], start_tick=7200, placement_id='repeat')
        self.assertEqual(project['placements'][1]['base_snapshot']['phrase_id'], phrase['id'])
        self.assertNotEqual(model.placed_notes(project['placements'][1])[0]['id'], model.placed_notes(project['placements'][2])[0]['id'])

    def test_heuristic_boundaries_never_cut_a_sustained_note(self):
        src = source(); batch = melody.prepare_source(src)
        phrases = [m for m in batch['materials'] if m['kind'] == 'phrase' and m['generation'] is None]
        self.assertEqual([m['length_ticks'] for m in phrases], [2640, 1440])
        rebuilt = []
        for phrase in phrases:
            meta = phrase['provenance']
            self.assertTrue(meta['heuristic'])
            self.assertEqual(meta['segmentation_version'], melody.SEGMENTATION_VERSION)
            for n in phrase['notes']:
                rebuilt.append((n['pitch'], n['start_tick'] + meta['source_start_tick'], n['duration_tick'], n['origin']))
        self.assertEqual(rebuilt, [(n['pitch'], n['start_tick'], n['duration_tick'], n['origin']) for n in src['notes']])

    def test_default_real_three_rules_prefer_complete_phrase(self):
        batch = melody.prepare_source(source()); by_id = {m['id']: m for m in batch['materials']}
        candidates = [by_id[i] for i in batch['candidates']]
        self.assertEqual([m['generation']['method'] for m in candidates], ['variant', 'answer', 'rhythm'])
        self.assertEqual(len({melody.music_signature(m) for m in candidates}), 3)
        for candidate in candidates:
            parent = by_id[candidate['generation']['input_material_ids'][0]]
            self.assertEqual(parent['kind'], 'phrase'); self.assertTrue(parent['provenance']['phrase_complete'])
            self.assertNotEqual(melody.music_signature(candidate), melody.music_signature(parent))
            self.assertTrue(any(m['phrase_id'] == candidate['id'] for m in batch['materials']))

    def test_no_complete_phrase_falls_back_to_first_sounding_block(self):
        src = source(events=[(60, 2400, 240)], length=2640)
        batch = melody.prepare_source(src); by_id = {m['id']: m for m in batch['materials']}
        original = [m for m in batch['materials'] if m['kind'] == 'block' and m['phrase_id'] is None and m['generation'] is None]
        self.assertEqual(original[0]['notes'], [])
        self.assertIn('PHRASE_FALLBACK', [w['code'] for w in batch['warnings']])
        for ident in batch['candidates']:
            self.assertEqual(by_id[ident]['generation']['input_material_ids'], [original[1]['id']])

    def test_dedup_does_not_use_velocity_or_metadata_as_difference(self):
        def fake(base, method, seed):
            result = copy.deepcopy(base); result['id'] = method
            result['label'] = method
            for n in result['notes']:
                n['velocity'] = 40
            return result
        with patch.object(melody, 'derive', side_effect=fake):
            batch = melody.prepare_source(source())
        self.assertEqual(batch['candidates'], [])
        self.assertEqual(sum(w['code'] == 'DUPLICATE_CANDIDATE' for w in batch['warnings']), 3)
        self.assertTrue(any(w['code'] == 'INSUFFICIENT_CANDIDATES' for w in batch['warnings']))

    def test_actual_tiny_material_reports_candidate_shortage(self):
        batch = melody.prepare_source(source(events=[(60, 0, 1)], length=1))
        self.assertLess(len(batch['candidates']), 3)
        self.assertIn('NO_VALID_VARIATION', [w['code'] for w in batch['warnings']])
        self.assertIn('INSUFFICIENT_CANDIDATES', [w['code'] for w in batch['warnings']])

    def test_multiple_sources_with_same_note_names_stay_distinct(self):
        project = prepared_project(source('one'), source('two'))
        sources = {s['id']: s for s in project['sources']}
        for material in project['materials']:
            model.material_check(material, sources)
        ids = [m['id'] for m in project['materials']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({n['origin']['source_id'] for m in project['materials'] for n in m['notes']}, {'one', 'two'})

    def test_prepare_and_split_return_deep_copies_and_replay(self):
        src = source(); before = copy.deepcopy(src)
        first = melody.prepare_source(src); self.assertEqual(first, melody.prepare_source(src))
        first['materials'][0]['provenance']['source_provenance']['path'] = 'changed'
        first['materials'][0]['notes'][0]['origin']['track_id'] = 'changed'
        self.assertEqual(src, before)
        phrase = base(); before = copy.deepcopy(phrase)
        children = melody.split_phrase(phrase)
        self.assertEqual(children, melody.split_phrase(phrase))
        children[0]['provenance']['source_provenance']['path'] = 'changed'
        self.assertEqual(phrase, before)


class RuleTests(unittest.TestCase):
    def test_all_six_deterministic_actual_changes_and_complete_metadata(self):
        src = source(); original = base(src); before = copy.deepcopy(original)
        random.seed(77); state = random.getstate()
        for method in melody.METHODS:
            with self.subTest(method=method):
                derived = melody.derive(original, method, seed=31)
                self.assertEqual(derived, melody.derive(original, method, seed=31))
                self.assertEqual(derived['length_ticks'], original['length_ticks'])
                self.assertNotEqual(melody.music_signature(derived), melody.music_signature(original))
                model.material_check(derived, {src['id']: src})
                notes = sorted(derived['notes'], key=lambda n: n['start_tick'])
                self.assertTrue(all(a['start_tick'] + a['duration_tick'] <= b['start_tick'] for a, b in zip(notes, notes[1:])))
                self.assertEqual(set(derived['generation']), {'method', 'parameters', 'seed', 'rng_version', 'algorithm_version',
                    'input_fingerprint', 'input_material_ids', 'base_notes', 'key_context', 'operations'})
                self.assertEqual(derived['generation']['base_notes'], original['notes'])
                self.assertTrue(derived['generation']['operations'])
                self.assertTrue(all(n['lineage'] and n['slice'] is None for n in derived['notes']))
                self.assertFalse({n['id'] for n in derived['notes']} & {n['id'] for n in original['notes']})
        self.assertEqual(original, before); self.assertEqual(random.getstate(), state)

    def test_variant_preserves_opening_and_answer_responds_to_contour(self):
        original = base()
        variant = melody.derive(original, 'variant')
        self.assertEqual(variant['notes'][0]['pitch'], original['notes'][0]['pitch'])
        self.assertEqual([(n['start_tick'], n['duration_tick']) for n in variant['notes']],
                         [(n['start_tick'], n['duration_tick']) for n in original['notes']])
        answer = melody.derive(original, 'answer')
        self.assertGreater(original['notes'][1]['pitch'], original['notes'][0]['pitch'])
        self.assertLess(answer['notes'][1]['pitch'], answer['notes'][0]['pitch'])

    def test_rhythm_and_density_have_real_rhythm_and_event_changes(self):
        original = base()
        rhythm = melody.derive(original, 'rhythm')
        self.assertNotEqual([(n['start_tick'], n['duration_tick']) for n in original['notes']],
                            [(n['start_tick'], n['duration_tick']) for n in rhythm['notes']])
        dense = melody.derive(original, 'density')
        sparse = melody.derive(original, 'density', parameters={'direction': 'sparser'})
        self.assertGreater(len(dense['notes']), len(original['notes']))
        self.assertLess(len(sparse['notes']), len(original['notes']))

    def test_develop_preserves_and_then_sequences_a_motif(self):
        original = base(); developed = melody.derive(original, 'develop')
        self.assertEqual([n['pitch'] for n in developed['notes'][:2]], [n['pitch'] for n in original['notes'][:2]])
        self.assertNotEqual([n['pitch'] for n in developed['notes'][2:]], [n['pitch'] for n in original['notes'][2:]])
        op = developed['generation']['operations'][0]
        self.assertEqual(op['operation'], 'motif-sequence')
        self.assertEqual(op['motif_note_ids'], [n['id'] for n in original['notes'][:2]])

    def test_counter_is_one_replacement_voice(self):
        original = base(); counter = melody.derive(original, 'counter')
        self.assertEqual(len(counter['notes']), len(original['notes']))
        self.assertEqual(counter['generation']['operations'][0]['voices'], 1)
        self.assertNotEqual([n['pitch'] for n in counter['notes']], [n['pitch'] for n in original['notes']])

    def test_counter_shortenings_remain_expressible_and_are_recorded(self):
        src = source(events=[(60, 0, 960), (64, 960, 120), (67, 1080, 240), (65, 1320, 300)], length=1620)
        original = base(src); before = copy.deepcopy(original)
        counter = melody.derive(original, 'counter')
        self.assertEqual([n['duration_tick'] for n in counter['notes']], [770, 100, 200, 240])
        self.assertEqual([n['start_tick'] for n in counter['notes']], [0, 960, 1080, 1320])
        self.assertEqual(counter['length_ticks'], 1620)
        self.assertTrue(all(n['duration_tick'] % 10 == 0 for n in counter['notes']))
        self.assertEqual(counter['generation']['algorithm_version'], melody.COUNTER_ALGORITHM_VERSION)
        op = counter['generation']['operations'][0]
        self.assertEqual(op['rule_unit_ticks'], 10)
        self.assertEqual([a['shortened_by_tick'] for a in op['articulation']], [190, 20, 40, 60])
        for note, prior, record in zip(counter['notes'], original['notes'], op['articulation']):
            self.assertEqual(record['input_note_id'], prior['id'])
            self.assertEqual(record['original_duration_tick'], prior['duration_tick'])
            self.assertEqual(record['output_duration_tick'], note['duration_tick'])
            self.assertEqual(record['original_duration_tick'] - record['shortened_by_tick'], note['duration_tick'])
            self.assertFalse(record['preserved_exact_tick'])
        self.assertEqual(counter, melody.derive(original, 'counter'))
        self.assertEqual(original, before)
        model.material_check(counter, {src['id']: src})

    def test_counter_preserves_nonmultiple_durations_and_exact_onsets(self):
        src = source(events=[(60, 1, 239), (64, 241, 37), (67, 281, 300)], length=581)
        original = base(src); counter = melody.derive(original, 'counter')
        self.assertEqual([n['duration_tick'] for n in counter['notes']], [239, 37, 240])
        self.assertEqual([n['start_tick'] for n in counter['notes']], [1, 241, 281])
        self.assertEqual(counter['length_ticks'], 581)
        self.assertEqual([a['shortened_by_tick'] for a in counter['generation']['operations'][0]['articulation']], [0, 0, 60])
        self.assertEqual([a['preserved_exact_tick'] for a in counter['generation']['operations'][0]['articulation']], [True, True, False])
        self.assertNotEqual([n['pitch'] for n in original['notes']], [n['pitch'] for n in counter['notes']])
        # Only exercise the renderer's preflight: no LMMS lookup or device use.
        import curve_audition
        with patch.object(curve_audition, 'find_lmms', side_effect=AssertionError('must reject before renderer lookup')):
            with self.assertRaises(model.ProjectError) as caught:
                curve_audition.render_audition(counter)
        self.assertEqual(caught.exception.code, 'OUTPUT_TIME_UNREPRESENTABLE')

    def test_counter_small_units_stay_positive_without_creating_fractional_units(self):
        for duration in (1, 10, 20, 30, 40, 50):
            src = source(events=[(60, 0, duration)], length=duration)
            counter = melody.derive(base(src), 'counter')
            self.assertEqual(counter['notes'][0]['duration_tick'], 40 if duration == 50 else duration)
            self.assertGreater(counter['notes'][0]['duration_tick'], 0)

    def test_actual_theme_c_first_block_counter_retains_tick_expressibility(self):
        import curve_workflow
        from runtime_config import ASSETS
        batch = curve_workflow.prepare_import(ASSETS / 'theme-c.mid')
        original = next(m for m in batch['materials'] if m['kind'] == 'block' and m['phrase_id'] is None and m['generation'] is None)
        self.assertEqual(original['length_ticks'], 1920)
        self.assertEqual([n['duration_tick'] for n in original['notes']], [960, 120, 120])
        counter = melody.derive(original, 'counter')
        self.assertEqual([n['duration_tick'] for n in counter['notes']], [770, 100, 100])
        self.assertEqual([n['start_tick'] for n in counter['notes']], [n['start_tick'] for n in original['notes']])
        self.assertTrue(all(n['start_tick'] % 10 == 0 and n['duration_tick'] % 10 == 0 for n in counter['notes']))
        self.assertEqual(counter['length_ticks'], original['length_ticks'])

    def test_nested_repeated_multisource_combo_derives_new_phrase(self):
        s1 = source('one', [(60, 0, 240), (64, 240, 240)], 480)
        s2 = source('two', [(67, 0, 240), (69, 240, 240)], 480)
        a = base(s1); b = base(s2)
        inner = combination('inner', [a, b, a]); outer = combination('outer', [inner, a])
        before = copy.deepcopy(outer)
        for method in melody.METHODS:
            with self.subTest(method=method):
                derived = melody.derive(outer, method)
                self.assertEqual((derived['kind'], derived['children'], derived['phrase_id']), ('phrase', [], None))
                model.material_check(derived, {s1['id']: s1, s2['id']: s2})
                self.assertEqual(derived['provenance']['component_snapshots'], outer['children'])
                paths = [p['component_path'] for p in derived['provenance']['component_paths']]
                self.assertEqual(paths, [['occ-0', 'occ-0'], ['occ-0', 'occ-1'], ['occ-0', 'occ-2'], ['occ-1']])
                self.assertIsNone(derived['provenance']['source_start_tick'])
                project = model.new_project(); project['sources'] = [s1, s2]
                project['materials'] = [a, b, derived] + melody.split_phrase(derived)
                model.validate(project)
        self.assertEqual(outer, before)

    def test_independent_child_derivation_drops_old_phrase_membership(self):
        phrase = base(); block = melody.split_phrase(phrase)[1]
        derived = melody.derive(block, 'variant')
        self.assertIsNone(derived['phrase_id'])
        self.assertEqual(derived['provenance']['input_phrase_id'], phrase['id'])
        self.assertTrue(all(n['slice'] is None for n in derived['notes']))

    def test_signature_ignores_identity_velocity_metadata_but_not_real_music(self):
        original = base(); changed = copy.deepcopy(original)
        changed.update(id='new', label='label'); changed['provenance']['seed'] = 999
        for i, n in enumerate(changed['notes']):
            n.update(id=str(i), velocity=1)
        self.assertEqual(melody.music_signature(original), melody.music_signature(changed))
        changed['notes'][0]['pitch'] += 1
        self.assertNotEqual(melody.music_signature(original), melody.music_signature(changed))
        changed = copy.deepcopy(original); changed['length_ticks'] += 1
        self.assertNotEqual(melody.music_signature(original), melody.music_signature(changed))

    def test_key_inference_is_recorded_without_default_c(self):
        material = base(source(events=[(66, 0, 240), (70, 240, 240), (73, 480, 240)], length=720))
        del material['provenance']['key_context']
        derived = melody.derive(material, 'variant')
        self.assertEqual(derived['generation']['key_context']['method'], 'duration-weighted-scale-v1')
        self.assertNotEqual(derived['generation']['key_context']['tonic'], 0)

    def test_varied_short_rhythms_and_edge_registers_remain_valid(self):
        rng = random.Random(901)
        for case in range(20):
            events = []; cursor = rng.randrange(0, 20)
            for _ in range(rng.randrange(1, 10)):
                duration = rng.choice((1, 2, 37, 239, 300))
                events.append((rng.choice((0, 1, 60, 66, 126, 127)), cursor, duration))
                cursor += duration + rng.choice((0, 1, 60, 240))
            src = source(str(case), events, events[-1][1] + events[-1][2])
            original = base(src)
            for method in melody.METHODS:
                with self.subTest(case=case, method=method):
                    try:
                        derived = melody.derive(original, method, seed=case)
                    except model.ProjectError as exc:
                        self.assertEqual(exc.code, 'NO_VALID_VARIATION')
                    else:
                        self.assertEqual(derived, melody.derive(original, method, seed=case))
                        model.material_check(derived, {src['id']: src})
                        self.assertEqual(derived['length_ticks'], src['length_ticks'])
                        self.assertNotEqual(melody.music_signature(original), melody.music_signature(derived))

    def test_reslicing_keeps_existing_parent_emission_offsets(self):
        phrase = base(source(events=[(60, 0, 3000)], length=3000))
        phrase['notes'][0]['slice'] = dict(parent_emission_id='full-sound', offset_tick=300, parent_duration_tick=4000)
        blocks = melody.split_phrase(phrase)
        self.assertEqual([b['notes'][0]['slice']['offset_tick'] for b in blocks], [300, 2220])
        self.assertEqual({b['notes'][0]['slice']['parent_emission_id'] for b in blocks}, {'full-sound'})


class FailureAndEdgeTests(unittest.TestCase):
    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(model.ProjectError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_rest_is_a_valid_subblock_but_not_a_generation_base(self):
        phrase = base(source(events=[(60, 2400, 240)], length=2640))
        children = melody.split_phrase(phrase)
        self.assertEqual(children[0]['notes'], [])
        self.assert_code('EMPTY_MATERIAL', melody.derive, children[0], 'variant')
        phrase['notes'] = []
        self.assertEqual(melody.split_phrase(phrase)[0]['notes'], [])
        src = source(); src['notes'] = []
        self.assert_code('EMPTY_MATERIAL', melody.prepare_source, src)

    def test_no_actual_difference_is_a_structured_failure(self):
        tiny = base(source(events=[(60, 0, 1)], length=1))
        self.assert_code('NO_VALID_VARIATION', melody.derive, tiny, 'answer', parameters={'degree_shift': 0})
        for method in ('rhythm', 'develop', 'density'):
            self.assert_code('NO_VALID_VARIATION', melody.derive, tiny, method)

    def test_invalid_methods_parameters_seed_and_no_bridge(self):
        original = base()
        for method in ('bridge', 'completion', 'connection', None):
            self.assert_code('UNSUPPORTED_METHOD', melody.derive, original, method)
        for method, params in [('variant', {'fraction': float('nan')}), ('variant', {'fraction': True}),
                              ('variant', {'max_step': 0}), ('answer', {'degree_shift': True}),
                              ('rhythm', {'unit_ticks': 0}), ('density', {'direction': 'louder'}),
                              ('develop', {'unknown': 1})]:
            self.assert_code('INVALID_PARAMETERS', melody.derive, original, method, parameters=params)
        self.assert_code('INVALID_PARAMETERS', melody.derive, original, 'variant', seed=True)
        bridge = copy.deepcopy(original); bridge['kind'] = 'bridge'
        self.assert_code('UNSUPPORTED_METHOD', melody.derive, bridge, 'variant')
        self.assert_code('INVALID_PARAMETERS', melody.split_phrase, melody.split_phrase(original)[0])

    def test_malformed_notes_overlaps_sources_and_combinations_fail_without_mutation(self):
        cases = []
        overlap = base(); overlap['notes'][1]['start_tick'] = 241; cases.append(overlap)
        missing = base(); del missing['notes'][0]['origin']; cases.append(missing)
        boolean = base(); boolean['notes'][0]['duration_tick'] = True; cases.append(boolean)
        duplicate = base(); duplicate['notes'][1]['id'] = duplicate['notes'][0]['id']; cases.append(duplicate)
        invalid_slice = base(); invalid_slice['notes'][0]['slice'] = dict(parent_emission_id='x', offset_tick=1, parent_duration_tick=1); cases.append(invalid_slice)
        combo = combination('combo', [base(), base()]); combo['children'][1]['offset_tick'] += 1; cases.append(combo)
        for material in cases:
            before = copy.deepcopy(material)
            with self.assertRaises(model.ProjectError):melody.derive(material, 'variant')
            self.assertEqual(material, before)
        for update in ({'length_ticks': 4081}, {'provenance': {}}, {'notes': [dict(source()['notes'][0], origin=None)]}):
            src = source(); src.update(update)
            with self.assertRaises(model.ProjectError):melody.prepare_source(src)
        src = source(); src['provenance']['key_context'] = None
        self.assert_code('INVALID_PARAMETERS', melody.prepare_source, src)

    def test_midi_edge_pitches_and_short_ticks_never_escape_bounds(self):
        for pitch in (0, 127):
            src = source(events=[(pitch, 0, 1)], length=1); material = base(src)
            for method in melody.METHODS:
                try:
                    derived = melody.derive(material, method)
                except model.ProjectError as exc:
                    self.assertEqual(exc.code, 'NO_VALID_VARIATION')
                else:
                    model.material_check(derived, {src['id']: src})
                    self.assertTrue(all(0 <= n['pitch'] <= 127 and n['duration_tick'] == 1 for n in derived['notes']))

    def test_beyond_twelve_sources_and_nonbar_short_tail(self):
        project = prepared_project(*(source(str(i), [(60, 0, 239)], 239) for i in range(13)))
        self.assertEqual(len(project['sources']), 13)
        self.assertTrue(all(m['length_ticks'] == 239 for m in project['materials']))


if __name__ == '__main__':
    unittest.main()
