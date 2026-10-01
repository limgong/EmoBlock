import unittest
import emotion_input as ui
import story_engine as e
from test_story import fixture


class DefaultStoryTests(unittest.TestCase):
    def test_thirteen_bars_at_different_tempos(self):
        for bpm in (65,120):
            p=fixture();p['bpm']=bpm;p=ui.default_story(p)
            self.assertAlmostEqual(p['duration'],13*240/bpm)
            self.assertEqual([v['emotion'] for v in p['curve']],['calm','suspense','crisis','sad','resolve','calm'])
            self.assertEqual([round((v['end']-v['start'])*bpm/240) for v in p['curve']],[1,2,3,2,4,1])
            self.assertTrue(ui.is_default_story(p))

    def test_calm_theme_and_peak_retained_suspense_carries_connection(self):
        p=ui.default_story(fixture());q=e.plan(p)
        self.assertEqual(q['blocks'][0]['kind'],'content')
        self.assertEqual(q['blocks'][-1]['kind'],'transition_ending')
        for b in q['blocks']:
            if b['emotion']=='resolve':self.assertEqual(b['kind'],'content')
        suspense=[b for b in q['blocks'] if b['emotion']=='suspense']
        self.assertEqual([b['kind'] for b in suspense],['transition_keep','bridge'])

    def test_custom_edit_not_default(self):
        p=ui.default_story(fixture());p['curve'][0]['level']=.4
        self.assertFalse(ui.is_default_story(p))

    def test_generation_does_not_reset_custom_curve(self):
        p=ui.default_story(fixture());p=ui.paint_blocks(p,0,p['duration'],'hope',.4,.4)
        q=e.plan(p)
        self.assertTrue(all(b['emotion']=='hope' for b in q['blocks']))


if __name__=='__main__':unittest.main()
