"""Behavior contracts for reusable snapshots, ordered uses and actual score inputs."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
import assembly as a
import default_melody
import story_engine as engine
import intensity_curve
import studio_model


def scenario():
    p=a.new_project(default_melody.source())
    b=default_melody.source();b['id']='B';b['name']='长中文 English 原始旋律';b['notes']=[dict(n,pitch=n['pitch']+2) for n in b['notes']]
    p=a.add_source(p,b);A=p['library'][:3];B=next(m for m in p['library'] if m['name']=='B1')
    p=a.save_combination(p,[A[1],B],'C');C=p['library'][-1]
    for m in (A[0],C,A[2]):p=a.insert(p,m['id'])
    return p


class AssemblyTests(unittest.TestCase):
    def test_empty_and_default_blocks_are_separate(self):
        p=a.new_project(default_melody.source());self.assertFalse(p['uses']);self.assertEqual(p['duration'],0)
        self.assertTrue(p['library']);engine.validate(p,False)
        with self.assertRaisesRegex(ValueError,'拖入'):engine.plan(p)

    def test_splitting_rest_short_tail_and_crossing_note(self):
        s=default_melody.source();s['ticks']=4300;s['notes']=[dict(start=1800,duration=300,pitch=60,velocity=80)]
        p=a.new_project(s);self.assertEqual([m['ticks'] for m in p['library']],[1920,1920,460])
        self.assertEqual(p['library'][0]['notes'][0]['duration'],120)
        self.assertEqual(p['library'][1]['notes'][0]['start'],0);self.assertEqual(p['library'][1]['notes'][0]['duration'],180)
        self.assertFalse(p['library'][2]['notes'])
        p=a.insert(p,p['library'][2]['id']);p['melody_only']=True
        plan=engine.plan(p);score=engine.compile_score(plan)
        self.assertEqual(plan['total_ticks'],460);self.assertFalse(score['layers']);self.assertEqual(len(plan['blocks']),1)

    def test_nested_noncontiguous_repeated_combination_snapshots(self):
        p=scenario();A=p['library'][:3];B=next(m for m in p['library'] if m['name']=='B1')
        p=a.save_combination(p,[A[1],B,A[1]],'C重复');C=p['library'][-1]
        self.assertEqual(a.composition(C),'A2＋B1＋A2')
        p=a.save_combination(p,[C,A[2],C],'嵌套');m=p['library'][-1]
        self.assertEqual([v['name'] for v in a.leaves(m)],['A2','B1','A2','A3','A2','B1','A2'])
        p=a.insert(p,m['id']);old=copy.deepcopy(p['uses'][-1]['material'])
        p['library'][-1]['name']='改名';self.assertEqual(p['uses'][-1]['material'],old)
        engine.validate(p)

    def test_repeats_emotions_identity_and_time_anchored_curve(self):
        p=scenario();p=a.insert(p,p['uses'][0]['material_id']);p=a.paint(p,[0],'crisis')
        self.assertEqual(p['uses'][-1]['emotion'],'calm');self.assertNotEqual(p['uses'][0]['id'],p['uses'][-1]['id'])
        p['intensity_points']=[dict(time=0,level=.2),dict(time=3,level=.9),dict(time=10,level=.4)]
        moved=a.reorder(p,0,2);self.assertEqual(moved['intensity_points'],p['intensity_points']);self.assertEqual(moved['uses'][2]['emotion'],'crisis')
        appended=a.insert(moved,moved['library'][0]['id']);self.assertEqual(appended['intensity_points'][-1],dict(time=12,level=.4))
        deleted=a.delete(appended,[0]);self.assertEqual(deleted['duration'],8)
        self.assertEqual(deleted['intensity_points'][-1]['level'],intensity_curve.evaluate(appended['intensity_points'],8))
        self.assertEqual(deleted['uses'][1]['id'],moved['uses'][2]['id'])
        self.assertEqual(a.change_bpm(p,60)['duration'],20)

    def test_generator_uses_exact_assembly_order_and_component_boundaries(self):
        p=scenario();p=a.paint(p,[1],'suspense');p=a.paint(p,[2],'crisis')
        p['intensity_points']=[dict(time=0,level=.2),dict(time=6.5,level=.9),dict(time=8,level=.3)]
        plan=engine.plan(p);score=engine.compile_score(plan)
        self.assertEqual(plan['total_ticks'],7680);self.assertEqual(score['report']['duration_seconds'],8)
        self.assertEqual([v['name'] for v in plan['assembly_blocks']],['A1','C','A3'])
        owners=[r['assembly_order'] for r in plan['blocks']];self.assertEqual(owners,sorted(owners));self.assertEqual(set(owners),{0,1,2})
        for row in plan['blocks']:
            use=p['uses'][row['assembly_order']];self.assertEqual(row['use_id'],use['id']);self.assertEqual(row['assembly_material_id'],use['material_id'])
            self.assertTrue(row['assembly_sources']);self.assertEqual(row['assembly_sources'][0]['start_tick'],row['start_tick'])
        self.assertEqual([leaf['name'] for r in plan['blocks'] if r['assembly_order']==1 for leaf in r['assembly_sources']],['A2','B1'])
        self.assertEqual(plan['anchors'][0]['use_id'],p['uses'][2]['id'])
        self.assertEqual(engine.automatic_peak_anchor(p)['use_id'],p['uses'][2]['id'])
        self.assertEqual(p,plan['project'])

    def test_local_grid_does_not_requantize_short_combo_boundaries(self):
        s=default_melody.source();s['ticks']=2160;s['notes']=a.notes_in(s['notes'],0,2160)
        p=a.new_project(s);tail=p['library'][1];full=p['library'][0]
        p=a.save_combination(p,[tail,full,tail],'短边界');p=a.insert(p,p['library'][-1]['id'])
        plan=engine.plan(p);self.assertEqual([(r['start_tick'],r['end_tick']) for r in plan['blocks']],[(0,240),(240,2160),(2160,2400)])
        self.assertEqual(plan['total_ticks'],2400)

    def test_no_legacy_source_or_duration_limits_and_save_reopen(self):
        p=a.new_project()
        for i in range(13):
            s=default_melody.source();s['id']='source'+str(i);p=a.add_source(p,s)
        p=a.save_combination(p,[p['library'][0]]*70,'长组合');p=a.insert(p,p['library'][-1]['id'])
        engine.validate(p);self.assertEqual(engine.plan(p)['total_ticks'],134400)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'工程 中文.json'
            studio_model.save_project(studio_model.materials.new_pool(),None,[dict(emotion='calm',start=.2,end=.4)],[],{'story':p},path=path)
            reopened=studio_model.load_project(path)['settings']['story'];self.assertEqual(reopened,p);engine.validate(reopened)
        legacy=engine.new_project();legacy['sources']=[default_melody.source()]
        self.assertEqual(engine.plan(legacy)['project']['schema'],engine.SCHEMA)

    def test_bad_snapshots_rejected_without_silent_normalization(self):
        p=scenario()
        for mutate in (lambda q:q['uses'][0].update(material_id='wrong'),lambda q:q['uses'][0].update(id=q['uses'][1]['id']),lambda q:q.update(duration=99),lambda q:q['uses'][1]['material']['components'].reverse()):
            q=copy.deepcopy(p);mutate(q)
            with self.assertRaises((ValueError,KeyError)):engine.validate(q)

    def test_automatic_variations_keep_repeat_use_mapping_and_connections(self):
        p=scenario();ident=p['library'][0]['id']
        p['uses']=[];p=a.normalize(p)
        for i in range(4):p=a.insert(p,ident)
        p['intensity_points']=[dict(time=0,level=.2),dict(time=7,level=.9),dict(time=8,level=.3)]
        plan=engine.plan(p)
        self.assertEqual([b['version'] for b in plan['blocks']],['original','variant','answer','original'])
        self.assertEqual([b['assembly_order'] for b in plan['blocks']],[0,1,2,3])
        self.assertEqual(len(engine.compile_score(plan)['report']['boundaries']),3)
        self.assertEqual(plan['total_ticks'],7680)

    def test_generator_reads_each_use_snapshot_even_with_same_reusable_id(self):
        p=a.new_project(default_melody.source());ident=p['library'][0]['id']
        p=a.insert(a.insert(p,ident),ident)
        p['uses'][1]['material']['notes']=[dict(n,pitch=n['pitch']+12) for n in p['uses'][1]['material']['notes']]
        engine.validate(p);plan=engine.plan(p)
        bank=plan['source_catalog'];self.assertEqual(len(bank),2)
        self.assertEqual(bank[0]['id'],p['uses'][0]['id']);self.assertEqual(bank[1]['id'],p['uses'][1]['id'])
        self.assertEqual(bank[1]['notes'],p['uses'][1]['material']['notes'])
        self.assertGreater(min(n['pitch'] for n in plan['blocks'][1]['notes']),min(n['pitch'] for n in plan['blocks'][0]['notes']))

    def test_secondary_role_setting_reaches_material_and_use_snapshots(self):
        p=scenario();sid=p['sources'][1]['id'];changed=a.set_source_role(p,sid,'climax')
        leaf=next(m for m in changed['library'] if m['name']=='B1');self.assertEqual(leaf['role'],'climax')
        self.assertEqual(changed['uses'][1]['material']['components'][1]['role'],'climax')
        self.assertEqual(changed['uses'][1]['material']['notes'],p['uses'][1]['material']['notes'])
        self.assertEqual(changed['duration'],p['duration']);engine.validate(changed)
