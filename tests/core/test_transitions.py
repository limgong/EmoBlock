import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_structure import fixture
import structure_engine as s
import flow_engine as f
import local_engine as local
import studio_model as model


class TransitionTests(unittest.TestCase):
    def setUp(self):
        pool,themes,*_=fixture()
        self.doc=f.prepare(s.create(pool,[i['id'] for i in themes]))

    def add(self,doc=None,bars=1):
        doc=doc or self.doc
        return f.prepare(s.edit(doc,'add_transition',entry_id=doc['placements'][0]['id'],bars=bars))

    def test_insert_duration_order_and_notes(self):
        for bars in (1,2):
            doc=self.add(bars=bars);rows=s.timeline(doc)['rows']
            self.assertEqual([e['slot_id'] for e in doc['placements'] if e['kind']=='slot'],self.doc['locked_order'])
            self.assertEqual(rows[1]['bars'],bars);self.assertEqual(rows[2]['start_bar'],5+bars)
            self.assertEqual(s.timeline(doc)['bars'],16+bars)
            item=s.entry_material(doc,doc['placements'][1]);ns=s.materials.notes_of(item)
            self.assertEqual(ns[-1].start+ns[-1].duration,bars*f.BAR)
            self.assertEqual(ns[0].pitch,s.materials.notes_of(s.entry_material(doc,doc['placements'][0]))[-1].pitch)
            self.assertEqual(ns[-1].pitch,s.materials.notes_of(s.entry_material(doc,doc['placements'][2]))[0].pitch)
            self.assertEqual(doc['pool'],self.doc['pool'])

    def test_remove_restores_and_no_mutation(self):
        before=copy.deepcopy(self.doc);doc=self.add()
        restored=f.prepare(s.edit(doc,'remove_transition',entry_id=doc['placements'][1]['id']))
        self.assertEqual(restored['placements'],before['placements'])
        self.assertEqual(restored['expression'],before['expression']);self.assertEqual(self.doc,before)

    def test_invalid_insertions(self):
        for bars in (0,3,True,1.5):
            with self.assertRaises(ValueError):self.add(bars=bars)
        with self.assertRaises(ValueError):s.edit(self.doc,'add_transition',entry_id=self.doc['placements'][-1]['id'])
        doc=self.add()
        with self.assertRaises(ValueError):self.add(doc)
        with self.assertRaises(ValueError):s.edit(doc,'add_transition',entry_id=doc['placements'][1]['id'])
        with self.assertRaises(ValueError):s.edit(doc,'remove_transition',entry_id=doc['placements'][0]['id'])

    def test_endpoints_checked(self):
        doc=self.add();doc['placements'][1]['right_entry']='wrong'
        with self.assertRaises(ValueError):s.validate(doc)

    def test_expression_and_region_lengths(self):
        doc=f.set_region(self.doc,0,0,'hope',.2,.7);doc=f.set_region(doc,1,1,'crisis',.8,1)
        doc=self.add(doc,2);e=doc['placements'][1]
        self.assertEqual(doc['expression'][e['id']],dict(emotion='crisis',start=.7,end=.8))
        doc=f.set_region(doc,0,2,'sad',0,1)
        self.assertAlmostEqual(doc['expression'][e['id']]['start'],.4)
        self.assertAlmostEqual(doc['expression'][e['id']]['end'],.6)

    def test_compile_playback_and_connection_off(self):
        doc=self.add()
        for enabled in (False,True):
            score=f.compile_score(doc,enabled);rep=score['report']
            self.assertEqual(rep['bars'],17);self.assertEqual(rep['duration_seconds'],34)
            self.assertEqual(len(rep['transition_blocks']),1)
            blocks=model.playback_blocks(rep)
            self.assertEqual(blocks[1]['kind'],'transition')
            self.assertEqual(model.active_block(blocks,8.1),1)
            self.assertEqual(model.active_block(blocks,10.1),2)
            self.assertTrue(score['report']['theme_preserved'])

    def test_new_structure_needs_new_local_baseline(self):
        base=f.compile_score(self.doc);base['report']['output_directory']='baseline'
        with self.assertRaisesRegex(ValueError,'结构'):local.compile_local(self.add(),self.doc,base)

    def test_saved_transition_and_local_edit(self):
        doc=self.add(bars=2)
        with tempfile.TemporaryDirectory() as tmp,patch.object(s,'ROOT',Path(tmp)):
            report=f.generate(doc,render=False)
            changed=f.set_region(doc,1,1,'crisis',.8,.9)
            revised=local.prepare_revision(changed,report)
            self.assertTrue(revised['report']['local_revision']['preservation_verified'])
            path=model.save_project(doc['pool'],doc,[dict(emotion='calm',start=.3,end=.5)],[],path=Path(tmp)/'project.json')
            loaded=model.load_project(path)
            self.assertEqual(f.compile_score(loaded['doc']),f.compile_score(doc))

    def test_bound_to_actual_replaced_endpoint(self):
        doc=self.add();variant=next(i for i in doc['pool']['items'] if i['name']=='B_c1')
        doc=f.prepare(s.edit(doc,'replace',slot_id=doc['backbone'][1]['id'],material_id=variant['id']))
        item=s.entry_material(doc,doc['placements'][1])
        self.assertEqual(item['parents'][1],variant['id'])
        self.assertIn('B_c1',item['name'])


if __name__=='__main__':unittest.main()
