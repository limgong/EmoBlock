from pathlib import Path
import unittest
import curve_workflow


class AcceptanceSampleTests(unittest.TestCase):
    def test_calm_monophonic_sample_imports_without_changing_original(self):
        folder=Path(__file__).resolve().parents[2]/'assets/samples'
        original=(folder/'EmoBlocks-Calm.mmp').read_bytes()
        batch=curve_workflow.prepare_import(folder/'EmoBlocks-Calm-Monophonic.mmp')
        self.assertTrue(batch['sources'])
        self.assertTrue(batch['materials'])
        self.assertEqual((folder/'EmoBlocks-Calm.mmp').read_bytes(),original)
