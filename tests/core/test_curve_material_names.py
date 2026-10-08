"""Persisted category, ancestry, combination and atomic undo naming."""
import copy
import unittest
import curve_material_names as names
import curve_project as model
import curve_workflow
from test_curve_workflow import project, material

class MaterialNameTests(unittest.TestCase):
    def batch(self,controller,values,kind='IMPORT',target=None):
        captured=controller.capture_job(kind,target)
        result=controller.apply_batch(dict(sources=[],materials=values,warnings=[]),captured['token'])
        self.assertTrue(result['changed'])
        return controller.state()['project']['materials'][-len(values):]

    def test_numbering_multiple_import_and_reopen_does_not_depend_on_view(self):
        controller=curve_workflow.Controller(project())
        values=[material('new1'),material('new2')]
        added=self.batch(controller,values)
        self.assertEqual([names.short_name(m) for m in added],['A1','A2'])
        saved=copy.deepcopy(controller.state()['project'])
        reopened=curve_workflow.Controller(saved)
        added=self.batch(reopened,[material('new3')])
        self.assertEqual(names.short_name(added[0]),'A3')
        reopened.undo();self.assertEqual(reopened.state()['project'],saved)

    def test_derived_prime_repeat_and_chain_keep_input_identity(self):
        controller=curve_workflow.Controller(project())
        target=self.batch(controller,[material('leaf')])[0]
        def derive(ident,base):
            value=copy.deepcopy(base);value.update(id=ident,generation={'method':'answer'},phrase_id=None)
            return self.batch(controller,[value],'DERIVE',dict(kind='material',id=base['id']))[0]
        first=derive('first',target);second=derive('second',target)
        self.assertEqual([names.short_name(m) for m in (first,second)],['A1′','A1′(2)'])
        child=derive('child',first);self.assertEqual(names.short_name(child),'A1′′')
        self.assertEqual(target,controller.state()['project']['materials'][-4])

    def test_automatic_categories_and_nested_combination(self):
        p=project();p['materials'][0]['label']='A8';controller=curve_workflow.Controller(p)
        generated=material('new');generated['generation']={'method':'answer'}
        bridge=material('bridge');bridge['generation']={'method':'bridge_phrase'}
        added=self.batch(controller,[generated,bridge]);self.assertEqual([names.short_name(m) for m in added],['B1','C1'])
        current=controller.state()['project'];a=current['materials'][0];b=added[0]
        combo=curve_workflow.combine(current,[a,b],'ignored')
        combined=self.batch(controller,[combo],'COMBINE')[0]
        self.assertEqual(names.short_name(combined),'A8+B1')
        current=controller.state()['project']
        nested=curve_workflow.combine(current,[combined,a],'ignored')
        result=self.batch(controller,[nested],'COMBINE')[0]
        self.assertEqual(names.short_name(result),'A8+B1+A8')
        model.validate(controller.state()['project'])

    def test_persisted_name_and_arbitrary_display_label_do_not_forge_identity(self):
        item=material('unchanged');original=names.short_name(item)
        item['label']='rename';self.assertEqual(names.short_name(item),original)
        item['label']='rename · M27';self.assertEqual(names.short_name(item),'M27')

    def test_hidden_original_slice_reuses_visible_number(self):
        controller=curve_workflow.Controller(project())
        standard=material('standard');standard['provenance']['source_start_tick']=1920
        phrase=material('parent',kind='phrase');phrase['provenance']['source_start_tick']=1920
        child=copy.deepcopy(standard);child.update(id='slice',phrase_id='parent')
        added=self.batch(controller,[standard,phrase,child])
        self.assertEqual([names.short_name(m) for m in (added[0],added[2])],['A1','A1'])
        next_import=self.batch(controller,[material('next')])[0]
        self.assertEqual(names.short_name(next_import),'A2')
