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
from test_curve_workflow import project, material
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


class BridgeServiceTests(unittest.TestCase):
    def test_current_complete_none_no_fake_completion_or_edit(self):
        c=complete();before=c.project;history=copy.deepcopy((c.session._undo,c.session._redo))
        cap=c.capture_bridge();req=cap['request'];token=cap['token']
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
        with self.assertRaises(m.ProjectError):c.capture_bridge()
        self.assertEqual(c._bundle['attempts'],[]);self.assertEqual(c._jobs,{})
        c=complete();cap=c.capture_bridge()
        with self.assertRaises(m.ProjectError) as exc:c.capture_bridge()
        self.assertEqual(exc.exception.code,'DUPLICATE_REQUEST');self.assertTrue(c.cancel_bridge(cap['token']))
        self.assertEqual(c.bridge_state()['outcome']['plan_fingerprint'],None)

    def test_one_insufficient_candidate_local_scope_remaining_gaps(self):
        c=fixture();cap=c.capture_completion(c.gap_items()[0]['id'])
        outcome=prepared(cap['request'],[completion_proposal(cap['request'])])
        self.assertEqual(outcome['status'],'INSUFFICIENT');self.assertTrue(c.finish_completion(cap['token'],outcome))
        bridge=c.capture_bridge(outcome['candidates'][0]['id'],cap['token']['request_id'])
        req=bridge['request'];self.assertEqual(req['remaining_gaps'],outcome['candidates'][0]['remaining_gaps'])
        self.assertEqual(req['resolved_ranges'],[dict(start_tick=0,end_tick=3360)])
        self.assertEqual(c.project,req['input_project']);self.assertEqual(c.project['materials'],req['base_project']['materials'])
        self.assertTrue(c.cancel_bridge(bridge['token']))

    def test_atomic_locks_before_generation_and_failed_transaction(self):
        c=complete();cap=c.capture_bridge();token=cap['token'];req=cap['request']
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
        c=complete();cap=c.capture_bridge();req=cap['request'];token=cap['token']
        plan=c.lock_bridge(token,decision(req,[(1920,3840),(5760,7680)]));c.begin_bridge_generation(token,plan)
        first=b.failure_result(req,plan,'automatic-0',b.error('SYNTHETIC_FAILURE','模拟失败'))
        self.assertTrue(c.record_bridge_result(token,first));self.assertFalse(c.record_bridge_result(token,first))
        self.assertTrue(c.cancel_bridge(token));old=c.bridge_state();self.assertEqual(old['status'],'CANCELLED')
        self.assertEqual([r['status'] for r in old['results']],['FAILED','CANCELLED'])
        self.assertEqual([p['status'] for p in old['protections'] if p['kind']=='bridge'],['RANGE_LOCKED']*2)
        self.assertFalse(c.finish_bridge(token,raw(req,plan)));self.assertFalse(c.record_bridge_result(token,first))
        new=c.capture_bridge();self.assertGreater(new['request']['plan_version'],req['plan_version'])
        self.assertNotEqual(new['request']['plan_id'],req['plan_id']);self.assertEqual(c._bridge_attempt(token['request_id'])['protections'],old['protections'])
        self.assertFalse(c.fail_bridge(token,b.error('LATE','迟到')));self.assertEqual(c.bridge_state()['status'],'RUNNING')

    def test_edit_undo_never_revives_parent_or_bridge(self):
        c=complete();before=c.project;cap=c.capture_bridge();token=cap['token'];req=cap['request']
        c.lock_bridge(token,decision(req,[(1920,3840)]))
        c.edit('set_melody_only',value=True);c.undo();self.assertEqual(c.project,before)
        self.assertEqual(c.bridge_state()['status'],'STALE');self.assertFalse(c.accepts(token))
        self.assertFalse(c.cancel_bridge(token));self.assertFalse(c.bridge_state()['capabilities']['can_plan_connections'])
        store.validate_bundle(c._current_bundle())
        c=fixture();cap=c.capture_completion(c.gap_items()[0]['id']);outcome=prepared(cap['request'],[completion_proposal(cap['request'])])
        c.finish_completion(cap['token'],outcome);c.edit('set_melody_only',value=True);c.undo()
        with self.assertRaises(m.ProjectError):c.capture_bridge(outcome['candidates'][0]['id'],cap['token']['request_id'])

    def test_manual_none_actual_ready_set_preserves_old_lock(self):
        c=complete(manual=True);cap=c.capture_bridge();req=cap['request'];token=cap['token']
        old=copy.deepcopy([p for p in c.project['protections'] if p['kind']=='bridge'])
        plan=c.lock_bridge(token,decision(req));rows=[b.inherited_result(req,plan,owner) for owner in plan['inherited_bridge_ids']]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'READY')
        self.assertEqual(rows[0]['material'],c.project['placements'][-1]['base_snapshot'])
        c.begin_bridge_generation(token,plan);self.assertTrue(c.finish_bridge(token,raw(req,plan,rows)))
        self.assertEqual([p for p in c.bridge_state()['protections'] if p['kind']=='bridge'],old)
        self.assertEqual(c.bridge_state()['outcome']['notes'],req['base_notes'])

    def test_pure_restore_running_interrupts_without_music_calls(self):
        c=complete();cap=c.capture_bridge();plan=c.lock_bridge(cap['token'],decision(cap['request'],[(1920,3840)]))
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
        c=complete();before=c.project;cap=c.capture_bridge()
        self.assertTrue(c.fail_bridge(cap['token'],RuntimeError('decision error')))
        state=c.bridge_state();self.assertEqual(state['status'],'FAILED');self.assertIsNone(state['plan'])
        self.assertIsNone(state['outcome']['plan_fingerprint']);self.assertEqual(state['outcome']['results'],[])
        with patch('curve_store.save',side_effect=OSError('unwritable')):
            with self.assertRaises(OSError):c.save_snapshot()
        self.assertEqual(c.project,before);self.assertTrue(c.state()['is_saved']);self.assertTrue(c.state()['staging_dirty'])
        store.validate_bundle(c._current_bundle())


if __name__=='__main__':unittest.main()
