import copy
import unittest
import block_editor
import emotion_input
import intensity_curve
import story_engine
import default_melody


class BlockEditorTests(unittest.TestCase):
    def project(self):
        p=emotion_input.default_story();p['continuous_intensity']=True
        p['sources']=[default_melody.source()]
        return emotion_input.normalize(p)

    def test_reorder_preserves_coverage_and_source(self):
        p=self.project();original=copy.deepcopy(p)
        q=block_editor.reorder(p,1,4)
        self.assertEqual(p,original)
        self.assertEqual([v['emotion'] for v in q['curve']],['calm','crisis','sad','resolve','suspense','calm'])
        cursor=0
        for v in q['curve']:
            self.assertAlmostEqual(v['start'],cursor);cursor=v['end']
            self.assertAlmostEqual(v['start']%2,0)
        self.assertEqual(cursor,p['duration'])
        self.assertEqual(q['sources'],p['sources'])
        self.assertEqual(len(story_engine.plan(q)['blocks']),13)

    def test_strength_controls_follow_moved_blocks(self):
        p=self.project()
        p['intensity_points']=[dict(time=v['time'],level=i/13) for i,v in enumerate(intensity_curve.controls(p))]
        q=block_editor.reorder(p,1,4)
        expected=[0,3,4,5,6,7,8,9,10,11,1,2,12]
        self.assertEqual([v['level'] for v in q['intensity_points']],[i/13 for i in expected])

    def test_first_last_and_merged_neighbors(self):
        p=self.project();q=block_editor.reorder(p,0,5)
        self.assertEqual(q['curve'][0]['emotion'],'suspense')
        self.assertEqual(q['curve'][-1]['emotion'],'calm')
        self.assertEqual(q['curve'][-1]['end']-q['curve'][-1]['start'],4)
        self.assertEqual(q['duration'],p['duration'])

    def test_fixed_anchor_blocks_crossing_but_allows_unrelated_move(self):
        p=self.project();p['anchors']=[dict(time=12,hold=2,emotion='sad',level=.3)]
        p=emotion_input.normalize(p)
        with self.assertRaisesRegex(ValueError,'固定'):block_editor.reorder(p,1,4)
        q=block_editor.reorder(p,0,1)
        self.assertEqual(q['anchors'],p['anchors'])

    def test_override_blocks_crossing(self):
        p=self.project();p['overrides']=[dict(start=12,end=14,emotion='sad',level=.3)]
        with self.assertRaisesRegex(ValueError,'固定'):block_editor.reorder(p,1,4)

    def test_partial_tail_cannot_move(self):
        p=emotion_input.resize_duration(self.project(),25)
        with self.assertRaisesRegex(ValueError,'四拍'):block_editor.reorder(p,len(p['curve'])-1,0)

    def test_noop_and_insertion_targets(self):
        p=self.project()
        self.assertEqual(block_editor.reorder(p,1,1),p)
        self.assertEqual(block_editor.insertion_index(p,1,-100),0)
        self.assertEqual(block_editor.insertion_index(p,1,100),len(p['curve'])-1)

    def test_clear_middle_preserves_both_ramps_metadata_and_project(self):
        p=self.project();source_id=p['sources'][0]['id']
        p['overrides']=[dict(start=2,end=10,emotion='hope',level=.2,end_level=1.,
                             source_id=source_id,metadata={'label':'keep'})]
        original=copy.deepcopy(p)
        q=block_editor.clear_overrides(p,4,6)
        self.assertEqual(p,original)
        self.assertEqual([(v['start'],v['end']) for v in q['overrides']],[(2,4),(6,10)])
        for value,levels in zip(q['overrides'],[(.2,.4),(.6,1.)]):
            self.assertAlmostEqual(value['level'],levels[0])
            self.assertAlmostEqual(value['end_level'],levels[1])
            self.assertEqual(value['source_id'],source_id)
            self.assertEqual(value['metadata'],{'label':'keep'})
        self.assertEqual({k:v for k,v in q.items() if k!='overrides'},
                         {k:v for k,v in original.items() if k!='overrides'})
        q['overrides'][0]['metadata']['label']='changed'
        q['sources'][0]['name']='changed'
        self.assertEqual(p,original)

    def test_clear_range_spans_multiple_overrides_and_interpolates_decrease(self):
        p=self.project()
        p['overrides']=[dict(start=0,end=4,emotion='sad',level=.9,end_level=.5),
                        dict(start=4,end=6,emotion='calm',level=.3),
                        dict(start=6,end=10,emotion='hope',level=.8,end_level=.4)]
        q=block_editor.clear_overrides(p,2,8)
        self.assertEqual([(v['start'],v['end']) for v in q['overrides']],[(0,2),(8,10)])
        self.assertAlmostEqual(q['overrides'][0]['end_level'],.7)
        self.assertAlmostEqual(q['overrides'][1]['level'],.6)
        self.assertEqual(q['overrides'][1]['end_level'],.4)

    def test_clear_constant_override_without_end_level(self):
        p=self.project();p['overrides']=[dict(start=2,end=10,emotion='calm',level=.3)]
        q=block_editor.clear_overrides(p,4,6)
        for value in q['overrides']:
            self.assertEqual(value['level'],.3)
            self.assertEqual(value['end_level'],.3)

    def test_clear_all_keeps_anchors_and_duration(self):
        p=self.project();p['anchors']=[dict(time=12,hold=2,emotion='sad',level=.3)]
        p['overrides']=[dict(start=2,end=4,emotion='hope',level=.7)]
        q=block_editor.clear_overrides(p,0,p['duration'])
        self.assertEqual(q,dict(p,overrides=[]))

    def test_clear_nonoverlapping_or_empty_ranges_returns_independent_copy(self):
        p=self.project();p['overrides']=[dict(start=2,end=4,emotion='hope',level=.7)]
        for start,end in ((0,2),(4,6)):
            q=block_editor.clear_overrides(p,start,end)
            self.assertEqual(q,p)
            self.assertIsNot(q,p)
            self.assertIsNot(q['overrides'][0],p['overrides'][0])
        p['overrides']=[]
        self.assertEqual(block_editor.clear_overrides(p,0,2),p)

    def test_clear_rejects_invalid_ranges_without_mutation(self):
        p=self.project();original=copy.deepcopy(p)
        for start,end in ((-1,2),(0,p['duration']+1),(2,2),(4,2),
                          (float('nan'),2),(0,float('inf')),('0',2),(None,2),(False,2)):
            with self.subTest(start=start,end=end):
                with self.assertRaises(ValueError):block_editor.clear_overrides(p,start,end)
                self.assertEqual(p,original)

    def test_clear_rejects_short_remainder_instead_of_removing_outside_range(self):
        p=self.project();p['overrides']=[dict(start=2,end=4,emotion='hope',level=.7)]
        original=copy.deepcopy(p)
        for start,end in ((2.05,4),(2,3.95)):
            with self.assertRaisesRegex(ValueError,'0.1'):
                block_editor.clear_overrides(p,start,end)
        self.assertEqual(p,original)


if __name__=='__main__':unittest.main()
