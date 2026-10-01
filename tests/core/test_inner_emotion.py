import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_structure import fixture
import flow_engine as f
import local_engine as local
import studio_model as model


class InnerTests(unittest.TestCase):
    def setUp(self):
        pool,themes,*_=fixture();self.doc=f.prepare(f.structure.create(pool,[i['id'] for i in themes]))
        self.ident=self.doc['placements'][1]['id']

    def changed(self):return f.set_block_region(self.doc,self.ident,3,4,'crisis',.6,.9)

    def test_partial_expression_preserves_other_bars_and_structure(self):
        before=copy.deepcopy(self.doc);doc=self.changed()
        self.assertEqual(doc['placements'],before['placements']);self.assertEqual(doc['pool'],before['pool'])
        settings=doc['expression'][self.ident]['bar_settings']
        self.assertEqual([v['emotion'] for v in settings],['calm','calm','crisis','crisis'])
        self.assertEqual(settings[:2],f.bar_settings(before['expression'][self.ident],4)[:2])
        self.assertEqual(self.doc,before)

    def test_generation_changes_within_block(self):
        score=f.compile_score(self.changed())
        self.assertEqual(score['report']['bar_emotions'][4:8],['calm','calm','crisis','crisis'])
        self.assertEqual(score['total_ticks'],16*f.BAR)
        internal=[r for r in score['report']['boundaries'] if r['kind']=='within_block']
        self.assertEqual(len(internal),1);self.assertEqual(internal[0]['tick'],6*f.BAR)
        self.assertEqual(internal[0]['from_entry'],internal[0]['to_entry'])
        self.assertTrue(score['report']['theme_preserved'])

    def test_invalid_settings(self):
        for a,b,e,x,y in [(0,2,'calm',0,1),(3,2,'calm',0,1),(1,5,'calm',0,1),(1,2,'bad',0,1),(1,2,'calm',float('nan'),1),(1,2,'calm',0,2)]:
            with self.assertRaises(ValueError):f.set_block_region(self.doc,self.ident,a,b,e,x,y)
        with self.assertRaises(ValueError):f.set_block_region(self.doc,'missing',1,2,'calm',0,1)

    def test_full_region_overrides_details(self):
        doc=f.set_region(self.changed(),1,1,'hope',.2,.8)
        self.assertNotIn('bar_settings',doc['expression'][self.ident])
        self.assertEqual(f.compile_score(doc)['report']['bar_emotions'][4:8],['hope']*4)

    def test_transition_can_change_emotion_inside(self):
        doc=f.prepare(f.structure.edit(self.doc,'add_transition',entry_id=self.doc['placements'][0]['id'],bars=2))
        ident=doc['placements'][1]['id'];doc=f.set_block_region(doc,ident,2,2,'resolve',.8,1)
        self.assertEqual(f.compile_score(doc)['report']['bar_emotions'][4:6],['calm','resolve'])

    def test_snapshot_playback_uses_current_bar(self):
        score=f.compile_score(self.changed());block=model.playback_blocks(score['report'])[1]
        self.assertEqual(model.playback_emotion(block,8.1)['emotion'],'calm')
        self.assertEqual(model.playback_emotion(block,12.1)['emotion'],'crisis')
        self.assertEqual(model.playback_emotion(block,12.1)['bar'],3)
        self.assertEqual(model.playback_emotion(dict(start_seconds=0,end_seconds=8,emotion='sad'),1)['emotion'],'sad')

    def test_serialization_and_local_preservation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(f.structure,'ROOT',Path(tmp)):
            report=f.generate(self.doc,render=False);doc=self.changed()
            result=local.prepare_revision(doc,report)
            self.assertTrue(result['report']['local_revision']['preservation_verified'])
            path=model.save_project(doc['pool'],doc,[dict(emotion='calm',start=.2,end=.3)],[],path=Path(tmp)/'p.json')
            self.assertEqual(model.load_project(path)['doc'],doc)
            updated=f.generate(doc,render=False,arrangement=result)
            # Remove an internal change via whole-block edit, using saved local baseline.
            flat=f.set_region(doc,1,1,'hope',.4,.8)
            revised=local.prepare_revision(flat,updated)
            self.assertFalse(any(r['kind']=='within_block' for r in revised['report']['boundaries']))

    def test_malformed_bar_settings_rejected(self):
        doc=self.changed();doc['expression'][self.ident]['bar_settings'].pop()
        with self.assertRaises(ValueError):f.validate(doc)


if __name__=='__main__':unittest.main()
