"""P3 memory/transaction behavior. Hand-built notes are structural fixtures."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import curve_project as m
import curve_memory as memory
import curve_session
import curve_store
import curve_workflow as w
from test_curve_workflow import project, material, note, manual_bridge


def fixture(item=None):
    p=project()
    if item is not None:
        p['materials']=[copy.deepcopy(item)]
        p['sources'][0]['length_ticks']=item['length_ticks']
        p['sources'][0]['notes']=[note(length=item['length_ticks'])]
    m.validate(p)
    return p


def points(total, tick, level=1):
    if tick==0:return [dict(tick=0,level=level),dict(tick=total,level=.1)]
    if tick==total:return [dict(tick=0,level=.1),dict(tick=total,level=level)]
    return [dict(tick=0,level=.1),dict(tick=tick,level=level),dict(tick=total,level=.1)]


class MemoryBehavior(unittest.TestCase):
    def legacy_memory(self, p, bound=False):
        lock=copy.deepcopy(manual_bridge()['protections'][0])
        lock.update(id='manual-memory',kind='memory',owner_id='user',
            placement_id='one' if bound else None,component_path=[],
            start_tick=0,end_tick=240,plan_id=None,plan_version=None,
            notes=m.placed_notes(p['placements'][0]) if p['placements'] else [note()],
            input_fingerprint='legacy-content')
        lock['structure_fingerprint']=m.structure_fingerprint(lock)
        return lock

    def assert_legacy_roundtrip(self, p):
        for rev in m.SUPPORTED_CONTRACT_REVS:
            with self.subTest(rev=rev),tempfile.TemporaryDirectory() as tmp:
                p=copy.deepcopy(p);p['contract_rev']=rev;m.validate(p)
                original=curve_store.save(curve_store.new_bundle(p),Path(tmp)/'legacy.json')
                original_bytes=original.read_bytes()
                c=w.Controller();c.load(original)
                self.assertEqual(c.project,p);self.assertTrue(c.state()['is_saved'])
                self.assertFalse(c.state()['can_undo']);self.assertFalse(c.state()['can_redo'])
                saved=c.save_snapshot(Path(tmp)/'copy.json')
                self.assertEqual(curve_store.load(saved)['bundle']['project'],p)
                self.assertEqual(original.read_bytes(),original_bytes)
                self.assertEqual(m.fingerprint(c.project),m.fingerprint(p))

    def test_legacy_unbound_memory_with_and_without_placement_reads_and_saves_exactly(self):
        p=m.edit(fixture(),'place',material_id='A1',start_tick=0,placement_id='one')
        p['protections']=[self.legacy_memory(p)]
        self.assert_legacy_roundtrip(p)
        p['placements']=[]
        self.assert_legacy_roundtrip(p)

    def test_legacy_bound_partial_or_current_variant_memory_retains_original_semantics(self):
        p=m.edit(fixture(),'place',material_id='A1',start_tick=0,placement_id='one')
        lock=self.legacy_memory(p,bound=True)
        lock['end_tick']=120;lock['notes'][0]['duration_tick']=120
        lock['structure_fingerprint']=m.structure_fingerprint(lock);p['protections']=[lock]
        self.assert_legacy_roundtrip(p)
        variant=copy.deepcopy(p['placements'][0]['base_snapshot']);variant['notes'][0]['pitch']=67
        p['placements'][0]['emotion_variant']=variant
        p['protections']=[self.legacy_memory(p,bound=True)]
        self.assert_legacy_roundtrip(p)

    def test_legacy_fixed_memory_not_unlocked_and_managed_memory_still_strict(self):
        p=m.edit(fixture(),'place',material_id='A1',start_tick=0,placement_id='one')
        p['protections']=[self.legacy_memory(p)]
        c=w.Controller(p);c.session.mark_saved();before=c.project
        token=c.capture_job('AUDITION',dict(kind='placement',id='one'))['token']
        for action,args in [('move',dict(placement_id='one',start_tick=480)),
                            ('delete',dict(placement_id='one'))]:
            with self.assertRaises(m.ProjectError):c.edit(action,**args)
            self.assertEqual(c.project,before);self.assertTrue(c.state()['is_saved'])
            self.assertFalse(c.state()['can_undo']);self.assertTrue(c.accepts(token))
        c.edit('set_intensity',points=points(p['total_ticks'],120))
        self.assertEqual(next(x for x in c.project['protections'] if x['id']=='manual-memory'),p['protections'][0])
        automatic=next(x for x in c.project['protections'] if x['id']==memory.managed_id(c.project))
        bad=c.project;target=next(x for x in bad['protections'] if x['id']==automatic['id'])
        target['placement_id']=None
        with self.assertRaises(m.ProjectError):m.validate(bad)
        bad=c.project;target=next(x for x in bad['protections'] if x['id']==automatic['id'])
        target['notes'][0]['pitch']+=1;target['structure_fingerprint']=m.structure_fingerprint(target)
        with self.assertRaises(m.ProjectError):m.validate(bad)

    def test_crossing_memory_legacy_lock_and_bridge_invalidation_save_and_undo(self):
        c=w.Controller(fixture(material(length=4000)))
        c.edit('place',material_id='A1',start_tick=0,placement_id='one')
        p=c.project
        old=self.legacy_memory(p)
        old['notes'][0]['duration_tick']=240
        old['structure_fingerprint']=m.structure_fingerprint(old)
        p['protections'].append(old);c=w.Controller(p)
        c.edit('add_material',material=material('bridge',1920,'bridge'))
        c.edit('place',material_id='bridge',start_tick=5760,placement_id='bridge-use')
        c.session.mark_saved();before=c.project
        bridge=next(x for x in before['protections'] if x['kind']=='bridge')
        c.edit('set_intensity',points=[dict(tick=0,level=.3),dict(tick=before['total_ticks'],level=.25)])
        after=c.project;m.validate(after)
        self.assertEqual(next(x for x in after['protections'] if x['kind']=='bridge'),bridge)
        self.assertEqual(next(x for x in after['protections'] if x['id']=='manual-memory'),old)
        history=after['records'][0]['payload']['audit_context']
        archived=next(x for x in history['protections'] if x['id']==memory.managed_id(after))
        self.assertEqual((archived['start_tick'],archived['end_tick']),(0,1920))
        self.assertEqual(archived['notes'][0]['duration_tick'],4000)
        with tempfile.TemporaryDirectory() as tmp:
            path=c.save_snapshot(Path(tmp)/'bridge-memory.json');loaded=w.Controller();loaded.load(path)
            self.assertEqual(loaded.project,after)
        c.undo();self.assertEqual(c.project,before)
        c.redo();self.assertEqual(c.project,after)
        bad=copy.deepcopy(after)
        archived=next(x for x in bad['records'][0]['payload']['audit_context']['protections']
                      if x['id']==memory.managed_id(after))
        archived['notes'][0]['pitch']+=1
        archived['structure_fingerprint']=m.structure_fingerprint(archived)
        with self.assertRaises(m.ProjectError):m.validate(bad)

    def test_historical_memory_rest_with_bridge_rejects_inserted_notes(self):
        item=material(length=4080,kind='phrase');item['notes']=[note('head',120),note('tail',80,4000)]
        c=w.Controller(fixture(item));c.edit('place',material_id='A1',start_tick=0)
        c.edit('set_intensity',points=points(c.project['total_ticks'],2100))
        c.edit('add_material',material=material('bridge',1920,'bridge'))
        c.edit('place',material_id='bridge',start_tick=5760)
        c.edit('set_intensity',points=points(c.project['total_ticks'],2200))
        p=c.project;m.validate(p)
        history=p['records'][0]['payload']['audit_context']
        archived=next(x for x in history['protections'] if x['kind']=='memory')
        self.assertEqual(archived['notes'],[])
        placement=history['placements'][0]
        variant=copy.deepcopy(placement['base_snapshot']);variant['notes'].append(note('intruder',100,2000))
        placement['emotion_variant']=variant
        with self.assertRaises(m.ProjectError):m.validate(p)

    def test_chosen_variant_pitch_short_tail_persists_not_original_source(self):
        item=material(length=240);item['notes'][0]['pitch']=67
        c=w.Controller(fixture(item));c.edit('place',material_id='A1',start_tick=0,placement_id='chosen')
        lock=c.project['protections'][0]
        self.assertEqual(lock['notes'][0]['pitch'],67)
        self.assertEqual(c.project['sources'][0]['notes'][0]['pitch'],60)
        self.assertEqual((lock['start_tick'],lock['end_tick']),(0,240))
        before=c.project
        with tempfile.TemporaryDirectory() as tmp:
            path=c.save_snapshot(Path(tmp)/'memory.json');loaded=w.Controller();loaded.load(path)
            self.assertEqual(loaded.project,before);self.assertTrue(loaded.state()['is_saved'])
            self.assertEqual(loaded.state()['memory_info'],c.state()['memory_info'])

    def test_equal_peak_boundary_endpoint_gap_and_blank_are_distinct(self):
        c=w.Controller(fixture(material(length=1920)));total=c.project['total_ticks']
        c.edit('place',material_id='A1',start_tick=0,placement_id='first')
        c.edit('place',material_id='A1',start_tick=1920,placement_id='second')
        c.edit('place',material_id='A1',start_tick=total-1920,placement_id='last')
        c.edit('set_intensity',points=[dict(tick=0,level=.1),dict(tick=1920,level=.9),
            dict(tick=3000,level=.9),dict(tick=total,level=.1)])
        info=c.state()['memory_info'];self.assertEqual(info['peak_tick'],1920);self.assertEqual(info['placement_id'],'second')
        c.edit('set_intensity',points=points(total,total))
        info=c.state()['memory_info'];self.assertEqual(info['lookup_tick'],total-1);self.assertEqual(info['placement_id'],'last')
        c.edit('delete',placement_id='last');self.assertEqual(c.state()['memory_info']['state'],'PENDING_GAP')
        self.assertFalse(c.project['protections'])
        c.edit('mark_blank',start_tick=total-1920,end_tick=total)
        self.assertEqual(c.state()['memory_info']['state'],'PRESERVE_BLANK');self.assertFalse(c.project['protections'])

    def test_nested_combination_is_one_placement_with_actual_component_range(self):
        c=w.Controller(fixture())
        inner=w.combine(c.project,['A1','A1'])
        c.edit('add_material',material=inner)
        outer=w.combine(c.project,[inner['id'],'A1'])
        c.edit('add_material',material=outer)
        c.edit('place',material_id=outer['id'],start_tick=1200,placement_id='combo')
        total=c.project['total_ticks'];c.edit('set_intensity',points=points(total,1500))
        info=c.state()['memory_info']
        self.assertEqual(len(info['component_path']),2)
        self.assertEqual(info['range'],dict(start_tick=1440,end_tick=1680))
        self.assertEqual(len(c.project['placements']),1)
        self.assertEqual(c.project['placements'][0]['length_ticks'],720)
        c.edit('set_intensity',points=points(total,1850))
        self.assertEqual(c.state()['memory_info']['range'],dict(start_tick=1680,end_tick=1920))
        self.assertEqual(len(c.state()['memory_info']['component_path']),1)

    def test_long_crossing_note_is_complete_and_whole_support_is_immutable(self):
        item=material(length=5000,kind='phrase');item['notes']=[note(length=4000)]
        c=w.Controller(fixture(item));c.edit('place',material_id='A1',start_tick=0,placement_id='long')
        c.edit('set_intensity',points=points(c.project['total_ticks'],2200))
        lock=c.project['protections'][0]
        self.assertEqual((lock['start_tick'],lock['end_tick']),(1920,3840))
        self.assertEqual((lock['notes'][0]['start_tick'],lock['notes'][0]['duration_tick']),(0,4000))
        bad=copy.deepcopy(c.project);variant=copy.deepcopy(item);extra=note('intruder',100,100)
        variant['notes'].append(extra);bad['placements'][0]['emotion_variant']=variant
        with self.assertRaises(m.ProjectError):m.validate(bad)
        strict=copy.deepcopy(lock);strict['kind']='theme'
        with self.assertRaises(m.ProjectError):m.protection_check(strict,c.project['total_ticks'],
            m.indexed(c.project['placements']),m.source_index(c.project['sources']))

    def test_internal_full_rest_is_bound_ready_without_fake_blank(self):
        item=material(length=4080,kind='phrase')
        item['notes']=[note('head',120),note('tail',80,4000)]
        c=w.Controller(fixture(item));c.edit('place',material_id='A1',start_tick=0)
        c.edit('set_intensity',points=points(c.project['total_ticks'],2100))
        info=c.state()['memory_info'];self.assertEqual(info['state'],'BOUND')
        lock=c.project['protections'][0];self.assertEqual(lock['notes'],[]);self.assertEqual(lock['blank_mask'],[])
        self.assertEqual(lock['status'],'CONTENT_READY');m.validate(c.project)
        bad=copy.deepcopy(c.project);variant=copy.deepcopy(item);variant['notes'].append(note('added',100,2000))
        bad['placements'][0]['emotion_variant']=variant
        with self.assertRaises(m.ProjectError):m.validate(bad)

    def test_move_and_delete_recompute_atomically_without_moving_curve(self):
        c=w.Controller(fixture());c.edit('place',material_id='A1',start_tick=0,placement_id='one')
        before=c.project;line=before['intensity_points']
        c.edit('move',placement_id='one',start_tick=240)
        self.assertEqual(c.project['intensity_points'],line);self.assertFalse(c.project['protections'])
        self.assertEqual(c.state()['memory_info']['state'],'PENDING_GAP')
        c.undo();self.assertEqual(c.project,before)
        c.edit('set_intensity',points=points(c.project['total_ticks'],120))
        c.edit('delete',placement_id='one')
        self.assertFalse(c.project['placements']);self.assertFalse(c.project['protections'])
        c.undo();self.assertEqual(c.state()['memory_info']['placement_id'],'one')

    def test_callback_failure_is_whole_transaction_with_saved_redo_and_token(self):
        c=w.Controller(fixture());c.edit('place',material_id='A1',start_tick=0,placement_id='one')
        c.session.mark_saved();c.edit('set_melody_only',value=True);c.undo()
        before=c.project;state=c.state();token=c.capture_job('AUDITION',dict(kind='placement',id='one'))['token']
        callbacks=[lambda a,b: (_ for _ in ()).throw(RuntimeError('failed compute')),
            lambda a,b: dict(automatic_memory=None,emotion_variants={}),
            lambda a,b: dict(automatic_memory=memory.expected_protection(b),emotion_variants={'alien':None})]
        for callback in callbacks:
            with patch.object(c.session,'_recompute',callback):
                with self.assertRaises((RuntimeError,m.ProjectError)):
                    c.edit('set_intensity',points=points(before['total_ticks'],120))
            self.assertEqual(c.project,before)
            self.assertEqual(c.state()['can_redo'],state['can_redo']);self.assertEqual(c.state()['can_undo'],state['can_undo'])
            self.assertTrue(c.state()['is_saved']);self.assertTrue(c.accepts(token))

    def test_callback_cannot_change_fixed_bridge_or_memory_rest(self):
        c=w.Controller(manual_bridge());total=c.project['total_ticks']
        c.edit('set_intensity',points=points(total,2000));before=c.project
        def corrupt(a,b):
            item=copy.deepcopy(b['placements'][0]['base_snapshot']);item['notes'][0]['pitch']+=1
            return dict(automatic_memory=memory.expected_protection(b),emotion_variants={'P':item})
        with patch.object(c.session,'_recompute',corrupt):
            with self.assertRaises(m.ProjectError):c.edit('set_intensity',points=points(total,2100))
        self.assertEqual(c.project,before)
        old_bridge=next(p for p in before['protections'] if p['kind']=='bridge')
        c.edit('move',placement_id='P',start_tick=4800)
        new_bridge=next(p for p in c.project['protections'] if p['kind']=='bridge')
        self.assertEqual(new_bridge['plan_version'],old_bridge['plan_version']+1)
        self.assertFalse(any(p['kind']=='memory' for p in c.project['protections']))
        c.undo();self.assertEqual(c.project,before)

    def test_failed_automatic_bridge_is_not_unlocked_by_memory_recompute(self):
        p=manual_bridge();lock=p['protections'][0];plan=p['records'][0]
        lock.update(origin='automatic',status='RANGE_LOCKED',notes=[],structure_fingerprint=None)
        plan.update(status='FAILED');plan['payload'].update(automatic_decision='selected',bridge_ids=['P'],manual_bridge_ids=[],
            ranges=[dict(start_tick=lock['start_tick'],end_tick=lock['end_tick'])])
        m.validate(p);c=w.Controller(p)
        c.edit('set_intensity',points=points(p['total_ticks'],100))
        bridge=next(q for q in c.project['protections'] if q['kind']=='bridge')
        self.assertEqual(bridge,lock)
        before=c.project
        with self.assertRaises(m.ProjectError):c.edit('move',placement_id='P',start_tick=4800)
        self.assertEqual(c.project,before)

    def test_changed_intensity_then_undo_still_invalidates_old_async_result(self):
        c=w.Controller(fixture());c.edit('place',material_id='A1',start_tick=0,placement_id='one')
        c.edit('place',material_id='A1',start_tick=480,placement_id='two')
        token=c.capture_job('AUDITION',dict(kind='placement',id='two'))['token'];before=c.project
        c.edit('set_intensity',points=points(c.project['total_ticks'],500));c.undo()
        self.assertEqual(c.project,before);self.assertFalse(c.accepts(token));self.assertFalse(c.cancel_job(token))
        combo=w.combine(c.project,['A1','A1']);batch=dict(sources=[],materials=[combo],warnings=[])
        self.assertFalse(c.apply_batch(batch,token)['changed'])
        current=c.capture_job('COMBINE')['token'];self.assertTrue(c.apply_batch(batch,current)['changed'])
        self.assertFalse(c.apply_batch(batch,current)['changed']);self.assertEqual(len(c.project['materials']),2)

    def test_trace_retains_peak_valley_plateau_and_commits_once(self):
        total=15360
        trace=[dict(tick=300,level=.2),dict(tick=500,level=.9),dict(tick=520,level=.9),
            dict(tick=570,level=.2),dict(tick=700,level=.5),dict(tick=700,level=.6),dict(tick=900,level=.7)]
        normalized=memory.normalize_trace(trace,total,tolerance=.1)
        self.assertIn(dict(tick=500,level=.9),normalized);self.assertIn(dict(tick=520,level=.9),normalized)
        self.assertIn(dict(tick=570,level=.2),normalized);self.assertEqual(normalized[0]['tick'],0);self.assertEqual(normalized[-1]['tick'],total)
        c=w.Controller(fixture());before=c.project;c.edit('set_intensity',points=normalized)
        for tick in range(0,total+1,61):self.assertTrue(0<=m.intensity_at(c.project,tick)<=1)
        self.assertEqual(c.state()['memory_info']['peak_tick'],500)
        self.assertTrue(c.undo());self.assertEqual(c.project,before);self.assertFalse(c.undo())

    def test_trace_invalid_and_noop_do_not_change_history_or_saved_state(self):
        c=w.Controller(fixture());c.session.mark_saved();c.edit('set_melody_only',value=True);c.undo()
        before=c.project
        self.assertFalse(c.edit('set_intensity',points=before['intensity_points']))
        self.assertTrue(c.state()['can_redo']);self.assertTrue(c.state()['is_saved'])
        for trace in ([],[dict(tick=-1,level=.5)],[dict(tick=1,level=float('nan'))],[dict(tick=1,level=1.1)]):
            with self.assertRaises(m.ProjectError):memory.normalize_trace(trace,before['total_ticks'])
        self.assertEqual(c.project,before);self.assertTrue(c.state()['can_redo'])

    def test_flat_trace_simplifies_without_losing_earliest_peak(self):
        normalized=memory.normalize_trace([dict(tick=tick,level=.25) for tick in range(0,1001,10)],1000)
        self.assertEqual(normalized,[dict(tick=0,level=.25),dict(tick=1000,level=.25)])

    def test_existing_p2_saved_content_is_not_recomputed_on_read_or_save(self):
        p=m.edit(fixture(), 'place', material_id='A1', start_tick=0, placement_id='one')
        self.assertFalse(p['protections'])
        with tempfile.TemporaryDirectory() as tmp:
            path=curve_store.save(curve_store.new_bundle(p),Path(tmp)/'p2.json')
            c=w.Controller();c.load(path)
            self.assertEqual(c.project,p);self.assertTrue(c.state()['is_saved'])
            self.assertIsNone(c.state()['memory_info']['protection_id'])
            saved=c.save_snapshot(Path(tmp)/'same.json')
            self.assertEqual(curve_store.load(saved)['bundle']['project'],p)
            c.edit('set_melody_only',value=True)
            self.assertEqual(len(c.project['protections']),1)
            c.undo();self.assertEqual(c.project,p);self.assertTrue(c.state()['is_saved'])


if __name__=='__main__':unittest.main()
