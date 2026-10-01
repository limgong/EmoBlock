import copy
import unittest
import emotion_input as e


class TimelineLengthTests(unittest.TestCase):
    def test_extend_and_trim_by_beats(self):
        for bpm in (65,120,220):
            p=e.default_story();p['bpm']=bpm;p=e.default_story(p);before=copy.deepcopy(p)
            q=e.resize_blocks(p,1)
            self.assertAlmostEqual(q['duration'],14*240/bpm)
            self.assertEqual(q['curve'][:-1],p['curve'][:-1])
            self.assertEqual(q['curve'][-1]['emotion'],'calm')
            self.assertAlmostEqual(q['curve'][-1]['end'],q['duration'])
            r=e.resize_blocks(q,-1)
            self.assertEqual(r,p);self.assertEqual(p,before)

    def test_shrink_removes_tail(self):
        p=e.default_story();q=e.resize_blocks(p,-1)
        self.assertEqual(q['duration'],24)
        self.assertEqual(q['curve'][-1]['emotion'],'resolve')
        self.assertEqual(q['curve'][-1]['end'],24)

    def test_protection_and_limits(self):
        p=e.default_story();p['anchors']=[dict(time=24,hold=2,emotion='calm',level=.25)]
        with self.assertRaisesRegex(ValueError,'固定记忆点'):e.resize_blocks(p,-1)
        p=e.default_story();p['overrides']=[dict(start=24,end=26,emotion='calm',level=.25)]
        with self.assertRaisesRegex(ValueError,'手动修改块'):e.resize_blocks(p,-1)
        for seconds in (2,482):
            with self.assertRaises(ValueError):e.resize_duration(e.default_story(),seconds)

    def test_ramp_and_partial_grid(self):
        p=e.default_story();p['curve'][-1].update(level=.5,end_level=.1)
        q=e.resize_duration(p,25)
        self.assertAlmostEqual(q['curve'][-1]['end_level'],.3)
        self.assertEqual(e.resize_blocks(q,-1)['duration'],24)
        self.assertEqual(e.resize_blocks(q,1)['duration'],28)
