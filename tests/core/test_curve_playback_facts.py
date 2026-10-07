"""Playback facts and drag previews never borrow live edit state or compose."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import curve_project as model
import curve_workflow as workflow
import curve_recommendations as rec
import curve_final as final
import curve_final_render as audio
from test_curve_bridges import complete
from test_curve_final import simulated_render


class PlaybackFactsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.controller = complete()
        capture = self.controller.capture_recommendations(mode='melody_only')
        with patch.object(audio, 'render', side_effect=simulated_render(self.tmp.name)):
            outcome = rec.prepare_recommendations(capture['request'], source_facts=capture['source_facts'])
        self.assertTrue(outcome['candidates'], outcome['failures'])
        self.controller.finish_recommendations(capture['token'], outcome)
        self.candidate = outcome['candidates'][0]

    def state(self):
        c = self.controller
        return copy.deepcopy((c.project, c._bundle, c.session._undo, c.session._redo,
                              c.session._revision, c.session._requests, c.state()['is_saved'], c._staging_dirty))

    def test_two_sides_are_exact_detached_saved_scores_and_pure(self):
        before = self.state()
        with patch('curve_bridge_music.decide', side_effect=AssertionError('replan')), \
             patch('curve_bridge_music.generate', side_effect=AssertionError('compose')), \
             patch.object(final, 'arrange', side_effect=AssertionError('arrange')), \
             patch.object(audio, 'render', side_effect=AssertionError('render')):
            views = [self.controller.recommendation_playback(self.candidate['id'], side)
                     for side in ('comparison', 'final')]
        for side, view in zip(('comparison', 'final'), views):
            score = rec.resolve(self.controller._bundle['final_facts'], self.candidate[side + '_score_ref'])
            self.assertEqual(view['score_ref'], final.ref(score))
            self.assertEqual(view['asset']['score_ref'], final.ref(score))
            self.assertEqual(view['notes'], score['notes'])
            self.assertEqual(view['target'], dict(kind='recommendation', id=self.candidate['id'],
                                                side=side, mode='melody_only'))
            view['notes'].clear()
            view['segments'].clear()
            view['asset']['files'].clear()
        self.assertNotEqual(views[0]['score_ref'], views[1]['score_ref'])
        self.assertEqual(self.state(), before)

    def test_history_after_edit_keeps_accepted_score_mapping(self):
        with patch('curve_store.data_root', return_value=Path(self.tmp.name)):
            accepted = self.controller.apply_recommendation(self.candidate['id'])
        result_id = accepted['receipt']['result_id']
        first = self.controller.history_playback(result_id)
        self.controller.edit('resize', grid_count=self.controller.project['grid_count'] + 1)
        self.assertEqual(self.controller.accepted_state()['status'], 'STALE')
        before = self.state()
        after = self.controller.history_playback(result_id)
        self.assertEqual(after, first)
        self.assertEqual(after['target']['id'], result_id)
        self.assertLess(after['total_ticks'], self.controller.project['total_ticks'])
        self.assertEqual(self.state(), before)

    def test_modes_and_missing_file_cannot_borrow_another_asset(self):
        with self.assertRaises(model.ProjectError):
            self.controller.recommendation_playback(self.candidate['id'], mode='arranged')
        with self.assertRaises(model.ProjectError):
            self.controller.recommendation_playback(self.candidate['id'], kind='unknown')
        view = self.controller.recommendation_playback(self.candidate['id'])
        Path(view['asset']['files']['wav']['path']).unlink()
        with self.assertRaises(model.ProjectError):
            self.controller.recommendation_playback(self.candidate['id'])
        # Missing final must not silently return still-valid comparison.
        self.assertEqual(self.controller.recommendation_playback(self.candidate['id'], 'comparison')['target']['side'], 'comparison')

    def test_legacy_unmapped_keeps_audio_without_invented_editor_navigation(self):
        asset = dict(wav_path=str(Path(self.tmp.name) / 'old.wav'), body_seconds=2, audio_seconds=3,
                     fingerprint='history:test')
        with patch.object(self.controller, 'history_asset', return_value=asset):
            view = self.controller.history_playback('history:test')
        self.assertFalse(view['mapping_available'])
        self.assertEqual(view['segments'], [])
        self.assertIsNone(view['notes'])
        self.assertEqual(view['asset'], asset)
        with self.assertRaises(model.ProjectError):
            self.controller.history_playback('history:test', 'arranged')


class PreviewEditTests(unittest.TestCase):
    def test_preview_matches_formal_gate_and_leaves_active_request_history_saved_intact(self):
        c = complete()
        c.session.mark_saved()
        captured = c.capture_job('AUDITION', dict(kind='material', id=c.project['materials'][0]['id']))
        before = copy.deepcopy((c.state(), c.session.__dict__, c._bundle, c._jobs))
        refused = c.preview_edit('resize', grid_count=1)
        self.assertFalse(refused['allowed'])
        self.assertTrue(refused['error']['message'])
        self.assertEqual((c.state(), c.session.__dict__, c._bundle, c._jobs), before)
        allowed = c.preview_edit('resize', grid_count=c.project['grid_count'] + 1)
        self.assertTrue(allowed['allowed'])
        self.assertTrue(allowed['changed'])
        self.assertTrue(c.accepts(captured['token']))
        self.assertEqual((c.state(), c.session.__dict__, c._bundle, c._jobs), before)
        # Preview does not grant permission against later changed state.
        c.edit('resize', grid_count=c.project['grid_count'] + 1)
        undo = copy.deepcopy(c.session._undo)
        with self.assertRaises(model.ProjectError):
            c.edit('resize', grid_count=1)
        self.assertEqual(c.session._undo, undo)

    def test_overlap_and_failed_official_recompute_are_not_preview_success(self):
        c = complete()
        first = c.project['placements'][0]
        before = copy.deepcopy((c.project, c.session._undo, c.session._redo))
        self.assertFalse(c.preview_edit('place', material_id=first['material_id'], start_tick=first['start_tick'])['allowed'])
        with patch.object(c.session, '_recompute', return_value=dict(automatic_memory=None, emotion_variants={})):
            self.assertFalse(c.preview_edit('resize', grid_count=c.project['grid_count'] + 1)['allowed'])
        self.assertEqual((c.project, c.session._undo, c.session._redo), before)
