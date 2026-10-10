"""Lossless fact compaction must not weaken musical or editing guarantees."""
import copy
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import curve_copy
import curve_frozen as frozen
import curve_graph as graph
import curve_json
import curve_project as m
import curve_recommendations as rec
import curve_bridges as bridge
import curve_connections as connection
from test_curve_bridges import complete, decision
from test_curve_connections import ready_bridge, begin
from test_curve_final import simulated_render


class FrozenFactsTests(unittest.TestCase):
    def test_canonical_bytes_digests_and_edit_detection(self):
        original = {'notes': [{'pitch': 60, 'level': -0.0}], 'text': '情绪🎵',
                    'values': [1e-7, 1e16, 2**100, True, None]}
        expected = m.canonical_bytes(original)
        for encoder in ('auto', 'stdlib'):
            with patch.dict(os.environ, {'EMOBLOCKS_JSON_ENCODER': encoder}), frozen.scope():
                first = frozen.freeze(original)
                self.assertEqual(m.canonical_bytes(first), expected)
                self.assertEqual(m.digest('facts', first), m.digest('facts', original))
                self.assertIs(first, frozen.freeze(copy.deepcopy(original)))
                original['notes'][0]['pitch'] += 1
                second = frozen.freeze(original)
                self.assertNotEqual(m.digest('facts', first), m.digest('facts', second))
                self.assertEqual(first['notes'][0]['pitch'], original['notes'][0]['pitch']-1)
                expected = m.canonical_bytes(original)

    def test_interned_equal_children_expand_to_independent_editable_containers(self):
        for copier in ('auto', 'stdlib'):
            with patch.dict(os.environ, {'EMOBLOCKS_JSON_COPY': copier}), frozen.scope():
                view = frozen.freeze({'records': [], 'notes': [], 'snapshots': [{}, {}]})
                self.assertIs(view['records'], view['notes'])
                with self.assertRaises(TypeError): view['records'].append(1)
                with self.assertRaises(TypeError): view['snapshots'][0]['new'] = 1
                for result in (frozen.thaw(view), curve_copy.deepcopy(view)):
                    self.assertIs(type(result), dict)
                    result['records'].append('undo')
                    result['snapshots'][0]['changed'] = True
                    self.assertEqual(result['notes'], [])
                    self.assertEqual(result['snapshots'][1], {})
                    self.assertEqual(view['records'], [])

    def test_ordinary_aliases_cycles_and_custom_hooks_keep_deepcopy_behavior(self):
        shared = []; value = {'a': shared, 'b': shared}; value['self'] = value
        result = curve_copy.deepcopy(value)
        self.assertIs(result['a'], result['b'])
        self.assertIs(result, result['self'])
        self.assertIsNot(result, value)

    def test_tuple_and_old_native_fallback_expand_interned_siblings_independently(self):
        with frozen.scope():
            child = frozen.freeze([])
            for native in (curve_json._native, SimpleNamespace(clone=lambda value: (_ for _ in ()).throw(TypeError()))):
                with patch.object(curve_json, '_native', native):
                    result = curve_copy.deepcopy({'siblings': (child, child)})
                    self.assertIs(type(result['siblings']), tuple)
                    result['siblings'][0].append('changed')
                    self.assertEqual(result['siblings'][1], [])


class StoredGraphTests(unittest.TestCase):
    def fixture(self):
        facts = [{'id': str(i), 'pitch': 60+i%12, 'notes': [i, i+1]} for i in range(80)]
        return {'current': facts, 'snapshot': copy.deepcopy(facts), 'audit': copy.deepcopy(facts),
                'numbers': [True, 1, 1.0, -0.0, 0.0, 1e-7, 2**100]}

    def test_roundtrip_exact_values_and_no_edit_aliases_native_and_fallback(self):
        value = self.fixture(); text = graph.dumps(value)
        self.assertEqual(json.loads(text)['schema'], graph.SCHEMA)
        self.assertLess(len(text), len(m.canonical(value)))
        for native in (curve_json._native, None):
            with patch.object(curve_json, '_native', native):
                result = graph.loads(text)
                self.assertEqual(m.canonical_bytes(result), m.canonical_bytes(value))
                result['current'][0]['notes'].append(999)
                self.assertEqual(result['snapshot'][0]['notes'], [0, 1])
                self.assertEqual(result['audit'][0]['notes'], [0, 1])

    def test_plain_current_json_still_reads_and_small_values_stay_plain(self):
        value = self.fixture()
        self.assertEqual(graph.loads(json.dumps(value)), value)
        self.assertEqual(graph.loads(graph.dumps({'a': [1, 2]})), {'a': [1, 2]})
        self.assertNotIn('schema', json.loads(graph.dumps({'a': [1, 2]})))

    def test_corrupt_graphs_rejected_before_native_expansion(self):
        valid = {'schema': graph.SCHEMA, 'root': 1,
                 'nodes': [[1, [[0, 1]]], [1, [[1, 0]]]]}
        mutations = []
        for mutate in (
            lambda v: v.update(root=True),
            lambda v: v.update(extra=1),
            lambda v: v['nodes'][0][1].append([1, 1]),
            lambda v: v['nodes'][1][1].clear(),
            lambda v: v['nodes'][0][1].append([0, {}]),
            lambda v: v['nodes'][0][1].append([0, float('nan')]),
            lambda v: v['nodes'][0].__setitem__(0, True),
        ):
            damaged = copy.deepcopy(valid); mutate(damaged); mutations.append(damaged)
        duplicate = {'schema': graph.SCHEMA, 'root': 0,
                     'nodes': [[0, [['x', [0, 1]], ['x', [0, 2]]]]]}
        mutations.append(duplicate)
        for damaged in mutations:
            with self.subTest(damaged=damaged), self.assertRaises(ValueError): graph.unpack(damaged)

    def test_expansion_bomb_and_depth_bound_rejected_without_allocation(self):
        nodes = [[1, [[0, 'x']]]]
        for i in range(30): nodes.append([1, [[1, i], [1, i]]])
        with self.assertRaisesRegex(ValueError, 'size/depth'):
            graph.unpack(dict(schema=graph.SCHEMA, root=len(nodes)-1, nodes=nodes))
        nodes = [[1, []]]
        for i in range(201): nodes.append([1, [[1, i]]])
        with self.assertRaisesRegex(ValueError, 'size/depth'):
            graph.unpack(dict(schema=graph.SCHEMA, root=len(nodes)-1, nodes=nodes))
        with patch.object(graph, 'MAX_BYTES', 100), self.assertRaises(ValueError):
            graph.dumps(self.fixture())


class EmptyTransitionTests(unittest.TestCase):
    def test_full_none_pipeline_skips_composers_but_keeps_boundary_and_music(self):
        controller = complete()
        captured = controller.capture_recommendations(parameters={
            'bridge_parameters': {'policy': 'none'}, 'connection_parameters': {'policy': 'none'}})
        import curve_final_render as audio
        import curve_final as final
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(audio, 'render', side_effect=simulated_render(directory)), \
                patch('curve_workflow.generate_bridges', side_effect=AssertionError('empty composer')), \
                patch('story_engine.generate_connection_request', side_effect=AssertionError('empty composer')), \
                patch.object(final, 'apply_boundaries', wraps=final.apply_boundaries) as boundaries:
            result = rec.prepare_recommendations(captured['request'])
            self.assertEqual(result['status'], 'INSUFFICIENT')  # Complete input has one valid proposal.
            self.assertEqual(result['failures'], [])
            self.assertEqual(len(result['candidates']), 1)
            self.assertGreater(boundaries.call_count, 0)
            self.assertTrue(controller.finish_recommendations(captured['token'], result))

    def test_bridge_none_still_authenticated_registered_and_cancelable(self):
        controller = complete(); before = controller.project
        cap = controller.capture_bridge(algorithm_version=bridge.ALGORITHM)
        plan = controller.lock_bridge(cap['token'], decision(cap['request']))
        controller.begin_bridge_generation(cap['token'], plan)
        raw = rec._empty_raw(bridge, cap['request'], plan, None)
        bridge.validate_raw(cap['request'], plan, raw)
        self.assertTrue(controller.finish_bridge(cap['token'], raw))
        self.assertEqual(controller.bridge_state()['status'], 'READY')
        self.assertEqual(controller.project, before)
        cancelled = rec._empty_raw(bridge, cap['request'], plan, lambda: True)
        bridge.validate_raw(cap['request'], plan, cancelled)
        self.assertEqual(cancelled['status'], 'CANCELLED')
        changed = copy.deepcopy(plan); changed['version'] += 1
        with self.assertRaises(m.ProjectError): rec._empty_raw(bridge, cap['request'], changed, None)

    def test_empty_connection_preserves_notes_and_protection(self):
        controller = ready_bridge(); cap, plan = begin(controller, ())
        raw = rec._empty_raw(connection, cap['request'], plan, None)
        connection.validate_raw(cap['request'], plan, raw)
        self.assertTrue(controller.finish_connection(cap['token'], raw))
        self.assertEqual(controller.connection_state()['outcome']['notes'], cap['request']['actual_layout']['notes'])
        cancelled = rec._empty_raw(connection, cap['request'], plan, lambda: True)
        connection.validate_raw(cap['request'], plan, cancelled)

    def test_actual_windows_and_inherited_bridge_cannot_use_empty_shortcut(self):
        for manual, ranges in ((False, ((1920, 3840),)), (True, ())):
            controller = complete(manual=manual)
            cap = controller.capture_bridge(algorithm_version=bridge.ALGORITHM)
            plan = controller.lock_bridge(cap['token'], decision(cap['request'], ranges))
            with self.assertRaises(m.ProjectError): rec._empty_raw(bridge, cap['request'], plan, None)
        controller = ready_bridge(); cap, plan = begin(controller)
        with self.assertRaises(m.ProjectError): rec._empty_raw(connection, cap['request'], plan, None)
