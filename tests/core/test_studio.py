import copy
import tempfile
import unittest
from pathlib import Path
import studio_model as m
from runtime_config import ASSETS


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.theme=m.materials.import_theme(ASSETS/'theme-c.mid',name='A')
        self.curve=[dict(emotion='calm',start=.2,end=.4),dict(emotion='crisis',start=.4,end=.9),dict(emotion='resolve',start=.7,end=.95)]

    def test_quick_pipeline(self):
        doc=m.quick_document(self.theme,self.curve)
        self.assertEqual(len(doc['placements']),3)
        self.assertEqual([v['emotion'] for v in doc['expression'].values()],['calm','crisis','resolve'])
        self.assertEqual(m.flow.compile_score(doc)['report']['duration_seconds'],24)

    def test_one_segment(self):
        doc=m.quick_document(self.theme,self.curve[:1]);self.assertEqual(len(doc['pool']['items']),1)

    def test_six_segments(self):
        doc=m.quick_document(self.theme,self.curve*2);self.assertEqual(len(doc['placements']),6)

    def test_source_unchanged(self):
        before=copy.deepcopy(self.theme);m.quick_document(self.theme,self.curve);self.assertEqual(self.theme,before)

    def test_reproducible_notes(self):
        a=m.quick_document(self.theme,self.curve);b=m.quick_document(self.theme,self.curve)
        self.assertEqual([i['notes'] for i in a['pool']['items']],[i['notes'] for i in b['pool']['items']])

    def test_invalid_curve(self):
        for curve in ([],self.curve*3,[dict(emotion='calm',start=float('nan'),end=.5)]):
            with self.assertRaises(ValueError):m.quick_document(self.theme,curve)

    def test_project_roundtrip(self):
        doc=m.quick_document(self.theme,self.curve)
        with tempfile.TemporaryDirectory() as tmp:
            path=m.save_project(doc['pool'],doc,self.curve,[],dict(seed=123),Path(tmp)/'studio.json')
            result=m.load_project(path)
            self.assertEqual(result['doc'],doc);self.assertEqual(result['settings']['seed'],123)
            with self.assertRaises(FileExistsError):m.save_project(doc['pool'],doc,self.curve,[],path=path)

    def test_legacy_structure(self):
        doc=m.quick_document(self.theme,self.curve)
        with tempfile.TemporaryDirectory() as tmp:
            path=m.structure.save(doc,Path(tmp)/'structure.json');self.assertEqual(m.load_project(path)['doc'],doc)

    def test_merge_candidates_preserves_backbone(self):
        doc=m.quick_document(self.theme,self.curve);pool=copy.deepcopy(doc['pool'])
        child=m.materials.generate_candidates(self.theme,'variant',43)[0];m.materials.add_item(pool,child)
        result=m.merge_pool(doc,pool)
        self.assertEqual(result['placements'],doc['placements']);self.assertEqual(result['expression'],doc['expression'])


if __name__=='__main__':unittest.main()
