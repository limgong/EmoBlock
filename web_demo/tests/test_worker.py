"""Worker observability does not alter the progress or cancellation contract."""
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch
from web_demo.api.core import recommendations


class WorkerTests(unittest.TestCase):
    def execute(self, prepare):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        folder = Path(directory.name)
        (folder/'input.json').write_text(json.dumps({'request': {'id':'fixture'}, 'source_facts': []}))
        with patch.object(sys, 'argv', ['worker', str(folder)]), patch.object(recommendations, 'prepare_recommendations', side_effect=prepare), patch.dict('os.environ'):
            runpy.run_module('web_demo.api.worker', run_name='__main__')
        return folder

    def test_light_progress_and_terminal_timing_preserve_output(self):
        def prepare(request, **kwargs):
            self.assertEqual(request, {'id': 'fixture'})
            self.assertFalse(kwargs['include_stage_bundle'])
            self.assertEqual(kwargs['source_facts'], [])
            self.assertFalse(kwargs['should_cancel']())
            for seq, phase in enumerate(('BASE_COMPLETION', 'RENDERING'), 1):
                self.assertTrue(kwargs['on_progress'](dict(seq=seq, phase=phase, message='test', candidate_id=None)))
            return {'status': 'SUCCEEDED', 'fixture': True}
        folder = self.execute(prepare)
        self.assertEqual(json.loads((folder/'output.json').read_text()), {'status': 'SUCCEEDED', 'fixture': True})
        self.assertEqual(json.loads((folder/'progress.json').read_text()), dict(seq=2, phase='RENDERING', message='test'))
        timing = json.loads((folder/'timings.json').read_text())
        self.assertEqual(timing['status'], 'SUCCEEDED')
        self.assertEqual([e['seq'] for e in timing['events']], [1, 2])
        self.assertGreaterEqual(timing['elapsed_seconds'], timing['events'][-1]['elapsed_seconds'])

    def test_cancel_file_is_still_observed_by_both_callbacks(self):
        def prepare(request, **kwargs):
            folder = Path(sys.argv[1]); (folder/'cancel').touch()
            self.assertTrue(kwargs['should_cancel']())
            self.assertFalse(kwargs['on_progress'](dict(seq=1, phase='BASE_COMPLETION', message='test')))
            return {'status': 'CANCELLED'}
        folder = self.execute(prepare)
        self.assertEqual(json.loads((folder/'timings.json').read_text())['status'], 'CANCELLED')

    def test_timing_io_failure_does_not_fail_the_result(self):
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.name == 'timings.part': raise OSError('fixture telemetry failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'write_text', write):
            folder = self.execute(lambda request, **kwargs: {'status': 'SUCCEEDED'})
        self.assertEqual(json.loads((folder/'output.json').read_text())['status'], 'SUCCEEDED')
        self.assertFalse((folder/'error.json').exists())

    def test_error_retains_diagnostic_code_and_exit_status(self):
        from curve_project import ProjectError
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        folder = Path(directory.name); (folder/'input.json').write_text(json.dumps({'request': {}, 'source_facts': []}))
        with patch.object(sys, 'argv', ['worker', str(folder)]), patch.object(recommendations, 'prepare_recommendations', side_effect=ProjectError('STALE_SNAPSHOT', 'fixture')), patch.dict('os.environ'), self.assertRaises(SystemExit) as error:
            runpy.run_module('web_demo.api.worker', run_name='__main__')
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(json.loads((folder/'error.json').read_text())['code'], 'STALE_SNAPSHOT')
        self.assertEqual(json.loads((folder/'timings.json').read_text())['status'], 'FAILED')
