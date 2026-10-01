import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audio_import


class AudioImportTests(unittest.TestCase):
    def test_rejects_unsupported_input_before_running_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'reference.txt';source.write_text('no audio',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'不支持'):
                audio_import.transcribe_audio(source,120,output_root=Path(folder)/'out')

    def test_rejects_tempo_outside_project_range(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'reference.wav';source.write_bytes(b'RIFF')
            with self.assertRaisesRegex(ValueError,'40～220'):
                audio_import.transcribe_audio(source,221,output_root=Path(folder)/'out')

    def test_runs_worker_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            source=folder/'my melody.wav';source.write_bytes(b'RIFF-test')
            worker=folder/'worker.py';worker.write_text('# test worker',encoding='utf-8')

            def fake_run(command,**kwargs):
                Path(command[3]).write_bytes(b'MThd-test-midi')
                return subprocess.CompletedProcess(
                    command,0,stdout='log\n{"note_count": 7, "duration_seconds": 2.5}\n',stderr=''
                )

            with mock.patch('audio_import.subprocess.run',side_effect=fake_run) as run:
                result=audio_import.transcribe_audio(
                    source,96,output_root=folder/'imports',
                    python_executable=sys.executable,worker_path=worker,
                )

            self.assertTrue(Path(result['midi_path']).is_file())
            self.assertEqual(result['note_count'],7)
            metadata=json.loads(Path(result['metadata_path']).read_text(encoding='utf-8'))
            self.assertEqual(metadata['source_audio'],str(source.resolve()))
            self.assertEqual(metadata['bpm'],96.0)
            command=run.call_args.args[0]
            self.assertEqual(command[0],str(Path(sys.executable).resolve()))
            self.assertEqual(command[-1],'96.0')


if __name__ == '__main__':
    unittest.main()
