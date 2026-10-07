"""P6 independent gates and transactions. Hand-built music is fault-path evidence."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import curve_connections as n
import curve_bridges as b
import curve_project as m
import curve_workflow as w
import curve_store as store
from test_curve_bridges import complete, decision, raw, historical_automatic, material
from test_curve_candidates import fixture, prepared, proposal as completion_proposal


def ready_bridge(controller=None, ranges=()):
    controller = controller or complete()
    cap = controller.capture_bridge(algorithm_version=b.ALGORITHM)
    plan = controller.lock_bridge(cap['token'], decision(cap['request'], ranges))
    controller.begin_bridge_generation(cap['token'], plan)
    result = b.generate_bridges(cap['request'], plan)
    assert controller.finish_bridge(cap['token'], result)
    return controller


def proposal(request, ranges=(), technique='diatonic_guide'):
    windows = []
    for i, (start, end) in enumerate(ranges):
        windows.append(dict(id='connection-' + str(i), start_tick=start, end_tick=end, technique=technique,
            context={}, original_notes=n.ordered([x for x in request['actual_layout']['notes'] if m.intersects(n.support(x), dict(start_tick=start, end_tick=end))]),
            reasons=[n.error('TEST_WINDOW', '事务测试窗口')], key_context=dict(tonic=0, mode='major', confidence=1., method='test'),
            parameters=dict(target_ticks=end-start, unit_ticks=1)))
    for win in windows:
        left, right = n.window_context(request, win, windows)
        win['context'] = dict(left=left, right=right, motif_note_ids=list(dict.fromkeys(x['id'] for x in
            win['original_notes'] + [x for x in (left, right) if x])))
    joints = []
    for left in windows:
        for right in windows:
            if left['end_tick'] == right['start_tick']:
                joints.append(dict(id='joint-' + left['id'], left_connection_id=left['id'], right_connection_id=right['id'],
                    tick=left['end_tick'], relation='test-arrival', left_endpoint=None,
                    right_endpoint=dict(pitch=62, start_tick=right['start_tick'], duration_tick=(right['end_tick']-right['start_tick'])//2)))
    return dict(schema='emoblocks.connection-proposal.v1', spec_rev=m.SPEC_REV, contract_rev=n.REV,
        request_fingerprint=n.request_fingerprint(request), decision='selected' if windows else 'none',
        none_reason=None if windows else 'NOT_NEEDED', windows=windows, reasons=[n.error('TEST_DECISION', '事务测试')],
        assessments=[], joint_boundary_conditions=joints, search=dict(tested_windows=len(windows), termination='COMPLETE'))


def result(request, plan, index=0):
    win = plan['windows'][index]; parents = m.indexed(request['actual_layout']['notes'])
    parent = parents[win['context']['motif_note_ids'][0]]
    span = win['end_tick'] - win['start_tick']; half = span // 2
    notes = []
    for i, pitch in enumerate((62, 60)):
        notes.append(dict(parent, id=win['id'] + ':new-' + str(i), pitch=pitch,
            start_tick=win['start_tick'] + i * half, duration_tick=half,
            lineage=list(dict.fromkeys(parent['lineage'] + [parent['id']])), slice=None))
    for joint in plan['joint_boundary_conditions']:
        if joint['left_connection_id'] == win['id'] and joint['left_endpoint'] is None: notes[-1]['duration_tick'] -= 1
    operations = [dict(operation='connection-motif-cell', input_note_id=parent['id'], parent_ref=n.parent_ref(request, parent['id']),
        output_note_id=x['id'], rule=win['technique'], from_pitch=parent['pitch'], to_pitch=x['pitch'],
        start_tick=x['start_tick'], duration_tick=x['duration_tick']) for x in notes]
    return dict(**n.result_header(request, plan, win['id']), status='READY', notes=notes, operations=operations,
        generation=n.generation_data(request, plan, win, operations), content_fingerprint=n.content_fingerprint(
            {k: win[k] for k in ('start_tick', 'end_tick')}, notes), error=None)


def begin(controller, ranges=((1920, 3840),), technique='diatonic_guide'):
    cap = controller.capture_connection()
    plan = controller.plan_connection(cap['token'], proposal(cap['request'], ranges, technique))
    controller.begin_connection_generation(cap['token'], plan)
    return cap, plan


class ConnectionServiceTests(unittest.TestCase):
    def test_none_stage_isolated_and_caps_closed(self):
        c = ready_bridge(); before = c.project; parent = c.bridge_state(); history = copy.deepcopy((c.session._undo, c.session._redo))
        cap, plan = begin(c, ()); self.assertFalse(c.finish_job(cap['token']))
        self.assertTrue(c.finish_connection(cap['token'], n.raw_outcome(cap['request'], plan, [])))
        state = c.connection_state()
        self.assertEqual(state['status'], 'READY'); self.assertEqual(state['outcome']['notes'], parent['outcome']['notes'])
        self.assertEqual(state['protections'], parent['protections']); self.assertTrue(state['capabilities']['can_plan_boundaries'])
        for key in ('can_apply', 'can_audition', 'can_export_final'): self.assertFalse(state['capabilities'][key])
        self.assertEqual(c.project, before); self.assertEqual((c.session._undo, c.session._redo), history)
        self.assertTrue(c.state()['is_saved']); self.assertTrue(c.state()['staging_dirty'])
        self.assertEqual(c.project['contract_rev'], m.CONTRACT_REV); self.assertEqual(cap['token']['contract_rev'], n.REV)

    def test_real_bridge_set_and_version_gate(self):
        c = ready_bridge(complete(manual=True)); parent = c.bridge_state()
        ref = dict(attempt_id=parent['attempt_id'], **{k: parent[k] for k in ('request', 'plan', 'protections', 'results', 'outcome')})
        mutations = []
        for change in ('missing', 'duplicate', 'extra', 'failed', 'range_locked', 'old_plan', 'wrong_protection', 'fake_none'):
            damaged = copy.deepcopy(ref)
            if change == 'missing': damaged['results'] = []
            if change == 'duplicate': damaged['results'].append(copy.deepcopy(damaged['results'][0]))
            if change == 'extra': damaged['results'][0]['bridge_id'] = 'unknown'
            if change == 'failed': damaged['outcome']['status'] = 'FAILED'
            if change == 'range_locked': damaged['protections'][-1]['status'] = 'RANGE_LOCKED'
            if change == 'old_plan': damaged['plan']['version'] += 1
            if change == 'wrong_protection': damaged['protections'][-1]['id'] = 'other'
            if change == 'fake_none': damaged['plan'] = None
            mutations.append((change, damaged))
        for name, ref in mutations:
            with self.subTest(name=name), self.assertRaises(m.ProjectError): n.make_request(c.project, ref)
        cap, plan = begin(c, ()); self.assertEqual(len(cap['request']['bridge_ref']['results']), 1)
        self.assertTrue(c.finish_connection(cap['token'], n.raw_outcome(cap['request'], plan, [])))

    def test_unready_and_latest_stale_not_fallback(self):
        c = complete(); self.assertEqual(c.connection_state()['status'], 'IDLE')
        with self.assertRaises(m.ProjectError): c.capture_connection()
        c = ready_bridge(c); first = c.bridge_state()['attempt_id']
        newer = c.capture_bridge(algorithm_version=b.ALGORITHM); c.cancel_bridge(newer['token'])
        with self.assertRaises(m.ProjectError): c.capture_connection()
        selected = c.capture_connection(first); self.assertEqual(selected['request']['bridge_ref']['attempt_id'], first)
        self.assertTrue(c.cancel_job(selected['token']))

    def test_actual_bridge_endpoint_not_old_base_and_scope_intrusions(self):
        c = complete(); high=material('higher-original',1920);high['notes'][0]['pitch']=73
        c.edit('add_material',material=high);c.edit('delete',placement_id='use2')
        c.edit('place',material_id=high['id'],start_tick=3840,placement_id='use2')
        c = ready_bridge(c,ranges=((1920, 5760),)); cap = c.capture_connection(); req = cap['request']
        actual = req['actual_layout']['notes']; end = max((x for x in actual if x['start_tick'] < 5760), key=lambda x:x['start_tick'])
        old=max((x for x in req['bridge_ref']['request']['base_notes'] if x['start_tick']<5760),key=lambda x:x['start_tick'])
        self.assertNotEqual(end['pitch'],old['pitch'])
        good = proposal(req, ((5760, 7680),)); self.assertEqual(good['windows'][0]['context']['left'], end)
        for ranges in (((0, 7680),), ((1800, 2040),), ((5000, 6000),)):
            with self.subTest(ranges=ranges), self.assertRaises(m.ProjectError): c.plan_connection(cap['token'], proposal(req, ranges))
        plan = c.plan_connection(cap['token'], good)
        changed = copy.deepcopy(plan); changed['bridge_plan_version'] += 1; changed['plan_fingerprint'] = n.plan_fingerprint(changed)
        with self.assertRaises(m.ProjectError): n.validate_plan(req, changed)

    def test_full_plan_atomic_conflict_and_adjacent_conditions(self):
        c = ready_bridge(); cap = c.capture_connection(); before = copy.deepcopy(c._bundle)
        for ranges in (((1920,3840),(2880,5760)), ((1920,3840),(10000,14000))):
            with self.assertRaises(m.ProjectError): c.plan_connection(cap['token'], proposal(cap['request'], ranges))
            self.assertEqual(c._bundle, before)
        p = proposal(cap['request'], ((1920,3840),(3840,5760))); p['joint_boundary_conditions'] = []
        with self.assertRaises(m.ProjectError): c.plan_connection(cap['token'], p)
        plan = c.plan_connection(cap['token'], proposal(cap['request'], ((1920,3840),(3840,5760))))
        self.assertTrue(c.begin_connection_generation(cap['token'], plan))
        rows = [result(cap['request'],plan, i) for i in range(2)]
        self.assertTrue(c.finish_connection(cap['token'], n.raw_outcome(cap['request'],plan,rows)))

    def test_selected_result_is_actual_overlay_and_stream_duplicate(self):
        c = ready_bridge(); before = c.project; cap, plan = begin(c); row = result(cap['request'], plan)
        self.assertTrue(c.record_connection_result(cap['token'], row)); self.assertFalse(c.record_connection_result(cap['token'], row))
        self.assertEqual(c.connection_state()['status'], 'RUNNING')
        self.assertTrue(c.finish_connection(cap['token'], n.raw_outcome(cap['request'], plan, [row])))
        self.assertNotEqual(n.music_signature(c.connection_state()['outcome']['notes']), n.music_signature(cap['request']['actual_layout']['notes']))
        self.assertEqual(c.project, before); self.assertEqual(c.bridge_state()['protections'], c.connection_state()['protections'])
        self.assertFalse(c.finish_connection(cap['token'], n.raw_outcome(cap['request'], plan, [row])))

    def test_rehashed_time_source_generation_and_identity_fraud(self):
        c = ready_bridge(); cap, plan = begin(c); req = cap['request']; valid = result(req, plan)
        for change in ('outside', 'fake_parent', 'wrong_lineage', 'fake_origin', 'old_id', 'seed', 'bool_version', 'original', 'null_failure'):
            bad = copy.deepcopy(valid)
            if change == 'outside': bad['notes'][0]['start_tick'] = 0; bad['operations'][0]['start_tick'] = 0
            if change == 'fake_parent': bad['operations'][0]['input_note_id'] = 'fake'
            if change == 'wrong_lineage': bad['notes'][0]['lineage'] = ['fake']
            if change == 'fake_origin': bad['notes'][0]['origin'] = dict(source_id='fake',track_id='fake',source_note_id='fake')
            if change == 'old_id': bad['notes'][0]['id'] = req['actual_layout']['notes'][0]['id']; bad['operations'][0]['output_note_id'] = bad['notes'][0]['id']
            if change == 'seed': bad['generation']['seed'] += 1
            if change == 'bool_version': bad['plan_version'] = True
            if change == 'original': bad['original_notes'] = []
            if change == 'null_failure': bad = n.failure_result(req,plan,plan['windows'][0]['id'],n.error('TEST','故障')); bad['notes']=None
            else:
                bad['content_fingerprint'] = n.content_fingerprint(bad['range'], bad['notes'])
                if change not in ('seed',): bad['generation'] = n.generation_data(req,plan,plan['windows'][0],bad['operations'])
            with self.subTest(change=change), self.assertRaises(m.ProjectError): n.validate_result(req,plan,bad)

    def test_no_music_change_single_note_and_shared_rest_fraud(self):
        c = ready_bridge(); cap, plan = begin(c); req = cap['request']; win = plan['windows'][0]
        original = win['original_notes'][0]
        op = dict(operation='connection-motif-cell',input_note_id=original['id'],parent_ref=n.parent_ref(req,original['id']),
            output_note_id=original['id'],rule='preserve',from_pitch=original['pitch'],to_pitch=original['pitch'],
            start_tick=original['start_tick'],duration_tick=original['duration_tick'])
        row = dict(**n.result_header(req,plan,win['id']),status='READY',notes=[original],operations=[op],
            generation=n.generation_data(req,plan,win,[op]),content_fingerprint=n.content_fingerprint({k:win[k] for k in ('start_tick','end_tick')},[original]),error=None)
        with self.assertRaises(m.ProjectError):n.validate_result(req,plan,row)
        c.cancel_connection(cap['token']); cap, plan = begin(c,((1920,3840),(3840,5760))); row=result(cap['request'],plan)
        row['notes'][-1]['duration_tick']+=1;row['operations'][-1]['duration_tick']+=1
        row['generation']=n.generation_data(cap['request'],plan,plan['windows'][0],row['operations']);row['content_fingerprint']=n.content_fingerprint(row['range'],row['notes'])
        with self.assertRaises(m.ProjectError):n.validate_result(cap['request'],plan,row)

    def test_partial_fail_preserves_bridge_and_result_without_final_caps(self):
        c=ready_bridge(); cap,plan=begin(c,((1920,3840),(5760,7680))); first=result(cap['request'],plan)
        self.assertTrue(c.record_connection_result(cap['token'],first))
        second=n.failure_result(cap['request'],plan,plan['windows'][1]['id'],n.error('TEST_FAILURE','第二连接模拟失败'))
        self.assertTrue(c.record_connection_result(cap['token'],second)); state=c.connection_state()
        self.assertEqual(state['status'],'FAILED');self.assertEqual(state['results'],[first,second]);self.assertIsNone(state['outcome']['notes'])
        self.assertFalse(state['capabilities']['can_plan_boundaries']);self.assertEqual(state['preview']['notes'],cap['request']['actual_layout']['notes'])
        self.assertEqual(state['preview']['connection_overlays'][0]['status'],'CONTENT_READY')
        self.assertEqual(state['protections'],c.bridge_state()['protections']);self.assertEqual(c._jobs,{})

    def test_raw_exact_set_and_outside_claims_do_not_bypass(self):
        for which in ('missing','duplicate','extra','changed_after_stream'):
            c=ready_bridge();cap,plan=begin(c);row=result(cap['request'],plan);rows=[copy.deepcopy(row)]
            if which=='missing':rows=[]
            if which=='duplicate':rows.append(copy.deepcopy(row))
            if which=='extra':rows[0]['connection_id']='extra'
            if which=='changed_after_stream':
                c.record_connection_result(cap['token'],row);rows[0]['notes'][0]['velocity']+=1
                rows[0]['content_fingerprint']=n.content_fingerprint(rows[0]['range'],rows[0]['notes'])
            self.assertFalse(c.finish_connection(cap['token'],n.raw_outcome(cap['request'],plan,rows)))
            self.assertEqual(c.connection_state()['status'],'FAILED');self.assertEqual(c._jobs,{})

    def test_cancel_retry_late_undo_and_preserved_old_attempt(self):
        c=ready_bridge(); before=c.project;cap,plan=begin(c);row=result(cap['request'],plan);c.record_connection_result(cap['token'],row)
        c.cancel_job(cap['token']);old=copy.deepcopy(c.connection_state());new=c.capture_connection()
        self.assertGreater(new['request']['plan_version'],cap['request']['plan_version']);self.assertNotEqual(new['token'],cap['token'])
        self.assertFalse(c.record_connection_result(cap['token'],row));self.assertFalse(c.cancel_connection(cap['token']))
        self.assertEqual(c._connection_attempt(cap['token']['request_id'])['connection']['outcome'],old['outcome'])
        c.edit('set_melody_only',value=True);c.undo();self.assertEqual(c.project,before)
        self.assertEqual(c.connection_state()['status'],'STALE');self.assertEqual(c.bridge_state()['status'],'STALE')
        self.assertFalse(c.accepts(new['token']));self.assertFalse(c.connection_state()['capabilities']['can_plan_boundaries'])
        with self.assertRaises(m.ProjectError):c.capture_connection()

    def test_pure_saved_restore_running_ready_failed_and_write_failure(self):
        for ending in ('running','ready','failed','preplan_cancel'):
            c=ready_bridge();cap=c.capture_connection()
            if ending!='preplan_cancel':
                plan=c.plan_connection(cap['token'],proposal(cap['request'],((1920,3840),)));c.begin_connection_generation(cap['token'],plan)
                row=result(cap['request'],plan);c.record_connection_result(cap['token'],row)
                if ending=='ready':c.finish_connection(cap['token'],n.raw_outcome(cap['request'],plan,[row]))
                if ending=='failed':c.fail_connection(cap['token'],n.error('TEST','保存故障事实'))
            else:c.cancel_connection(cap['token'])
            with tempfile.TemporaryDirectory() as d:
                before=c.project;undo=copy.deepcopy(c.session._undo)
                with patch.object(store,'save',side_effect=OSError('simulated write failure')):
                    with self.assertRaises(OSError):c.new()
                self.assertEqual(c.project,before);self.assertEqual(c.session._undo,undo);self.assertTrue(c.state()['staging_dirty'])
                target=Path(d)/'快照 文件.json';c.save_snapshot(target);saved=target.read_bytes()
                with patch.object(b,'decide_bridge',side_effect=AssertionError('no algorithm')),patch.object(b,'generate_bridges',side_effect=AssertionError('no algorithm')),patch.object(n,'plan_connection_blocks',side_effect=AssertionError('no algorithm')),patch.object(n,'generate_connection_blocks',side_effect=AssertionError('no algorithm')),patch('curve_memory.recompute',side_effect=AssertionError('no recompute')),patch('curve_emotion.emotion_variant',side_effect=AssertionError('no emotion')),patch('threading.Thread.start',side_effect=AssertionError('no thread')):
                    restored=w.Controller();restored.load(target);store.validate_bundle(restored._current_bundle());restored.save_snapshot(Path(d)/'另存.json')
                self.assertEqual(restored.project,before);self.assertEqual(target.read_bytes(),saved)
                self.assertEqual(restored.connection_state()['status'],'INTERRUPTED' if ending=='running' else c.connection_state()['status'])

    def test_historical_actual_velocity_not_lock_snapshot(self):
        for velocity in (80,100):
            c=ready_bridge(w.Controller(historical_automatic(velocity)));cap,plan=begin(c,())
            self.assertTrue(c.finish_connection(cap['token'],n.raw_outcome(cap['request'],plan,[])))
            self.assertEqual(c.connection_state()['outcome']['notes'][0]['velocity'],velocity)
            self.assertEqual(c.connection_state()['protections'][0]['notes'][0]['velocity'],80)

    def test_partial_candidate_preserves_remaining_gaps_and_base(self):
        c=fixture();cap=c.capture_completion(c.gap_items()[0]['id']);outcome=prepared(cap['request'],[completion_proposal(cap['request'])]);c.finish_completion(cap['token'],outcome)
        bridge=c.capture_bridge(outcome['candidates'][0]['id'],cap['token']['request_id'], algorithm_version=b.ALGORITHM);plan=c.lock_bridge(bridge['token'],decision(bridge['request']));c.begin_bridge_generation(bridge['token'],plan)
        c.finish_bridge(bridge['token'],b.generate_bridges(bridge['request'],plan));cap,plan=begin(c,())
        self.assertTrue(c.finish_connection(cap['token'],n.raw_outcome(cap['request'],plan,[])))
        self.assertEqual(c.connection_state()['remaining_gaps'],outcome['candidates'][0]['remaining_gaps'])
        self.assertFalse(c.connection_state()['capabilities']['can_export_final'])
        self.assertEqual(c.connection_state()['request']['bridge_ref']['request']['input_project'],c.project)

    def test_finite_parameters_budget_and_musical_seed_identity_independence(self):
        c=ready_bridge();cap,plan=begin(c);req=cap['request']
        for params in ({'max_notes':True},{'max_windows':9},{'min_window_ticks':4000},{'policy':'random'}):
            with self.assertRaises(m.ProjectError):n.parameters(params)
        p=proposal(req);p['search']['termination']='WINDOW_BUDGET'
        with self.assertRaises(m.ProjectError):n.make_plan(req,p)
        changed=copy.deepcopy(req);changed['request_id']='other';changed['plan_id']='other-plan';changed['plan_version']+=1
        self.assertEqual(n.musical_seed(req,plan,plan['windows'][0]),n.musical_seed(changed,plan,plan['windows'][0]))


    def test_nominal_memory_rest_and_full_crossing_note_support(self):
        c=w.Controller(m.new_project(6));tail=material('4000-tick-tail',4000)
        c.edit('add_source',source=dict(id='S',label='完整长音测试来源',length_ticks=4000,notes=copy.deepcopy(tail['notes']),provenance={'method':'test-fixture'}))
        c.edit('add_material',material=tail)
        first=w.combine(c.project,[tail]);nested=w.combine(c.project,[first,tail])
        c.edit('add_material',material=nested);c.edit('place',material_id=nested['id'],start_tick=0,placement_id='nested-use')
        c.edit('mark_blank',start_tick=8000,end_tick=11520)
        c=ready_bridge(c);cap=c.capture_connection(parameters=dict(max_window_ticks=4000));req=cap['request']
        lock=next(x for x in req['actual_layout']['protections'] if x['kind']=='memory')
        self.assertEqual(lock['end_tick'],1920);self.assertEqual(n.protection_ranges([lock]),[dict(start_tick=0,end_tick=4000)])
        self.assertGreater(len(lock['component_path']),0)
        for bounds in (((1920,3840),),((7600,8500),)):
            with self.assertRaises(m.ProjectError):c.plan_connection(cap['token'],proposal(req,bounds))
        plan=c.plan_connection(cap['token'],proposal(req,((4000,8000),)))
        c.begin_connection_generation(cap['token'],plan);row=result(req,plan)
        self.assertTrue(c.finish_connection(cap['token'],n.raw_outcome(req,plan,[row])))
        self.assertTrue(any(op['parent_ref']['component_path'] for op in row['operations']))

    def test_legal_window_but_note_extends_into_bridge_and_conflicting_duplicate(self):
        c=ready_bridge(ranges=((5760,7680),));cap,plan=begin(c,((3840,5760),));req=cap['request'];row=result(req,plan)
        protection=copy.deepcopy(c.bridge_state()['protections'])
        bad=copy.deepcopy(row);bad['notes'][-1]['duration_tick']+=10;bad['operations'][-1]['duration_tick']+=10
        bad['generation']=n.generation_data(req,plan,plan['windows'][0],bad['operations']);bad['content_fingerprint']=n.content_fingerprint(bad['range'],bad['notes'])
        self.assertFalse(c.record_connection_result(cap['token'],bad));self.assertEqual(c.connection_state()['status'],'FAILED')
        self.assertEqual(c.connection_state()['protections'],protection)
        cap,plan=begin(c,((3840,5760),));row=result(cap['request'],plan)
        c.record_connection_result(cap['token'],row);bad=copy.deepcopy(row);bad['notes'][0]['velocity']+=1;bad['content_fingerprint']=n.content_fingerprint(bad['range'],bad['notes'])
        self.assertFalse(c.record_connection_result(cap['token'],bad));self.assertEqual(c.connection_state()['status'],'FAILED')
        self.assertEqual(c.connection_state()['results'][0],row)

    def test_source_internal_rest_is_not_gap_and_memory_rest_stays_protected(self):
        tail=material('rest-phrase',1920)
        tail['notes'][0]['duration_tick']=240
        second=copy.deepcopy(tail['notes'][0]);second.update(id='n2',pitch=64,start_tick=1680)
        second['origin']['source_note_id']='n2';tail['notes'].append(second)
        c=w.Controller(m.new_project())
        c.edit('add_source',source=dict(id='S',label='带自然休止的原句',length_ticks=1920,
            notes=copy.deepcopy(tail['notes']),provenance={'method':'test-fixture'}))
        c.edit('add_material',material=tail);c.edit('place',material_id=tail['id'],start_tick=0)
        c.edit('mark_blank',start_tick=1920,end_tick=15360)
        self.assertEqual(c.gap_items(),[])
        c=ready_bridge(c);cap=c.capture_connection();req=cap['request']
        self.assertEqual(req['actual_layout']['remaining_gaps'],[])
        self.assertEqual(proposal(req,((480,960),))['windows'][0]['original_notes'],[])
        with self.assertRaises(m.ProjectError):c.plan_connection(cap['token'],proposal(req,((480,960),)))

    def test_bad_parent_registry_rejects_before_publication_and_cleans_token(self):
        c=ready_bridge();c._bundle['snapshots'][0]['content_fingerprint']='tampered-registry'
        before=copy.deepcopy(c._bundle);music=c.project;history=copy.deepcopy((c.session._undo,c.session._redo))
        with self.assertRaises(m.ProjectError):c.capture_connection()
        self.assertEqual(c._bundle,before);self.assertEqual(c.project,music);self.assertEqual((c.session._undo,c.session._redo),history)
        self.assertEqual(c._jobs,{});self.assertEqual(c.session._requests,{});self.assertIsNone(c._connection_id)

    def test_multiple_original_notes_with_only_one_pitch_edit_cannot_be_ready(self):
        for changed_index in (0, 1):
            c=ready_bridge();before=c.project;history=copy.deepcopy((c.session._undo,c.session._redo));parent=c.bridge_state()
            cap,plan=begin(c,((1920,5760),));req=cap['request'];win=plan['windows'][0]
            originals=copy.deepcopy(win['original_notes']);notes=copy.deepcopy(originals)
            changed=notes[changed_index];source=originals[changed_index]
            changed.update(id='one-pitch-only-'+str(changed_index),pitch=62,
                lineage=list(dict.fromkeys(source['lineage']+[source['id']])),slice=None)
            operations=[dict(operation='connection-motif-cell',input_note_id=p['id'],parent_ref=n.parent_ref(req,p['id']),
                output_note_id=x['id'],rule=win['technique'] if i==changed_index else 'preserve',from_pitch=p['pitch'],
                to_pitch=x['pitch'],start_tick=x['start_tick'],duration_tick=x['duration_tick']) for i,(p,x) in enumerate(zip(originals,notes))]
            row=dict(**n.result_header(req,plan,win['id']),status='READY',notes=notes,operations=operations,
                generation=n.generation_data(req,plan,win,operations),content_fingerprint=n.content_fingerprint(
                    {k:win[k] for k in ('start_tick','end_tick')},notes),error=None)
            with self.subTest(changed_index=changed_index),self.assertRaises(m.ProjectError) as exc:n.validate_result(req,plan,row)
            self.assertEqual(exc.exception.code,'NO_CONNECTION_DEVELOPMENT')
            self.assertFalse(c.finish_connection(cap['token'],n.raw_outcome(req,plan,[row])))
            self.assertEqual(c.connection_state()['status'],'FAILED');self.assertFalse(c.connection_state()['capabilities']['can_plan_boundaries'])
            self.assertEqual(c.connection_state()['error']['code'],'NO_CONNECTION_DEVELOPMENT')
            self.assertEqual(c.project,before);self.assertEqual(c.bridge_state(),parent)
            self.assertEqual((c.session._undo,c.session._redo),history);self.assertEqual(c._jobs,{})
            with tempfile.TemporaryDirectory() as directory:
                path=c.save_snapshot(Path(directory)/'single pitch rejected.json');restored=w.Controller();restored.load(path)
                self.assertEqual(restored.connection_state()['status'],'FAILED');self.assertFalse(restored.connection_state()['capabilities']['can_plan_boundaries'])
