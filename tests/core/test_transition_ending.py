import unittest
import emotion_input as ui
import story_engine as e
from test_story import fixture


class EndingTests(unittest.TestCase):
    def test_cadence_preserves_time_and_outgoing_voice(self):
        p=ui.default_story(fixture());q=e.plan(p);last=q['blocks'][-1];prior=q['blocks'][-2]
        self.assertEqual(last['kind'],'transition_ending')
        self.assertEqual(last['end_tick']-last['start_tick'],1920)
        self.assertEqual(last['notes'][0]['pitch'],prior['notes'][-1]['pitch'])
        self.assertEqual(last['notes'][-1]['pitch']%12,0)
        self.assertEqual(last['notes'][-1]['duration'],960)
        self.assertEqual(last['level'],prior['end_level'])
        self.assertEqual(last['end_level'],.25)
        self.assertFalse(last['source_spans'])
        score=e.compile_score(q)
        self.assertEqual(score['report']['playback_blocks'][-1]['kind'],'transition_ending')
        self.assertFalse(any(n.start>=last['start_tick']+960 for l in score['layers'] if l['name'] in ('pulse','kick','snare','hat') for n in l['notes']))

    def test_anchor_and_override_protected(self):
        for key,item in [('anchors',dict(time=24,hold=2,emotion='calm',level=.25)),
                         ('overrides',dict(start=24,end=26,emotion='calm',level=.25))]:
            p=ui.default_story(fixture());p[key]=[item]
            self.assertNotEqual(e.plan(p)['blocks'][-1]['kind'],'transition_ending')

    def test_nonterminal_calm_not_ending(self):
        p=ui.default_story(fixture());p['curve'][-1]['emotion']='hope'
        self.assertFalse(any(b['kind']=='transition_ending' for b in e.plan(p)['blocks']))

    def test_multiple_ending_blocks(self):
        p=ui.default_story(fixture());p['duration']=30;p['curve'][-1]['end']=30
        q=e.plan(p);ending=[b for b in q['blocks'] if b['kind']=='transition_ending']
        self.assertEqual(len(ending),3)
        self.assertEqual(ending[0]['level'],.85)
        self.assertAlmostEqual(ending[-1]['end_level'],.25)
        e.compile_score(q)
