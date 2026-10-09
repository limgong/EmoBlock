"""Acceleration must preserve bytes, invalid-input gates and task isolation."""
import copy
import hashlib
import json
import math
import os
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

import curve_json as codec
import curve_project as model
import curve_recommendations as recommendations
import curve_final_render as audio
from test_curve_bridges import complete
from test_curve_final import simulated_render


def standard(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class CanonicalEncodingTests(unittest.TestCase):
    def assert_same(self, value):
        expected = standard(value)
        self.assertEqual(model.canonical(value), expected)
        self.assertEqual(model.canonical_bytes(value), expected.encode('utf-8'))
        self.assertEqual(model.digest('fixed-domain', value), hashlib.sha256(('fixed-domain\n' + expected).encode()).hexdigest())

    def test_fixed_vectors_and_float_spelling(self):
        values = [None, True, False, 0, -1, 2**64-1, 2**100, 0.0, -0.0,
                  1e-7, 1e-5, 1e16, 1e308, 5e-324, math.pi,
                  '情绪🎵\u2028\u2029\x00\b\f\n\r\t\\"/',
                  {'🎵': 1, '情绪': 2, 'a': [None, .3, (4, -0.0)]},
                  {1: 'one', 2: 'two'}]
        for value in values:
            with self.subTest(value=value): self.assert_same(value)

    def test_random_finite_double_values_have_identical_bytes(self):
        generator = random.Random(1979)
        values = [struct.unpack('>d', generator.getrandbits(64).to_bytes(8, 'big'))[0] for _ in range(3000)]
        self.assert_same({'values': [value for value in values if math.isfinite(value)]})

    def test_nonfinite_cyclic_and_invalid_types_remain_rejected(self):
        cyclic = []; cyclic.append(cyclic)
        values = [float('nan'), float('inf'), -float('inf'), {'x': [float('nan')]},
                  cyclic, {1: 'one', 'two': 2}, {'x': {1, 2}}, object()]
        for value in values:
            with self.subTest(kind=type(value)), self.assertRaises(model.ProjectError) as error:
                model.canonical(value)
            self.assertEqual(error.exception.code, 'INVALID_PROJECT')
            with self.assertRaises(model.ProjectError): model.canonical_bytes(value)

    def test_deep_custom_and_surrogate_values_keep_standard_fallback(self):
        deep = 1
        for _ in range(220): deep = [deep]
        self.assert_same(deep)
        class CustomDict(dict): pass
        self.assert_same(CustomDict(x=1e-7))
        self.assertEqual(model.canonical('\ud800'), standard('\ud800'))
        with self.assertRaises(UnicodeEncodeError): model.digest('fixed-domain', '\ud800')

    def test_native_module_present_and_explicit_fallback(self):
        if codec._native is None: self.skipTest('optional compiled extension is not installed')
        with patch.dict(os.environ, {'EMOBLOCKS_JSON_ENCODER': 'auto'}):
            self.assertEqual(codec.encoder_name(), 'native')
            with patch.object(codec._native, 'dumps', wraps=codec._native.dumps) as native:
                self.assert_same({'level': 1e-7, 'name': '欢乐颂'})
                self.assertEqual(native.call_count, 3)
        with patch.dict(os.environ, {'EMOBLOCKS_JSON_ENCODER': 'stdlib'}), patch.object(codec._native, 'dumps', side_effect=AssertionError('must not run')):
            self.assertEqual(codec.encoder_name(), 'stdlib')
            self.assert_same({'level': 1e-7})
        with patch.object(codec, '_native', None): self.assert_same({'level': 1e-7})

    def test_shared_objects_and_later_edits_never_reuse_encoded_content(self):
        child = {'notes': [60], 'level': .5}; value = [child, child]
        self.assert_same(value); before = model.digest('edit', value)
        child['notes'][0] = 61
        self.assert_same(value); self.assertNotEqual(before, model.digest('edit', value))


class GenerationScopeTests(unittest.TestCase):
    def test_pure_cache_is_bounded_mutation_sensitive_and_returns_independent_values(self):
        calls = []
        def check(value):
            calls.append(copy.deepcopy(value))
            return {'validated': copy.deepcopy(value)}
        with model.validation_scope() as scope:
            value = {'pitch': 60}
            first = model.cached_validation(check, (value,), {}); first['validated']['pitch'] = 0
            self.assertEqual(model.cached_validation(check, (value,), {})['validated']['pitch'], 60)
            self.assertEqual(len(calls), 1)
            value['pitch'] = 61
            self.assertEqual(model.cached_validation(check, (value,), {})['validated']['pitch'], 61)
            self.assertEqual(len(calls), 2)
            for pitch in range(140): model.cached_validation(check, ({'pitch': pitch},), {})
            self.assertLessEqual(len(scope['native_checks']), 128)
        self.assertIsNone(model._VALIDATION_CONTEXT.get())

    def test_full_and_light_progress_preserve_music_and_release_each_task_scope(self):
        controller = complete(); captured = controller.capture_recommendations()
        events = []; scopes = []; results = []
        with tempfile.TemporaryDirectory() as directory, patch.object(audio, 'render', side_effect=simulated_render(directory)):
            for include in (True, False):
                received = []
                def progress(event):
                    received.append(event); scopes.append(model._VALIDATION_CONTEXT.get())
                result = recommendations.prepare_recommendations(captured['request'], on_progress=progress, include_stage_bundle=include)
                self.assertTrue(result['candidates'], result['failures'])
                self.assertTrue(all(('stage_bundle' in event) == include for event in received))
                self.assertTrue(all(scope is scopes[-1] for scope in scopes[-len(received):]))
                self.assertIsNone(model._VALIDATION_CONTEXT.get())
                events.append(received); results.append(result)
        self.assertEqual([(e['seq'], e['phase'], e['message']) for e in events[0]], [(e['seq'], e['phase'], e['message']) for e in events[1]])
        self.assertEqual([c['music_fingerprint'] for c in results[0]['candidates']], [c['music_fingerprint'] for c in results[1]['candidates']])
        self.assertEqual(results[0]['stage_bundle'], results[1]['stage_bundle'])
        self.assertIsNot(scopes[0], scopes[-1])

    def test_cancellation_and_exception_release_the_operation_scope(self):
        captured = complete().capture_recommendations()
        result = recommendations.prepare_recommendations(captured['request'], should_cancel=lambda: True, include_stage_bundle=False)
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertIsNone(model._VALIDATION_CONTEXT.get())
        changed = copy.deepcopy(captured['request']); changed['input_project']['bpm'] = 0
        with self.assertRaises(model.ProjectError): recommendations.prepare_recommendations(changed)
        self.assertIsNone(model._VALIDATION_CONTEXT.get())
