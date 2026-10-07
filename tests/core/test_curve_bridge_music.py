"""P5 real phrase/lineage tests using independent frozen Request/Plan fixtures.

The plan helper models published data, not Controller transaction authorization.
Actual phase/late-token/restore/authentication acceptance belongs to lead tests.
"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import curve_bridge_music as bridge
import curve_emotion as emotion
import curve_melody as melody
import curve_project as m


def fixture(blocks=4, rough=True, emotions=None, tail=0, tonic=0):
    p = m.new_project(blocks); p['project_id'] = 'p5-music-fixture'
    source_notes = []; length = p['total_ticks'] - tail
    for index in range(blocks):
        start = index*1920; duration = min(1920, length-start)
        if duration <= 0:
            continue
        notes = []
        for j, onset in enumerate(range(0, duration, 240)):
            pitch = ((60 if j % 2 == 0 else 84) if rough else (60, 62, 64, 67)[j % 4]) + tonic
            sid = 'source:%d:%d' % (index, j)
            note = dict(id='note:%d:%d' % (index, j), pitch=pitch, start_tick=onset,
                duration_tick=min(240, duration-onset), velocity=80,
                origin=dict(source_id='S', track_id='track', source_note_id=sid), lineage=[], slice=None)
            notes.append(note); source_notes.append(dict(copy.deepcopy(note), id=sid, start_tick=start+onset))
        material = dict(id='material:%d' % index, label='fixture', kind='phrase', length_ticks=duration,
            notes=notes, provenance=dict(source_id='S', source_start_tick=start,
                key_context=dict(tonic=tonic, mode='major', confidence=1., method='fixture-explicit')),
            generation=None, phrase_id=None, children=[])
        p['materials'].append(material)
        p['placements'].append(dict(id='place:%d' % index, material_id=material['id'], base_snapshot=copy.deepcopy(material),
            start_tick=start, length_ticks=duration, emotion=(emotions or ['calm']*blocks)[index], emotion_variant=None))
    p['sources'] = [dict(id='S', label='source', length_ticks=p['total_ticks'], notes=source_notes, provenance=dict(track_id='track'))]
    if tail:
        p['blank_regions'] = [dict(id='tail-rest', start_tick=length, end_tick=p['total_ticks'], reason='主动留白')]
    m.validate(p)
    return p


def request(p=None, parameters=None, seed=31):
    p = copy.deepcopy(fixture() if p is None else p); fp = m.fingerprint(p)
    gaps = m.gaps(p); cursor = 0; resolved = []
    for gap in gaps:
        if cursor < gap['start_tick']:
            resolved.append(dict(start_tick=cursor, end_tick=gap['start_tick']))
        cursor = gap['end_tick']
    if cursor < p['total_ticks']:
        resolved.append(dict(start_tick=cursor, end_tick=p['total_ticks']))
    ranges = sorted({(r['start_tick'], r['end_tick']) for v in p['protections'] for r in m.protection_ranges(v)})
    return dict(schema='emoblocks.bridge-request.v1', spec_rev=m.SPEC_REV, contract_rev=bridge.CONTRACT_REV,
        request_id='request', snapshot_id='snapshot', session_id='session', edit_revision=0,
        input_contract_rev=p['contract_rev'], input_fingerprint=fp, input_project=p,
        input_kind='current_complete', completion_ref=None, base_project=copy.deepcopy(p), base_fingerprint=fp,
        resolved_ranges=resolved, remaining_gaps=[dict(id=m.digest('emoblocks.gap.v1',dict(input_fingerprint=fp,range=r)),**r) for r in gaps], base_notes=sorted(
            [n for v in p['placements'] for n in m.placed_notes(v)], key=lambda n:(n['start_tick'], n['pitch'], n['duration_tick'], n['id'])),
        protection_summary=dict(fingerprint=m.protection_summary(p['protections']), ranges=[dict(start_tick=a, end_tick=b) for a,b in ranges]),
        blank_regions=copy.deepcopy(p['blank_regions']), plan_id='plan', plan_version=1,
        seed=seed, algorithm_version=bridge.ALGORITHM_VERSION,
        parameters=dict(dict(policy='auto', max_windows=2, max_window_blocks=8, max_window_tests=128, max_notes=512), **(parameters or {})))


def window(req, start, end, ident='window', other_ranges=()):
    places = sorted(req['base_project']['placements'], key=lambda p:p['start_tick'])
    regions = [dict(start_tick=start, end_tick=end)] + list(other_ranges)
    touched = [p for p in places if start < p['start_tick']+p['length_ticks'] and p['start_tick'] < end]
    outside = [p for p in places if not any(r['start_tick'] < p['start_tick']+p['length_ticks'] and p['start_tick'] < r['end_tick'] for r in regions)]
    lefts = [p for p in outside if p['start_tick']+p['length_ticks'] <= start]
    rights = [p for p in outside if p['start_tick'] >= end]
    left = lefts[-1] if lefts else None; right = rights[0] if rights else None
    inner = [n for n in req['base_notes'] if start <= n['start_tick'] < end]
    return dict(id=ident, start_tick=start, end_tick=end, placement_ids=[p['id'] for p in touched],
        context=dict(left=dict(placement_id=left['id'], notes=m.placed_notes(left)) if left else None,
            right=dict(placement_id=right['id'], notes=m.placed_notes(right)) if right else None,
            motif_note_ids=[n['id'] for n in inner[:6]],
            key_context=copy.deepcopy(touched[0]['base_snapshot']['provenance']['key_context'])),
        emotion_segments=[dict(start_tick=max(start,p['start_tick']), end_tick=min(end,p['start_tick']+p['length_ticks']), emotion=p['emotion']) for p in touched],
        blank_mask=[dict(start_tick=max(start,b['start_tick']),end_tick=min(end,b['end_tick'])) for b in req['blank_regions'] if start < b['end_tick'] and b['start_tick'] < end])


def locked_plan(req, windows=(), joints=()):
    # Independently reconstruct the documented transaction output.
    inherited = [p for p in req['base_project']['protections'] if p['kind'] == 'bridge']
    locks = copy.deepcopy(req['base_project']['protections'])
    refs = [dict(bridge_id=w['id'], protection_id='lock:'+w['id']) for w in windows]
    refs += [dict(bridge_id=p['owner_id'],protection_id=p['id']) for p in inherited]
    for w, ref in zip(windows, refs):
        locks.append(dict(id=ref['protection_id'], kind='bridge', owner_id=w['id'], placement_id=None, component_path=[],
            start_tick=w['start_tick'],end_tick=w['end_tick'],status='RANGE_LOCKED', origin='automatic', plan_id=req['plan_id'],
            plan_version=req['plan_version'], input_fingerprint=req['input_fingerprint'], notes=[],structure_fingerprint=None,blank_mask=copy.deepcopy(w['blank_mask'])))
    plan = dict(schema='emoblocks.bridge-plan.v1',spec_rev=m.SPEC_REV,contract_rev=bridge.CONTRACT_REV,
        id=req['plan_id'],version=req['plan_version'],request_id=req['request_id'],snapshot_id=req['snapshot_id'],
        input_fingerprint=req['input_fingerprint'],base_fingerprint=req['base_fingerprint'],candidate_id=None,
        request_fingerprint=m.digest('emoblocks.bridge-request.v1',req), decision='selected' if windows else 'none',
        windows=copy.deepcopy(list(windows)),inherited_bridge_ids=[p['owner_id'] for p in inherited],protection_refs=refs,
        reasons=[dict(code='FIXTURE',message='冻结测试计划',details={})],assessments=[],joint_boundary_conditions=copy.deepcopy(list(joints)),
        search=dict(tested_windows=len(windows),termination='EXHAUSTED'),range_lock_fingerprint=m.protection_summary(locks))
    plan['plan_fingerprint'] = m.digest('emoblocks.bridge-plan.v1',plan)
    return plan


def rehash(plan):
    plan['plan_fingerprint'] = m.digest('emoblocks.bridge-plan.v1',{k:v for k,v in plan.items() if k != 'plan_fingerprint'})
    return plan


def music(result):
    return [(n['pitch'],n['start_tick'],n['duration_tick']) for n in result['notes']]


class BridgeMusicTests(unittest.TestCase):
    def test_selected_two_three_four_long_and_natural_none(self):
        for count in (2,3,4,8):
            with self.subTest(count=count):
                req = request(fixture(count)); original = copy.deepcopy(req)
                proposal = bridge.decide(req)
                self.assertEqual('selected',proposal['decision'])
                chosen=proposal['windows'][0]
                self.assertEqual(count,(chosen['end_tick']-chosen['start_tick']+1919)//1920)
                self.assertTrue(any(a.get('benefit',0) and a['benefit'] > 0 for a in proposal['assessments']))
                self.assertEqual(req,original)
                self.assertLessEqual(proposal['search']['tested_windows'],128)
                # Explicit whole-length windows must all be musically generatable.
                w = window(req,0,count*1920)
                result = bridge.generate(req,locked_plan(req,[w]))
                self.assertEqual('SUCCEEDED',result['status'],result)
                self.assertEqual(count, len(result['results'][0]['children']))
        for count in (2,3,4,8):
            req=request(fixture(count,rough=False))
            self.assertEqual('none',bridge.decide(req)['decision'])

    def test_exact_length_source_ledger_development_and_no_base_mutation(self):
        req=request(fixture(3)); w=window(req,0,5760); plan=locked_plan(req,[w]); before=copy.deepcopy((req,plan))
        row=bridge.generate(req,plan)['results'][0]; base=row['base_material']
        self.assertEqual('phrase',row['material']['kind']); self.assertEqual(5760,base['length_ticks'])
        self.assertEqual(len(base['notes']),len(row['operations']))
        rules={c['rule'] for c in row['operations']}
        self.assertTrue({'opening','answer','arrival'} <= rules)
        self.assertNotEqual(music(row),[(n['pitch'],n['start_tick'],n['duration_tick']) for n in req['base_notes']])
        parents={n['id']:n for n in req['base_notes']}
        for c,n in zip(row['operations'],base['notes']):
            parent=parents[c['input_note_id']]
            self.assertEqual(n['origin'],parent['origin']); self.assertIn(parent['id'],n['lineage'])
            self.assertEqual((n['pitch'],n['start_tick'],n['duration_tick']),(c['to_pitch'],c['start_tick'],c['duration_tick']))
            self.assertIsNone(n['slice'])
        self.assertEqual(before,(req,plan))
        for child in row['children']:
            self.assertEqual(row['material']['id'],child['phrase_id'])
        self.assertEqual('lock:window',row['protection_id'])

    def test_new_uuid_reverse_order_and_joint_endpoint_invariance(self):
        req=request(fixture(4,emotions=['hope','sad','crisis','resolve']))
        first=window(req,0,3840,'A',[dict(start_tick=3840,end_tick=7680)])
        second=window(req,3840,7680,'B',[dict(start_tick=0,end_tick=3840)])
        joint=dict(id='joint',left_bridge_id='A',right_bridge_id='B',tick=3840,relation='shared-tonic',
            reasons=[],left_endpoint=dict(pitch=60,start_tick=3720,duration_tick=120),right_endpoint=dict(pitch=60,start_tick=3840,duration_tick=120))
        plan=locked_plan(req,[first,second],[joint]); rows=bridge.generate(req,plan)['results']
        self.assertEqual((60,3720,120),music(rows[0])[-1]); self.assertEqual((60,3840,120),music(rows[1])[0])
        reverse=locked_plan(req,[second,first],[joint]); backwards=bridge.generate(req,reverse)['results']
        self.assertEqual({r['bridge_id']:music(r) for r in rows},{r['bridge_id']:music(r) for r in backwards})
        other=copy.deepcopy(req)
        other.update(request_id='request2',snapshot_id='snapshot2',session_id='session2',plan_id='plan2',plan_version=17)
        new_windows=copy.deepcopy([first,second]); new_windows[0]['id']='AA';new_windows[1]['id']='BB'
        new_joint=dict(joint,id='joint2',left_bridge_id='AA',right_bridge_id='BB')
        replay=bridge.generate(other,locked_plan(other,new_windows,[new_joint]))['results']
        self.assertEqual([music(r) for r in rows],[music(r) for r in replay])

    def test_each_emotion_segment_same_base_and_note_owned_once(self):
        req=request(fixture(3,emotions=['hope','crisis','sad'])); w=window(req,0,5760)
        row=bridge.generate(req,locked_plan(req,[w]))['results'][0]
        self.assertEqual(1,row['emotion_processing']['pass_count'])
        base=row['base_material']; selected=[]
        for segment in row['emotion_processing']['segments']:
            variant=segment['variant']; generation=variant['generation']
            self.assertEqual(base['notes'],generation['base_notes'])
            self.assertEqual([base['id']],generation['input_material_ids'])
            self.assertEqual(segment['emotion'],generation['emotion'])
            selected += [n for n in variant['notes'] if segment['range']['start_tick'] <= n['start_tick'] < segment['range']['end_tick']]
        self.assertEqual(sorted(selected,key=lambda n:(n['start_tick'],n['id'])),row['material']['notes'])
        self.assertEqual(len(base['notes']),len(selected))

    def test_one_sided_non_c_key_and_actual_rest_mask(self):
        req=request(fixture(4,tail=240,tonic=2)); w=window(req,3840,7680)
        self.assertIsNotNone(w['context']['left']);self.assertIsNone(w['context']['right'])
        row=bridge.generate(req,locked_plan(req,[w]))['results'][0]
        self.assertEqual(2,row['base_material']['generation']['key_context']['tonic'])
        self.assertTrue(all(n['start_tick']+n['duration_tick'] <= 7440 for n in row['notes']))
        # Real interior blank, not fabricated completion or cropped source.
        p=fixture(4); p['placements'].pop(1)
        p['blank_regions']=[dict(id='rest',start_tick=1920,end_tick=3840,reason='主动留白')];m.validate(p)
        req=request(p);row=bridge.generate(req,locked_plan(req,[window(req,0,7680)]))['results'][0]
        self.assertTrue(all(not (n['start_tick'] < 3840 and n['start_tick']+n['duration_tick'] > 1920) for n in row['notes']))

    def test_exact_one_tick_and_240_tail_children_without_quantizing(self):
        req=request(fixture(3)); w=window(req,0,4080)
        # Need a boundary not cutting the captured 3840..4080 actual note.
        row=bridge.generate(req,locked_plan(req,[w]))['results'][0]
        self.assertEqual([1920,1920,240],[c['length_ticks'] for c in row['children']])
        req=request(fixture(2)); w=window(req,0,1)
        # Original note must fit whole support. A 1tick actual source event is
        # legal; the rest of this placed phrase is an internal rest, not gap.
        for project in (req['input_project'],req['base_project']):
            project['placements'][0]['base_snapshot']['notes']=project['placements'][0]['base_snapshot']['notes'][:1]
            project['placements'][0]['base_snapshot']['notes'][0]['duration_tick']=1
        req=request(req['base_project']);w=window(req,0,1)
        row=bridge.generate(req,locked_plan(req,[w]))['results'][0]
        self.assertEqual([(60,0,1)],music(row));self.assertEqual(1,row['children'][0]['length_ticks'])

    def test_long_note_boundary_is_not_a_fourbeat_transition(self):
        p=fixture(2)
        actual=p['placements'][0]['base_snapshot']
        actual['notes']=[dict(n,start_tick=i*300,duration_tick=300) for i,n in enumerate(actual['notes'][:6])]
        req=request(p)
        bad=window(req,0,1700)
        with self.assertRaises(m.ProjectError):bridge.generate(req,locked_plan(req,[bad]))
        whole=window(req,0,3840);row=bridge.generate(req,locked_plan(req,[whole]))['results'][0]
        self.assertTrue(any(n['start_tick'] < 1920 < n['start_tick']+n['duration_tick'] for n in row['base_material']['notes']) or
            not any(n['start_tick']==1920 for n in row['base_material']['notes']))

    def test_all_blank_and_policy_none_are_real_no_bridge_versions(self):
        p=m.new_project(4);p['project_id']='blank';p['blank_regions']=[dict(id='all',start_tick=0,end_tick=p['total_ticks'],reason='主动留白')]
        req=request(p);proposal=bridge.decide(req)
        self.assertEqual('none',proposal['decision']);self.assertTrue(proposal['reasons'])
        self.assertEqual('SUCCEEDED',bridge.generate(req,locked_plan(req))['status'])
        req=request();req['parameters']['policy']='none'
        proposal=bridge.decide(req);self.assertEqual('POLICY_NONE',proposal['search']['termination'])
        self.assertEqual([],bridge.generate(req,locked_plan(req))['results'])

    def test_manual_bridge_none_inherits_identity_and_original_lock(self):
        p=fixture(2);place=p['placements'][0];place['base_snapshot']['kind']='bridge'
        p['materials'][0]['kind']='bridge';m.register_manual_bridge(p,place);m.validate(p)
        req=request(p);plan=locked_plan(req);before=copy.deepcopy(req)
        with patch.object(emotion,'emotion_variant',side_effect=AssertionError('no inherited recomposition')):
            raw=bridge.generate(req,plan)
        row=raw['results'][0]
        self.assertEqual('SUCCEEDED',raw['status']);self.assertEqual('inherited',row['origin'])
        self.assertEqual(m.placed_notes(place),row['notes']);self.assertEqual([],row['children'])
        self.assertEqual(plan['id'],row['plan_id']);self.assertNotEqual(row['plan_id'],p['protections'][0]['plan_id'])
        self.assertEqual(before,req)
        # Existing P3 bridge protection is never weakened by P5.
        with self.assertRaises(m.ProjectError):emotion.emotion_variant(place['base_snapshot'],'hope',p['intensity_points'],0,[])

    def test_protection_layers_and_pending_bridge_lock_are_not_writable(self):
        p=fixture(4)
        lock=dict(id='protected',kind='manual',owner_id='user',placement_id=None,component_path=[],start_tick=0,end_tick=3840,
            status='RANGE_LOCKED',origin='manual',plan_id=None,plan_version=None,input_fingerprint='original',notes=[],structure_fingerprint=None,blank_mask=[])
        p['protections']=[lock];m.validate(p)
        for kind in ('manual','theme','memory'):
            p['protections'][0]['kind']=kind;req=request(p)
            with self.assertRaises(m.ProjectError):bridge.generate(req,locked_plan(req,[window(req,0,3840)]))
            proposal=bridge.decide(req)
            self.assertTrue(all(w['start_tick'] >= 3840 for w in proposal['windows']))

    def test_public_lock_mapping_and_plan_tampering_rejected_even_rehashed(self):
        req=request();w=window(req,0,3840);plan=locked_plan(req,[w])
        mutations=[lambda p:p['protection_refs'].clear(),lambda p:p['protection_refs'].append(p['protection_refs'][0]),
            lambda p:p['protection_refs'][0].update(protection_id='wrong-lock'),lambda p:p.update(version=7),
            lambda p:p['windows'][0].update(blank_mask=[dict(start_tick=0,end_tick=120)]),
            lambda p:p['windows'][0]['context'].update(motif_note_ids=['unrelated'])]
        for mutate in mutations:
            altered=copy.deepcopy(plan);mutate(altered);rehash(altered)
            with self.subTest(plan=altered):
                with self.assertRaises(m.ProjectError):bridge.generate(req,altered)

    def test_invalid_stale_incomplete_input_and_bad_parameters_are_errors_not_none(self):
        req=request();invalid=copy.deepcopy(req);invalid['base_fingerprint']='stale'
        with self.assertRaises(m.ProjectError):bridge.decide(invalid)
        p=fixture();p['placements'].pop(1)
        with self.assertRaises(m.ProjectError):bridge.decide(request(p))
        for key,value in [('max_notes',True),('max_window_tests',2049),('seed',-1)]:
            bad=copy.deepcopy(req)
            if key=='seed':bad[key]=value
            else:bad['parameters'][key]=value
            with self.assertRaises(m.ProjectError):bridge.decide(bad)

    def test_finite_search_cancel_and_per_bridge_budget_no_truncation(self):
        req=request();req['parameters']['max_window_tests']=1
        proposal=bridge.decide(req);self.assertEqual(1,proposal['search']['tested_windows']);self.assertEqual('WINDOW_BUDGET',proposal['search']['termination'])
        with self.assertRaises(m.ProjectError) as error:bridge.decide(req,lambda:True)
        self.assertEqual('CANCELLED',error.exception.code)
        req=request();req['parameters']['max_notes']=1;w=window(req,0,3840)
        raw=bridge.generate(req,locked_plan(req,[w]));row=raw['results'][0]
        self.assertEqual('FAILED',raw['status']);self.assertEqual([],row['notes']);self.assertIsNone(row['base_material'])
        raw=bridge.generate(req,locked_plan(req,[w]),lambda:True)
        self.assertEqual('CANCELLED',raw['status']);self.assertEqual('CANCELLED',raw['results'][0]['status'])

    def test_partial_failure_retains_ready_stream_and_all_terminal_identities(self):
        req=request(fixture(4));ranges=[dict(start_tick=0,end_tick=3840),dict(start_tick=3840,end_tick=7680)]
        windows=[window(req,r['start_tick'],r['end_tick'],str(i),[ranges[1-i]]) for i,r in enumerate(ranges)]
        joints=bridge._joint_conditions(windows);plan=locked_plan(req,windows,joints);before=copy.deepcopy(plan)
        original=melody.compose_bridge_phrase
        def failing(request,window,*args,**kw):
            if window['id']=='1':raise m.ProjectError('BRIDGE_GENERATION_FAILED','second failed')
            return original(request,window,*args,**kw)
        streamed=[];events=[]
        with patch.object(melody,'compose_bridge_phrase',side_effect=failing):
            raw=bridge.generate(req,plan,on_result=streamed.append,on_progress=events.append)
        self.assertEqual('FAILED',raw['status']);self.assertEqual(['READY','FAILED'],[r['status'] for r in raw['results']])
        self.assertEqual(raw['results'],streamed);self.assertEqual(before,plan)
        self.assertEqual([1,2,3],[e['event_seq'] for e in events])
        self.assertTrue(all(e['phase']=='BRIDGE_GENERATION' for e in events))
        with self.assertRaises(RuntimeError):bridge.generate(req,plan,on_result=lambda r:(_ for _ in ()).throw(RuntimeError('queue failed')))

    def test_ledger_mutations_fail_locally_not_just_a_changed_hash(self):
        req=request();w=window(req,0,3840);base=melody.compose_bridge_phrase(req,w,[])
        mutations=[lambda b:b['notes'][0].update(origin=dict(source_id='S',track_id='track',source_note_id='source:1:0')),
            lambda b:b['notes'][0]['lineage'].append('fake'),lambda b:b['notes'][0].update(pitch=61),
            lambda b:b['generation']['operations'][0]['parent_ref'].update(note_id='note:1:0'),
            lambda b:b['generation']['operations'].pop()]
        for mutate in mutations:
            altered=copy.deepcopy(base);mutate(altered)
            with self.assertRaises(m.ProjectError):bridge._verify_base_music(req,w,altered)

    def test_nested_repeat_component_identity_and_known_origins(self):
        p=fixture(4);leaf=copy.deepcopy(p['materials'][0])
        def combo(ident,children):
            parts=[];notes=[];offset=0
            for i,c in enumerate(children):
                parts.append(dict(occurrence_id=ident+':'+str(i),offset_tick=offset,snapshot=copy.deepcopy(c)))
                count=len(notes)
                notes.extend(dict(n,id=ident+':n:'+str(count+j),start_tick=n['start_tick']+offset) for j,n in enumerate(c['notes']))
                offset += c['length_ticks']
            return dict(id=ident,label=ident,kind='combination',length_ticks=offset,notes=notes,provenance=dict(key_context=leaf['provenance']['key_context']),generation=None,phrase_id=None,children=parts)
        inner=combo('inner',[leaf,leaf]);outer=combo('outer',[inner,inner]);p['materials'].append(outer)
        p['placements']=[dict(id='nested',material_id='outer',base_snapshot=copy.deepcopy(outer),start_tick=0,length_ticks=7680,emotion='calm',emotion_variant=None)]
        req=request(p);w=window(req,0,7680);w['context']['motif_note_ids']=[req['base_notes'][i]['id'] for i in (0,8,16,24)]
        row=bridge.generate(req,locked_plan(req,[w]))['results'][0]
        paths={tuple(c['parent_ref']['component_path']) for c in row['operations']}
        self.assertEqual({('outer:0','inner:0'),('outer:0','inner:1'),('outer:1','inner:0'),('outer:1','inner:1')},paths)
        self.assertEqual('combination',p['placements'][0]['base_snapshot']['kind'])
        self.assertEqual('phrase',row['material']['kind'])

    def test_generation_never_enters_legacy_planner_or_p6(self):
        req=request();w=window(req,0,3840)
        with patch('story_engine.plan_story',create=True,side_effect=AssertionError('legacy forbidden')):
            raw=bridge.generate(req,locked_plan(req,[w]))
        self.assertEqual('SUCCEEDED',raw['status'])
        self.assertNotIn('capabilities',raw);self.assertNotIn('final_score',raw)

    def test_single_p4_candidate_partial_gaps_and_real_source_closure(self):
        import curve_candidates as candidates
        from test_curve_candidates import fixture as p4_fixture, proposal, prepared
        controller=p4_fixture();project=controller.project
        p4_request=candidates.make_request(project,controller.gap_items()[0]['id'])
        candidate=prepared(p4_request,[proposal(p4_request)])['candidates'][0]
        req=request(candidate['project'])
        req.update(input_kind='completed_candidate',input_project=copy.deepcopy(project),
            input_fingerprint=m.fingerprint(project),input_contract_rev=project['contract_rev'],
            completion_ref=dict(attempt_id=p4_request['request_id'],candidate_id=candidate['id'],request=p4_request,candidate=candidate))
        bridge.decide(req)
        self.assertEqual([(0,3360)],[(r['start_tick'],r['end_tick']) for r in req['resolved_ranges']])
        bad=copy.deepcopy(req);bad['completion_ref']['candidate']['notes']=[]
        with self.assertRaises(m.ProjectError):bridge.decide(bad)

    def test_managed_memory_protects_full_long_onset_before_nominal_range(self):
        import curve_memory
        p=fixture(4)
        # A single phrase has a 1800..2100 note crossing the earliest peak bar.
        whole=copy.deepcopy(p['materials'][0]);whole.update(id='whole',length_ticks=7680)
        whole['notes']=[dict(n,id='whole:'+str(i)) for i,n in enumerate([n for place in p['placements'] for n in m.placed_notes(place)])]
        whole['notes']=[n for n in whole['notes'] if not (1680 <= n['start_tick'] <= 1920)]
        whole['notes'].append(dict(copy.deepcopy(p['materials'][0]['notes'][0]),id='long',start_tick=1800,duration_tick=300))
        whole['notes'].sort(key=lambda n:n['start_tick'])
        p['materials'].append(whole);p['placements']=[dict(id='whole-use',material_id='whole',base_snapshot=whole,start_tick=0,length_ticks=7680,emotion='calm',emotion_variant=None)]
        p['intensity_points']=[dict(tick=0,level=.2),dict(tick=1920,level=1.),dict(tick=7680,level=.1)]
        p['protections']=[curve_memory.expected_protection(p)];m.validate(p)
        req=request(p);w=window(req,0,1920)
        with self.assertRaises(m.ProjectError):bridge.generate(req,locked_plan(req,[w]))
        self.assertTrue(any(r['start_tick']==1800 for r in req['protection_summary']['ranges']))

    def test_cancel_inside_note_loop_and_cancel_after_one_ready_preserve_facts(self):
        req=request();w=window(req,0,3840);calls=[0]
        def cancel():
            calls[0]+=1
            return calls[0] >= 6
        raw=bridge.generate(req,locked_plan(req,[w]),cancel)
        self.assertEqual('CANCELLED',raw['status']);self.assertEqual([],raw['results'][0]['notes'])
        req=request(fixture(4));regions=[dict(start_tick=0,end_tick=3840),dict(start_tick=3840,end_tick=7680)]
        windows=[window(req,r['start_tick'],r['end_tick'],str(i),[regions[1-i]]) for i,r in enumerate(regions)]
        plan=locked_plan(req,windows,bridge._joint_conditions(windows));stream=[]
        raw=bridge.generate(req,plan,lambda:bool(stream),on_result=stream.append)
        self.assertEqual(['READY','CANCELLED'],[r['status'] for r in raw['results']])
        self.assertTrue(raw['results'][0]['notes']);self.assertEqual(stream,raw['results'])

    def test_actual_public_gate_adjacent_blank_and_decision_roundtrip(self):
        import curve_bridges as gate
        for mode in ('decision','adjacent','blank'):
            with self.subTest(mode=mode):
                req=gate.make_request(fixture(4,emotions=['hope','sad','crisis','resolve'],tail=240 if mode=='blank' else 0))
                proposal=bridge.decide(req)
                if mode=='adjacent':
                    regions=[dict(start_tick=0,end_tick=3840),dict(start_tick=3840,end_tick=7680)]
                    proposal['windows']=[window(req,r['start_tick'],r['end_tick'],str(i),[regions[1-i]]) for i,r in enumerate(regions)]
                    proposal['joint_boundary_conditions']=bridge._joint_conditions(proposal['windows'])
                plan=gate.make_plan(req,proposal);raw=bridge.generate(req,plan)
                self.assertEqual('SUCCEEDED',raw['status']);gate.validate_raw(req,plan,raw)
                for row in raw['results']:
                    self.assertEqual(next(r['protection_id'] for r in plan['protection_refs'] if r['bridge_id']==row['bridge_id']),row['protection_id'])

    def test_actual_gate_rejects_rehashed_pitch_timing_extra_origin_and_lineage(self):
        import curve_bridges as gate
        req=gate.make_request(fixture(2));plan=gate.make_plan(req,bridge.decide(req));raw=bridge.generate(req,plan)
        row=raw['results'][0];gate.validate_result(req,plan,row)
        mutations=[lambda r:r['base_material']['notes'][0].update(pitch=61),
            lambda r:r['base_material']['notes'][0].update(start_tick=1),
            lambda r:r['base_material']['notes'][0].update(duration_tick=241),
            lambda r:r['base_material']['notes'].append(dict(r['base_material']['notes'][0],id='extra')),
            lambda r:r['base_material']['notes'][0]['origin'].update(source_note_id='source:1:0'),
            lambda r:r['base_material']['notes'][0]['lineage'].append('fake'),
            lambda r:r['operations'][0]['parent_ref'].update(note_id='note:1:0')]
        for mutate in mutations:
            bad=copy.deepcopy(row);mutate(bad)
            bad['content_fingerprint']=gate.content_fingerprint(bad['range'],plan['windows'][0]['blank_mask'],bad['notes'])
            with self.assertRaises(m.ProjectError):gate.validate_result(req,plan,bad)

    def test_actual_stream_partial_failure_pure_saved_restore_no_late_acceptance(self):
        import curve_workflow as workflow
        import curve_store
        import curve_memory
        controller=workflow.Controller(fixture(4));cap=controller.capture_bridge();req=cap['request'];token=cap['token']
        regions=[dict(start_tick=0,end_tick=3840),dict(start_tick=3840,end_tick=7680)]
        proposal=bridge.decide(req)
        proposal['windows']=[window(req,r['start_tick'],r['end_tick'],str(i),[regions[1-i]]) for i,r in enumerate(regions)]
        proposal['joint_boundary_conditions']=bridge._joint_conditions(proposal['windows'])
        plan=controller.lock_bridge(token,proposal);self.assertTrue(controller.begin_bridge_generation(token,plan))
        original=melody.compose_bridge_phrase
        def failing(request,window,*args,**kw):
            if window['id']=='1':raise m.ProjectError('BRIDGE_GENERATION_FAILED','explicit second failure')
            return original(request,window,*args,**kw)
        accepted=[]
        with patch.object(melody,'compose_bridge_phrase',side_effect=failing):
            raw=bridge.generate(req,plan,on_result=lambda row:accepted.append(controller.record_bridge_result(token,row)))
        # Failure records may consume the token immediately. finish is idempotent
        # and may then be rejected; saved facts must still be complete.
        controller.finish_bridge(token,raw)
        state=controller.bridge_state();self.assertEqual('FAILED',state['status']);self.assertTrue(accepted[0])
        self.assertEqual(['READY','FAILED'],[r['status'] for r in state['results']])
        self.assertEqual(['CONTENT_READY','RANGE_LOCKED'],[p['status'] for p in state['protections'] if p['kind']=='bridge'])
        self.assertFalse(controller.record_bridge_result(token,raw['results'][0]));self.assertFalse(controller.finish_bridge(token,raw))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'partial.json'
            with patch.object(bridge,'decide',side_effect=AssertionError('pure restore')),patch.object(bridge,'generate',side_effect=AssertionError('pure restore')),patch.object(melody,'compose_bridge_phrase',side_effect=AssertionError('pure restore')),patch.object(emotion,'emotion_variant',side_effect=AssertionError('pure restore')),patch.object(curve_memory,'recompute',side_effect=AssertionError('pure restore')):
                controller.save_snapshot(path)
                restored=curve_store.load(path)
                attempt=restored['bundle']['attempts'][-1]
                self.assertEqual('FAILED',attempt['state']);self.assertEqual(state['results'],attempt['bridge']['results'])

    def test_unprotected_interior_of_independent_phrase_can_be_selected(self):
        import curve_memory
        p=fixture(4);whole=copy.deepcopy(p['materials'][0]);whole.update(id='whole',length_ticks=7680)
        whole['notes']=[dict(n,id='whole:'+str(i)) for i,n in enumerate([n for place in p['placements'] for n in m.placed_notes(place)])]
        p['materials'].append(whole);p['placements']=[dict(id='whole-use',material_id='whole',base_snapshot=whole,start_tick=0,length_ticks=7680,emotion='calm',emotion_variant=None)]
        p['protections']=[curve_memory.expected_protection(p)];m.validate(p)
        req=request(p);proposal=bridge.decide(req)
        self.assertEqual('selected',proposal['decision'])
        self.assertTrue(all(w['start_tick'] >= 1920 for w in proposal['windows']))

    def test_precise_original_ticks_and_pitch_edges_not_silently_quantized(self):
        p=fixture(3)
        notes=p['placements'][2]['base_snapshot']['notes']
        notes[0]['duration_tick']=1
        req=request(p);w=window(req,0,3841)
        row=bridge.generate(req,locked_plan(req,[w]))['results'][0]
        self.assertEqual(3841,row['material']['length_ticks'])
        self.assertEqual(1,row['base_material']['generation']['parameters']['rule_unit_ticks'])
        self.assertTrue(any(n['duration_tick']%10 for n in row['notes']))
        self.assertEqual(1,p['placements'][2]['base_snapshot']['notes'][0]['duration_tick'])
        for pitch in (0,127):
            p=fixture(2)
            for place in p['placements']:
                for n in place['base_snapshot']['notes']:n['pitch']=pitch
            req=request(p);w=window(req,0,3840)
            row=bridge.generate(req,locked_plan(req,[w]))['results'][0]
            self.assertTrue(all(0 <= n['pitch'] <= 127 for n in row['notes']))

    def test_none_preserves_failed_historical_automatic_lock_as_required_failure(self):
        import curve_bridges as gate
        p=fixture(2)
        p['protections']=[dict(id='old-lock',kind='bridge',owner_id='old-bridge',placement_id=None,component_path=[],
            start_tick=0,end_tick=1920,status='RANGE_LOCKED',origin='automatic',plan_id='old-plan',plan_version=1,
            input_fingerprint='old-input',notes=[],structure_fingerprint=None,blank_mask=[])]
        p['records']=[dict(id='old-plan',kind='bridge_plan',version=1,status='FAILED',input_fingerprint='old-input',dependencies=[],
            payload=dict(candidate_id='old-candidate',candidate_fingerprint='old-input',automatic_decision='selected',
                bridge_ids=['old-bridge'],manual_bridge_ids=[],ranges=[dict(start_tick=0,end_tick=1920)],reasons=[],joint_boundary_conditions=[]))]
        m.validate(p);req=gate.make_request(p,values=dict(policy='none'));plan=gate.make_plan(req,bridge.decide(req))
        before=copy.deepcopy((req,plan));raw=bridge.generate(req,plan);gate.validate_raw(req,plan,raw)
        self.assertEqual('FAILED',raw['status']);self.assertEqual('BRIDGE_NOT_READY',raw['results'][0]['error']['code'])
        self.assertEqual('old-lock',raw['results'][0]['protection_id']);self.assertEqual(before,(req,plan))


if __name__ == '__main__':
    unittest.main()


class GlobalBridgeTests(unittest.TestCase):
    def test_adjacent_cost_dp_keeps_distinct_end_states(self):
        rows=[dict(range=dict(start_tick=a,end_tick=b),benefit=g) for a,b,g in [(0,3840,.5),(1920,5760,.6),(5760,9600,.5)]]
        expected=[dict(start_tick=0,end_tick=3840),dict(start_tick=5760,end_tick=9600)]
        self.assertEqual(expected,bridge._select_global(rows,2))
        self.assertEqual(expected,bridge._select_global(list(reversed(rows)),2))

    def test_dp_matches_independent_exhaustive_proof_including_ties(self):
        import itertools
        import random
        rng=random.Random(31)
        for case in range(25):
            rows=[]
            for a,b in rng.sample([(a,b) for a in range(0,8) for b in range(a+1,9)],8):
                rows.append(dict(range=dict(start_tick=a*120,end_tick=b*120),benefit=rng.choice([.04,.1,.35,.5,.6])))
            maximum=3;legal=[(0,())]
            for count in range(1,maximum+1):
                for subset in itertools.combinations(rows,count):
                    ordered=sorted(subset,key=lambda v:v['range']['start_tick']);rs=tuple((v['range']['start_tick'],v['range']['end_tick']) for v in ordered)
                    if any(a[1]>b[0] for a,b in zip(rs,rs[1:])):continue
                    score=sum(round(v['benefit']*100000000) for v in ordered)-35000000*sum(a[1]==b[0] for a,b in zip(rs,rs[1:]))
                    legal.append((score,rs))
            _,expected=min(legal,key=lambda v:(-v[0],len(v[1]),sum(b-a for a,b in v[1]),v[1]))
            self.assertEqual([dict(start_tick=a,end_tick=b) for a,b in expected],bridge._select_global(rows,maximum),case)

    def test_fair_budget_reaches_later_regions_with_honest_incomplete(self):
        import curve_phrase_analysis as analysis
        from test_curve_phrase_analysis import global_request
        for blocks in (8,16):
            req=global_request(fixture(blocks));facts=analysis.analyze(req)
            queue,seed_count,regions,boundaries=bridge._fair_queue(req,facts)
            proposal=bridge.decide(req);coverage=proposal['search']['coverage']
            expected=[r for r in regions if any(r['start_tick']<=a<r['end_tick'] for a,b in queue)]
            self.assertEqual(expected,coverage['evaluated_regions'])
            self.assertGreater(coverage['evaluated_regions'][-1]['start_tick'],req['base_project']['total_ticks']//2)
            self.assertEqual(128,proposal['search']['tested_windows']);self.assertFalse(coverage['coverage_complete'])
            self.assertEqual('WINDOW_BUDGET',proposal['search']['termination'])
            analysis.validate_search(req,proposal)
        req=global_request(fixture(8,rough=False),dict(max_window_tests=1))
        proposal=bridge.decide(req)
        self.assertEqual('none',proposal['decision']);self.assertEqual('REGION_BUDGET',proposal['search']['termination'])
        self.assertEqual('SEARCH_INCOMPLETE',proposal['reasons'][0]['code'])

    def test_policy_none_no_analysis_and_all_protected_complete_none(self):
        import curve_phrase_analysis as analysis
        from test_curve_phrase_analysis import global_request,far_theme
        req=global_request(fixture(),dict(policy='none'))
        with patch.object(analysis,'analyze',side_effect=AssertionError('policy none must not analyze')):
            proposal=bridge.decide(req);analysis.validate_search(req,proposal)
        self.assertIsNone(proposal['search']['analysis']);self.assertFalse(proposal['search']['coverage']['coverage_complete'])
        self.assertEqual('POLICY_NONE',proposal['search']['termination']);self.assertEqual([],proposal['assessments'])
        p=far_theme();a,z=7680,11520
        lock=dict(id='middle',kind='manual',owner_id='middle',placement_id=None,component_path=[],start_tick=a,end_tick=z,
                  status='CONTENT_READY',origin='manual',plan_id=None,plan_version=None,input_fingerprint=m.fingerprint(p),
                  notes=[n for n in m.current_notes(p) if a<=n['start_tick']<z],structure_fingerprint=None,blank_mask=[])
        lock['structure_fingerprint']=m.structure_fingerprint(lock);p['protections'].append(lock)
        req=global_request(p);proposal=bridge.decide(req);analysis.validate_search(req,proposal)
        self.assertEqual('NO_WRITABLE_WINDOW',proposal['reasons'][0]['code'])
        self.assertTrue(proposal['search']['coverage']['coverage_complete']);self.assertEqual(0,proposal['search']['tested_windows'])
        self.assertEqual([],proposal['search']['coverage']['evaluated_regions'])

    def test_search_limit_and_cancel_do_not_claim_none(self):
        import curve_phrase_analysis as analysis
        from test_curve_phrase_analysis import global_request
        req=global_request(fixture(8));original=copy.deepcopy(req)
        with patch.dict(analysis.LIMITS,candidates=4),self.assertRaises(m.ProjectError) as error:bridge.decide(req)
        self.assertEqual('SEARCH_LIMIT',error.exception.code)
        for limit in (0,12,30):
            calls=iter([False]*limit+[True])
            with self.assertRaises(m.ProjectError) as error:bridge.decide(req,lambda:next(calls,True))
            self.assertEqual('CANCELLED',error.exception.code)
        self.assertEqual(original,req)

    def test_queue_coverage_score_and_dp_forgery_rejected_purely(self):
        import curve_phrase_analysis as analysis
        from test_curve_phrase_analysis import global_request
        req=global_request(fixture(8));proposal=bridge.decide(req)
        mutations=[lambda p:p['search']['coverage'].update(coverage_complete=True),
                   lambda p:p['search'].update(tested_windows=127),
                   lambda p:p['search']['coverage']['evaluated_regions'].pop(),
                   lambda p:p['assessments'].reverse(),
                   lambda p:p['assessments'][0].update(benefit=1.),
                   lambda p:p['windows'].clear()]
        for mutate in mutations:
            bad=copy.deepcopy(proposal);mutate(bad)
            with self.subTest(mutation=mutate),self.assertRaises(m.ProjectError):analysis.validate_search(req,bad)
        bad=copy.deepcopy(proposal);bad['search'].pop('analysis')
        with self.assertRaises(m.ProjectError):analysis.validate_search(req,bad)
        with patch.object(bridge,'decide',side_effect=AssertionError('no decide')),\
             patch.object(bridge,'generate',side_effect=AssertionError('no generate')),\
             patch.object(analysis,'analyze',side_effect=AssertionError('no analyze')):
            analysis.validate_search(req,proposal)

    def test_generation_version_remains_v1_for_global_planner(self):
        import curve_phrase_analysis as analysis
        from test_curve_phrase_analysis import global_request
        req=global_request(fixture(4),dict(max_window_tests=2048))
        proposal=bridge.decide(req);self.assertEqual('selected',proposal['decision'])
        plan=locked_plan(req,proposal['windows'],proposal['joint_boundary_conditions'])
        for field in ('reasons','assessments','search'):plan[field]=copy.deepcopy(proposal[field])
        rehash(plan);before=copy.deepcopy(plan)
        outcome=bridge.generate(req,plan);self.assertEqual('SUCCEEDED',outcome['status'],outcome)
        for result in outcome['results']:
            self.assertEqual('curve-bridge-v1',result['base_material']['generation']['algorithm_version'])
            self.assertEqual('curve-bridge-v1',result['material']['generation']['algorithm_version'])
        self.assertEqual(before,plan)
        legacy=copy.deepcopy(req);legacy['algorithm_version']=bridge.ALGORITHM_VERSION
        other=locked_plan(legacy,plan['windows'],plan['joint_boundary_conditions'])
        replay=bridge.generate(legacy,other)
        self.assertEqual([music(r) for r in outcome['results']],[music(r) for r in replay['results']])
        bad=copy.deepcopy(req);bad['algorithm_version']='unknown'
        with self.assertRaises(m.ProjectError):bridge.decide(bad)
        bad=copy.deepcopy(plan);bad['search']={'tested_windows':0,'termination':'EXHAUSTED'};rehash(bad)
        with self.assertRaises(m.ProjectError):bridge.generate(req,bad)

    def test_long_phrase_has_legal_interior_and_preserves_blank_mask(self):
        from test_curve_phrase_analysis import global_request
        p=fixture(8);material=copy.deepcopy(p['materials'][0]);material.update(id='long',length_ticks=p['total_ticks'],notes=copy.deepcopy(m.current_notes(p)))
        p['materials'].append(material);place=copy.deepcopy(p['placements'][0]);place.update(material_id='long',base_snapshot=copy.deepcopy(material),length_ticks=p['total_ticks']);p['placements']=[place]
        req=global_request(p,dict(max_window_tests=2048));proposal=bridge.decide(req)
        self.assertTrue(any(a['range'] and 0<a['range']['start_tick']<a['range']['end_tick']<p['total_ticks'] and a['benefit'] is not None for a in proposal['assessments']))
        p=fixture(3,tail=240);req=global_request(p,dict(max_window_tests=2048));original=copy.deepcopy(req)
        proposal=bridge.decide(req)
        for w in proposal['windows']:self.assertEqual(bridge._mask(p,w),w['blank_mask'])
        self.assertEqual(original,req)

    def test_global_full_note_guards_blank_and_existing_bridge_are_independent(self):
        from test_curve_phrase_analysis import global_request,far_theme
        import curve_phrase_analysis as analysis
        p=far_theme();lock=p['protections'][0]
        # Each independently authenticated manual layer remains unavailable.
        lock['start_tick']=6000;lock['end_tick']=7680
        lock['notes']=[n for n in m.current_notes(p) if 6000<=n['start_tick']<7680]
        lock['structure_fingerprint']=m.structure_fingerprint(lock)
        req=global_request(p);proposal=bridge.decide(req);analysis.validate_search(req,proposal)
        for window in proposal['windows']:
            self.assertTrue(bridge._legal(req,window))
            self.assertFalse(any(m.intersects(window,bridge._support(n)) for v in p['protections'] for n in v['notes']))
        # Existing manual bridge material retains its ready content; policy none
        # returns no new windows and never clears the bridge lock.
        from test_curve_workflow import manual_bridge
        p=manual_bridge();p['blank_regions']=[dict(id='left',start_tick=0,end_tick=1920,reason='blank'),
            dict(id='right',start_tick=3840,end_tick=p['total_ticks'],reason='blank')]
        req=global_request(p,dict(policy='none'));before=copy.deepcopy(req)
        proposal=bridge.decide(req);analysis.validate_search(req,proposal)
        self.assertEqual('none',proposal['decision']);self.assertEqual(before,req)
        self.assertEqual(1,len(req['base_project']['protections']))


    def test_global_managed_memory_cross_onset_support_and_partial_gap(self):
        import curve_memory
        import curve_phrase_analysis as analysis
        from test_curve_phrase_analysis import global_request
        p=fixture(4);whole=copy.deepcopy(p['materials'][0]);whole.update(id='whole',length_ticks=7680)
        whole['notes']=[dict(n,id='whole:'+str(i)) for i,n in enumerate(m.current_notes(p))]
        whole['notes']=[n for n in whole['notes'] if not 1680<=n['start_tick']<=1920]
        whole['notes'].append(dict(copy.deepcopy(p['materials'][0]['notes'][0]),id='long',start_tick=1800,duration_tick=300))
        whole['notes'].sort(key=lambda n:n['start_tick'])
        p['materials'].append(whole);p['placements']=[dict(id='whole-use',material_id='whole',base_snapshot=whole,start_tick=0,length_ticks=7680,emotion='calm',emotion_variant=None)]
        p['intensity_points']=[dict(tick=0,level=.2),dict(tick=1920,level=1.),dict(tick=7680,level=.1)]
        p['protections']=[curve_memory.expected_protection(p)];m.validate(p)
        req=global_request(p,dict(max_window_tests=2048));proposal=bridge.decide(req);analysis.validate_search(req,proposal)
        support=dict(start_tick=1800,end_tick=2100)
        self.assertTrue(any(r['start_tick']==1800 for r in req['protection_summary']['ranges']))
        self.assertTrue(all(not m.intersects(w,support) for w in proposal['windows']))
        self.assertTrue(all(b['tick'] not in range(1801,2100) for b in proposal['search']['analysis']['boundaries']))
        # Real P4 single-gap completion preserves the other gap and resolved set.
        from test_curve_candidates import fixture as gap_fixture,prepared,proposal as gap_proposal
        import curve_candidates as candidates
        controller=gap_fixture();project=controller.project
        completion=candidates.make_request(project,controller.gap_items()[0]['id'])
        candidate=prepared(completion,[gap_proposal(completion)])['candidates'][0]
        ref=dict(attempt_id=completion['request_id'],candidate_id=candidate['id'],request=completion,candidate=candidate)
        import curve_bridges as public
        req=public.make_request(project,ref,algorithm_version=public.GLOBAL_ALGORITHM)
        proposal=bridge.decide(req);analysis.validate_search(req,proposal)
        self.assertEqual([(0,3360)],[(r['start_tick'],r['end_tick']) for r in req['resolved_ranges']])
        self.assertTrue(all(any(r['start_tick']<=w['start_tick']<w['end_tick']<=r['end_tick'] for r in req['resolved_ranges']) for w in proposal['windows']))
