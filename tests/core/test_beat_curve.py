import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_structure import fixture
import flow_engine as f
import local_engine as local
import studio_model as model


class BeatTests(unittest.TestCase):
    def setUp(self):
        pool,themes,*_=fixture();self.doc=f.prepare(f.structure.create(pool,[i['id'] for i in themes]));self.id=self.doc['placements'][1]['id']

    def changed(self):return f.edit_beat_node(self.doc,self.id,2,'crisis',.9)

    def test_interpolation_and_switch(self):
        value=self.changed()['expression'][self.id]
        self.assertEqual(f.expression_at(value,4,1)['emotion'],'calm')
        self.assertAlmostEqual(f.expression_at(value,4,1)['intensity'],.625)
        self.assertEqual(f.expression_at(value,4,2)['emotion'],'crisis')
        self.assertAlmostEqual(f.expression_at(value,4,2)['intensity'],.9)

    def test_actual_beat_arrangement(self):
        a=f.compile_score(self.doc,False);b=f.compile_score(self.changed(),False)
        self.assertEqual(b['report']['beat_expressions'][16+2]['emotion'],'crisis')
        self.assertNotEqual(a['layers'],b['layers']);self.assertEqual(a['total_ticks'],b['total_ticks'])
        self.assertTrue(any(r['tick']==4*f.BAR+2*f.PPQ for r in b['report']['boundaries']))
        self.assertTrue(b['report']['theme_preserved'])

    def test_endpoints_and_invalid(self):
        for beat in (-1,17,True,1.5):
            with self.assertRaises(ValueError):f.edit_beat_node(self.doc,self.id,beat,'calm',.5)
        for level in (-1,2,float('nan')):
            with self.assertRaises(ValueError):f.edit_beat_node(self.doc,self.id,2,'calm',level)
        for beat in (0,16):
            with self.assertRaises(ValueError):f.edit_beat_node(self.changed(),self.id,beat,remove=True)

    def test_update_remove_deterministic_no_mutation(self):
        before=copy.deepcopy(self.doc);changed=self.changed()
        changed=f.edit_beat_node(changed,self.id,2,'sad',.3)
        self.assertEqual(len(changed['expression'][self.id]['beat_nodes']),3)
        result=f.edit_beat_node(changed,self.id,2,remove=True)
        self.assertEqual(len(result['expression'][self.id]['beat_nodes']),2)
        self.assertEqual(before,self.doc)
        self.assertEqual(f.compile_score(result),f.compile_score(result))

    def test_modes_require_reset(self):
        bars=f.set_block_region(self.doc,self.id,2,3,'hope',.2,.6)
        with self.assertRaises(ValueError):f.edit_beat_node(bars,self.id,2,'crisis',.5)
        with self.assertRaises(ValueError):f.set_block_region(self.changed(),self.id,1,2,'sad',.3,.4)
        reset=f.set_region(self.changed(),1,1,'hope',.2,.6)
        self.assertNotIn('beat_nodes',reset['expression'][self.id])

    def test_snapshot_playback(self):
        report=f.compile_score(self.changed())['report'];block=report['playback_blocks'][1]
        self.assertEqual(model.playback_emotion(block,block['start_seconds']+.9)['emotion'],'calm')
        current=model.playback_emotion(block,block['start_seconds']+1.1)
        self.assertEqual(current['emotion'],'crisis');self.assertEqual(current['beat'],3)

    def test_transition_block_nodes(self):
        doc=f.prepare(f.structure.edit(self.doc,'add_transition',entry_id=self.doc['placements'][0]['id'],bars=1))
        doc=f.edit_beat_node(doc,doc['placements'][1]['id'],1,'resolve',.9)
        self.assertEqual(f.compile_score(doc)['report']['beat_expressions'][17]['emotion'],'resolve')

    def test_save_local_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(f.structure,'ROOT',Path(tmp)):
            report=f.generate(self.doc,render=False);doc=self.changed()
            result=local.prepare_revision(doc,report)
            self.assertTrue(result['report']['local_revision']['preservation_verified'])
            rep=f.generate(doc,render=False,arrangement=result)
            changed=f.edit_beat_node(doc,self.id,3,'sad',.4)
            self.assertTrue(local.prepare_revision(changed,rep)['report']['local_revision']['preservation_verified'])
            path=model.save_project(doc['pool'],doc,[dict(emotion='calm',start=.3,end=.4)],[],path=Path(tmp)/'p.json')
            self.assertEqual(model.load_project(path)['doc'],doc)

    def test_bad_node_order(self):
        doc=self.changed();doc['expression'][self.id]['beat_nodes'].reverse()
        with self.assertRaises(ValueError):f.validate(doc)


if __name__=='__main__':unittest.main()
