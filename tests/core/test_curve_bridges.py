"""P5 service gates: hand-built decisions test transactions, not music quality."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import curve_bridges as b
import curve_project as m
import curve_store as store
import curve_workflow as w
from test_curve_workflow import project, material, manual_bridge
from test_curve_candidates import fixture, prepared, proposal as completion_proposal


def complete(manual=False):
    p=m.edit(project(),'resize',grid_count=6)
    p=m.edit(p,'add_material',material=material('long',1920))
    if manual:p=m.edit(p,'add_material',material=material('manual',1920,'bridge'))
    c=w.Controller(p)
    for i in range(6):
        c.edit('place',material_id='manual' if manual and i==5 else 'long',start_tick=i*1920,placement_id='use'+str(i))
    c.session.mark_saved()
    return c


def decision(req, ranges=()):
    windows=[]
    for i,(a,z) in enumerate(ranges):
        windows.append(dict(id='automatic-'+str(i),start_tick=a,end_tick=z,placement_ids=[],context={},
                            emotion_segments=[],blank_mask=[]))
    for win in windows:
        win['placement_ids']=[p['id'] for p in sorted(req['base_project']['placements'],key=lambda p:(p['start_tick'],p['id']))
                              if m.intersects(b.extent(p),win)]
        left,right=b.context_sides(req,win,windows)
        win['context']=dict(left=left,right=right,motif_note_ids=[n['id'] for n in req['base_notes'] if m.intersects(b.support(n),win)],
                            key_context=dict(tonic=0,mode='major',confidence=.8,method='test-key'))
        win['emotion_segments']=b.emotion_segments(req,win);win['blank_mask']=b.blank_mask(req,win)
    return dict(schema='emoblocks.bridge-proposal.v1',spec_rev=m.SPEC_REV,contract_rev=b.REV,
        request_fingerprint=b.request_fingerprint(req),decision='selected' if windows else 'none',windows=windows,
        reasons=[b.error('TEST_DECISION','事务测试决策')],assessments=[],joint_boundary_conditions=[],
        search=dict(tested_windows=len(windows),termination='TEST_COMPLETE'))


def raw(req, plan, rows=(), status='SUCCEEDED', error=None):
    return dict(schema='emoblocks.bridge-raw-outcome.v1',spec_rev=m.SPEC_REV,contract_rev=b.REV,
        request_fingerprint=b.request_fingerprint(req),plan_id=plan['id'],plan_version=plan['version'],
        status=status,results=list(rows),error=error)


def historical_automatic(velocity):
    """Valid old ready record; current performance may differ from its snapshot."""
    p=manual_bridge();plan=p['records'][0];lock=p['protections'][0]
    lock['origin']='automatic'
    plan['payload'].update(automatic_decision='selected',bridge_ids=['P'],manual_bridge_ids=[],
                           ranges=[dict(start_tick=1920,end_tick=3840)])
    p['records'].append(dict(id='old-result',kind='bridge_result',version=1,status='READY',
        input_fingerprint=plan['input_fingerprint'],dependencies=[dict(id=plan['id'],version=plan['version'])],
        payload=dict(bridge_id='P',plan_id=plan['id'],plan_version=plan['version'],protection_id=lock['id'],
            material_snapshot=copy.deepcopy(p['placements'][0]['base_snapshot']),validation=dict(valid=True))))
    p['blank_regions']=[dict(id='left',start_tick=0,end_tick=1920,reason='主动留白'),
                       dict(id='right',start_tick=3840,end_tick=p['total_ticks'],reason='主动留白')]
    p['placements'][0]['base_snapshot']['notes'][0]['velocity']=velocity
    m.validate(p)
    return p


class BridgeServiceTests(unittest.TestCase):
    def test_current_complete_none_no_fake_completion_or_edit(self):
        c=complete();before=c.project;history=copy.deepcopy((c.session._undo,c.session._redo))
        cap=c.capture_bridge(algorithm_version=b.ALGORITHM);req=cap['request'];token=cap['token']
        self.assertEqual(req['input_kind'],'current_complete');self.assertIsNone(req['completion_ref'])
        self.assertEqual(token['contract_rev'],b.REV);self.assertEqual(c.project['contract_rev'],m.CONTRACT_REV)
        plan=c.lock_bridge(token,decision(req));self.assertTrue(c.accepts(token))
        self.assertTrue(c.begin_bridge_generation(token,plan));self.assertTrue(c.finish_bridge(token,raw(req,plan)))
        state=c.bridge_state();self.assertEqual(state['status'],'READY');self.assertEqual(state['plan']['decision'],'none')
        self.assertTrue(state['capabilities']['can_plan_connections'])
        self.assertFalse(state['capabilities']['can_apply']);self.assertFalse(state['capabilities']['can_export_final'])
        self.assertEqual(state['outcome']['notes'],req['base_notes']);self.assertEqual(c.project,before)
        self.assertEqual((c.session._undo,c.session._redo),history);self.assertTrue(c.state()['is_saved'])
        self.assertTrue(c.state()['staging_dirty']);self.assertFalse(c.finish_bridge(token,raw(req,plan)))

    def test_gap_no_fake_current_input_and_duplicate_request(self):
        c=fixture()
        with self.assertRaises(m.ProjectError):c.capture_bridge(algorithm_version=b.ALGORITHM)
        self.assertEqual(c._bundle['attempts'],[]);self.assertEqual(c._jobs,{})
        c=complete();cap=c.capture_bridge(algorithm_version=b.ALGORITHM)
        with self.assertRaises(m.ProjectError) as exc:c.capture_bridge(algorithm_version=b.ALGORITHM)
        self.assertEqual(exc.exception.code,'DUPLICATE_REQUEST');self.assertTrue(c.cancel_bridge(cap['token']))
        self.assertEqual(c.bridge_state()['outcome']['plan_fingerprint'],None)

    def test_one_insufficient_candidate_local_scope_remaining_gaps(self):
        c=fixture();cap=c.capture_completion(c.gap_items()[0]['id'])
        outcome=prepared(cap['request'],[completion_proposal(cap['request'])])
        self.assertEqual(outcome['status'],'INSUFFICIENT');self.assertTrue(c.finish_completion(cap['token'],outcome))
        bridge=c.capture_bridge(outcome['candidates'][0]['id'],cap['token']['request_id'], algorithm_version=b.ALGORITHM)
        req=bridge['request'];self.assertEqual(req['remaining_gaps'],outcome['candidates'][0]['remaining_gaps'])
        self.assertEqual(req['resolved_ranges'],[dict(start_tick=0,end_tick=3360)])
        self.assertEqual(c.project,req['input_project']);self.assertEqual(c.project['materials'],req['base_project']['materials'])
        self.assertTrue(c.cancel_bridge(bridge['token']))

    def test_atomic_locks_before_generation_and_failed_transaction(self):
        c=complete();cap=c.capture_bridge(algorithm_version=b.ALGORITHM);token=cap['token'];req=cap['request']
        before=copy.deepcopy(c._bundle);bad=decision(req,[(1920,3840),(5760,7680)])
        bad['windows'][1]['start_tick']=2000
        with self.assertRaises(m.ProjectError):c.lock_bridge(token,bad)
        self.assertEqual(c._bundle,before);self.assertEqual(c.bridge_state()['phase'],'BRIDGE_DECISION')
        plan=c.lock_bridge(token,decision(req,[(1920,3840),(5760,7680)]))
        state=c.bridge_state();self.assertEqual(state['phase'],'BRIDGE_LOCKED')
        self.assertEqual([p['status'] for p in state['protections'] if p['kind']=='bridge'],['RANGE_LOCKED']*2)
        self.assertEqual(len(plan['protection_refs']),2);self.assertTrue(c.accepts(token))
        with self.assertRaises(m.ProjectError):c.lock_bridge(token,decision(req))
        self.assertFalse(c.finish_job(token));self.assertFalse(state['capabilities']['can_plan_connections'])

    def test_failure_cancel_locks_old_callback_and_new_plan_isolation(self):
        c=complete();cap=c.capture_bridge(algorithm_version=b.ALGORITHM);req=cap['request'];token=cap['token']
        plan=c.lock_bridge(token,decision(req,[(1920,3840),(5760,7680)]));c.begin_bridge_generation(token,plan)
        first=b.failure_result(req,plan,'automatic-0',b.error('SYNTHETIC_FAILURE','模拟失败'))
        self.assertTrue(c.record_bridge_result(token,first));self.assertFalse(c.record_bridge_result(token,first))
        self.assertTrue(c.cancel_bridge(token));old=c.bridge_state();self.assertEqual(old['status'],'CANCELLED')
        self.assertEqual([r['status'] for r in old['results']],['FAILED','CANCELLED'])
        self.assertEqual([p['status'] for p in old['protections'] if p['kind']=='bridge'],['RANGE_LOCKED']*2)
        self.assertFalse(c.finish_bridge(token,raw(req,plan)));self.assertFalse(c.record_bridge_result(token,first))
        new=c.capture_bridge(algorithm_version=b.ALGORITHM);self.assertGreater(new['request']['plan_version'],req['plan_version'])
        self.assertNotEqual(new['request']['plan_id'],req['plan_id']);self.assertEqual(c._bridge_attempt(token['request_id'])['protections'],old['protections'])
        self.assertFalse(c.fail_bridge(token,b.error('LATE','迟到')));self.assertEqual(c.bridge_state()['status'],'RUNNING')

    def test_edit_undo_never_revives_parent_or_bridge(self):
        c=complete();before=c.project;cap=c.capture_bridge(algorithm_version=b.ALGORITHM);token=cap['token'];req=cap['request']
        c.lock_bridge(token,decision(req,[(1920,3840)]))
        c.edit('set_melody_only',value=True);c.undo();self.assertEqual(c.project,before)
        self.assertEqual(c.bridge_state()['status'],'STALE');self.assertFalse(c.accepts(token))
        self.assertFalse(c.cancel_bridge(token));self.assertFalse(c.bridge_state()['capabilities']['can_plan_connections'])
        store.validate_bundle(c._current_bundle())
        c=fixture();cap=c.capture_completion(c.gap_items()[0]['id']);outcome=prepared(cap['request'],[completion_proposal(cap['request'])])
        c.finish_completion(cap['token'],outcome);c.edit('set_melody_only',value=True);c.undo()
        with self.assertRaises(m.ProjectError):c.capture_bridge(outcome['candidates'][0]['id'],cap['token']['request_id'], algorithm_version=b.ALGORITHM)

    def test_manual_none_actual_ready_set_preserves_old_lock(self):
        c=complete(manual=True);cap=c.capture_bridge(algorithm_version=b.ALGORITHM);req=cap['request'];token=cap['token']
        old=copy.deepcopy([p for p in c.project['protections'] if p['kind']=='bridge'])
        plan=c.lock_bridge(token,decision(req));rows=[b.inherited_result(req,plan,owner) for owner in plan['inherited_bridge_ids']]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'READY')
        self.assertEqual(rows[0]['material'],c.project['placements'][-1]['base_snapshot'])
        c.begin_bridge_generation(token,plan);self.assertTrue(c.finish_bridge(token,raw(req,plan,rows)))
        self.assertEqual([p for p in c.bridge_state()['protections'] if p['kind']=='bridge'],old)
        self.assertEqual(c.bridge_state()['outcome']['notes'],req['base_notes'])

    def test_pure_restore_running_interrupts_without_music_calls(self):
        c=complete();cap=c.capture_bridge(algorithm_version=b.ALGORITHM);plan=c.lock_bridge(cap['token'],decision(cap['request'],[(1920,3840)]))
        c.begin_bridge_generation(cap['token'],plan)
        with tempfile.TemporaryDirectory() as tmp:
            path=c.save_snapshot(Path(tmp)/'保存 中文.json');original=c.project
            with (patch('curve_workflow.decide_bridge',side_effect=AssertionError('decision')),
                  patch('curve_workflow.generate_bridges',side_effect=AssertionError('generate')),
                  patch('curve_memory.recompute',side_effect=AssertionError('memory'))):
                loaded=store.load(path);d=w.Controller();d.load(path)
            attempt=loaded['bundle']['attempts'][-1]
            self.assertEqual(attempt['state'],'INTERRUPTED');self.assertEqual(attempt['bridge']['plan'],plan)
            self.assertEqual(d.project,original);self.assertEqual(d._jobs,{})
            self.assertEqual(d.bridge_state()['status'],'INTERRUPTED');self.assertTrue(d.state()['staging_dirty'])
            self.assertEqual([p['status'] for p in d.bridge_state()['protections'] if p['kind']=='bridge'],['RANGE_LOCKED'])

    def test_decision_error_audit_and_save_failure(self):
        c=complete();before=c.project;cap=c.capture_bridge(algorithm_version=b.ALGORITHM)
        self.assertTrue(c.fail_bridge(cap['token'],RuntimeError('decision error')))
        state=c.bridge_state();self.assertEqual(state['status'],'FAILED');self.assertIsNone(state['plan'])
        self.assertIsNone(state['outcome']['plan_fingerprint']);self.assertEqual(state['outcome']['results'],[])
        with patch('curve_store.save',side_effect=OSError('unwritable')):
            with self.assertRaises(OSError):c.save_snapshot()
        self.assertEqual(c.project,before);self.assertTrue(c.state()['is_saved']);self.assertTrue(c.state()['staging_dirty'])
        store.validate_bundle(c._current_bundle())


class BridgeActualMusicTests(unittest.TestCase):
    def start(self, count=4):
        from test_curve_bridge_music import fixture as music_fixture
        c=w.Controller(music_fixture(count));cap=c.capture_bridge(algorithm_version=b.ALGORITHM)
        return c,cap

    def test_public_actual_roundtrip_source_and_reproducibility_no_p6(self):
        c,cap=self.start();before=c.project;req=cap['request'];token=cap['token']
        with patch('story_engine.plan',side_effect=AssertionError('old planner')),patch('story_engine.generate',side_effect=AssertionError('final pipeline')):
            prop=w.decide_bridge(req);plan=c.lock_bridge(token,prop)
            self.assertEqual(c.bridge_state()['phase'],'BRIDGE_LOCKED');c.begin_bridge_generation(token,plan)
            result=w.generate_bridges(req,plan);b.validate_raw(req,plan,result)
        self.assertEqual(prop['decision'],'selected');self.assertEqual(result['status'],'SUCCEEDED')
        self.assertTrue(c.record_bridge_result(token,result['results'][0]))
        self.assertTrue(c.finish_bridge(token,result));self.assertEqual(c.project,before)
        row=result['results'][0];self.assertEqual(row['material']['length_ticks'],plan['windows'][0]['end_tick'])
        self.assertEqual(row['emotion_processing']['pass_count'],1);self.assertEqual(len(row['children']),4)
        self.assertEqual(len(row['operations']),len(row['base_material']['notes']))
        self.assertTrue(any(op['rule'] in ('answer','sequence','rhythm') for op in row['operations']))
        other=c.capture_bridge(algorithm_version=b.ALGORITHM);otherplan=c.lock_bridge(other['token'],w.decide_bridge(other['request']))
        regenerated=w.generate_bridges(other['request'],otherplan)
        musical=lambda rows:[(n['pitch'],n['start_tick'],n['duration_tick']) for r in rows for n in r['notes']]
        self.assertEqual(musical(result['results']),musical(regenerated['results']))

    def test_partial_success_failure_retains_content_and_both_locks(self):
        c,cap=self.start(6);req=cap['request'];token=cap['token']
        prop=decision(req,[(0,3840),(7680,11520)]);plan=c.lock_bridge(token,prop);c.begin_bridge_generation(token,plan)
        generated=w.generate_bridges(req,plan);b.validate_raw(req,plan,generated)
        first=generated['results'][0];self.assertTrue(c.record_bridge_result(token,first))
        failure=b.error('SYNTHETIC_FAILURE','第二桥模拟失败')
        second=b.failure_result(req,plan,plan['windows'][1]['id'],failure)
        self.assertTrue(c.finish_bridge(token,raw(req,plan,[first,second],'FAILED',failure)))
        state=c.bridge_state();self.assertEqual(state['status'],'FAILED')
        self.assertEqual([p['status'] for p in state['protections']],['CONTENT_READY','RANGE_LOCKED'])
        self.assertFalse(state['capabilities']['can_plan_connections']);self.assertEqual(state['results'][0],first)
        self.assertEqual(c._bridge_attempt(token['request_id'])['staged_materials'][0],first['material'])
        before=copy.deepcopy(state)
        self.assertFalse(c.finish_bridge(token,generated));self.assertEqual(c.bridge_state(),before)

    def test_tamper_pitch_time_source_ledger_children_masks_and_hash_rejected(self):
        c,cap=self.start();req=cap['request'];plan=c.lock_bridge(cap['token'],w.decide_bridge(req))
        actual=w.generate_bridges(req,plan)['results'][0];b.validate_result(req,plan,actual)
        changes=[lambda r:r['base_material']['notes'][0].update(pitch=61),
                 lambda r:r['material']['notes'][0].update(start_tick=1),
                 lambda r:r['notes'][0].update(duration_tick=1),
                 lambda r:r['operations'][0]['parent_ref'].update(note_id='wrong'),
                 lambda r:r['operations'][0].update(input_note_id=req['base_notes'][-1]['id']),
                 lambda r:r['base_material']['notes'][0].update(lineage=[]),
                 lambda r:r['base_material']['notes'][0]['origin'].update(source_note_id='source:1:0'),
                 lambda r:r['base_material']['generation'].update(input_fingerprint='forged'),
                 lambda r:r['material']['provenance'].update(parent_snapshots={}),
                 lambda r:r['children'][0]['notes'][0].update(pitch=61),
                 lambda r:r['emotion_processing']['segments'][0].update(seed=0),
                 lambda r:r.update(plan_version=plan['version']+1)]
        for change in changes:
            bad=copy.deepcopy(actual);change(bad)
            bad['content_fingerprint']=b.content_fingerprint(bad['range'],plan['windows'][0]['blank_mask'],bad['notes'])
            with self.subTest(change=change),self.assertRaises(m.ProjectError):b.validate_result(req,plan,bad)
        for rows in ([],[actual,actual],[dict(actual,bridge_id='extra')]):
            with self.assertRaises(m.ProjectError):b.validate_raw(req,plan,raw(req,plan,rows))

    def test_ready_persistence_is_pure_and_attempt_tampering_fails(self):
        c,cap=self.start();req=cap['request'];plan=c.lock_bridge(cap['token'],w.decide_bridge(req));c.begin_bridge_generation(cap['token'],plan)
        result=w.generate_bridges(req,plan);self.assertTrue(c.finish_bridge(cap['token'],result))
        with tempfile.TemporaryDirectory() as tmp:
            path=c.save_snapshot(Path(tmp)/'桥 ready 中文.json')
            with (patch('curve_bridge_music.decide',side_effect=AssertionError('decision')),
                  patch('curve_melody.compose_bridge_phrase',side_effect=AssertionError('compose')),
                  patch('curve_emotion.emotion_variant',side_effect=AssertionError('emotion')),
                  patch('curve_memory.recompute',side_effect=AssertionError('memory'))):
                archive=store.load(path)['bundle'];store.validate_bundle(archive)
            self.assertEqual(archive['attempts'][-1]['bridge']['outcome'],c.bridge_state()['outcome'])
            bad=copy.deepcopy(archive);bad['attempts'][-1]['protections'][0]['notes'][0]['pitch']+=1
            with self.assertRaises(m.ProjectError):store.validate_bundle(bad)

    def test_nested_combination_flat_identity_keeps_real_occurrence_path(self):
        from test_curve_bridge_music import fixture as music_fixture
        p=music_fixture();first,second=p['materials'][:2]
        combo=w.combine(p,[first,second]);nested=w.combine(p,[combo,first]);nested['id']='nested'
        for i,n in enumerate(nested['notes']):n['id']='independent-flat-'+str(i)
        m.material_check(nested,m.source_index(p['sources']))
        p['materials'].append(nested);p['placements']=[dict(id='nested-use',material_id=nested['id'],base_snapshot=nested,
             start_tick=0,length_ticks=nested['length_ticks'],emotion='calm',emotion_variant=None)]
        p['blank_regions']=[dict(id='endblank',start_tick=nested['length_ticks'],end_tick=p['total_ticks'],reason='主动留白')]
        c=w.Controller(p);cap=c.capture_bridge(algorithm_version=b.ALGORITHM);req=cap['request']
        expected=[combo['children'][0]['occurrence_id'],first['id']]
        ref=b.parent_ref(req,'nested-use:'+nested['notes'][0]['id'])
        self.assertEqual(ref['component_path'],[nested['children'][0]['occurrence_id'],combo['children'][0]['occurrence_id']])
        plan=c.lock_bridge(cap['token'],decision(req,[(0,nested['length_ticks'])]))
        result=w.generate_bridges(req,plan);b.validate_raw(req,plan,result)
        self.assertEqual(result['status'],'SUCCEEDED')

    def test_historical_ready_velocity_only_inheritance_none_selected_and_pure_restore(self):
        for policy in ('none','selected'):
            for velocity in (80,100):
                with self.subTest(policy=policy,velocity=velocity):
                    p=historical_automatic(velocity)
                    if policy=='selected':
                        p['blank_regions']=[];p['materials'].append(material('normal',1920))
                        for i in (0,2,3,4,5,6,7):
                            p['placements'].append(dict(id='normal-'+str(i),material_id='normal',base_snapshot=material('normal',1920),
                                start_tick=i*1920,length_ticks=1920,emotion='calm',emotion_variant=None))
                    m.validate(p);before=copy.deepcopy(p)
                    with tempfile.TemporaryDirectory() as tmp:
                        path=store.save(store.new_bundle(p),Path(tmp)/'old.json')
                        self.assertEqual(store.load(path)['bundle']['project'],p)
                        c=w.Controller(p);c.session.mark_saved();cap=c.capture_bridge(parameters={'policy':'none'} if policy=='none' else None, algorithm_version=b.ALGORITHM)
                        req=cap['request'];prop=w.decide_bridge(req) if policy=='none' else decision(req,[(5760,9600)])
                        plan=c.lock_bridge(cap['token'],prop);c.begin_bridge_generation(cap['token'],plan)
                        generated=w.generate_bridges(req,plan);b.validate_raw(req,plan,generated)
                        inherited=next(r for r in generated['results'] if r['origin']=='inherited')
                        self.assertEqual(inherited['notes'][0]['velocity'],velocity)
                        self.assertEqual(inherited['material']['notes'][0]['velocity'],80)
                        self.assertEqual(m.structural_notes(inherited['notes']),m.structural_notes(p['protections'][0]['notes']))
                        for key in ('pitch','start_tick','duration_tick'):
                            bad=copy.deepcopy(inherited);bad['notes'][0][key]+=1
                            bad['content_fingerprint']=b.content_fingerprint(bad['range'],[],bad['notes'])
                            with self.assertRaises(m.ProjectError):b.validate_result(req,plan,bad)
                        self.assertTrue(c.finish_bridge(cap['token'],generated));self.assertEqual(c.bridge_state()['status'],'READY')
                        self.assertEqual(c.project,before);self.assertTrue(c.state()['is_saved'])
                        lock=next(v for v in c.bridge_state()['protections'] if v['id']==p['protections'][0]['id'])
                        self.assertEqual(lock,p['protections'][0]);self.assertEqual(c.project['records'],before['records'])
                        c.save_snapshot(Path(tmp)/'ready.json')
                        with (patch('curve_bridge_music.decide',side_effect=AssertionError('decision')),
                              patch('curve_bridge_music.generate',side_effect=AssertionError('music')),
                              patch('curve_emotion.emotion_variant',side_effect=AssertionError('emotion'))):
                            archive=store.load(Path(tmp)/'ready.json');store.validate_bundle(archive['bundle'])
                        self.assertEqual(archive['bundle']['attempts'][-1]['bridge']['outcome'],c.bridge_state()['outcome'])


if __name__=='__main__':unittest.main()
