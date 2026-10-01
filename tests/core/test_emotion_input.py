import unittest
import story_engine as e
from emotion_input import paint,put_anchor


class EmotionInputTests(unittest.TestCase):
    def test_empty_project_can_paint(self):
        p=e.new_project();q=paint(p,8,0,'hope',.3,.8)
        self.assertEqual(q['curve'][0]['start'],0);self.assertEqual(p['curve'],[])

    def test_overlap_splits_and_preserves_curve(self):
        p=paint(e.new_project(),0,20,'calm',0,1);q=paint(p,5,15,'crisis',.9,.9)
        self.assertEqual(len(q['curve']),3)
        self.assertEqual(q['curve'][0]['end_level'],.25)
        self.assertEqual(q['curve'][2]['level'],.75)
        self.assertEqual(len(p['curve']),1)

    def test_full_paint(self):
        p=paint(e.new_project(),4,8,'calm',.1,.2);q=paint(p,-3,100,'resolve',.7,1)
        self.assertEqual(len(q['curve']),1);self.assertEqual(q['curve'][0]['end'],48)

    def test_click_not_region(self):
        with self.assertRaises(ValueError):paint(e.new_project(),3,3,'calm',.2,.2)

    def test_anchor_clamp_and_update(self):
        p=put_anchor(e.new_project(),47,'crisis',.9)
        self.assertEqual(p['anchors'][0]['hold'],1)
        q=put_anchor(p,47.5,'resolve',1)
        self.assertEqual(len(q['anchors']),1);self.assertEqual(q['anchors'][0]['time'],47)
        self.assertEqual(q['anchors'][0]['emotion'],'resolve')

    def test_anchor_before_another(self):
        p=put_anchor(e.new_project(),10,'crisis',.9);q=put_anchor(p,9,'hope',.6)
        self.assertEqual(q['anchors'][1]['hold'],1)

    def test_move_before_import(self):
        p=paint(e.new_project(),0,4,'calm',.2,.2)
        self.assertEqual(e.move_region(p,0,2)['curve'][0]['start'],2)

    def test_paint_keeps_fixed_anchor(self):
        p=put_anchor(e.new_project(),10,'crisis',1);q=paint(p,0,48,'calm',.1,.1)
        self.assertEqual(q['anchors'],p['anchors'])
        self.assertEqual(e.state_at(q,10)['emotion'],'crisis')


if __name__=='__main__':unittest.main()
