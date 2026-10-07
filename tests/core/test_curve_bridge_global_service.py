"""Global positioning keeps existing transaction and pure restore guarantees."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import curve_bridges as bridges
import curve_bridge_music as music
import curve_phrase_analysis as analysis
import curve_project as model
import curve_store as store
import curve_workflow as workflow
import curve_recommendations as recommendations
import curve_final_render as final_audio
from test_curve_bridge_music import fixture


class GlobalBridgeServiceTests(unittest.TestCase):
    def controller(self):
        return workflow.Controller(fixture(4))

    def test_new_capture_and_public_route_bind_global_algorithm(self):
        controller = self.controller()
        before = controller.project
        captured = controller.capture_bridge(parameters={'policy': 'none'})
        request = captured['request']
        self.assertEqual(request['algorithm_version'], bridges.GLOBAL_ALGORITHM)
        self.assertEqual(request['contract_rev'], bridges.REV)
        self.assertEqual(request['base_notes'], bridges.actual_notes(before))
        proposal = workflow.decide_bridge(request)
        self.assertIsNone(proposal['search']['analysis'])
        self.assertEqual(proposal['search']['termination'], 'POLICY_NONE')
        plan = controller.lock_bridge(captured['token'], proposal)
        controller.begin_bridge_generation(captured['token'], plan)
        result = workflow.generate_bridges(request, plan)
        self.assertTrue(controller.finish_bridge(captured['token'], result))
        self.assertTrue(controller.bridge_state()['capabilities']['can_plan_connections'])
        self.assertEqual(controller.project, before)
        self.assertFalse(controller.session._undo)

    def test_forged_global_proof_cannot_register_half_plan(self):
        controller = self.controller()
        captured = controller.capture_bridge()
        proposal = music.decide(captured['request'])
        before = copy.deepcopy(controller._bundle)
        for mutation in ('missing_analysis', 'count', 'assessment'):
            invalid = copy.deepcopy(proposal)
            if mutation == 'missing_analysis':
                invalid['search']['analysis'] = None
            elif mutation == 'count':
                invalid['search']['tested_windows'] += 1
            else:
                self.assertTrue(invalid['assessments'])
                invalid['assessments'][0]['benefit'] += 1
            with self.subTest(mutation=mutation), self.assertRaises(model.ProjectError):
                controller.lock_bridge(captured['token'], invalid)
            self.assertEqual(controller._bundle, before)
            self.assertIsNone(controller._bridge_attempt(captured['attempt_id'])['bridge']['plan'])

    def test_lock_and_restore_authenticate_without_replanning(self):
        controller = self.controller()
        captured = controller.capture_bridge()
        proposal = music.decide(captured['request'])
        self.assertTrue(proposal['windows'])
        with patch.object(analysis, 'analyze', side_effect=AssertionError('restore analyzed again')), \
             patch.object(music, 'decide', side_effect=AssertionError('restore replanned')), \
             patch.object(music, 'generate', side_effect=AssertionError('restore generated')):
            plan = controller.lock_bridge(captured['token'], proposal)
            attempt = controller._bridge_attempt(captured['attempt_id'])
            self.assertTrue(attempt['protections'])
            self.assertEqual({p['status'] for p in attempt['protections'] if p['kind'] == 'bridge'}, {'RANGE_LOCKED'})
            self.assertEqual(attempt['bridge']['phase'], 'BRIDGE_LOCKED')
            with tempfile.TemporaryDirectory() as folder:
                path = controller.save_snapshot(Path(folder) / 'locked.json')
                restored = store.load(path)
                stage = restored['bundle']['attempts'][-1]
                self.assertEqual(stage['state'], 'INTERRUPTED')
                self.assertEqual(stage['bridge']['plan'], plan)
                self.assertEqual(stage['protections'], attempt['protections'])
                self.assertEqual(restored['bundle']['project'], controller.project)

    def test_cancel_then_undo_cannot_resurrect_global_request(self):
        controller = self.controller()
        captured = controller.capture_bridge()
        proposal = music.decide(captured['request'])
        plan = controller.lock_bridge(captured['token'], proposal)
        self.assertTrue(controller.cancel_bridge(captured['token']))
        before = controller.project
        controller.edit('set_intensity', points=[{'tick': 0, 'level': .4},
                                                 {'tick': before['total_ticks'], 'level': .4}])
        controller.undo()
        self.assertEqual(controller.project, before)
        self.assertFalse(controller.accepts(captured['token']))
        with self.assertRaises(model.ProjectError):
            controller.lock_bridge(captured['token'], proposal)
        self.assertEqual(controller._bridge_attempt(captured['attempt_id'])['bridge']['plan'], plan)

    def test_legacy_request_restore_keeps_its_original_grammar(self):
        controller = self.controller()
        captured = controller.capture_bridge(parameters={'policy': 'none'},
                                              algorithm_version=bridges.ALGORITHM)
        proposal = music.decide(captured['request'])
        self.assertEqual(set(proposal['search']), {'tested_windows', 'termination'})
        plan = controller.lock_bridge(captured['token'], proposal)
        controller.begin_bridge_generation(captured['token'], plan)
        controller.finish_bridge(captured['token'], music.generate(captured['request'], plan))
        with tempfile.TemporaryDirectory() as folder:
            path = controller.save_snapshot(Path(folder) / 'legacy.json')
            with patch.object(analysis, 'analyze', side_effect=AssertionError('legacy upgraded')), \
                 patch.object(music, 'decide', side_effect=AssertionError('legacy replanned')):
                restored = store.load(path)
        old = restored['bundle']['attempts'][-1]['bridge']
        self.assertEqual(old['request']['algorithm_version'], bridges.ALGORITHM)
        self.assertEqual(set(old['plan']['search']), {'tested_windows', 'termination'})
        self.assertEqual(old['plan'], plan)

    def test_recommendation_routes_global_and_applies_the_auditioned_score(self):
        # Renderer simulation authenticates transaction binding, not listening.
        from test_curve_bridges import complete
        from test_curve_final import simulated_render
        controller = complete()
        before = controller.project
        captured = controller.capture_recommendations(mode='melody_only')
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(final_audio, 'render', side_effect=simulated_render(folder)), \
             patch.object(workflow, 'decide_bridge', wraps=workflow.decide_bridge) as routed:
            outcome = recommendations.prepare_recommendations(captured['request'],
                source_facts=captured['source_facts'])
            self.assertTrue(outcome['candidates'], outcome['failures'])
            self.assertTrue(routed.call_args_list)
            self.assertTrue(all(call.args[0]['algorithm_version'] == bridges.GLOBAL_ALGORITHM
                                for call in routed.call_args_list))
            self.assertTrue(controller.finish_recommendations(captured['token'], outcome))
            candidate = outcome['candidates'][0]
            asset = controller.recommendation_asset(candidate['id'])
            self.assertEqual(controller.project, before)
            self.assertFalse(controller.session._undo)
            accepted = controller.apply_recommendation(candidate['id'],
                confirmation_ref=controller.confirmation_ref(candidate['id']))
            self.assertEqual(controller.history_asset(accepted['receipt']['result_id'])['score_ref'],
                             asset['score_ref'])
            after = controller.project
            with patch.object(music, 'generate', side_effect=AssertionError('redo regenerated')), \
                 patch.object(music, 'decide', side_effect=AssertionError('redo replanned')):
                controller.undo()
                self.assertEqual(controller.project, before)
                controller.redo()
                self.assertEqual(controller.project, after)


if __name__ == '__main__':
    unittest.main()
