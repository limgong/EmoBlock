import copy
import unittest
import default_melody
import emotion_input
import story_engine


class PaintSourcesTests(unittest.TestCase):
    def project(self):
        p=story_engine.new_project();p['duration']=12
        first=default_melody.source();second=copy.deepcopy(first);second['id']='second-source'
        p['sources']=[first,second]
        p['curve']=[dict(start=0,end=4,emotion='calm',level=0.,end_level=.4,source_id=first['id']),
                    dict(start=4,end=8,emotion='sad',level=.8,end_level=.4,source_id=second['id']),
                    dict(start=8,end=12,emotion='resolve',level=.4,end_level=.8)]
        return p

    def test_paint_preserves_multiple_sources_and_interpolates_across_stroke(self):
        p=self.project();q=emotion_input.paint(p,2,10,'hope',.2,1.)
        self.assertEqual([(r['start'],r['end']) for r in q['curve']],[(0,2),(2,4),(4,8),(8,10),(10,12)])
        painted=q['curve'][1:4]
        self.assertEqual([r.get('source_id') for r in painted],[p['sources'][0]['id'],p['sources'][1]['id'],None])
        self.assertEqual([r['emotion'] for r in painted],['hope']*3)
        for region,levels in zip(painted,[(.2,.4),(.4,.8),(.8,1.)]):
            self.assertAlmostEqual(region['level'],levels[0])
            self.assertAlmostEqual(region['end_level'],levels[1])
        self.assertAlmostEqual(q['curve'][0]['end_level'],.2)
        self.assertAlmostEqual(q['curve'][-1]['level'],.6)

    def test_block_paint_keeps_sources_after_snapping_and_normalizing(self):
        p=emotion_input.normalize(self.project())
        q=emotion_input.paint_blocks(p,2.3,9.6,'crisis',.9,.3)
        for time,source_id in ((3,p['sources'][0]['id']),(5,p['sources'][1]['id']),(9,None)):
            state=story_engine.state_at(q,time)
            self.assertEqual(state['source_id'],source_id)
            self.assertEqual(state['emotion'],'crisis')
            self.assertAlmostEqual(state['level'],.9+(.3-.9)*(time-2)/8)
        self.assertEqual(q['curve'][0]['emotion'],'calm')
        self.assertEqual(q['curve'][-1]['emotion'],'resolve')

    def test_identical_sources_merge_and_blank_gaps_remain_automatic(self):
        p=self.project();source_id=p['sources'][0]['id']
        p['curve'][1]['source_id']=source_id
        q=emotion_input.paint(p,0,12,'hope',.2,.8)
        self.assertEqual([(r['start'],r['end'],r.get('source_id')) for r in q['curve']],[(0,8,source_id),(8,12,None)])
        p['curve']=[dict(start=4,end=8,emotion='calm',level=.3,source_id=source_id)]
        q=emotion_input.paint(p,0,12,'hope',.2,.8)
        self.assertEqual([(r['start'],r['end'],r.get('source_id')) for r in q['curve']],[(0,4,None),(4,8,source_id),(8,12,None)])

    def test_history_snapshot_and_other_project_data_remain_unchanged(self):
        p=self.project();p['continuous_intensity']=True
        p['anchors']=[dict(time=10,hold=2,emotion='sad',level=.3)]
        p['overrides']=[dict(start=6,end=8,emotion='calm',level=.2)]
        p=emotion_input.normalize(p);history=[copy.deepcopy(p)];original=copy.deepcopy(p)
        q=emotion_input.paint_blocks(p,2,10,'hope',.4,.6)
        self.assertEqual(p,original)
        for key in ('anchors','overrides','sources','intensity_points','duration','bpm'):
            self.assertEqual(q[key],p[key])
        q['sources'][0]['name']='changed'
        q['curve'][0]['source_id']='changed'
        self.assertEqual(history.pop(),original)
        self.assertEqual(p,original)


if __name__=='__main__':unittest.main()
