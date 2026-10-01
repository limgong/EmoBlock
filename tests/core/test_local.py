import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_structure import fixture
import flow_engine as f
import local_engine as local
import studio_model as model


class LocalTests(unittest.TestCase):
    def setUp(self):
        pool,themes,*_=fixture()
        self.doc=f.prepare(f.structure.create(pool,[i['id'] for i in themes]))
        self.base=f.compile_score(self.doc)
        self.base['report']['output_directory']='baseline'
        self.changed=f.set_region(self.doc,1,1,'crisis',.75,.95)

    def test_preserve_outside_and_last_block(self):
        result=local.compile_local(self.changed,self.doc,self.base)
        info=result['report']['local_revision'];windows=info['affected_ticks']
        self.assertEqual(local.events_outside(self.base,windows),local.events_outside(result,windows))
        self.assertIn('D',info['preserved_blocks'])
        self.assertGreater(info['preserved_event_count'],0)
        self.assertNotEqual(self.base['layers'],result['layers'])
        self.assertEqual(result['total_ticks'],self.base['total_ticks'])

    def test_deterministic_no_mutation(self):
        old=copy.deepcopy((self.doc,self.base,self.changed))
        a=local.compile_local(self.changed,self.doc,self.base)
        self.assertEqual(a,local.compile_local(self.changed,self.doc,self.base))
        self.assertEqual(old,(self.doc,self.base,self.changed))

    def test_edges_and_nonadjacent_changes(self):
        for indices in ([0],[3],[0,3],[0,1,2,3]):
            doc=self.doc
            for i in indices:doc=f.set_region(doc,i,i,'resolve',.9,.9)
            result=local.compile_local(doc,self.doc,self.base)
            info=result['report']['local_revision']
            self.assertEqual(len(info['changed_entries']),len(indices))
            self.assertTrue(all(0<=a<b<=result['total_ticks'] for a,b in info['affected_ticks']))

    def test_sustain_not_cut(self):
        result=local.compile_local(self.changed,self.doc,self.base)
        windows=result['report']['local_revision']['affected_ticks']
        for score in (self.base,result):
            for layer in score['layers']:
                for n in layer['notes']:
                    if local.touches(n,windows):
                        self.assertTrue(any(a<=n.start and n.start+n.duration<=b for a,b in windows))

    def test_disabled_connections_only_target(self):
        base=f.compile_score(self.doc,False);base['report']['output_directory']='baseline'
        result=local.compile_local(self.changed,self.doc,base,False)
        self.assertEqual(result['report']['local_revision']['affected_ticks'],[[4*f.BAR,8*f.BAR]])
        self.assertEqual(result['report']['local_revision']['boundary_blocks'],[])

    def test_no_change_rejected(self):
        with self.assertRaisesRegex(ValueError,'没有'):local.compile_local(self.doc,self.doc,self.base)

    def test_connection_toggle_rejected(self):
        with self.assertRaisesRegex(ValueError,'连接开关'):local.compile_local(self.changed,self.doc,self.base,False)

    def test_structural_change_rejected(self):
        variant=next(i for i in self.doc['pool']['items'] if i['name']=='B_c1')
        doc=f.prepare(f.structure.edit(self.changed,'replace',slot_id=self.doc['backbone'][1]['id'],material_id=variant['id']))
        with self.assertRaisesRegex(ValueError,'结构'):local.compile_local(doc,self.doc,self.base)

    def test_disk_chain_save_load_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(f.structure,'ROOT',Path(tmp)):
            report=f.generate(self.doc,render=False)
            first=local.prepare_revision(self.changed,report)
            revised=f.generate(self.changed,render=False,arrangement=first)
            next_doc=f.set_region(self.changed,2,2,'sad',.4,.2)
            second=local.prepare_revision(next_doc,revised)
            windows=second['report']['local_revision']['affected_ticks']
            self.assertEqual(local.events_outside(first,windows),local.events_outside(second,windows))
            path=model.save_project(self.changed['pool'],self.changed,[dict(emotion='calm',start=.2,end=.3)],
                [dict(mode='baseline',report=report),dict(mode='local',report=revised)],path=Path(tmp)/'project.json')
            loaded=model.load_project(path)
            self.assertEqual(local.prepare_revision(next_doc,loaded['results'][1]['report']),second)
            score_path=Path(report['output_directory'])/'score.json'
            score_path.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'音符文件'):local.prepare_revision(self.changed,report)

    def test_missing_baseline_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'缺失'):local.prepare_revision(self.changed,dict(output_directory=tmp))

    def test_legacy_score_without_hash(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(f.structure,'ROOT',Path(tmp)):
            report=f.generate(self.doc,render=False)
            path=Path(report['output_directory'])/'report.json'
            value=json.loads(path.read_text(encoding='utf-8'));value.pop('score_sha256')
            path.write_text(json.dumps(value),encoding='utf-8')
            self.assertTrue(local.prepare_revision(self.changed,report)['report']['local_revision']['preservation_verified'])


if __name__=='__main__':unittest.main()
