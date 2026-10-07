"""Actual mapped widgets with fault-controlled providers; no claim of real audio."""
import copy
import threading
from unittest.mock import patch
from test_curve_ui import MappedUIFixture
import curve_ui


class PlaybackIntentTests(MappedUIFixture):
    def click(self, widget):
        self.root.update();widget.event_generate('<ButtonPress-1>',x=8,y=8)
        widget.event_generate('<ButtonRelease-1>',x=8,y=8);self.root.update()

    def start_waiting(self):
        self.provider.gate=threading.Event()
        self.app.select_target('material','block')
        self.click(self.app.play_button)
        self.assertTrue(self.app.jobs)
        self.assertEqual(self.app.player.calls,[])
        job=next(iter(self.app.jobs.values()))
        self.assertEqual(self.app.play_intent.current['token'],job['token'])
        return job

    def test_selection_is_not_an_audition_then_one_button_prepares_and_plays(self):
        card=self.app.page.cards.rows['block']
        card.event_generate('<ButtonPress-1>',x=10,y=14)
        card.event_generate('<ButtonRelease-1>',x=10,y=14);self.root.update()
        self.assertEqual(self.app.selected_target,('material','block'))
        self.assertEqual(self.app.player.calls,[])
        before=self.controller.state()['project']
        self.click(self.app.play_button);self.finish_jobs()
        self.assertEqual(len(self.app.player.calls),1)
        self.assertEqual(before,self.controller.state()['project'])
        self.assertIsNone(self.app.play_intent.current)

    def test_stop_keeps_backend_token_valid_and_cache_but_rejects_late_play(self):
        job=self.start_waiting()
        self.click(self.app.stop_button)
        self.assertTrue(self.controller.accepts(job['token']))
        self.provider.gate.set();self.finish_jobs()
        self.assertTrue(self.app.ready_assets)
        self.assertEqual(self.app.player.calls,[])
        self.click(self.app.play_button);self.assertEqual(len(self.app.player.calls),1)
        self.assertFalse(self.app.jobs)

    def test_changed_selection_rejects_valid_backend_result_without_stealing_play(self):
        job=self.start_waiting();self.app.select_target('material','phrase')
        self.assertTrue(self.controller.accepts(job['token']))
        self.provider.gate.set();self.finish_jobs()
        self.assertTrue(self.app.ready_assets);self.assertEqual(self.app.player.calls,[])
        self.assertEqual(self.app.selected_target,('material','phrase'))

    def test_mode_change_cancels_intent_without_cancelling_source_job(self):
        job=self.start_waiting();self.app.recommendation.mode.set('情绪编配')
        self.app.recommendation.mode_changed()
        self.assertTrue(self.controller.accepts(job['token']))
        self.provider.gate.set();self.finish_jobs();self.assertEqual(self.app.player.calls,[])

    def test_cancel_edit_undo_same_content_cannot_restore_old_intent(self):
        before=copy.deepcopy(self.controller.state()['project']);job=self.start_waiting()
        self.click(self.app.cancel_button)
        self.app.edit('place',material_id='block',start_tick=0);self.app.undo()
        self.assertEqual(before,self.controller.state()['project'])
        self.provider.gate.set()
        self.app.messages.put((job['token'],True,self.provider.render_audition(job['snapshot']['target'])))
        self.app.drain_jobs();self.assertEqual(self.app.player.calls,[])
        self.assertIsNone(self.app.play_intent.current)

    def test_new_audition_supersedes_previous_and_thread_start_failure_clears_busy(self):
        old=self.start_waiting();self.app.audition_target('material','phrase')
        current=next(iter(self.app.jobs.values()))
        self.assertNotEqual(old['token'],current['token'])
        self.provider.gate.set()
        self.app.messages.put((old['token'],True,self.provider.render_audition(old['snapshot']['target'])))
        self.finish_jobs();self.assertEqual(len(self.app.player.calls),1)
        self.assertEqual(self.app.playing_target['target'],('material','phrase'))
        self.app.stop();self.app.ready_assets.clear();self.app.ready_file_digests.clear()
        before=self.controller.state()['project']
        with patch('curve_ui.threading.Thread.start',side_effect=RuntimeError('start failed')):
            self.app.audition_target('material','block')
        self.assertFalse(self.app.jobs);self.assertIsNone(self.app.play_intent.current)
        self.assertEqual(before,self.controller.state()['project'])
        self.assertIsNone(self.app.playing_target)

    def test_combo_cancel_is_inert_and_fresh_explicit_combo_audition_uses_shared_player(self):
        before=copy.deepcopy(self.controller.state()['project'])
        self.app.add_combo(self.app.resolve('material','block'),'phrase','left')
        self.click(self.app.page.combo_panel.winfo_children()[-1].winfo_children()[-1])
        self.assertEqual(before,self.controller.state()['project']);self.assertFalse(self.app.combo_inputs)
        self.app.add_combo(self.app.resolve('material','block'),'phrase','right')
        self.app.audition_combo();self.finish_jobs()
        self.assertEqual(len(self.app.player.calls),1);self.assertEqual(before,self.controller.state()['project'])

    def test_profile_or_file_changed_cache_does_not_play_or_delete_output(self):
        self.app.select_target('material','block');self.app.prepare_selected();self.finish_jobs()
        self.wav.write_bytes(self.wav.read_bytes()+b'changed')
        self.assertFalse(self.app.play_selected());self.assertTrue(self.wav.exists())
        self.assertEqual(self.app.player.calls,[])

    def test_a_b_a_and_duplicate_delivery_cannot_revive_consumed_intent(self):
        job=self.start_waiting()
        self.app.select_target('material','phrase');self.app.select_target('material','block')
        self.provider.gate.set();self.finish_jobs()
        self.assertEqual(self.app.player.calls,[])
        self.app.audition_selected();self.assertEqual(len(self.app.player.calls),1)
        self.app.messages.put((job['token'],True,self.provider.render_audition(job['snapshot']['target'])))
        self.app.drain_jobs();self.assertEqual(len(self.app.player.calls),1)

    def test_changed_draft_name_invalidates_pending_audition(self):
        self.app.add_combo(self.app.resolve('material','block'),'phrase','left')
        self.provider.gate=threading.Event();self.app.audition_combo()
        self.app.page.combo_name.set('改名后的草稿')
        self.provider.gate.set();self.finish_jobs()
        self.assertTrue(self.app.ready_assets);self.assertEqual(self.app.player.calls,[])
