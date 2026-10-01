import copy
import unittest
import emotion_input as ui
import story_engine as e
from test_story import fixture


class PeakMemoryTests(unittest.TestCase):
    def test_default_peak_is_resolve_original(self):
        for bpm in (40,65,120,220):
            p=fixture();p['bpm']=bpm;p=ui.default_story(p);before=copy.deepcopy(p)
            a=e.automatic_peak_anchor(p);q=e.plan(p)
            self.assertAlmostEqual(a['time'],8*240/bpm)
            self.assertAlmostEqual(a['hold'],240/bpm)
            row=next(r for r in q['blocks'] if r['id']==q['anchors'][0]['entry_id'])
            self.assertTrue(row['pinned']);self.assertEqual(row['kind'],'content')
            self.assertEqual(row['version'],'original');self.assertEqual(row['source_spans'][0]['start'],0)
            self.assertEqual(row['emotion'],'resolve');self.assertEqual(p,before)
            self.assertEqual(p['curve'][2]['level'],.5)
            self.assertTrue(q['anchors'][0]['auto_peak'])

    def test_late_peak_restarts_original_not_cycle_variant(self):
        p=ui.default_story(fixture());p['curve'][4]['level']=p['curve'][4]['end_level']=1
        q=e.plan(p);a=e.automatic_peak_anchor(p)
        self.assertEqual(a['time'],16)
        row=next(r for r in q['blocks'] if r['start_seconds']==16)
        self.assertEqual(row['version'],'original')
        self.assertEqual(row['source_spans'][0]['start'],0)
        self.assertEqual([n['pitch'] for n in row['notes']],[60,62,64,66])

    def test_ramp_peak_and_tie(self):
        p=ui.default_story(fixture());p['curve']=[dict(start=0,end=26,emotion='resolve',level=.1,end_level=1)]
        a=e.automatic_peak_anchor(p);self.assertEqual(a['time'],24)
        self.assertAlmostEqual(a['end_level'],1)
        p['curve']=[dict(start=0,end=10,emotion='hope',level=.9),dict(start=10,end=26,emotion='resolve',level=.9)]
        self.assertEqual(e.automatic_peak_anchor(p)['time'],0)

    def test_manual_priority_and_source_choice(self):
        p=ui.default_story(fixture());other=copy.deepcopy(p['sources'][0]);other.update(id='other',role='secondary')
        p['sources'].append(other);p['curve'][4]['source_id']='other'
        self.assertEqual(e.automatic_peak_anchor(p)['source_id'],'other')
        p['anchors']=[dict(time=16,hold=2,emotion='hope',level=.8)]
        self.assertIsNone(e.automatic_peak_anchor(p));self.assertEqual(len(e.plan(p)['anchors']),1)
        p['anchors']=[];p['overrides']=[dict(start=16,end=18,emotion='hope',level=.8)]
        self.assertIsNone(e.automatic_peak_anchor(p))
