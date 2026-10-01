"""Debounced, latest-request-only preview computation for a Tk page.

Create ``PreviewPlanner(root.after, root.after_cancel, compute, on_result,
on_error)`` on the UI thread. Call ``request(project)`` after edits and call
``poll()`` periodically (for example every 100 ms) from that same thread.
``request`` immediately deep-copies the project, so subsequent editor changes
cannot affect the computation. After the default 180 ms quiet period, a daemon
worker calls ``compute(snapshot)``. The compute function must not access Tk.

There is at most one worker at a time. Edits arriving during a computation
replace the pending request; the latest snapshot runs after both the current
worker has finished and its own debounce delay has expired. Obsolete results
and errors are silently discarded. Only ``poll`` delivers the current result
to ``on_result(result)`` or a computation exception to ``on_error(exception)``.

``invalidate()`` cancels pending work and invalidates the running result, while
allowing later requests. ``close()`` does the same permanently. Neither method
waits for or attempts to interrupt an already-running computation. Call close
before destroying the page and cancel the page's separate polling timer.
All public methods must run on the thread that created the planner.
"""

import copy
import queue
import threading


class PreviewPlanner:
    def __init__(self, schedule, cancel, compute, on_result, on_error, delay=180):
        if delay < 0:
            raise ValueError("Preview debounce delay must be non-negative")
        self._schedule = schedule
        self._cancel = cancel
        self._compute = compute
        self._on_result = on_result
        self._on_error = on_error
        self._delay = delay
        self._owner = threading.get_ident()
        self._revision = 0
        self._timer = None
        self._pending = None
        self._ready = False
        self._worker = None
        self._results = queue.Queue()
        self._closed = False

    def request(self, project):
        """Keep a private snapshot of the latest project and reset its delay."""
        self._assert_owner()
        if self._closed:
            return
        snapshot = copy.deepcopy(project)
        self._revision += 1
        revision = self._revision
        self._cancel_timer()
        self._pending = (revision, snapshot)
        self._ready = False
        self._timer = self._schedule(
            self._delay, lambda: self._debounce_elapsed(revision)
        )

    def invalidate(self):
        """Discard all outstanding work; the planner remains usable."""
        self._assert_owner()
        self._revision += 1
        self._cancel_timer()
        self._pending = None
        self._ready = False
        self._discard_results()

    def poll(self):
        """Deliver current completions on the UI thread and start ready work."""
        self._assert_owner()
        if self._closed:
            self._discard_results()
            return
        if self._worker is not None:
            # Even after queue.put(), a thread may still be exiting. Wait for
            # that exit before starting another worker or invoking callbacks.
            if self._worker.is_alive():
                return
            self._worker = None
        while True:
            try:
                revision, succeeded, value = self._results.get_nowait()
            except queue.Empty:
                break
            if self._closed or revision != self._revision:
                continue
            callback = self._on_result if succeeded else self._on_error
            callback(value)
        self._start_if_ready()

    def close(self):
        """Permanently stop scheduling and ignore all outstanding results."""
        self._assert_owner()
        self.invalidate()
        self._closed = True

    def _assert_owner(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError("PreviewPlanner methods must run on the UI thread")

    def _cancel_timer(self):
        if self._timer is not None:
            timer, self._timer = self._timer, None
            try:
                self._cancel(timer)
            except Exception:
                # Tk may already have fired the timer or destroyed its widget.
                # The revision check also protects against a late callback.
                pass

    def _debounce_elapsed(self, revision):
        self._assert_owner()
        if self._closed or revision != self._revision:
            return
        self._timer = None
        self._ready = True
        self._start_if_ready()

    def _start_if_ready(self):
        if self._closed or not self._ready or self._pending is None:
            return
        if self._worker is not None:
            return
        revision, snapshot = self._pending
        self._pending = None
        self._ready = False
        self._worker = threading.Thread(
            target=self._run, args=(revision, snapshot),
            name="EmoBlocks-preview", daemon=True,
        )
        self._worker.start()

    def _run(self, revision, snapshot):
        try:
            result = self._compute(snapshot)
        except Exception as error:
            self._results.put((revision, False, error))
        else:
            self._results.put((revision, True, result))

    def _discard_results(self):
        while True:
            try:
                self._results.get_nowait()
            except queue.Empty:
                return
