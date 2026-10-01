import copy
import tempfile
import unittest
from pathlib import Path
import studio_model as m
from runtime_config import ASSETS


class Tests(unittest.TestCase):
    def setUp(self):
        path=ASSETS/'EmoBlocks-Calm.mmp'
        a=m.materials.import_theme(path,start_bar=1,bars=4,name='A',simultaneous='lower',trim_overlaps=True)
        b=m.materials.import_theme(path,start_bar=5,bars=4,name='B',simultaneous='lower',trim_overlaps=True,key=(a['tonic'],a['mode']))
        self.themes=[a,b];self.curve=[dict(emotion='calm',start=.2,end=.4),dict(emotion='crisis',start=.5,end=.9)]

    def test_all_themes_preserved_in_order(self):
        doc=m.multi_document(self.themes,self.curve)
        self.assertEqual([r['name'] for r in m.structure.timeline(doc)['rows']],['A','B'])
        self.assertEqual([i['notes'] for i in doc['pool']['items']],[i['notes'] for i in self.themes])

    def test_curve_count_mismatch(self):
        with self.assertRaises(ValueError):m.multi_document(self.themes,self.curve[:1])

    def test_different_tempo_rejected(self):
        themes=copy.deepcopy(self.themes);themes[1]['bpm']+=10
        with self.assertRaises(ValueError):m.multi_document(themes,self.curve)

    def test_different_key_rejected(self):
        themes=copy.deepcopy(self.themes);themes[1]['tonic']=(themes[0]['tonic']+2)%12
        with self.assertRaises(ValueError):m.multi_document(themes,self.curve)

    def test_position_and_tail(self):
        report=m.flow.compile_score(m.multi_document(self.themes,self.curve))['report']
        blocks=m.playback_blocks(report)
        self.assertEqual(m.active_block(blocks,0),0)
        self.assertEqual(m.active_block(blocks,7.999),0)
        self.assertEqual(m.active_block(blocks,8),1)
        self.assertIsNone(m.active_block(blocks,16.2))

    def test_legacy_result_snapshot(self):
        doc=m.multi_document(self.themes,self.curve)
        with tempfile.TemporaryDirectory() as tmp:
            m.structure.save(doc,Path(tmp)/'structure.json')
            blocks=m.playback_blocks(dict(output_directory=tmp,duration_seconds=16))
            self.assertEqual([b['name'] for b in blocks],['A','B'])

    def test_invalid_timing_rejected(self):
        report=m.flow.compile_score(m.multi_document(self.themes,self.curve))['report']
        report['playback_blocks'][1]['start_seconds']=10
        with self.assertRaises(ValueError):m.playback_blocks(report)

    def test_input_list_roundtrip(self):
        doc=m.multi_document(self.themes,self.curve)
        with tempfile.TemporaryDirectory() as tmp:
            path=m.save_project(doc['pool'],doc,self.curve,[],dict(input_themes=self.themes),Path(tmp)/'studio.json')
            self.assertEqual(m.load_project(path)['settings']['input_themes'],self.themes)


if __name__=='__main__':unittest.main()
