"""P4 independent actual-music gates and staging persistence, no mocked audio."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import curve_candidates as c
import curve_project as m
import curve_store as store
import curve_workflow as w
import curve_memory
from test_curve_workflow import project, material, manual_bridge


def fixture():
    p = project()
    p = m.edit(p, 'resize', grid_count=2)
    p = m.edit(p, 'add_material', material=material('left', 1200))
    p = m.edit(p, 'add_material', material=material('right', 1920))
    controller = w.Controller(p)
    controller.edit('place', material_id='left', start_tick=0, placement_id='left-use')
    controller.edit('place', material_id='right', start_tick=1440, placement_id='right-use')
    return controller


def score():
    v = {key: .5 for key in c.WEIGHTS}
    return dict(v, total=sum(v[k]*weight for k, weight in c.WEIGHTS.items()))


def proposal(request, material_id='A1', emotion='calm'):
    mat = next(v for v in request['project']['materials'] if v['id'] == material_id)
    items = []
    for gap in request['target_gaps']:
        for start in range(gap['start_tick'], gap['end_tick'], mat['length_ticks']):
            items.append(dict(gap_id=gap['id'], start_tick=start, material=copy.deepcopy(mat), emotion=emotion))
    return dict(id='raw', placements=items, score=score(), reasons=[])


def raw(proposals):
    return dict(proposals=proposals, search=dict(expansions=len(proposals), generated_notes=0,
                termination='RAW_POOL_EXHAUSTED', raw_termination='RAW_POOL_EXHAUSTED', rejections=[]), error=None)


def prepared(request, proposals):
    module = types.SimpleNamespace(propose=lambda *a, **k: raw(proposals))
    with patch.dict('sys.modules', curve_completion=module):
        return c.prepare_completion(request)


class CandidateTests(unittest.TestCase):
    def test_exact_240_selected_current_music_unchanged_other_gap_retained(self):
        controller = fixture(); p = controller.project
        gap = controller.gap_items()[0]
        self.assertEqual((gap['start_tick'], gap['end_tick']), (1200, 1440))
        request = c.make_request(p, gap['id'])
        value = prepared(request, [proposal(request)])
        self.assertEqual(value['status'], 'INSUFFICIENT')
        candidate = value['candidates'][0]; c.validate_candidate(request, candidate)
        self.assertEqual(candidate['project']['placements'][:2], p['placements'])
        self.assertEqual(candidate['project']['total_ticks'], p['total_ticks'])
        self.assertEqual(candidate['project']['intensity_points'], p['intensity_points'])
        self.assertEqual([(g['start_tick'],g['end_tick']) for g in candidate['remaining_gaps']], [(3360,3840)])
        self.assertEqual(candidate['base_write_ranges'], [dict(start_tick=1200,end_tick=1440)])
        self.assertEqual(candidate['project']['materials'], p['materials'])
        self.assertEqual(controller.project, p)
        self.assertEqual(value['unresolved_targets'], [])
        self.assertFalse(candidate['capabilities']['can_apply'])

    def test_snapshot_revalidation_and_budgets(self):
        p = fixture().project; req = c.make_request(p)
        bad = copy.deepcopy(req); bad['target_gaps'][0]['end_tick'] -= 1
        with self.assertRaises(m.ProjectError): c.validate_request(bad)
        bad = copy.deepcopy(req); bad['contexts'][0]['left_notes'][0]['pitch'] += 1
        with self.assertRaises(m.ProjectError): c.validate_request(bad)
        for budget in [dict(max_expansions=True),dict(max_candidates=9),dict(unknown=1)]:
            with self.assertRaises(m.ProjectError): c.make_request(p,budget=budget)
        p = m.edit(p,'set_melody_only',value=True)
        with self.assertRaises(m.ProjectError) as exc: c.make_request(p,req['target_gaps'][0]['id'])
        self.assertEqual(exc.exception.code,'STALE_GAP')

    def test_empty_placeholder_partial_and_mixed_empty_rejected(self):
        controller = fixture(); p = controller.project
        empty = material('empty',120); empty['notes']=[]
        short = material('short',120)
        p=m.edit(p,'add_material',material=empty);p=m.edit(p,'add_material',material=short)
        req=c.make_request(p,c.gap_items(p)[0]['id']);item=proposal(req)
        half=proposal(req,'short')['placements'][0]
        cases=[[],[half], [dict(half,material=empty),dict(half,start_tick=1320)]]
        for items in cases:
            with self.subTest(items=items):
                value=prepared(req,[dict(item,placements=items)])
                self.assertEqual(value['status'],'FAILED');self.assertEqual(value['candidates'],[])
        bad=copy.deepcopy(item);bad['placements'][0]['material']['notes']=[]
        self.assertEqual(prepared(req,[bad])['status'],'FAILED')

    def test_active_blank_and_internal_rest_not_gaps(self):
        p=project(); rest=material('rests',1920);rest['notes'][0].update(start_tick=1680,duration_tick=240)
        p=m.edit(p,'add_material',material=rest);p=m.edit(p,'place',material_id='rests',start_tick=0)
        p=m.edit(p,'mark_blank',start_tick=1920,end_tick=2400,blank_id='blank',reason='主动')
        self.assertEqual([(g['start_tick'],g['end_tick']) for g in c.gap_items(p)],[(2400,15360)])

    def test_actual_post_music_de_dupe_and_third_pitch_survives(self):
        controller=fixture();p=controller.project
        second=material('same');other=material('different');other['notes'][0]['pitch']=67
        p=m.edit(p,'add_material',material=second);p=m.edit(p,'add_material',material=other)
        req=c.make_request(p,c.gap_items(p)[0]['id'])
        value=prepared(req,[proposal(req,'A1'),proposal(req,'same'),proposal(req,'different')])
        self.assertEqual(value['status'],'SUCCEEDED');self.assertEqual(len(value['candidates']),2)
        self.assertEqual(value['search']['termination'],'ENOUGH_CANDIDATES')
        self.assertEqual(value['search']['raw_termination'],'RAW_POOL_EXHAUSTED')
        self.assertEqual(value['differences'][0]['types'],['pitch'])
        self.assertNotEqual(*[v['music_fingerprint'] for v in value['candidates']])
        one=prepared(req,[proposal(req,'A1'),proposal(req,'same')])
        self.assertEqual(one['status'],'INSUFFICIENT');self.assertTrue(one['shortage_reasons'])
        bad=copy.deepcopy(value);bad['candidates'].append(copy.deepcopy(bad['candidates'][0]))
        with self.assertRaises(m.ProjectError):c.validate_outcome(req,bad)

    def test_derived_fields_and_outside_music_are_not_trusted(self):
        req=c.make_request(fixture().project);candidate=prepared(req,[proposal(req)])['candidates'][0]
        for key,value in [('notes',[]),('remaining_gaps',[dict(id='fake',start_tick=0,end_tick=1)]),('protection_summary','fake'),('memory_info',{})]:
            bad=copy.deepcopy(candidate);bad[key]=value
            with self.subTest(key=key),self.assertRaises(m.ProjectError):c.validate_candidate(req,bad)
        bad=copy.deepcopy(candidate);bad['project']['placements'][1]['emotion']='hope'
        with self.assertRaises(m.ProjectError):c.validate_candidate(req,bad)

    def test_provenance_is_object_and_stored_emotion_validation_never_generates(self):
        import curve_emotion
        ctrl=fixture();job=ctrl.capture_completion(ctrl.gap_items()[0]['id']);req=job['request']
        value=prepared(req,[proposal(req,emotion='hope')]);candidate=value['candidates'][0]
        self.assertIsInstance(candidate['provenance'],dict)
        self.assertEqual(candidate['provenance']['placements'][0]['gap_id'],req['target_gaps'][0]['id'])
        with (patch.object(curve_memory,'recompute',side_effect=AssertionError('generation on read')),
              patch.object(curve_emotion,'emotion_variant',side_effect=AssertionError('generation on read')),
              patch.dict('sys.modules',curve_completion=types.SimpleNamespace(propose=lambda *a,**k:(_ for _ in()).throw(AssertionError('search on read'))))):
            c.validate_request(req);c.validate_candidate(req,candidate);c.validate_outcome(req,value)
            self.assertTrue(ctrl.finish_completion(job['token'],value))
            with tempfile.TemporaryDirectory() as tmp:
                path=ctrl.save_snapshot(Path(tmp)/'ready.json');before=path.read_bytes()
                loaded=w.Controller();loaded.load(path);copy_path=loaded.save_snapshot(Path(tmp)/'copy.json')
                self.assertEqual(store.load(copy_path)['bundle'],store.load(path)['bundle'])
                self.assertEqual(loaded.completion_state()['outcome'],value)
                self.assertEqual(path.read_bytes(),before)
        bad=copy.deepcopy(candidate);bad['provenance']=bad['provenance']['placements']
        with self.assertRaises(m.ProjectError):c.validate_candidate(req,bad)

    def test_stored_variant_ancestry_actual_music_and_protection_tampering_rejected(self):
        ctrl=fixture();req=c.make_request(ctrl.project,ctrl.gap_items()[0]['id'])
        candidate=prepared(req,[proposal(req,emotion='hope')])['candidates'][0]
        variant=candidate['project']['placements'][-1]['emotion_variant']
        self.assertTrue(variant['generation']['melody_changed'])
        for mutate in (lambda v:v['generation'].update(base_notes=[]),
                       lambda v:v['generation'].update(protection=dict(explicit_note_ids=['fake'],frozen_note_ids=[],ranges=[])),
                       lambda v:v['generation'].update(melody_changed=False),
                       lambda v:v['notes'][0].update(pitch=v['notes'][0]['pitch']+12),
                       lambda v:v['notes'][0].update(lineage=[]),
                       lambda v:v['generation'].update(operations=[])):
            bad=copy.deepcopy(candidate);mutate(bad['project']['placements'][-1]['emotion_variant'])
            bad['content_fingerprint']=m.fingerprint(bad['project'])
            bad['music_fingerprint']=m.digest('emoblocks.completion-music.v1',c.music_projection(bad['project']))
            bad['notes']=[n for p in bad['project']['placements'] for n in m.placed_notes(p)]
            with self.assertRaises(m.ProjectError):c.validate_candidate(req,bad)

    def test_stored_light_variant_cannot_disguise_extreme_shortening_with_updated_hashes(self):
        ctrl=fixture();req=c.make_request(ctrl.project,ctrl.gap_items()[0]['id'])
        candidate=prepared(req,[proposal(req,emotion='crisis')])['candidates'][0]
        variant=candidate['project']['placements'][-1]['emotion_variant'];variant['notes'][0]['duration_tick']=10
        operation=next(v for v in variant['generation']['operations'] if v['operation']=='local-emotion-melody')
        operation.update(output_duration_tick=10,shortened_by_tick=230)
        candidate['content_fingerprint']=m.fingerprint(candidate['project'])
        candidate['music_fingerprint']=m.digest('emoblocks.completion-music.v1',c.music_projection(candidate['project']))
        candidate['notes']=[n for p in candidate['project']['placements'] for n in m.placed_notes(p)]
        with self.assertRaises(m.ProjectError):c.validate_candidate(req,candidate)
        bad=copy.deepcopy(candidate);bad['project']['intensity_points'][1]['level']=.3
        with self.assertRaises(m.ProjectError):c.validate_candidate(req,bad)

    def test_peak_gap_formal_memory_before_emotion(self):
        controller=fixture();controller.edit('set_intensity',points=[dict(tick=0,level=.2),dict(tick=1320,level=.9),dict(tick=3840,level=.2)])
        p=controller.project;self.assertEqual(curve_memory.memory_info(p)['state'],'PENDING_GAP')
        req=c.make_request(p,c.gap_items(p)[0]['id']);value=prepared(req,[proposal(req,emotion='hope')])
        candidate=value['candidates'][0];protected=candidate['project']['protections'][-1]
        added=candidate['project']['placements'][-1]
        self.assertEqual(candidate['memory_info']['state'],'BOUND')
        self.assertEqual(protected['notes'][0]['pitch'],added['base_snapshot']['notes'][0]['pitch'])
        self.assertEqual(added['emotion_variant']['notes'][0]['pitch'],added['base_snapshot']['notes'][0]['pitch'])
        self.assertEqual(protected['end_tick']-protected['start_tick'],240)
        self.assertEqual(p,controller.project)

    def test_existing_custom_emotion_variant_preserved(self):
        import curve_emotion
        controller=fixture();p=controller.project
        place=p['placements'][1];place['emotion']='hope'
        place['emotion_variant']=curve_emotion.emotion_variant(place['base_snapshot'],'hope',p['intensity_points'],place['start_tick'],[],seed=99,parameters=dict(max_changes=1))
        m.validate(p);req=c.make_request(p,c.gap_items(p)[0]['id'])
        candidate=prepared(req,[proposal(req)])['candidates'][0]
        self.assertEqual(candidate['project']['placements'][:2],p['placements'])
        self.assertEqual(candidate['project']['materials'],p['materials'])

    def test_legacy_manual_memory_and_bridge_retained_and_failure_lock_rejects(self):
        p=manual_bridge(); req=c.make_request(p)
        value=prepared(req,[proposal(req)]);self.assertTrue(value['candidates'])
        candidate=value['candidates'][0];old=p['protections'][0]
        self.assertIn(old,candidate['project']['protections'])
        lock=dict(id='manual',kind='manual',owner_id='user',placement_id=None,component_path=[],start_tick=0,end_tick=240,
                  status='RANGE_LOCKED',origin='manual',plan_id=None,plan_version=None,input_fingerprint='fixed',notes=[],structure_fingerprint=None,blank_mask=[])
        p['protections'].append(lock);m.validate(p)
        with self.assertRaises(m.ProjectError) as exc:c.make_request(p)
        self.assertEqual(exc.exception.code,'PROTECTION_CONFLICT')

    def test_cancel_and_phase_isolation(self):
        req=c.make_request(fixture().project)
        with patch.dict('sys.modules',curve_completion=types.SimpleNamespace(propose=lambda *a,**k:(_ for _ in()).throw(AssertionError('search called')))):
            value=c.prepare_completion(req,should_cancel=lambda:True)
        self.assertEqual(value['status'],'CANCELLED');self.assertFalse(value['candidates'])
        import story_engine
        with patch.object(story_engine,'plan',side_effect=AssertionError('old planner')):
            self.assertTrue(prepared(req,[proposal(req)])['candidates'])

    def test_failed_bridge_gap_lock_cannot_be_cleared_by_completion(self):
        p=manual_bridge();lock=p['protections'][0];plan=p['records'][0];p['placements']=[]
        lock.update(placement_id=None,origin='automatic',status='RANGE_LOCKED',notes=[],structure_fingerprint=None)
        plan.update(status='FAILED');plan['payload'].update(automatic_decision='selected',bridge_ids=['P'],manual_bridge_ids=[],
            ranges=[dict(start_tick=lock['start_tick'],end_tick=lock['end_tick'])])
        m.validate(p);before=copy.deepcopy(p)
        with self.assertRaises(m.ProjectError) as exc:c.make_request(p)
        self.assertEqual(exc.exception.code,'PROTECTION_CONFLICT');self.assertEqual(p,before)

    def test_candidate_long_note_memory_and_nested_combination_paths(self):
        from test_curve_memory import fixture as memory_fixture, points
        long=material('A1',4000,'phrase');p=memory_fixture(long)
        p=m.edit(p,'resize',grid_count=3)
        p=m.edit(p,'mark_blank',start_tick=4000,end_tick=5760,blank_id='tail',reason='主动')
        p=m.edit(p,'set_intensity',points=points(5760,2200))
        req=c.make_request(p);value=prepared(req,[proposal(req,emotion='hope')]);cand=value['candidates'][0]
        lock=cand['project']['protections'][-1]
        self.assertEqual((lock['start_tick'],lock['end_tick']),(1920,3840))
        self.assertEqual((lock['notes'][0]['start_tick'],lock['notes'][0]['duration_tick']),(0,4000))
        combo=w.combine(project(),['A1','A1']);p=project();p=m.edit(p,'add_material',material=combo)
        nested=w.combine(p,[combo['id'], 'A1']);p=m.edit(p,'add_material',material=nested)
        p=m.edit(p,'mark_blank',start_tick=720,end_tick=p['total_ticks'],blank_id='rest',reason='主动')
        p=m.edit(p,'set_intensity',points=points(p['total_ticks'],300))
        req=c.make_request(p);cand=prepared(req,[proposal(req,nested['id'])])['candidates'][0]
        self.assertEqual(len(cand['memory_info']['component_path']),2)
        self.assertEqual(cand['memory_info']['range'],dict(start_tick=240,end_tick=480))

    def test_precise_one_tick_and_output_refusal_without_quantizing(self):
        import curve_audition
        p=project();one=material('one-tick',1);p=m.edit(p,'add_material',material=one)
        p=m.edit(p,'mark_blank',start_tick=1,end_tick=p['total_ticks'],blank_id='tail',reason='主动')
        req=c.make_request(p);cand=prepared(req,[proposal(req,'one-tick')])['candidates'][0]
        self.assertEqual(cand['project']['placements'][-1]['length_ticks'],1)
        with self.assertRaises(m.ProjectError) as exc:curve_audition.render_audition(one)
        self.assertEqual(exc.exception.code,'OUTPUT_TIME_UNREPRESENTABLE')
        self.assertEqual(cand['notes'][0]['duration_tick'],1)

    def test_slice_ties_use_placement_namespace_and_ignore_velocity(self):
        p=project(); sliced=material('sliced',240)
        sliced['notes'][0]['slice']=dict(parent_emission_id='one',offset_tick=0,parent_duration_tick=480)
        p=m.edit(p,'add_material',material=sliced);p=m.edit(p,'place',material_id='sliced',start_tick=0,placement_id='one')
        sliced=copy.deepcopy(sliced);sliced['id']='second';sliced['notes'][0]['slice']['offset_tick']=240
        p=m.edit(p,'add_material',material=sliced);p=m.edit(p,'place',material_id='second',start_tick=240,placement_id='two')
        self.assertEqual(len(c.music_projection(p)['notes']),2)
        q=copy.deepcopy(p);q['placements'][0]['base_snapshot']['notes'][0]['velocity']=99
        self.assertEqual(c.music_projection(q),c.music_projection(p))


class StagingTests(unittest.TestCase):
    def test_success_cancel_repeat_late_and_failure_no_current_state_change(self):
        ctrl=fixture();ctrl.session.mark_saved();before=ctrl.project;undo=ctrl.state()['can_undo']
        job=ctrl.capture_completion(ctrl.gap_items()[0]['id']);req=job['request']
        value=prepared(req,[proposal(req)])
        self.assertTrue(ctrl.accepts(job['token']));self.assertFalse(ctrl.finish_job(job['token']))
        self.assertTrue(ctrl.finish_completion(job['token'],value));self.assertFalse(ctrl.finish_completion(job['token'],value))
        self.assertEqual(ctrl.completion_state()['status'],'READY');self.assertTrue(ctrl.state()['staging_dirty']);self.assertTrue(ctrl.state()['is_saved'])
        second=ctrl.capture_completion(ctrl.gap_items()[0]['id'])
        with self.assertRaises(m.ProjectError):ctrl.capture_completion()
        self.assertTrue(ctrl.cancel_job(second['token']));third=ctrl.capture_completion()
        self.assertFalse(ctrl.accepts(second['token']));self.assertFalse(ctrl.fail_completion(second['token'],RuntimeError('late')))
        self.assertTrue(ctrl.accepts(third['token']));self.assertTrue(ctrl.fail_completion(third['token'],RuntimeError('failure')))
        fourth=ctrl.capture_completion();self.assertFalse(ctrl.finish_completion(fourth['token'],{}))
        self.assertEqual(ctrl.completion_state()['status'],'FAILED');self.assertFalse(ctrl.accepts(fourth['token']))
        self.assertEqual(ctrl.project,before);self.assertTrue(ctrl.state()['is_saved']);self.assertEqual(ctrl.state()['can_undo'],undo)

    def test_edit_undo_never_revives_staged_ready_and_save_failure_blocks_switch(self):
        ctrl=fixture();ctrl.session.mark_saved();job=ctrl.capture_completion();value=prepared(job['request'],[proposal(job['request'])])
        ctrl.finish_completion(job['token'],value);ctrl.edit('set_melody_only',value=True);ctrl.undo()
        self.assertTrue(ctrl.state()['is_saved']);self.assertEqual(ctrl.completion_state()['status'],'STALE')
        before=ctrl.project
        with patch.object(ctrl,'save_snapshot',side_effect=OSError('not writable')):
            with self.assertRaises(OSError):ctrl.new()
        self.assertEqual(ctrl.project,before);self.assertEqual(ctrl.completion_state()['status'],'STALE')

    def test_save_running_reload_interrupt_and_old_version_no_migration(self):
        p=fixture().project;p['contract_rev']='curve-workflow-v2-r3-p23';ctrl=w.Controller(p)
        ctrl.session.mark_saved();before=m.fingerprint(p);job=ctrl.capture_completion();self.assertEqual(job['request']['input_contract_rev'],p['contract_rev'])
        with tempfile.TemporaryDirectory() as tmp:
            path=ctrl.save_snapshot(Path(tmp)/'running.json');raw_data=json.loads(path.read_text())
            self.assertEqual(raw_data['project'],p);self.assertEqual(raw_data['snapshots'][0]['contract_rev'],p['contract_rev'])
            loaded=w.Controller();loaded.load(path)
            self.assertEqual(loaded.project,p);self.assertTrue(loaded.state()['is_saved']);self.assertTrue(loaded.state()['staging_dirty'])
            self.assertEqual(loaded.completion_state()['status'],'INTERRUPTED');self.assertFalse(loaded.accepts(job['token']))
            loaded.save_snapshot(Path(tmp)/'interrupted.json');self.assertFalse(loaded.state()['staging_dirty'])
            self.assertEqual(m.fingerprint(loaded.project),before)
        self.assertEqual(raw_data['attempts'][0]['state'],'RUNNING')

    def test_ready_reopen_revalidates_actual_candidate_and_music_saved_is_independent(self):
        ctrl=fixture();job=ctrl.capture_completion();ctrl.finish_completion(job['token'],prepared(job['request'],[proposal(job['request'])]))
        with tempfile.TemporaryDirectory() as tmp:
            path=ctrl.save_snapshot(Path(tmp)/'ready.json');loaded=w.Controller();loaded.load(path)
            self.assertEqual(loaded.completion_state()['status'],'READY');self.assertFalse(loaded.state()['staging_dirty'])
            self.assertEqual(loaded.project,ctrl.project)
            data=json.loads(path.read_text());data['attempts'][0]['completion']['outcome']['candidates'][0]['notes']=[]
            with self.assertRaises(m.ProjectError):store.validate_bundle(data)

    def test_no_targets_no_attempt_no_registration_no_dirty_or_undo(self):
        p=project();p=m.edit(p,'mark_blank',start_tick=0,end_tick=p['total_ticks'],reason='主动',blank_id='all')
        ctrl=w.Controller(p);ctrl.session.mark_saved();before=copy.deepcopy(ctrl._bundle)
        job=ctrl.capture_completion();self.assertIsNone(job['token']);self.assertIsNone(job['attempt_id'])
        self.assertEqual(job['immediate_outcome']['status'],'NOT_NEEDED');self.assertEqual(ctrl._bundle,before)
        self.assertTrue(ctrl.state()['is_saved']);self.assertFalse(ctrl.state()['staging_dirty']);self.assertFalse(ctrl.state()['can_undo'])

    def test_memory_recompute_exception_and_stale_running_remain_atomic(self):
        ctrl=fixture();ctrl.session.mark_saved();job=ctrl.capture_completion();before=ctrl.project
        with patch.object(curve_memory,'recompute',side_effect=RuntimeError('injected recompute failure')):
            with self.assertRaises(RuntimeError):prepared(job['request'],[proposal(job['request'])])
        self.assertTrue(ctrl.fail_completion(job['token'],RuntimeError('injected recompute failure')))
        self.assertEqual(ctrl.project,before);self.assertTrue(ctrl.state()['is_saved'])
        next_job=ctrl.capture_completion();ctrl.edit('set_melody_only',value=True);ctrl.undo()
        self.assertEqual(ctrl.project,before);self.assertEqual(ctrl.completion_state()['status'],'STALE')
        self.assertFalse(ctrl.accepts(next_job['token']))
        with tempfile.TemporaryDirectory() as tmp:
            path=ctrl.save_snapshot(Path(tmp)/'stale.json');loaded=w.Controller();loaded.load(path)
            self.assertEqual(loaded.completion_state()['status'],'STALE')

    def test_old_attempt_managed_history_long_note_keeps_p3_validation(self):
        from test_curve_memory import fixture as memory_fixture
        ctrl=w.Controller(memory_fixture(material(length=4000)))
        ctrl.edit('place',material_id='A1',start_tick=0,placement_id='long')
        ctrl.edit('add_material',material=material('bridge',1920,'bridge'))
        ctrl.edit('place',material_id='bridge',start_tick=5760,placement_id='bridge')
        ctrl.edit('set_intensity',points=[dict(tick=0,level=.3),dict(tick=15360,level=.2)])
        p=ctrl.project;b=store.new_bundle(p)
        b['snapshots']=[dict(id='original',spec_rev=m.SPEC_REV,contract_rev=p['contract_rev'],content_fingerprint=m.fingerprint(p),project=p)]
        b['attempts']=[dict(id='old-attempt',snapshot_id='original',input_fingerprint=m.fingerprint(p),state='READY',records=copy.deepcopy(p['records']),
                            protections=copy.deepcopy(p['protections']),staged_materials=[],error=None)]
        store.validate_bundle(b)
        with tempfile.TemporaryDirectory() as tmp:
            path=store.save(b,Path(tmp)/'history.json');loaded=store.load(path)
            self.assertEqual(loaded['bundle'],b)
        bad=copy.deepcopy(b);old=bad['attempts'][0]['records'][0]['payload']['audit_context']
        lock=next(v for v in old['protections'] if m.managed_memory(p,v));lock['notes'][0]['pitch']+=1;lock['structure_fingerprint']=m.structure_fingerprint(lock)
        with self.assertRaises(m.ProjectError):store.validate_bundle(bad)


if __name__ == '__main__':unittest.main()
