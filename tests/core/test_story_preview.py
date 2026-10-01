"""Exercise automatic preview through the real, hidden Tk page and app poll.

Only the debounce clock is replaced. The real background planner, music plan,
page callbacks, and application poll cooperate without sleeps or audio output.
"""

import copy
import threading
import tkinter as tk
import unittest
from unittest.mock import patch

from auto_preview import PreviewPlanner
import emotion_input
import story_engine as engine
from test_auto_preview import FakeScheduler
from unified_ui import UnifiedApp


class StoryPreviewTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.scheduler = FakeScheduler()
        self.compute = engine.plan
        self.gates = []
        self.accepted_projects = []
        self.addCleanup(self.cleanup)

        def planner(schedule, cancel, compute, on_result, on_error, delay=180):
            def receive(result):
                self.accepted_projects.append(copy.deepcopy(result['project']))
                on_result(result)

            return PreviewPlanner(
                self.scheduler.schedule, self.scheduler.cancel,
                lambda snapshot: self.compute(snapshot), receive, on_error, delay,
            )

        with patch('story_ui.PreviewPlanner', side_effect=planner):
            self.app = UnifiedApp(self.root)
        self.page = self.app.story_page
        self.root.update_idletasks()
        self.original = copy.deepcopy(self.page.project)

    def cleanup(self):
        for gate in self.gates:
            gate.set()
        if hasattr(self, 'page'):
            planner = self.page.preview_planner
            planner.close()
            if planner._worker is not None:
                planner._worker.join(5)
                self.assertFalse(planner._worker.is_alive())
            self.page.cancel_drag()
        if hasattr(self, 'app'):
            self.root.after_cancel(self.app.timer)
        self.root.destroy()

    def finish_worker(self):
        worker = self.page.preview_planner._worker
        self.assertIsNotNone(worker, 'No automatic preview was scheduled')
        worker.join(5)
        self.assertFalse(worker.is_alive(), 'Automatic preview did not finish')

    def poll_app(self):
        # Avoid accumulating real recurring timers when invoking the poll by hand.
        self.root.after_cancel(self.app.timer)
        self.app.poll()

    def complete_preview(self):
        self.scheduler.advance(180)
        self.finish_worker()
        self.poll_app()
        self.assertIsNotNone(self.page.planned, self.page.message.get())
        self.assertEqual(self.page.planned['project'], self.page.project)

    def test_initial_page_automatically_displays_a_plan_without_user_action(self):
        self.assertIsNone(self.page.planned)
        self.assertEqual(self.page.preview_status, '更新中')
        self.assertEqual(len(self.scheduler.pending), 1)
        self.complete_preview()
        self.assertEqual(self.page.preview_status, '')
        self.assertEqual(self.page.project, self.original)
        self.assertEqual(self.page.history, [])
        self.assertEqual(len(self.page.planned['blocks']), 13)
        self.assertEqual(
            list(self.page.blocks.get_children()),
            [block['id'] for block in self.page.planned['blocks']],
        )
        self.assertEqual(self.scheduler.pending, {})

    def test_committing_and_undoing_edits_both_refresh_the_automatic_plan(self):
        self.complete_preview()
        original_count = len(self.page.planned['blocks'])
        self.page.resize_timeline(1)
        self.assertIsNone(self.page.planned)
        self.assertEqual(self.page.preview_status, '更新中')
        self.assertEqual(len(self.page.history), 1)
        self.complete_preview()
        self.assertEqual(len(self.page.planned['blocks']), original_count + 1)
        self.assertGreater(self.page.planned['project']['duration'],
                           self.original['duration'])
        self.page.undo()
        self.assertIsNone(self.page.planned)
        self.complete_preview()
        self.assertEqual(self.page.project, self.original)
        self.assertEqual(len(self.page.planned['blocks']), original_count)
        self.assertEqual(self.page.history, [])

    def test_preview_does_not_dirty_project_or_change_saved_audio_history(self):
        self.app.dirty = False
        self.app.results = [dict(mode='saved', report=dict(
            output_directory='unchanged-history', duration_seconds=27, bars=13,
        ))]
        history_object = self.app.results
        history_snapshot = copy.deepcopy(history_object)
        self.app.result_list.insert('end', 'previous audio')
        self.app.result_list.selection_set(0)
        self.app.result_block.configure(values=('old block 1', 'old block 2'))
        self.app.result_block.current(1)
        self.page.input_blocks.selection_set('2')
        self.complete_preview()
        self.assertFalse(self.app.dirty)
        self.assertIs(self.app.results, history_object)
        self.assertEqual(self.app.results, history_snapshot)
        self.assertEqual(self.app.result_list.curselection(), (0,))
        self.assertEqual(self.app.result_block.current(), 1)
        self.assertEqual(self.app.result_block['values'], ('old block 1', 'old block 2'))
        self.assertEqual(self.page.input_blocks.selection(), ('2',))
        self.assertEqual(self.page.project, self.original)
        self.assertEqual(self.page.history, [])
        self.assertFalse(self.app.busy)

    def test_restoring_during_calculation_never_displays_the_old_engine_result(self):
        entered = threading.Event()
        release = threading.Event()
        self.gates.append(release)
        old_duration = self.original['duration']

        def compute(project):
            if project['duration'] == old_duration:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('Test did not release the old calculation')
            return engine.plan(project)

        self.compute = compute
        self.scheduler.advance(180)
        self.assertTrue(entered.wait(5))
        restored = emotion_input.resize_blocks(self.original, 1)
        self.page.restore(restored)
        self.scheduler.advance(180)
        release.set()
        self.finish_worker()
        self.poll_app()
        self.assertIsNone(self.page.planned)
        self.assertEqual(self.accepted_projects, [])
        self.finish_worker()
        self.poll_app()
        self.assertEqual(self.page.planned['project'], self.page.project)
        self.assertEqual(self.accepted_projects, [self.page.project])
        self.assertEqual(self.page.history, [])

    def test_removing_last_source_invalidates_an_already_computed_result(self):
        self.scheduler.advance(180)
        self.finish_worker()
        self.page.remove_source()
        self.assertEqual(self.page.project['sources'], [])
        self.assertEqual(self.page.preview_status, '导入旋律后显示来源')
        self.poll_app()
        self.assertIsNone(self.page.planned)
        self.assertEqual(self.accepted_projects, [])
        self.assertEqual(self.scheduler.pending, {})
        self.page.undo()
        self.complete_preview()
        self.assertEqual(self.page.project, self.original)

    def test_failed_preview_keeps_project_and_recovers_on_the_next_edit(self):
        def fail(project):
            raise ValueError('test preview unavailable')

        self.compute = fail
        self.app.dirty = False
        self.scheduler.advance(180)
        self.finish_worker()
        self.poll_app()
        self.assertIsNone(self.page.planned)
        self.assertEqual(self.page.preview_status, '暂不可用')
        self.assertIn('test preview unavailable', self.page.message.get())
        self.assertEqual(self.page.project, self.original)
        self.assertEqual(self.page.history, [])
        self.assertFalse(self.app.dirty)
        self.compute = engine.plan
        self.page.resize_timeline(1)
        self.complete_preview()
        self.assertEqual(self.page.preview_status, '')
        self.assertNotIn('test preview unavailable', self.page.message.get())


if __name__ == '__main__':
    unittest.main()
