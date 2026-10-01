import copy
import unittest
import emotion_input as ui
import story_engine as e
from test_story import fixture


class BlockSnapTests(unittest.TestCase):
    def test_fixed_four_beats_at_different_tempos(self):
        for bpm in (40,65,90,120,220):
            p=fixture();p['bpm']=bpm;p['duration']=32*60/bpm
            q=e.plan(ui.normalize(p))
            self.assertEqual(len(q['blocks']),8)
            for block in q['blocks']:
                self.assertEqual(block['end_tick']-block['start_tick'],4*e.PPQ)
                self.assertAlmostEqual(block['end_seconds']-block['start_seconds'],240/bpm)
            self.assertFalse(q['warnings'])

    def test_anchor_does_not_rebalance_regular_beats(self):
        p=fixture();p['anchors']=[dict(time=7.137,hold=2,emotion='crisis',level=.9)]
        grid=e.block_grid(p)
        for tick in range(0,48*960,1920):self.assertIn(tick,grid)
        self.assertIn(10*960,grid)

    def test_only_tail_truncated_without_anchor(self):
        p=fixture();p['duration']=9
        self.assertEqual(e.block_grid(p),[0,1920,3840,5760,7680,8640])

    def covered(self,p):
        grid=ui.grid_seconds(p);last=0
        for v in p['curve']:
            self.assertAlmostEqual(v['start'],last)
            self.assertTrue(any(abs(v['start']-t)<1e-7 for t in grid))
            self.assertTrue(any(abs(v['end']-t)<1e-7 for t in grid))
            last=v['end']
        self.assertAlmostEqual(last,p['duration'])

    def test_default_and_old_gap_filled(self):
        p=fixture();p['curve']=[dict(start=7,end=18,emotion='hope',level=.3,end_level=.7)]
        q=ui.normalize(p);self.covered(q);self.assertEqual(ui.normalize(q),q)
        self.assertEqual(p['curve'][0]['start'],7)

    def test_paint_partial_blocks_snap_and_fill(self):
        p=ui.normalize(fixture());q=ui.paint_blocks(p,4.23,13.4,'crisis',.7,1)
        self.covered(q);self.assertTrue(any(v['emotion']=='crisis' for v in q['curve']))

    def test_shared_boundary(self):
        p=ui.paint_blocks(fixture(),0,13,'hope',.4,.4)
        original=p['curve'][0]['end'];q=ui.resize_boundary(p,0,original+4)
        self.covered(q);self.assertGreater(q['curve'][0]['end'],original)
        self.assertEqual(q['curve'][0]['end'],q['curve'][1]['start'])

    def test_delete_fills_and_last_resets(self):
        p=ui.paint_blocks(fixture(),7,15,'crisis',.8,.9)
        i=next(i for i,v in enumerate(p['curve']) if v['emotion']=='crisis')
        q=ui.remove_region(p,i);self.covered(q)
        while len(q['curve'])>1:q=ui.remove_region(q,0)
        q=ui.remove_region(q,0);self.covered(q)

    def test_move_keeps_partition(self):
        p=ui.paint_blocks(fixture(),7,15,'crisis',.8,.8)
        i=next(i for i,v in enumerate(p['curve']) if v['emotion']=='crisis')
        q=ui.move_filled_region(p,i,4);self.covered(q)

    def test_full_coverage_bridge_replaces(self):
        p=ui.paint_blocks(fixture(),0,48,'calm',.2,.2)
        p=ui.paint_blocks(p,24,48,'crisis',1,1)
        q=e.plan(p);self.assertTrue(q['connection_windows'])
        self.assertTrue(any(b['kind']=='bridge' for b in q['blocks']))
        self.assertAlmostEqual(q['blocks'][-1]['end_seconds'],48)
        grid=e.block_grid(p)
        for b in q['blocks']:
            self.assertIn(b['start_tick'],grid);self.assertIn(b['end_tick'],grid)
            state=e.state_at(p,(b['start_seconds']+b['end_seconds'])/2)
            self.assertEqual(b['emotion'],state['emotion'])

    def test_anchor_never_replaced(self):
        p=ui.paint_blocks(fixture(),0,48,'calm',.2,.2)
        p=ui.normalize(ui.put_anchor(p,17.137,'crisis',1));q=e.plan(p);self.covered(p)
        for b in q['blocks']:
            if b['pinned']:self.assertEqual(b['kind'],'content')
        self.assertLessEqual(abs(q['anchors'][0]['error_seconds']),q['timing_tolerance_seconds'])

    def test_ramp_triggers_connection_without_blank(self):
        p=ui.paint_blocks(fixture(),0,48,'hope',.1,.65)
        q=e.plan(p);self.assertTrue(q['connection_windows'])
        self.assertEqual(p['curve'][0]['start'],0);self.assertEqual(p['curve'][-1]['end'],48)

    def test_small_change_no_replacement(self):
        p=ui.paint_blocks(fixture(),0,24,'calm',.2,.2)
        p=ui.paint_blocks(p,24,48,'calm',.3,.3)
        self.assertFalse(e.plan(p)['connection_windows'])


if __name__=='__main__':unittest.main()
