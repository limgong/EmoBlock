import unittest
import story_engine as e
import emotion_input as ui
from test_story import fixture


class ExpressionProtectionTests(unittest.TestCase):
    def test_user_2_4_2_4_1(self):
        p=fixture();p.update(bpm=65,duration=48);bar=240/65
        p['curve']=[dict(start=a*bar,end=min(48,b*bar),emotion=emotion,level=level,end_level=level)
                    for a,b,emotion,level in [(0,2,'calm',.25),(2,6,'suspense',.5),(6,8,'calm',.25),(8,12,'resolve',.85),(12,13,'calm',.25)]]
        q=e.plan(ui.normalize(p));strong=[b for b in q['blocks'] if b['emotion']=='resolve']
        self.assertEqual(len(strong),4)
        self.assertTrue(all(b['kind']=='content' for b in strong))
        # The quiet ending now has an explicit cadence without stealing climax time.
        self.assertEqual(q['blocks'][-1]['kind'],'transition_ending')
        self.assertAlmostEqual(q['blocks'][-1]['end_seconds'],48)

    def test_protection_is_intensity_not_label(self):
        p=fixture();p['curve']=[dict(start=0,end=24,emotion='calm',level=.85),dict(start=24,end=48,emotion='resolve',level=.25)]
        q=e.plan(ui.normalize(p))
        self.assertTrue(all(b['kind']=='content' for b in q['blocks'] if b['start_seconds']<24))
        self.assertTrue(all(w['start_seconds']>=24 for w in q['connection_windows']))

    def test_both_sides_strong_fallback(self):
        p=fixture();p['curve']=[dict(start=0,end=24,emotion='crisis',level=.85),dict(start=24,end=48,emotion='resolve',level=.85)]
        q=e.plan(ui.normalize(p));self.assertFalse(q['connection_windows']);self.assertTrue(q['warnings'])

    def test_high_end_of_ramp_not_replaced(self):
        p=ui.paint_blocks(fixture(),0,48,'hope',.1,.95);q=e.plan(p)
        self.assertFalse(q['connection_windows'])

    def test_more_intense_replacement_budget_smaller(self):
        lengths=[]
        for level in (.1,.6):
            p=fixture();p['curve']=[dict(start=0,end=24,emotion='calm',level=level),dict(start=24,end=48,emotion='resolve',level=1)]
            q=e.plan(ui.normalize(p));lengths.append(sum(w['end_seconds']-w['start_seconds'] for w in q['connection_windows']))
        self.assertGreater(lengths[0],lengths[1]);self.assertGreater(lengths[1],0)


if __name__=='__main__':unittest.main()
