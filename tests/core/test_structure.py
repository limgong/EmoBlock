import copy
import tempfile
import unittest
from pathlib import Path
import structure_engine as e
from runtime_config import ASSETS


def fixture():
    pool=e.materials.new_pool()
    source=ASSETS/'theme-c.mid'
    themes=[]
    for name in 'ABCD':
        theme=e.materials.import_theme(source,name=name); e.materials.add_item(pool,theme); themes.append(theme)
    variant=e.materials.generate_candidates(themes[1],'variant',31)[0]; variant['accepted']=True; variant['name']='B_c1'; e.materials.add_item(pool,variant)
    answer=e.materials.generate_candidates(themes[1],'answer',31)[0]; answer['accepted']=True; answer['name']='E'; e.materials.add_item(pool,answer)
    answer_variant=e.materials.generate_candidates(answer,'variant',32)[0]; answer_variant['accepted']=True; e.materials.add_item(pool,answer_variant)
    return pool,themes,variant,answer,answer_variant


class Tests(unittest.TestCase):
    def setUp(self):
        self.pool,self.themes,self.variant,self.answer,self.av=fixture()
        self.doc=e.create(self.pool,[i['id'] for i in self.themes])
        self.a,self.b,self.c,self.d=[s['id'] for s in self.doc['backbone']]

    def test_order_fixed(self):
        self.doc['placements']=[self.doc['placements'][i] for i in (0,2,3,1)]
        with self.assertRaises(ValueError):e.validate(self.doc)

    def test_missing_slot(self):
        self.doc['placements'].pop(1)
        with self.assertRaises(ValueError):e.validate(self.doc)

    def test_repeat_slot(self):
        item=copy.deepcopy(self.doc['placements'][0]); item['id']=e.uid(); self.doc['placements'].insert(1,item)
        with self.assertRaises(ValueError):e.validate(self.doc)

    def test_backbone_reorder(self):
        self.doc['backbone'].reverse()
        with self.assertRaises(ValueError):e.validate(self.doc)

    def test_replace_correct(self):
        result=e.edit(self.doc,'replace',slot_id=self.b,material_id=self.variant['id'])
        self.assertEqual(e.timeline(result)['rows'][1]['name'],'B_c1')

    def test_wrong_family_transaction(self):
        before=copy.deepcopy(self.doc)
        with self.assertRaises(ValueError):e.edit(self.doc,'replace',slot_id=self.c,material_id=self.variant['id'])
        self.assertEqual(before,self.doc)

    def test_answer_not_theme_variant(self):
        with self.assertRaises(ValueError):e.edit(self.doc,'replace',slot_id=self.b,material_id=self.av['id'])

    def test_answer_after_source(self):
        result=e.edit(self.doc,'insert',slot_id=self.b,material_id=self.answer['id'])
        self.assertEqual([r['name'] for r in e.timeline(result)['rows']],['A','B','E','C','D'])
        self.assertEqual(e.timeline(result)['bars'],20)

    def test_wrong_insertion(self):
        with self.assertRaises(ValueError):e.edit(self.doc,'insert',slot_id=self.c,material_id=self.answer['id'])

    def test_explicit_authorize(self):
        with self.assertRaises(ValueError):e.edit(self.doc,'authorize',slot_id=self.c,material_id=self.answer['id'])
        result=e.edit(self.doc,'authorize',slot_id=self.c,material_id=self.answer['id'],confirmed=True)
        result=e.edit(result,'insert',slot_id=self.c,material_id=self.answer['id'])
        e.validate(result)

    def test_answer_variant_allowed(self):
        e.validate(e.edit(self.doc,'insert',slot_id=self.b,material_id=self.av['id']))

    def test_unaccepted_rejected(self):
        self.doc['pool']['items'][-2]['accepted']=False
        with self.assertRaises(ValueError):e.edit(self.doc,'insert',slot_id=self.b,material_id=self.answer['id'])

    def test_remove_only_insert(self):
        with self.assertRaises(ValueError):e.edit(self.doc,'remove_insert',entry_id=self.doc['placements'][0]['id'])
        result=e.edit(self.doc,'insert',slot_id=self.b,material_id=self.answer['id'])
        result=e.edit(result,'remove_insert',entry_id=result['placements'][2]['id'])
        self.assertEqual(e.timeline(result)['bars'],16)

    def test_roundtrip_and_original_unchanged(self):
        before=copy.deepcopy(self.pool)
        result=e.edit(self.doc,'role',slot_id=self.a,role='起句')
        with tempfile.TemporaryDirectory() as tmp:
            path=e.save(result,Path(tmp)/'structure.json')
            self.assertEqual(e.load(path),result)
            with self.assertRaises(FileExistsError):e.save(result,path)
        self.assertEqual(before,self.pool)


if __name__=='__main__':unittest.main()
