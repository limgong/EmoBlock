import copy
import tempfile
import unittest
import wave
from pathlib import Path
from test_structure import fixture
import structure_engine as s
import flow_engine as f


class Tests(unittest.TestCase):
    def setUp(self):
        pool,themes,*_=fixture()
        self.doc=f.prepare(s.create(pool,[i['id'] for i in themes]))

    def test_region_spans_blocks(self):
        doc=f.set_region(self.doc,0,1,'hope',.2,.8)
        first,second=[doc['expression'][e['id']] for e in doc['placements'][:2]]
        self.assertAlmostEqual(first['end'],.5);self.assertEqual(first['end'],second['start'])
        self.assertEqual(second['end'],.8)

    def test_structure_unchanged(self):
        before=copy.deepcopy(self.doc)
        doc=f.set_region(self.doc,1,2,'crisis',.4,.9);f.compile_score(doc)
        self.assertEqual(self.doc,before)
        self.assertEqual(doc['placements'],before['placements'])
        self.assertEqual(doc['pool'],before['pool'])

    def test_invalid_regions(self):
        for args in [(2,1,'calm',.2,.6),(0,9,'calm',.2,.6),(0,1,'bad',.2,.6),(0,1,'calm',-.1,.6),(0,1,'calm',float('nan'),.6)]:
            with self.assertRaises(ValueError):f.set_region(self.doc,*args)

    def test_melody_preserved(self):
        score=f.compile_score(f.set_region(self.doc,0,3,'crisis',.1,.9))
        self.assertTrue(score['report']['theme_preserved'])
        self.assertEqual(score['total_ticks'],16*f.BAR)
        self.assertTrue(all(n.start+n.duration<=score['total_ticks'] for l in score['layers'] for n in l['notes']))

    def test_no_extra_tail_per_block(self):
        score=f.compile_score(self.doc)
        self.assertEqual(score['report']['duration_seconds'],32)
        self.assertEqual(len(score['report']['boundaries']),3)

    def test_connections_change_accompaniment(self):
        doc=f.set_region(self.doc,2,3,'crisis',.7,1)
        a=f.compile_score(doc,True);b=f.compile_score(doc,False)
        self.assertNotEqual(a['layers'],b['layers'])
        self.assertEqual([l for l in a['layers'] if l['name'].startswith('theme_')],[l for l in b['layers'] if l['name'].startswith('theme_')])
        self.assertTrue(all(row['actions'] for row in a['report']['boundaries']))

    def test_deterministic(self):self.assertEqual(f.compile_score(self.doc),f.compile_score(self.doc))

    def test_six_emotions_different(self):
        signatures=[]
        for emotion in f.music.EMOTIONS:
            score=f.compile_score(f.set_region(self.doc,0,3,emotion,.6,.6))
            signatures.append(repr(score['layers']))
        self.assertEqual(len(set(signatures)),6)

    def test_saved_expression(self):
        doc=f.set_region(self.doc,0,2,'hope',.1,.9)
        with tempfile.TemporaryDirectory() as tmp:
            path=s.save(doc,Path(tmp)/'doc.json')
            self.assertEqual(f.prepare(s.load(path)),doc)

    def test_streaming_audio(self):
        np=f.music.np
        with tempfile.TemporaryDirectory() as tmp:
            dry=Path(tmp)/'dry.wav';out=Path(tmp)/'out.wav'
            samples=np.zeros((44100,2),dtype='<i2');samples[::20]=30000
            with wave.open(str(dry),'wb') as w:
                w.setnchannels(2);w.setsampwidth(2);w.setframerate(44100);w.writeframes(samples.tobytes())
            report=f.finish_audio(dry,out,1)
            self.assertEqual(report['seconds'],2)
            self.assertGreater(report['peak'],.01)
            self.assertLessEqual(report['peak'],.9)
            self.assertEqual(report['clipped_samples'],0)
            with wave.open(str(out),'rb') as w:self.assertEqual(w.getnframes(),88200)


if __name__=='__main__':unittest.main()
