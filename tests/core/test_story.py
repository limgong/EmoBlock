import copy
import math
import tempfile
import unittest
from pathlib import Path
import story_engine as e
import studio_model


def fixture():
    p=e.new_project()
    p['sources']=[dict(id='s1',name='A',notes=[dict(pitch=60+i%4*2,start=i*480,duration=480,velocity=80) for i in range(16)],
                       ticks=7680,bpm=120,role='main',tonic=0,mode='major')]
    return p


class StoryTests(unittest.TestCase):
    def test_minimum_and_coverage(self):
        p=fixture();q=e.plan(p);blocks=q['blocks']
        self.assertEqual(blocks[0]['start_tick'],0)
        self.assertEqual(blocks[-1]['end_tick'],q['total_ticks'])
        for a,b in zip(blocks,blocks[1:]):self.assertEqual(a['end_tick'],b['start_tick'])
        for b in blocks:self.assertTrue(2<=b['end_seconds']-b['start_seconds']<=4)

    def test_short_inspiration(self):
        p=fixture();p['sources'][0]['notes']=p['sources'][0]['notes'][:1];p['sources'][0]['ticks']=480
        q=e.plan(p);self.assertEqual(len(q['materials']),4)
        self.assertGreater(len(q['blocks'][0]['notes']),1)

    def test_content_variations(self):
        bank=e.develop(fixture());self.assertNotEqual(bank[0]['notes'],bank[1]['notes'])
        self.assertEqual(bank[0]['notes'][:8],bank[1]['notes'][:8])
        self.assertEqual({m['source_id'] for m in bank},{'s1'})

    def test_original_order(self):
        q=e.plan(fixture());self.assertEqual([n['pitch'] for b in q['blocks'][:4] for n in b['notes']],[60+i%4*2 for i in range(16)])

    def test_arbitrary_anchor_grid(self):
        for bpm in (40,65,120,220):
            p=fixture();p['bpm']=bpm;p['anchors']=[dict(time=15.137,hold=2,emotion='crisis',level=.95)]
            q=e.plan(p);a=q['anchors'][0]
            self.assertLessEqual(abs(a['error_seconds']),q['timing_tolerance_seconds']+1e-9)
            r=next(r for r in q['blocks'] if r['id']==a['entry_id'])
            self.assertTrue(r['pinned']);self.assertEqual(r['emotion'],'crisis');self.assertEqual(r['level'],.95)

    def test_bridge_in_blank(self):
        p=fixture();p['anchors']=[dict(time=20,hold=2,emotion='crisis',level=1)]
        q=e.plan(p)
        self.assertTrue(any(b['kind']=='bridge' for b in q['blocks']))
        self.assertTrue(any(b['kind']=='transition_keep' for b in q['blocks']))
        before=next(b for b in q['blocks'] if b['end_seconds']==20)
        target=next(b for b in q['blocks'] if b['start_seconds']==20)
        self.assertEqual(before['notes'][-1]['pitch'],target['notes'][0]['pitch'])

    def test_transition_budget_does_not_shift(self):
        p=fixture();p['anchors']=[dict(time=2,hold=2,emotion='crisis',level=1)]
        q=e.plan(p);self.assertEqual(q['anchors'][0]['actual'],2)
        self.assertEqual(q['blocks'][0]['end_seconds'],2)
        self.assertEqual(q['blocks'][-1]['end_seconds'],48)

    def test_anchor_zero(self):
        p=fixture();p['anchors']=[dict(time=0,hold=2,emotion='resolve',level=1)]
        self.assertTrue(e.plan(p)['blocks'][0]['pinned'])

    def test_anchor_overlap_rejected(self):
        p=fixture();p['anchors']=[dict(time=4,hold=2,emotion='crisis',level=1),dict(time=5,hold=2,emotion='calm',level=.2)]
        with self.assertRaises(ValueError):e.plan(p)

    def test_overlap_curve_rejected(self):
        p=fixture();p['curve']=[dict(start=0,end=5,emotion='calm',level=.2),dict(start=4,end=8,emotion='hope',level=.5)]
        with self.assertRaises(ValueError):e.plan(p)

    def test_explicit_emotion_not_overwritten_by_bridge(self):
        p=fixture();p['curve']=[dict(start=0,end=20,emotion='calm',level=.2,end_level=.3)]
        p['anchors']=[dict(time=20,hold=2,emotion='crisis',level=1)]
        q=e.plan(p)
        for r in q['blocks']:
            if r['start_seconds']<20:self.assertEqual(r['emotion'],'calm')

    def test_multi_source_anchor_selects(self):
        p=fixture();s=copy.deepcopy(p['sources'][0]);s.update(id='s2',name='B',role='climax');p['sources'].append(s)
        p['anchors']=[dict(time=10,hold=2,emotion='crisis',level=1,source_id='s2')]
        q=e.plan(p);self.assertEqual(next(r for r in q['blocks'] if r['start_seconds']==10)['source_id'],'s2')

    def test_nonfirst_main(self):
        p=fixture();s=copy.deepcopy(p['sources'][0]);p['sources'][0]['role']='secondary';s.update(id='s2',role='main');p['sources'].append(s)
        self.assertEqual(e.plan(p)['main_source_id'],'s2')

    def test_edit_block_and_pin_guard(self):
        p=fixture();q=e.plan(p);r=q['blocks'][0]
        edited=e.edit_block(p,r,'sad',.3);self.assertEqual(e.plan(edited)['blocks'][0]['emotion'],'sad')
        self.assertEqual(p['overrides'],[])
        r['pinned']=True
        with self.assertRaises(ValueError):e.edit_block(p,r,'sad',.3)

    def test_drag_collision_atomic(self):
        p=fixture();p['curve']=[dict(start=0,end=4,emotion='calm',level=.2),dict(start=8,end=12,emotion='hope',level=.5)]
        moved=e.move_region(p,0,2);self.assertEqual(moved['curve'][0]['start'],2)
        with self.assertRaises(ValueError):e.move_region(p,0,6)
        self.assertEqual(p['curve'][0]['start'],0)

    def test_score_and_playback(self):
        q=e.plan(fixture());score=e.compile_score(q);report=score['report']
        blocks=studio_model.playback_blocks(report);self.assertEqual(len(blocks),len(q['blocks']))
        self.assertLessEqual(len([l for l in score['layers'] if not l['drum']]),15)
        for layer in score['layers']:
            for n in layer['notes']:
                self.assertGreater(n.duration,0);self.assertGreaterEqual(n.start,0);self.assertLessEqual(n.start+n.duration,score['total_ticks'])

    def test_persist_snapshots(self):
        p=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.json'
            studio_model.save_project(studio_model.materials.new_pool(),None,[dict(emotion='calm',start=.2,end=.3)],[],dict(story=p),path)
            result=studio_model.load_project(path)['settings']['story'];self.assertEqual(e.plan(result),e.plan(p))

    def test_bad_numbers(self):
        for bad in (float('nan'),float('inf'),0,1000):
            p=fixture();p['duration']=bad
            with self.assertRaises(ValueError):e.plan(p)

    def test_reference_validation(self):
        p=fixture();p['anchors']=[dict(time=10,hold=2,emotion='crisis',level=1,source_id='missing')]
        with self.assertRaises(ValueError):e.plan(p)

    def test_boundary_short_block_reported(self):
        p=fixture();p['anchors']=[dict(time=.5,hold=2,emotion='crisis',level=1)]
        q=e.plan(p);self.assertTrue(q['warnings']);self.assertEqual(q['anchors'][0]['actual'],.5)

    def test_input_not_mutated(self):
        p=fixture();original=copy.deepcopy(p);e.plan(p);self.assertEqual(p,original)


if __name__=='__main__':unittest.main()
