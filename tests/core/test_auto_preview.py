"""Deterministic scheduling tests: fake UI clock and explicit worker gates."""

import threading
import unittest

from auto_preview import PreviewPlanner


class FakeScheduler:
    def __init__(self):
        self.now = 0
        self.next_id = 0
        self.pending = {}

    def schedule(self, milliseconds, callback):
        self.next_id += 1
        self.pending[self.next_id] = (self.now + milliseconds, callback)
        return self.next_id

    def cancel(self, identifier):
        self.pending.pop(identifier, None)

    def advance(self, milliseconds):
        self.now += milliseconds
        while True:
            due = [(at, identifier, callback)
                   for identifier, (at, callback) in self.pending.items()
                   if at <= self.now]
            if not due:
                return
            _, identifier, callback = min(due)
            del self.pending[identifier]
            callback()


class PreviewPlannerTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = FakeScheduler()
        self.results = []
        self.errors = []
        self.planners = []
        self.gates = []

    def tearDown(self):
        for gate in self.gates:
            gate.set()
        for planner in self.planners:
            planner.close()
            if planner._worker is not None:
                planner._worker.join(2)
                self.assertFalse(planner._worker.is_alive())

    def planner(self, compute, on_result=None, on_error=None):
        planner = PreviewPlanner(
            self.scheduler.schedule, self.scheduler.cancel, compute,
            on_result or self.results.append, on_error or self.errors.append,
        )
        self.planners.append(planner)
        return planner

    def gate(self):
        gate = threading.Event()
        self.gates.append(gate)
        return gate

    def finish(self, planner):
        """Synchronize with completion; no timing assumption or busy polling."""
        self.assertIsNotNone(planner._worker)
        planner._worker.join(2)
        self.assertFalse(planner._worker.is_alive(), "Preview worker did not finish")

    def test_snapshot_is_independent_and_callbacks_only_run_in_poll(self):
        owner = threading.get_ident()
        compute_threads = []
        callback_threads = []

        def compute(snapshot):
            compute_threads.append(threading.get_ident())
            snapshot["values"].append(2)
            return snapshot

        def result(value):
            callback_threads.append(threading.get_ident())
            self.results.append(value)

        planner = self.planner(compute, on_result=result)
        project = {"values": [1]}
        planner.request(project)
        project["values"].append(99)
        self.scheduler.advance(179)
        self.assertEqual(compute_threads, [])
        self.scheduler.advance(1)
        self.assertTrue(planner._worker.daemon)
        self.finish(planner)
        self.assertEqual(self.results, [])
        planner.poll()
        self.assertEqual(self.results, [{"values": [1, 2]}])
        self.assertEqual(project, {"values": [1, 99]})
        self.assertNotEqual(compute_threads, [owner])
        self.assertEqual(callback_threads, [owner])
        planner.poll()
        self.assertEqual(len(self.results), 1)

    def test_repeated_edits_reset_debounce_and_compute_only_the_latest(self):
        calls = []
        planner = self.planner(lambda project: calls.append(project) or project)
        planner.request("first")
        old_callback = next(iter(self.scheduler.pending.values()))[1]
        self.scheduler.advance(100)
        planner.request("second")
        self.scheduler.advance(100)
        planner.request("latest")
        old_callback()  # Simulate cancellation racing with a dispatched timer.
        self.scheduler.advance(179)
        self.assertEqual(calls, [])
        self.assertEqual(len(self.scheduler.pending), 1)
        self.scheduler.advance(1)
        self.finish(planner)
        planner.poll()
        self.assertEqual(calls, ["latest"])
        self.assertEqual(self.results, ["latest"])

    def test_running_worker_coalesces_edits_and_never_overlaps_computation(self):
        entered = threading.Event()
        release = self.gate()
        calls = []

        def compute(project):
            calls.append(project)
            if project == "first":
                entered.set()
                self.assertTrue(release.wait(2))
            return project

        planner = self.planner(compute)
        planner.request("first")
        self.scheduler.advance(180)
        self.assertTrue(entered.wait(2))
        first_worker = planner._worker
        planner.request("discarded")
        self.scheduler.advance(180)
        planner.request("latest")
        self.scheduler.advance(180)
        planner.poll()
        self.assertIs(planner._worker, first_worker)
        self.assertEqual(calls, ["first"])
        release.set()
        self.finish(planner)
        planner.poll()
        self.assertEqual(self.results, [])
        self.finish(planner)
        planner.poll()
        self.assertEqual(calls, ["first", "latest"])
        self.assertEqual(self.results, ["latest"])

    def test_new_request_keeps_its_delay_when_previous_worker_finishes(self):
        release = self.gate()
        planner = self.planner(lambda project: release.wait(2) and project)
        planner.request("old")
        self.scheduler.advance(180)
        planner.request("new")
        release.set()
        self.finish(planner)
        planner.poll()
        self.assertIsNone(planner._worker)
        self.assertEqual(self.results, [])
        self.scheduler.advance(179)
        self.assertIsNone(planner._worker)
        self.scheduler.advance(1)
        self.finish(planner)
        planner.poll()
        self.assertEqual(self.results, ["new"])

    def test_invalidate_discards_late_result_and_allows_a_fresh_request(self):
        release = self.gate()
        planner = self.planner(lambda project: release.wait(2) and project)
        planner.request("old")
        self.scheduler.advance(180)
        planner.invalidate()
        release.set()
        self.finish(planner)
        planner.poll()
        self.assertEqual(self.results, [])
        planner.request("fresh")
        self.scheduler.advance(180)
        self.finish(planner)
        planner.poll()
        self.assertEqual(self.results, ["fresh"])

    def test_invalidate_cancels_pending_timer_and_queued_result(self):
        planner = self.planner(lambda project: project)
        planner.request("pending")
        late_callback = next(iter(self.scheduler.pending.values()))[1]
        planner.invalidate()
        self.assertEqual(self.scheduler.pending, {})
        late_callback()
        self.assertIsNone(planner._worker)
        planner.request("finished")
        self.scheduler.advance(180)
        self.finish(planner)
        planner.invalidate()
        planner.poll()
        self.assertEqual(self.results, [])

    def test_current_exception_reaches_error_callback_on_ui_thread(self):
        failure = ValueError("unusable source")
        callback_threads = []

        def compute(project):
            raise failure

        def error(exception):
            self.errors.append(exception)
            callback_threads.append(threading.get_ident())

        planner = self.planner(compute, on_error=error)
        planner.request({})
        self.scheduler.advance(180)
        self.finish(planner)
        self.assertEqual(self.errors, [])
        planner.poll()
        self.assertEqual(self.errors, [failure])
        self.assertEqual(callback_threads, [threading.get_ident()])
        self.assertEqual(self.results, [])

    def test_obsolete_error_does_not_replace_the_new_preview(self):
        release = self.gate()

        def compute(project):
            if project == "old":
                self.assertTrue(release.wait(2))
                raise ValueError("obsolete failure")
            return project

        planner = self.planner(compute)
        planner.request("old")
        self.scheduler.advance(180)
        planner.request("new")
        self.scheduler.advance(180)
        release.set()
        self.finish(planner)
        planner.poll()
        self.finish(planner)
        planner.poll()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.results, ["new"])

    def test_close_discards_running_result_pending_work_and_future_requests(self):
        release = self.gate()
        planner = self.planner(lambda project: release.wait(2) and project)
        planner.request("running")
        self.scheduler.advance(180)
        planner.request("pending")
        late_callback = next(iter(self.scheduler.pending.values()))[1]
        planner.close()
        planner.close()
        self.assertEqual(self.scheduler.pending, {})
        late_callback()
        planner.request("after close")
        self.assertEqual(self.scheduler.pending, {})
        release.set()
        self.finish(planner)
        planner.poll()
        self.assertEqual(self.results, [])
        self.assertEqual(self.errors, [])

    def test_callback_can_close_planner_without_starting_more_work(self):
        planner = self.planner(lambda project: project,
                               on_result=lambda result: planner.close())
        planner.request("current")
        self.scheduler.advance(180)
        self.finish(planner)
        planner.poll()
        planner.request("ignored")
        self.assertEqual(self.scheduler.pending, {})

    def test_poll_rejects_worker_thread_to_protect_tk_callbacks(self):
        planner = self.planner(lambda project: project)
        failures = []

        def off_thread_poll():
            try:
                planner.poll()
            except RuntimeError as error:
                failures.append(error)

        thread = threading.Thread(target=off_thread_poll)
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIn("UI thread", str(failures[0]))


if __name__ == "__main__":
    unittest.main()
