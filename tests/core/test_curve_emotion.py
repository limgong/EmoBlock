"""P3 melody/identity/protection behavior; no renderer or playback calls."""
import copy
import random
import unittest
from pathlib import Path
from unittest.mock import patch

import curve_emotion as emotion
import curve_melody as melody
import curve_project as model
from test_curve_melody import base, combination, source


def points(level=.5, end=24000):
    return [dict(tick=0, level=level), dict(tick=end, level=level)]


def absolute(note, start=0):
    return dict(copy.deepcopy(note), start_tick=note['start_tick'] + start)


def structural(note):
    return {k: v for k, v in note.items() if k != 'velocity'}


def call(material, name='hope', start=0, protected=None, ranges=None, **kwargs):
    return emotion.emotion_variant(material, name, points(), start, [] if protected is None else protected,
                                   protected_ranges=ranges, **kwargs)


class EmotionBehaviorTests(unittest.TestCase):
    def test_own_worktree_import_and_exact_public_signature(self):
        import inspect
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(Path(emotion.__file__).resolve(), root / 'backend/core/curve_emotion.py')
        self.assertEqual(list(inspect.signature(emotion.emotion_variant).parameters),
                         ['base', 'emotion', 'intensity_points', 'start_tick', 'protected_notes', 'protected_ranges', 'seed', 'parameters'])

    def test_six_emotions_actual_light_melody_and_substantive_hints(self):
        src = source(); original = base(src); before = copy.deepcopy(original)
        for name in model.EMOTIONS:
            with self.subTest(emotion=name):
                result = call(original, name)
                self.assertEqual(result['length_ticks'], original['length_ticks'])
                self.assertEqual(len(result['notes']), len(original['notes']))
                self.assertEqual([n['start_tick'] for n in result['notes']], [n['start_tick'] for n in original['notes']])
                model.material_check(result, {src['id']: src})
                changed = melody.music_signature(result) != melody.music_signature(original)
                self.assertEqual(result['generation']['melody_changed'], changed)
                self.assertEqual(changed, name != 'calm')
                hints = result['generation']['accompaniment_hints']
                self.assertTrue(hints['timbre']); self.assertTrue(hints['harmony'])
                self.assertEqual(hints['status'], 'suggested-not-rendered')
                self.assertEqual(hints['drums'], dict(enabled=False, fill=False))
                for a, b in zip(original['notes'], result['notes']):
                    self.assertLessEqual(abs(a['pitch'] - b['pitch']), 3)
                    self.assertLessEqual(b['duration_tick'], a['duration_tick'])
        self.assertEqual(original, before)

    def test_a_b_a_from_same_base_is_exact_and_prior_variant_is_rejected(self):
        original = base()
        state = random.getstate()
        a = call(original, 'hope', seed=71)
        b = call(original, 'sad', seed=71)
        self.assertNotEqual(melody.music_signature(a), melody.music_signature(b))
        self.assertEqual(a, call(original, 'hope', seed=71))
        self.assertEqual(a['generation']['base_notes'], original['notes'])
        self.assertEqual(random.getstate(), state)
        with self.assertRaises(model.ProjectError) as caught:
            call(a, 'sad')
        self.assertEqual(caught.exception.code, 'INVALID_PARAMETERS')

    def test_duplicate_uses_protection_and_variants_are_independent(self):
        original = base(); snapshot = copy.deepcopy(original)
        protect_all = [absolute(n) for n in original['notes']]
        first = call(original, 'crisis', protected=protect_all, ranges=[dict(start_tick=0, end_tick=4080)])
        second = call(original, 'crisis', start=5000)
        self.assertFalse(first['generation']['melody_changed'])
        self.assertTrue(second['generation']['melody_changed'])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first, call(original, 'crisis', protected=protect_all, ranges=[dict(start_tick=0, end_tick=4080)]))
        self.assertEqual(original, snapshot)

    def test_intensity_is_recomputed_and_dynamics_evidence_is_separate(self):
        original = base()
        low = emotion.emotion_variant(original, 'hope', points(.1), 0, [])
        high = emotion.emotion_variant(original, 'hope', points(.9), 0, [])
        self.assertNotEqual([n['velocity'] for n in low['notes']], [n['velocity'] for n in high['notes']])
        self.assertEqual(low, emotion.emotion_variant(original, 'hope', points(.1), 0, []))
        performance = next(o for o in low['generation']['operations'] if o['operation'] == 'velocity-expression')
        self.assertFalse(performance['melody_change'])
        self.assertEqual([e['original_velocity'] for e in performance['events']], [n['velocity'] for n in original['notes']])

    def test_nested_combo_preserves_complete_component_provenance_and_source(self):
        s1 = source('one', [(60, 0, 240), (64, 240, 240)], 480)
        s2 = source('two', [(67, 0, 240), (69, 240, 240)], 480)
        inner = combination('inner', [base(s1), base(s2), base(s1)])
        outer = combination('outer', [inner, base(s2)])
        before = copy.deepcopy(outer)
        result = call(outer, 'hope')
        self.assertEqual((result['kind'], result['children'], result['phrase_id']), ('phrase', [], None))
        self.assertEqual(result['provenance']['component_snapshots'], outer['children'])
        self.assertEqual([c['component_path'] for c in result['provenance']['component_paths']],
                         [['occ-0', 'occ-0'], ['occ-0', 'occ-1'], ['occ-0', 'occ-2'], ['occ-1']])
        model.material_check(result, {s1['id']: s1, s2['id']: s2})
        self.assertEqual({n['origin']['source_id'] for n in result['notes']}, {'one', 'two'})
        result['provenance']['component_snapshots'][0]['snapshot']['label'] = 'changed'
        self.assertEqual(outer, before)

    def test_selected_new_melody_is_base_not_original_source(self):
        original = base(); new = melody.derive(original, 'answer')
        protected = [absolute(n, 1000) for n in new['notes']]
        result = call(new, 'hope', start=1000, protected=protected, ranges=[dict(start_tick=1000, end_tick=5080)])
        self.assertEqual([structural(n) for n in result['notes']], [structural(n) for n in new['notes']])
        self.assertNotEqual([n['pitch'] for n in result['notes']], [n['pitch'] for n in original['notes']])
        self.assertEqual(result['generation']['input_material_ids'], [new['id']])

    def test_short_tail_and_independent_phrase_child_do_not_reference_old_parent(self):
        src = source(); original = base(src)
        tail = melody.split_phrase(original)[-1]
        self.assertEqual(tail['length_ticks'], 240)
        result = call(tail, 'hope')
        self.assertEqual(result['length_ticks'], 240)
        self.assertIsNone(result['phrase_id'])
        self.assertEqual(result['provenance']['input_phrase_id'], original['id'])
        self.assertTrue(all(n['duration_tick'] <= 240 for n in result['notes']))
        model.material_check(result, {src['id']: src})

    def test_playable_rhythm_remains_playable_and_exact_ticks_stay_exact(self):
        for events, length in [([(60, 0, 960), (64, 960, 120), (67, 1080, 240), (65, 1320, 300)], 1620),
                               ([(60, 1, 239), (64, 241, 37), (67, 281, 300)], 581)]:
            original = base(source(events=events, length=length))
            for name in model.EMOTIONS:
                with self.subTest(length=length, emotion=name):
                    result = call(original, name)
                    self.assertEqual(result['length_ticks'], length)
                    self.assertEqual([n['start_tick'] for n in result['notes']], [n['start_tick'] for n in original['notes']])
                    for old, new in zip(original['notes'], result['notes']):
                        if old['duration_tick'] % 10:
                            self.assertEqual(old['duration_tick'], new['duration_tick'])
                        else:
                            self.assertEqual(new['duration_tick'] % 10, 0)


class ProtectionTests(unittest.TestCase):
    def test_full_cross_boundary_sound_identity_and_ancestry_preserved(self):
        src = source(); original = base(src)
        cross = original['notes'][3]
        cross['lineage'] = ['prior-emission']
        cross['slice'] = dict(parent_emission_id='parent', offset_tick=30, parent_duration_tick=360)
        protected = [absolute(cross, 1000)]
        ranges = [dict(start_tick=2920, end_tick=4840)]
        for name in model.EMOTIONS:
            result = call(original, name, start=1000, protected=protected, ranges=ranges)
            actual = next(n for n in result['notes'] if n['id'] == cross['id'])
            self.assertEqual(structural(actual), structural(cross))
            self.assertEqual((actual['start_tick'], actual['duration_tick']), (1800, 300))
            self.assertEqual(original['notes'][3], cross)

    def test_protected_fourbeat_rest_remains_empty_and_other_half_can_change(self):
        original = base(source(events=[(60, 1920, 480), (64, 2640, 240), (60, 3360, 480)], length=3840))
        region = dict(start_tick=0, end_tick=1920)
        for name in ('hope', 'sad', 'suspense', 'crisis', 'resolve'):
            result = call(original, name, ranges=[region])
            self.assertTrue(result['generation']['melody_changed'])
            self.assertFalse(any(model.intersects(region, dict(start_tick=n['start_tick'], end_tick=n['start_tick'] + n['duration_tick'])) for n in result['notes']))

    def test_injected_attack_in_protected_rest_is_rejected_not_trusted(self):
        original = base(source(events=[(60, 1920, 480), (64, 2640, 240), (60, 3360, 480)], length=3840))
        real_guard = emotion._guard
        def add_attack(before, after, *args):
            after.append(dict(copy.deepcopy(before[0]), id='added', start_tick=480, duration_tick=120))
            return real_guard(before, after, *args)
        with patch.object(emotion, '_guard', side_effect=add_attack):
            with self.assertRaises(model.ProjectError) as caught:
                call(original, ranges=[dict(start_tick=0, end_tick=1920)])
        self.assertEqual(caught.exception.code, 'PROTECTION_CONFLICT')

    def test_injected_outside_note_extension_across_protection_is_rejected(self):
        original = base(source(events=[(60, 0, 480), (64, 960, 480)], length=1440))
        before = copy.deepcopy(original)
        def extend(note, *args):
            return dict(copy.deepcopy(note), start_tick=0, duration_tick=700)
        with patch.object(emotion, '_change_note', side_effect=extend):
            with self.assertRaises(model.ProjectError) as caught:
                call(original, ranges=[dict(start_tick=600, end_tick=800)])
        self.assertEqual(caught.exception.code, 'PROTECTION_CONFLICT')
        self.assertEqual(original, before)

    def test_injected_ancestry_change_is_rejected_even_outside_protection(self):
        original = base()
        def corrupt(note, *args):
            return dict(copy.deepcopy(note), pitch=note['pitch'] + 1, origin=None)
        with patch.object(emotion, '_change_note', side_effect=corrupt):
            with self.assertRaises(model.ProjectError) as caught:
                call(original)
        self.assertEqual(caught.exception.code, 'PROTECTION_CONFLICT')

    def test_forged_clipped_unknown_and_wrong_ancestry_protection_is_rejected(self):
        original = base(); protected = absolute(original['notes'][3], 1000)
        cases = [dict(protected, start_tick=2920, duration_tick=180), dict(protected, id='missing'),
                 dict(protected, pitch=66), dict(protected, lineage=['wrong']), dict(protected, slice=None, origin=None),
                 dict(protected, velocity=True)]
        for supplied in cases:
            with self.subTest(supplied=supplied), self.assertRaises(model.ProjectError) as caught:
                call(original, start=1000, protected=[supplied])
            self.assertEqual(caught.exception.code, 'PROTECTION_CONFLICT')
        with self.assertRaises(model.ProjectError):call(original, start=1000, protected=[protected, protected])

    def test_all_protected_and_pure_rest_have_honest_limitation_records(self):
        original = base()
        for name in model.EMOTIONS:
            result = call(original, name, protected=[absolute(n) for n in original['notes']], ranges=[dict(start_tick=0, end_tick=4080)])
            self.assertFalse(result['generation']['melody_changed'])
            self.assertIn('FULLY_PROTECTED', [w['code'] for w in result['generation']['warnings']])
            self.assertEqual([structural(n) for n in result['notes']], [structural(n) for n in original['notes']])
        rest = base(); rest['notes'] = []
        result = call(rest, 'crisis')
        self.assertEqual(result['notes'], [])
        self.assertFalse(result['generation']['melody_changed'])
        self.assertEqual(result['generation']['warnings'][0]['code'], 'PURE_REST')

    def test_ranges_outside_material_are_immutable_and_canonical(self):
        original = base()
        ranges = [dict(start_tick=9000, end_tick=10000), dict(start_tick=0, end_tick=120), dict(start_tick=120, end_tick=240)]
        before = copy.deepcopy(ranges)
        result = call(original, ranges=ranges)
        reordered = call(original, ranges=list(reversed(ranges)))
        self.assertEqual(result, reordered)
        self.assertEqual(ranges, before)
        self.assertEqual(call(original), call(original, ranges=[]))

    def test_protected_notes_without_ranges_preserve_note_without_guessing_range(self):
        original = base(); protected = [absolute(original['notes'][0])]
        result = call(original, protected=protected)
        self.assertEqual(result['generation']['protection']['ranges'], [])
        self.assertEqual(structural(result['notes'][0]), structural(original['notes'][0]))

    def test_any_base_note_inside_range_is_frozen_even_if_not_self_declared(self):
        original = base()
        result = call(original, 'crisis', ranges=[dict(start_tick=0, end_tick=4080)])
        self.assertFalse(result['generation']['melody_changed'])
        self.assertEqual([structural(n) for n in result['notes']], [structural(n) for n in original['notes']])

    def test_bridge_requires_complete_existing_protection_and_never_changes_melody(self):
        bridge = base(); bridge['kind'] = 'bridge'
        for protected, ranges in [([], []), ([absolute(n) for n in bridge['notes']], []),
                                  ([], [dict(start_tick=0, end_tick=4080)])]:
            with self.assertRaises(model.ProjectError) as caught:
                call(bridge, 'crisis', protected=protected, ranges=ranges)
            self.assertEqual(caught.exception.code, 'PROTECTION_CONFLICT')
        result = call(bridge, 'crisis', protected=[absolute(n) for n in bridge['notes']], ranges=[dict(start_tick=0, end_tick=4080)])
        self.assertEqual([structural(n) for n in result['notes']], [structural(n) for n in bridge['notes']])
        self.assertFalse(result['generation']['melody_changed'])

    def test_nested_existing_bridge_keeps_full_protection(self):
        leaf = base(source(events=[(60, 0, 240), (64, 240, 240)], length=480))
        bridge = copy.deepcopy(leaf); bridge['id'] = 'bridge'; bridge['kind'] = 'bridge'
        combo = combination('combo', [bridge, leaf])
        with self.assertRaises(model.ProjectError):call(combo)
        protected = [absolute(n) for n in combo['notes'][:2]]
        result = call(combo, protected=protected, ranges=[dict(start_tick=0, end_tick=480)])
        self.assertEqual([structural(n) for n in result['notes'][:2]], [structural(n) for n in combo['notes'][:2]])


class EdgeAndFailureTests(unittest.TestCase):
    def test_edge_pitch_short_notes_and_inadequate_material_report_truthfully(self):
        for pitch in (0, 127):
            src = source(events=[(pitch, 0, 1)], length=1); original = base(src)
            for name in model.EMOTIONS:
                result = call(original, name)
                model.material_check(result, {src['id']: src})
                self.assertEqual(result['notes'][0]['duration_tick'], 1)
                if not result['generation']['melody_changed']:
                    self.assertTrue(result['generation']['warnings'])
        result = call(base(source(events=[(0, 0, 1)], length=1)), 'sad')
        self.assertEqual(result['generation']['warnings'][0]['code'], 'NO_LEGAL_MELODIC_CHANGE')

    def test_invalid_input_is_structured_and_never_mutates_base(self):
        original = base(); before = copy.deepcopy(original)
        cases = [dict(emotion='unknown'), dict(seed=True), dict(start_tick=-1),
                 dict(parameters={'max_changes': True}), dict(parameters={'max_pitch_shift': 99}),
                 dict(parameters={'unknown': 1}), dict(protected_ranges=[dict(start_tick=10, end_tick=10)]),
                 dict(intensity_points=[]), dict(intensity_points=points(float('nan'))),
                 dict(intensity_points=[dict(tick=0, level=.5), dict(tick=0, level=.5)]),
                 dict(intensity_points=points(end=100))]
        defaults = dict(emotion='hope', intensity_points=points(), start_tick=0, protected_notes=[])
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(model.ProjectError):
                emotion.emotion_variant(original, **dict(defaults, **changes))
            self.assertEqual(original, before)
        bad = copy.deepcopy(original); bad['notes'][1]['start_tick'] = 241
        with self.assertRaises(model.ProjectError):call(bad)

    def test_generated_slice_changes_clear_old_emission_but_protected_slice_does_not(self):
        original = melody.split_phrase(base())[1]
        protected = [absolute(original['notes'][0])]
        result = call(original, 'hope', protected=protected)
        self.assertEqual(structural(result['notes'][0]), structural(original['notes'][0]))
        by_id = {n['id']: n for n in original['notes']}
        for note in result['notes']:
            if note['id'] not in by_id:
                self.assertIsNone(note['slice'])
                self.assertTrue(set(note['lineage']) & set(by_id))

    def test_varied_notes_stay_single_voice_deterministic_and_traceable(self):
        rng = random.Random(508)
        for case in range(12):
            events = []; cursor = rng.randrange(10)
            for _ in range(rng.randrange(1, 7)):
                duration = rng.choice((1, 37, 120, 239, 300))
                events.append((rng.choice((0, 60, 64, 67, 127)), cursor, duration))
                cursor += duration + rng.choice((0, 120, 240))
            src = source(str(case), events, events[-1][1] + events[-1][2]); original = base(src)
            for name in model.EMOTIONS:
                result = call(original, name, seed=case)
                self.assertEqual(result, call(original, name, seed=case))
                model.material_check(result, {src['id']: src})
                self.assertTrue(all(a['start_tick'] + a['duration_tick'] <= b['start_tick'] for a, b in zip(result['notes'], result['notes'][1:])))
                self.assertEqual(result['length_ticks'], original['length_ticks'])
                self.assertEqual(len(result['notes']), len(original['notes']))


if __name__ == '__main__':
    unittest.main()
