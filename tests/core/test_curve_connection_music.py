"""P6 contract music tests with actual P5/P6 service authentication.

P5 input is already authenticated by the real P5 service. P6 Request and Plan
fixtures reconstruct frozen section12 and do not claim Facade authorization.
"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import curve_bridge_music as bridge_music
import curve_bridges as bridges
import curve_connection_music as music
import curve_connections as service
import curve_project as m
from test_curve_bridge_music import fixture, window as bridge_window


def request(p=None, bridge_ranges=(), parameters=None, seed=41):
    p=copy.deepcopy(fixture(4) if p is None else p)
    token=dict(request_id='bridge-request',snapshot_id='bridge-snapshot',session_id='bridge-session',edit_revision=0,input_fingerprint=m.fingerprint(p))
    previous=bridges.make_request(p,token=token,plan_id='bridge-plan',values=dict(policy='auto' if bridge_ranges else 'none'))
    proposal=bridge_music.decide(previous)
    proposal.update(decision='selected' if bridge_ranges else 'none',windows=[
        bridge_window(previous,a,b,'bridge-'+str(i),[dict(start_tick=x,end_tick=y) for j,(x,y) in enumerate(bridge_ranges) if j!=i])
        for i,(a,b) in enumerate(bridge_ranges)])
    proposal['joint_boundary_conditions']=bridge_music._joint_conditions(proposal['windows'])
    plan=bridges.make_plan(previous,proposal);raw=bridge_music.generate(previous,plan)
    bridges.validate_raw(previous,plan,raw)
    protections=bridges.locks_with_results(previous,plan,raw['results'])
    outcome=bridges.make_outcome(previous,plan,raw['results'],raw['status'],raw['error'])
    ref=dict(attempt_id=previous['request_id'],request=previous,plan=plan,protections=protections,results=raw['results'],outcome=outcome)
    layout=dict(total_ticks=p['total_ticks'],bpm=p['bpm'],notes=copy.deepcopy(outcome['notes']),base_project=copy.deepcopy(previous['base_project']),
        bridge_overlays=bridges.preview(previous,plan,protections,raw['results'],outcome)['overlays'],protections=protections,
        blank_regions=copy.deepcopy(p['blank_regions']),remaining_gaps=copy.deepcopy(outcome['remaining_gaps']))
    ranges=[dict(start_tick=x['start_tick'],end_tick=x['end_tick']) for x in protections]
    ranges += [dict(start_tick=n['start_tick'],end_tick=n['start_tick']+n['duration_tick']) for x in protections for n in x['notes']]
    ranges=music._union(ranges)
    return dict(schema='emoblocks.connection-request.v1',spec_rev=m.SPEC_REV,contract_rev=music.CONTRACT_REV,
        request_id='connection-request',snapshot_id='connection-snapshot',session_id='session',edit_revision=0,
        input_contract_rev=p['contract_rev'],input_fingerprint=m.fingerprint(p),input_project=p,bridge_ref=ref,
        actual_layout=layout,layout_fingerprint=m.digest('emoblocks.connection-layout.v1',layout),
        protection_summary=dict(fingerprint=m.protection_summary(protections),ranges=ranges),plan_id='connection-plan',plan_version=1,
        seed=seed,algorithm_version=music.ALGORITHM_VERSION,parameters=dict(dict(policy='auto',max_windows=3,max_window_tests=128,
            max_window_ticks=3840,min_window_ticks=240,max_notes=512),**(parameters or {})))


def plan(req, windows=(), joints=()):
    old=req['bridge_ref']['plan']
    value=dict(schema='emoblocks.connection-plan.v1',spec_rev=m.SPEC_REV,contract_rev=music.CONTRACT_REV,
        id=req['plan_id'],version=req['plan_version'],request_id=req['request_id'],snapshot_id=req['snapshot_id'],
        request_fingerprint=m.digest('emoblocks.connection-request.v1',req),bridge_plan_id=old['id'],bridge_plan_version=old['version'],
        bridge_plan_fingerprint=old['plan_fingerprint'],layout_fingerprint=req['layout_fingerprint'],
        protection_summary_fingerprint=req['protection_summary']['fingerprint'],decision='selected' if windows else 'none',
        none_reason=None if windows else 'NOT_NEEDED',windows=copy.deepcopy(list(windows)),
        reasons=[dict(code='FIXTURE',message='冻结契约测试计划',details={})],assessments=[],joint_boundary_conditions=copy.deepcopy(list(joints)),
        search=dict(tested_windows=len(windows),termination='EXHAUSTED'))
    value['plan_fingerprint']=m.digest('emoblocks.connection-plan.v1',value)
    return value


def from_proposal(req,proposal):
    value=plan(req,proposal['windows'],proposal['joint_boundary_conditions'])
    for key in ('decision','none_reason','reasons','assessments','search'):value[key]=copy.deepcopy(proposal[key])
    return rehash(value)


def rehash(value):
    value['plan_fingerprint']=m.digest('emoblocks.connection-plan.v1',{k:v for k,v in value.items() if k!='plan_fingerprint'})
    return value


def notes_music(row):
    return sorted((n['pitch'],n['start_tick'],n['duration_tick']) for n in row['notes'])


class ConnectionMusicTests(unittest.TestCase):
    def test_seed_changes_actual_music_and_replay_preserves_full_result(self):
        rows=[]
        for seed in (41,42,41):
            req=request(seed=seed);before=copy.deepcopy(req)
            w=music._window(req,dict(start_tick=0,end_tick=1920),'motif_reply')
            proposal=music.plan(req)
            proposal.update(windows=[w],joint_boundary_conditions=[],decision='selected',none_reason=None)
            locked=service.make_plan(req,proposal)
            raw=music.generate(req,locked,req['actual_layout']);service.validate_raw(req,locked,raw)
            self.assertEqual('SUCCEEDED',raw['status']);self.assertEqual(before,req)
            rows.append(raw)
        self.assertNotEqual(notes_music(rows[0]['results'][0]),notes_music(rows[1]['results'][0]))
        self.assertEqual(rows[0],rows[2])

    def test_selected_and_natural_none_not_every_fourbeat_or_emotion(self):
        req=request();before=copy.deepcopy(req);proposal=music.plan(req)
        self.assertEqual('selected',proposal['decision']);self.assertEqual(before,req)
        raw=music.generate(req,from_proposal(req,proposal),req['actual_layout'])
        self.assertEqual('SUCCEEDED',raw['status'],raw)
        req=request(fixture(4,rough=False,emotions=['hope','sad','crisis','resolve']))
        proposal=music.plan(req);self.assertEqual('none',proposal['decision']);self.assertEqual('NOT_NEEDED',proposal['none_reason'])
        self.assertEqual([],music.generate(req,from_proposal(req,proposal),req['actual_layout'])['results'])

    def test_all_five_real_techniques_and_parent_lineage_metadata(self):
        req=request();by_id=m.indexed(req['actual_layout']['notes'])
        for technique in music.TECHNIQUES:
            with self.subTest(technique=technique):
                window=music._window(req,dict(start_tick=0,end_tick=1920),technique)
                raw=music.generate(req,plan(req,[window]),req['actual_layout']);self.assertEqual('SUCCEEDED',raw['status'],raw)
                row=raw['results'][0];self.assertGreaterEqual(len(row['notes']),2)
                self.assertNotEqual(notes_music(row),music._music(window['original_notes']))
                self.assertEqual('connection_phrase',row['generation']['method'])
                self.assertEqual(window['parameters'],row['generation']['parameters'])
                self.assertEqual(row['operations'],row['generation']['operations'])
                self.assertEqual([by_id[i] for i in window['context']['motif_note_ids']],row['generation']['base_notes'])
                for note,op in zip(row['notes'],row['operations']):
                    parent=by_id[op['input_note_id']]
                    self.assertEqual(note['id'],op['output_note_id']);self.assertEqual(parent['origin'],note['origin'])
                    self.assertEqual(parent['pitch'],op['from_pitch'])
                    if op['rule']=='preserve':self.assertEqual(parent,note)
                    else:
                        self.assertEqual(list(dict.fromkeys(parent['lineage']+[parent['id']])),note['lineage'])
                        self.assertIsNone(note['slice']);self.assertNotIn(note['id'],by_id)

    def test_real_bridge_context_replaces_old_endpoint_and_remains_unchanged(self):
        p=fixture(4);p['placements'][2]['base_snapshot']['notes'][-1]['pitch']=85;p['materials'][2]['notes'][-1]['pitch']=85
        next(n for n in p['sources'][0]['notes'] if n['id']=='source:2:7')['pitch']=85
        req=request(p,bridge_ranges=[(1920,5760)]);original=copy.deepcopy(req)
        w=music._window(req,dict(start_tick=5760,end_tick=7680),'diatonic_guide')
        expected=req['bridge_ref']['results'][0]['notes'][-1]
        self.assertEqual(expected,w['context']['left'])
        self.assertNotEqual(expected['id'],req['bridge_ref']['request']['base_notes'][23]['id'])
        self.assertNotEqual(expected['pitch'],req['bridge_ref']['request']['base_notes'][23]['pitch'])
        raw=music.generate(req,plan(req,[w]),req['actual_layout']);self.assertEqual('SUCCEEDED',raw['status'],raw)
        self.assertEqual(original,req)
        bridge_parent=[op for op in raw['results'][0]['operations'] if op['input_note_id']==expected['id']]
        # Even if the short phrase happens not to use the endpoint as a cell,
        # its complete captured motif/generation source still identifies it.
        self.assertIn(expected,raw['results'][0]['generation']['base_notes'])
        for op in bridge_parent:self.assertEqual('bridge',op['parent_ref']['kind'])

    def test_full_protection_and_no_legal_window_are_real_none(self):
        p=fixture(2)
        p['protections']=[dict(id='fixed',kind='manual',owner_id='user',placement_id=None,component_path=[],start_tick=0,end_tick=3840,
            status='RANGE_LOCKED',origin='manual',plan_id=None,plan_version=None,input_fingerprint='fixed',notes=[],structure_fingerprint=None,blank_mask=[])]
        req=request(p);proposal=music.plan(req)
        self.assertEqual('none',proposal['decision']);self.assertEqual('NO_LEGAL_WINDOW',proposal['none_reason'])
        self.assertTrue(proposal['assessments']);self.assertEqual(req['bridge_ref']['protections'],req['actual_layout']['protections'])

    def test_three_kinds_of_intrusion_and_crossing_original_support_rejected(self):
        req=request(bridge_ranges=[(1920,5760)])
        for a,b in ((0,3840),(0,7680),(3840,7680)):
            w=music._window(req,dict(start_tick=a,end_tick=b),'diatonic_guide')
            with self.assertRaises(m.ProjectError):music.generate(req,plan(req,[w]),req['actual_layout'])
        req=request();w=music._window(req,dict(start_tick=1,end_tick=960),'diatonic_guide')
        with self.assertRaises(m.ProjectError):music.generate(req,plan(req,[w]),req['actual_layout'])

    def test_blank_mask_and_internal_rests_not_gaps(self):
        p=fixture(4);p['placements'].pop(1);p['blank_regions']=[dict(id='blank',start_tick=1920,end_tick=3840,reason='主动留白')]
        req=request(p);proposal=music.plan(req)
        self.assertTrue(all(not m.intersects(w,p['blank_regions'][0]) for w in proposal['windows']))
        p=fixture(2);p['placements'][0]['base_snapshot']['notes']=p['placements'][0]['base_snapshot']['notes'][:1]
        req=request(p);self.assertEqual([],req['actual_layout']['remaining_gaps'])
        w=music._window(req,dict(start_tick=240,end_tick=960),'motif_reply')
        raw=music.generate(req,plan(req,[w]),req['actual_layout']);self.assertEqual('SUCCEEDED',raw['status'],raw)

    def test_joint_two_windows_reverse_and_new_identity_have_same_music(self):
        req=request();regions=[dict(start_tick=0,end_tick=1920),dict(start_tick=1920,end_tick=3840)]
        windows=[music._window(req,r,'diatonic_guide',regions) for r in regions];joints=music._joints(windows)
        raw=music.generate(req,plan(req,windows,joints),req['actual_layout']);self.assertEqual('SUCCEEDED',raw['status'],raw)
        reverse=music.generate(req,plan(req,list(reversed(windows)),joints),req['actual_layout'])
        self.assertEqual({r['connection_id']:notes_music(r) for r in raw['results']},{r['connection_id']:notes_music(r) for r in reverse['results']})
        other=copy.deepcopy(req);other.update(request_id='new-request',snapshot_id='new-snapshot',session_id='new-session',plan_id='new-plan',plan_version=9)
        new_windows=copy.deepcopy(windows)
        mapping={w['id']:'new-'+str(i) for i,w in enumerate(new_windows)}
        for w in new_windows:w['id']=mapping[w['id']]
        new_joints=[dict(j,id='new-joint',left_connection_id=mapping[j['left_connection_id']],right_connection_id=mapping[j['right_connection_id']]) for j in joints]
        replay=music.generate(other,plan(other,new_windows,new_joints),other['actual_layout'])
        self.assertEqual([notes_music(r) for r in raw['results']],[notes_music(r) for r in replay['results']])

    def test_partial_failure_and_cancel_preserve_ready_and_expected_ids(self):
        req=request();regions=[dict(start_tick=0,end_tick=960),dict(start_tick=1920,end_tick=2880)]
        windows=[music._window(req,r,'motif_reply',regions) for r in regions];p=plan(req,windows);before=copy.deepcopy(req)
        original=music._compose
        def fail_second(request,window,*a,**kw):
            if window['id']==windows[1]['id']:raise m.ProjectError('CONNECTION_GENERATION_FAILED','second fails')
            return original(request,window,*a,**kw)
        streamed=[]
        with patch.object(music,'_compose',side_effect=fail_second):raw=music.generate(req,p,req['actual_layout'],on_result=streamed.append)
        self.assertEqual('FAILED',raw['status']);self.assertEqual(['READY','FAILED'],[r['status'] for r in raw['results']])
        self.assertEqual(raw['results'],streamed);self.assertEqual(before,req)
        self.assertEqual(windows[1]['original_notes'],raw['results'][1]['original_notes']);self.assertIsNone(raw['results'][1]['generation'])
        streamed=[];raw=music.generate(req,p,req['actual_layout'],lambda:bool(streamed),on_result=streamed.append)
        self.assertEqual(['READY','CANCELLED'],[r['status'] for r in raw['results']])

    def test_cancel_every_note_callback_exception_and_no_fake_percentage(self):
        req=request();w=music._window(req,dict(start_tick=0,end_tick=1920),'motif_reply');p=plan(req,[w]);calls=[0]
        def cancel():calls[0]+=1;return calls[0]>3
        raw=music.generate(req,p,req['actual_layout'],cancel);self.assertEqual('CANCELLED',raw['status']);self.assertEqual([],raw['results'][0]['notes'])
        with self.assertRaises(RuntimeError):music.generate(req,p,req['actual_layout'],on_result=lambda r:(_ for _ in ()).throw(RuntimeError('queue fails')))
        events=[];music.generate(req,p,req['actual_layout'],on_progress=events.append)
        self.assertTrue(events);self.assertTrue(all(isinstance(e,str) and e for e in events));self.assertFalse(any('%' in e for e in events))

    def test_budget_exhaustion_without_proof_is_failure_not_no_window(self):
        req=request(parameters=dict(max_window_tests=1));req['parameters']['max_notes']=1
        with self.assertRaises(m.ProjectError) as exc:music.plan(req)
        self.assertEqual('SEARCH_BUDGET_EXHAUSTED',exc.exception.code)
        req=request(parameters=dict(max_notes=1));w=music._window(req,dict(start_tick=0,end_tick=1920),'motif_reply')
        raw=music.generate(req,plan(req,[w]),req['actual_layout']);self.assertEqual('FAILED',raw['status']);self.assertEqual([],raw['results'][0]['notes'])

    def test_bad_request_versions_parent_set_layout_and_parameters_raise(self):
        req=request()
        for mutate in (lambda r:r.update(seed=True),lambda r:r.update(layout_fingerprint='wrong'),lambda r:r['parameters'].update(max_notes=True),
            lambda r:r['bridge_ref']['outcome'].update(status='FAILED'),lambda r:r.update(contract_rev='p5')):
            bad=copy.deepcopy(req);mutate(bad)
            with self.assertRaises(m.ProjectError):music.plan(bad)
        w=music._window(req,dict(start_tick=0,end_tick=960),'motif_reply');bad=copy.deepcopy(req['actual_layout']);bad['notes'][0]['pitch']+=1
        with self.assertRaises(m.ProjectError):music.generate(req,plan(req,[w]),bad)

    def test_single_sides_different_key_and_short_precise_tick_not_quantized(self):
        req=request(fixture(2,tonic=2));w=music._window(req,dict(start_tick=0,end_tick=960),'motif_reply')
        row=music.generate(req,plan(req,[w]),req['actual_layout'])['results'][0]
        self.assertEqual(2,row['generation']['key_context']['tonic']);self.assertIsNone(w['context']['left'])
        p=fixture(2);notes=p['placements'][1]['base_snapshot']['notes'];notes[-1]['duration_tick']=239
        req=request(p);w=music._window(req,dict(start_tick=3600,end_tick=3839),'breath_close');req['parameters']['min_window_ticks']=1
        row=music.generate(req,plan(req,[w]),req['actual_layout'])['results'][0]
        self.assertEqual('READY',row['status']);self.assertEqual(1,w['parameters']['unit_ticks']);self.assertEqual(239,w['parameters']['target_ticks'])
        self.assertIsNone(w['context']['right']);self.assertEqual(239,p['placements'][1]['base_snapshot']['notes'][-1]['duration_tick'])

    def test_static_development_rejects_single_pitch_change_all_preserve_and_wrong_technique(self):
        req=request();w=music._window(req,dict(start_tick=0,end_tick=1920),'motif_reply')
        with self.assertRaises(m.ProjectError):music._verify_music(req,w,[],[dict(w['original_notes'][0],pitch=61)],[])
        with self.assertRaises(m.ProjectError):music._verify_music(req,w,[],w['original_notes'],[])
        raw=music.generate(req,plan(req,[w]),req['actual_layout']);row=raw['results'][0];bad=copy.deepcopy(row['notes']);bad[0]['pitch']=61
        with self.assertRaises(m.ProjectError):music._verify_music(req,w,[],bad,row['operations'])

    def test_no_bridge_recomposition_emotion_or_legacy_final_pipeline(self):
        req=request();w=music._window(req,dict(start_tick=0,end_tick=1920),'motif_reply')
        with patch.object(bridge_music,'generate',side_effect=AssertionError('no P5')),patch('curve_emotion.emotion_variant',side_effect=AssertionError('no emotion')),patch('story_engine.plan_story',create=True,side_effect=AssertionError('no final planner')):
            raw=music.generate(req,plan(req,[w]),req['actual_layout'])
        self.assertEqual('SUCCEEDED',raw['status']);self.assertNotIn('capabilities',raw)

    def test_real_public_plan_generation_gate_roundtrip_all_techniques(self):
        req=request();service.validate_request(req)
        for technique in music.TECHNIQUES:
            with self.subTest(technique=technique):
                w=music._window(req,dict(start_tick=0,end_tick=1920),technique)
                proposal=music.plan(req)
                proposal.update(windows=[w],joint_boundary_conditions=[],decision='selected',none_reason=None)
                locked=service.make_plan(req,proposal)
                raw=music.generate(req,locked,req['actual_layout']);service.validate_raw(req,locked,raw)
                self.assertEqual('SUCCEEDED',raw['status'],raw)

    def test_real_public_gate_adjacent_blank_and_actual_bridge_context(self):
        for req,regions in [(request(),[dict(start_tick=0,end_tick=1920),dict(start_tick=1920,end_tick=3840)]),
                (request(bridge_ranges=[(1920,5760)]),[dict(start_tick=5760,end_tick=7680)])]:
            proposal=music.plan(req)
            proposal['windows']=[music._window(req,r,'diatonic_guide',regions) for r in regions]
            proposal.update(decision='selected',none_reason=None,joint_boundary_conditions=music._joints(proposal['windows']))
            locked=service.make_plan(req,proposal);raw=music.generate(req,locked,req['actual_layout'])
            self.assertEqual('SUCCEEDED',raw['status'],raw);service.validate_raw(req,locked,raw)
            self.assertEqual(req['actual_layout']['protections'],req['bridge_ref']['protections'])

    def test_public_gate_rejects_tampered_structure_origin_parent_seed_and_impact(self):
        req=request();proposal=music.plan(req);locked=service.make_plan(req,proposal);raw=music.generate(req,locked,req['actual_layout'])
        row=raw['results'][0];service.validate_result(req,locked,row)
        changes=[lambda r:r['notes'][0].update(pitch=61),lambda r:r['notes'][0].update(start_tick=r['range']['start_tick']-1),
            lambda r:r['notes'][0].update(duration_tick=99999),lambda r:r['notes'][0]['origin'].update(source_note_id='source:1:0'),
            lambda r:r['notes'][0]['lineage'].append('fake'),lambda r:r['operations'][0]['parent_ref'].update(note_id='wrong'),
            lambda r:r['generation'].update(seed=1),lambda r:r.update(range=dict(start_tick=0,end_tick=1)),
            lambda r:r['notes'].append(dict(r['notes'][0],id='extra'))]
        for change in changes:
            bad=copy.deepcopy(row);change(bad);bad['content_fingerprint']=service.content_fingerprint(bad['range'],bad['notes'])
            with self.assertRaises(m.ProjectError):service.validate_result(req,locked,bad)

    def test_none_with_manual_bridge_keeps_actual_velocity_not_old_lock(self):
        import curve_emotion
        p=fixture(2,rough=False);place=p['placements'][0]
        place['base_snapshot']['kind']='bridge';p['materials'][0]['kind']='bridge';m.register_manual_bridge(p,place)
        p['intensity_points']=[dict(tick=0,level=1.),dict(tick=3840,level=1.)]
        protected=[dict(n,start_tick=n['start_tick']) for n in place['base_snapshot']['notes']]
        place.update(emotion='hope',emotion_variant=curve_emotion.emotion_variant(place['base_snapshot'],'hope',p['intensity_points'],0,protected,
            protected_ranges=[dict(start_tick=0,end_tick=1920)]))
        m.validate(p);req=request(p);before=copy.deepcopy(req);proposal=music.plan(req)
        self.assertEqual('none',proposal['decision']);locked=service.make_plan(req,proposal)
        raw=music.generate(req,locked,req['actual_layout']);service.validate_raw(req,locked,raw)
        outcome=service.make_outcome(req,locked,raw['results'],raw['status'])
        self.assertEqual(req['actual_layout']['notes'],outcome['notes'])
        self.assertNotEqual(req['actual_layout']['notes'][0]['velocity'],p['protections'][0]['notes'][0]['velocity'])
        self.assertEqual(before,req)

    def test_long_memory_full_support_before_nominal_range(self):
        import curve_memory
        p=fixture(4);whole=copy.deepcopy(p['materials'][0]);whole.update(id='whole',length_ticks=7680)
        whole['notes']=[dict(n,id='whole:'+str(i)) for i,n in enumerate([n for place in p['placements'] for n in m.placed_notes(place)])]
        whole['notes']=[n for n in whole['notes'] if not 1680<=n['start_tick']<=1920]
        whole['notes'].append(dict(copy.deepcopy(p['materials'][0]['notes'][0]),id='long',start_tick=1800,duration_tick=300))
        whole['notes'].sort(key=lambda n:n['start_tick']);p['materials'].append(whole)
        p['placements']=[dict(id='whole-use',material_id='whole',base_snapshot=whole,start_tick=0,length_ticks=7680,emotion='calm',emotion_variant=None)]
        p['intensity_points']=[dict(tick=0,level=.2),dict(tick=1920,level=1.),dict(tick=7680,level=.1)]
        p['protections']=[curve_memory.expected_protection(p)];m.validate(p);req=request(p)
        self.assertEqual(1800,req['protection_summary']['ranges'][0]['start_tick'])
        w=music._window(req,dict(start_tick=0,end_tick=1920),'motif_reply')
        with self.assertRaises(m.ProjectError):music.generate(req,plan(req,[w]),req['actual_layout'])
        proposal=music.plan(req)
        self.assertTrue(all(not m.intersects(w,req['protection_summary']['ranges'][0]) for w in proposal['windows']))

    def test_arbitrary_nested_combination_ids_resolve_concrete_occurrences(self):
        p=fixture(4);leaf=copy.deepcopy(p['materials'][0])
        def combo(ident,children):
            parts=[];notes=[];offset=0
            for i,c in enumerate(children):
                parts.append(dict(occurrence_id=ident+':part:'+str(i),offset_tick=offset,snapshot=copy.deepcopy(c)))
                count=len(notes);notes.extend(dict(n,id=ident+':flat:'+str(count+j),start_tick=offset+n['start_tick']) for j,n in enumerate(c['notes']))
                offset+=c['length_ticks']
            return dict(id=ident,label=ident,kind='combination',length_ticks=offset,notes=notes,provenance=leaf['provenance'],generation=None,phrase_id=None,children=parts)
        inner=combo('inner',[leaf,leaf]);outer=combo('outer',[inner,inner]);p['materials'].append(outer)
        p['placements']=[dict(id='nested',material_id=outer['id'],base_snapshot=outer,start_tick=0,length_ticks=7680,emotion='calm',emotion_variant=None)]
        req=request(p);w=music._window(req,dict(start_tick=1920,end_tick=3840),'motif_reply')
        proposal=music.plan(req);proposal.update(windows=[w],joint_boundary_conditions=[],decision='selected',none_reason=None)
        locked=service.make_plan(req,proposal);raw=music.generate(req,locked,req['actual_layout']);service.validate_raw(req,locked,raw)
        paths={tuple(o['parent_ref']['component_path']) for o in raw['results'][0]['operations']}
        self.assertIn(('outer:part:0','inner:part:1'),paths)

    def test_facade_real_streaming_partial_failure_pure_restore_and_late_callback(self):
        import curve_workflow,curve_store,curve_memory,curve_emotion
        controller=curve_workflow.Controller(fixture(4));cap=controller.capture_bridge(parameters=dict(policy='none'))
        bp=controller.lock_bridge(cap['token'],bridge_music.decide(cap['request']));controller.begin_bridge_generation(cap['token'],bp)
        self.assertTrue(controller.finish_bridge(cap['token'],bridge_music.generate(cap['request'],bp)))
        cap=controller.capture_connection();req=cap['request'];token=cap['token'];before=copy.deepcopy(controller.project)
        regions=[dict(start_tick=0,end_tick=960),dict(start_tick=1920,end_tick=2880)]
        proposal=music.plan(req);proposal['windows']=[music._window(req,r,'motif_reply',regions) for r in regions]
        proposal.update(decision='selected',none_reason=None,joint_boundary_conditions=[])
        locked=controller.plan_connection(token,proposal);self.assertTrue(controller.begin_connection_generation(token,locked))
        original=music._compose;accepted=[]
        def failing(request,window,*a,**kw):
            if window['id']==locked['windows'][1]['id']:raise m.ProjectError('CONNECTION_GENERATION_FAILED','explicit second failure')
            return original(request,window,*a,**kw)
        with patch.object(music,'_compose',side_effect=failing):
            raw=music.generate(req,locked,req['actual_layout'],on_result=lambda row:accepted.append(controller.record_connection_result(token,row)))
        state=controller.connection_state();self.assertEqual('FAILED',state['status']);self.assertEqual([True,True],accepted)
        self.assertEqual(['READY','FAILED'],[r['status'] for r in state['results']]);self.assertEqual(before,controller.project)
        self.assertFalse(controller.finish_connection(token,raw));self.assertFalse(controller.record_connection_result(token,raw['results'][0]))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'p6-partial.json'
            with patch.object(music,'plan',side_effect=AssertionError('pure restore')),patch.object(music,'generate',side_effect=AssertionError('pure restore')),patch.object(bridge_music,'generate',side_effect=AssertionError('pure restore')),patch.object(curve_memory,'recompute',side_effect=AssertionError('pure restore')),patch.object(curve_emotion,'emotion_variant',side_effect=AssertionError('pure restore')):
                controller.save_snapshot(path);loaded=curve_store.load(path)
                attempt=loaded['bundle']['attempts'][-1];self.assertEqual('FAILED',attempt['state'])
                self.assertEqual(state['results'],attempt['connection']['results'])

    def test_real_partial_p4_candidate_remaining_gap_is_never_written(self):
        import curve_candidates,curve_workflow
        from test_curve_candidates import fixture as p4_fixture
        controller=p4_fixture();cap=controller.capture_completion(controller.gap_items()[0]['id'])
        outcome=curve_candidates.prepare_completion(cap['request']);self.assertTrue(outcome['candidates'],outcome)
        self.assertTrue(controller.finish_completion(cap['token'],outcome))
        cap=controller.capture_bridge(outcome['candidates'][0]['id'],cap['attempt_id'],parameters=dict(policy='none'))
        bp=controller.lock_bridge(cap['token'],bridge_music.decide(cap['request']));controller.begin_bridge_generation(cap['token'],bp)
        self.assertTrue(controller.finish_bridge(cap['token'],bridge_music.generate(cap['request'],bp)))
        cap=controller.capture_connection();req=cap['request'];proposal=music.plan(req)
        self.assertTrue(req['actual_layout']['remaining_gaps'])
        self.assertTrue(all(not m.intersects(w,g) for w in proposal['windows'] for g in req['actual_layout']['remaining_gaps']))
        w=music._window(req,dict(start_tick=1200,end_tick=1440),'density_shift')
        proposal.update(windows=[w],decision='selected',none_reason=None,joint_boundary_conditions=[])
        locked=service.make_plan(req,proposal);raw=music.generate(req,locked,req['actual_layout']);service.validate_raw(req,locked,raw)
        self.assertEqual('SUCCEEDED',raw['status'],raw)

    def test_many_preserved_attacks_remain_full_original_notes(self):
        req=request(parameters=dict(max_window_ticks=7680));w=music._window(req,dict(start_tick=0,end_tick=7680),'retain_develop')
        raw=music.generate(req,plan(req,[w]),req['actual_layout']);service.validate_raw(req,plan(req,[w]),raw)
        self.assertEqual('SUCCEEDED',raw['status'],raw)
        for original in w['original_notes']:
            if original['start_tick']+original['duration_tick']<=3840:self.assertIn(original,raw['results'][0]['notes'])

    def test_different_keys_and_joint_real_rests(self):
        p=fixture(4);second=copy.deepcopy(p['sources'][0]);second['id']='S2'
        for n in second['notes']:n['pitch']+=2;n['origin']['source_id']='S2'
        p['sources'].append(second)
        place=p['placements'][1];place['base_snapshot']['provenance']['key_context']['tonic']=2
        for n in place['base_snapshot']['notes']:n['pitch']+=2;n['origin']['source_id']='S2'
        req=request(p);regions=[dict(start_tick=0,end_tick=1920),dict(start_tick=1920,end_tick=3840)]
        windows=[music._window(req,r,'diatonic_guide',regions) for r in regions]
        self.assertEqual([0,2],[w['key_context']['tonic'] for w in windows])
        joints=music._joints(windows);locked=plan(req,windows,joints)
        raw=music.generate(req,locked,req['actual_layout']);self.assertEqual('SUCCEEDED',raw['status'],raw);service.validate_raw(req,locked,raw)
        windows[0]=music._window(req,regions[0],'breath_close',regions)
        joints=music._joints(windows);joints[0]['right_endpoint']=None
        locked=plan(req,windows,joints);raw=music.generate(req,locked,req['actual_layout'])
        self.assertEqual('SUCCEEDED',raw['status'],raw);service.validate_raw(req,locked,raw)
        self.assertLess(raw['results'][0]['notes'][-1]['start_tick']+raw['results'][0]['notes'][-1]['duration_tick'],1920)
        self.assertGreater(raw['results'][1]['notes'][0]['start_tick'],1920)

    def test_new_p5_bridge_identity_changes_auth_hash_but_not_p6_music(self):
        first=request(bridge_ranges=[(1920,5760)]);other=copy.deepcopy(first);ref=other['bridge_ref'];p=other['input_project']
        old=bridges.make_request(p,token=dict(request_id='another-p5-request',snapshot_id='another-p5-snapshot',session_id='another-p5-session',edit_revision=1,input_fingerprint=m.fingerprint(p)),plan_id='another-p5-plan',plan_version=7)
        proposal=bridge_music.decide(old);proposal.update(decision='selected',windows=[bridge_window(old,1920,5760,'another-bridge')],joint_boundary_conditions=[])
        bp=bridges.make_plan(old,proposal);raw=bridge_music.generate(old,bp);bridges.validate_raw(old,bp,raw)
        ref=dict(attempt_id=old['request_id'],request=old,plan=bp,protections=bridges.locks_with_results(old,bp,raw['results']),results=raw['results'],outcome=bridges.make_outcome(old,bp,raw['results'],raw['status']))
        other=service.make_request(p,ref,seed=41)
        self.assertNotEqual(first['layout_fingerprint'],other['layout_fingerprint'])
        region=dict(start_tick=5760,end_tick=7680)
        w1=music._window(first,region,'motif_reply');w2=music._window(other,region,'motif_reply')
        r1=music.generate(first,plan(first,[w1]),first['actual_layout'])['results'][0]
        r2=music.generate(other,plan(other,[w2]),other['actual_layout'])['results'][0]
        self.assertEqual(r1['generation']['seed'],r2['generation']['seed']);self.assertEqual(notes_music(r1),notes_music(r2))

    def test_planning_can_be_cancelled_and_duplicate_partial_stream_stays_running(self):
        req=request()
        with self.assertRaises(m.ProjectError) as exc:music.plan(req,lambda:True)
        self.assertEqual('CANCELLED',exc.exception.code)
        import curve_workflow
        c=curve_workflow.Controller(fixture(4));cap=c.capture_bridge(parameters=dict(policy='none'))
        bp=c.lock_bridge(cap['token'],bridge_music.decide(cap['request']));c.begin_bridge_generation(cap['token'],bp)
        c.finish_bridge(cap['token'],bridge_music.generate(cap['request'],bp))
        cap=c.capture_connection();req=cap['request'];proposal=music.plan(req);locked=c.plan_connection(cap['token'],proposal)
        c.begin_connection_generation(cap['token'],locked);raw=music.generate(req,locked,req['actual_layout'])
        row=raw['results'][0];self.assertTrue(c.record_connection_result(cap['token'],row))
        self.assertFalse(c.record_connection_result(cap['token'],row));self.assertEqual('RUNNING',c.connection_state()['status'])
        self.assertTrue(c.cancel_connection(cap['token']));self.assertFalse(c.finish_connection(cap['token'],raw))
        state=c.connection_state();self.assertEqual('READY',state['results'][0]['status']);self.assertFalse(state['capabilities']['can_plan_boundaries'])


if __name__=='__main__':unittest.main()
