"""Frozen P7 provider tests, including pure public gate roundtrips.

Ordinary fixtures use authenticated real P5/P6 facts. Accepted-score unit
fixtures exercise the new ledger branch without claiming a P7 registry gate.
"""
import copy
import unittest
from unittest.mock import patch

import curve_boundary_music as music
import curve_connection_music as connection_music
import curve_connections as connections
import curve_bridges as bridges
import curve_project as m
from test_curve_connection_music import request as connection_request
from test_curve_bridge_music import fixture
from test_curve_melody import combination


def cells(project, block, values):
    material=project['materials'][block];notes=[]
    for i,(start,duration,pitch,*velocity) in enumerate(values):
        original=material['notes'][0]
        notes.append(dict(copy.deepcopy(original),id='note:%s:%s'%(block,i),pitch=pitch,start_tick=start,
            duration_tick=duration,velocity=velocity[0] if velocity else 80,
            origin=dict(source_id='S',track_id='track',source_note_id='source:%s:%s'%(block,i)),lineage=[],slice=None))
    material['notes']=notes;project['placements'][block]['base_snapshot']['notes']=copy.deepcopy(notes)
    project['sources'][0]['notes']=[dict(copy.deepcopy(n),id=n['origin']['source_note_id'],start_tick=j*1920+n['start_tick'])
        for j,material in enumerate(project['materials']) for n in material['notes']]
    return project


def short_project(lengths):
    p=fixture(1,rough=False);template=copy.deepcopy(p['materials'][0]);offset=0
    p['materials']=[];p['placements']=[];p['sources'][0]['notes']=[]
    for index,length in enumerate(lengths):
        sid='short-source:'+str(index)
        note=dict(copy.deepcopy(template['notes'][0]),id='short-note:'+str(index),pitch=60+index*4,
            start_tick=0,duration_tick=min(120,length),origin=dict(source_id='S',track_id='track',source_note_id=sid))
        material=dict(copy.deepcopy(template),id='short-material:'+str(index),length_ticks=length,notes=[note])
        material['provenance']['source_start_tick']=offset
        p['materials'].append(material)
        p['placements'].append(dict(id='short-use:'+str(index),material_id=material['id'],base_snapshot=copy.deepcopy(material),
            start_tick=offset,length_ticks=length,emotion='calm',emotion_variant=None))
        p['sources'][0]['notes'].append(dict(copy.deepcopy(note),id=sid,start_tick=offset))
        offset+=length
    p['blank_regions']=[] if offset==p['total_ticks'] else [dict(id='short-rest',start_tick=offset,end_tick=p['total_ticks'],reason='主动留白')]
    m.validate(p);return p


def ref(ident,fingerprint):return dict(id=ident,version=1,fingerprint=fingerprint)


def leaves(material,path=(),offset=0):
    if material['kind']!='combination':return [(offset,offset+material['length_ticks'],list(path),material)]
    return [v for child in material['children'] for v in leaves(child['snapshot'],path+(child['occurrence_id'],),offset+child['offset_tick'])]


def rehash(request):
    request['layout_fingerprint']=m.digest('emoblocks.final-layout.v1',request['actual_layout'])
    request['protection_summary']=dict(fingerprint=m.protection_summary(request['actual_layout']['protections']),ranges=music._guards(request))
    request['id']=m.digest('emoblocks.boundary-request-id.v1',dict(recommendation_request_id=request['token']['request_id'],
        candidate_ref=request['candidate_ref'],connection_attempt_id=request['connection_ref']['attempt_id'],
        plan_id=request['plan_id'],plan_version=request['plan_version']))
    return request


def request(project=None,parameters=None,bridge_ranges=(),seed=31):
    previous=connection_request(project or fixture(2,rough=False),bridge_ranges=bridge_ranges,parameters=dict(policy='none'))
    proposal=connection_music.plan(previous);plan=connections.make_plan(previous,proposal)
    raw=connection_music.generate(previous,plan,previous['actual_layout']);connections.validate_raw(previous,plan,raw)
    outcome=connections.make_outcome(previous,plan,raw['results'],raw['status'],raw['error']);connections.validate_outcome(previous,plan,outcome)
    old=previous['bridge_ref'];base=old['request']['base_project'];ledger=[]
    for n in outcome['notes']:
        row=next((r for r in old['results'] if n in r['notes']),None)
        if row:
            parent=dict(stage='bridge',owner_id=row['bridge_id'],note_id=n['id'],component_path=[],
                material_snapshot_id=row['material']['id'],content_fingerprint=row['content_fingerprint'])
            performance='bridge:'+row['bridge_id']
        else:
            old_parent=bridges.parent_ref(old['request'],n['id'])
            place=next(p for p in base['placements'] if p['id']==old_parent['placement_id']);snapshot=place['emotion_variant'] or place['base_snapshot']
            parent=dict(stage='placement',owner_id=place['id'],note_id=n['id'],component_path=old_parent['component_path'],
                material_snapshot_id=snapshot['id'],content_fingerprint=m.digest('emoblocks.material-snapshot.v1',snapshot))
            performance='place:'+place['id']+':'+':'.join(old_parent['component_path'])
        ledger.append(dict(note_id=n['id'],parent_ref=parent,performance_id=performance))
    points={0,base['total_ticks']}
    points.update(x for p in base['placements'] for x in (p['start_tick'],p['start_tick']+p['length_ticks']))
    points.update(x for r in old['results'] for x in (r['range']['start_tick'],r['range']['end_tick']))
    points.update(x for r in base['blank_regions'] for x in (r['start_tick'],r['end_tick']))
    points.update(x for r in outcome['remaining_gaps'] for x in (r['start_tick'],r['end_tick']))
    points.update(place['start_tick']+x for place in base['placements'] for a,b,_,_ in leaves(place['base_snapshot']) for x in (a,b))
    segments=[];points=sorted(points)
    for a,b in zip(points,points[1:]):
        if any(g['start_tick']<=a<b<=g['end_tick'] for g in outcome['remaining_gaps']):continue
        row=next((r for r in old['results'] if r['range']['start_tick']<=a<b<=r['range']['end_tick']),None)
        place=next((p for p in base['placements'] if p['start_tick']<=a<b<=p['start_tick']+p['length_ticks']),None)
        blank=next((r for r in base['blank_regions'] if r['start_tick']<=a<b<=r['end_tick']),None)
        if row:
            kind='bridge';owner=row['bridge_id'];fp=row['content_fingerprint'];snapshot=row['material'];performance='bridge:'+owner
        elif blank:
            kind='blank';owner=blank['id'];fp=m.digest('blank',blank);snapshot=None;performance=None
        else:
            kind='placement';owner=place['id'];snapshot=place['emotion_variant'] or place['base_snapshot'];fp=m.digest('emoblocks.material-snapshot.v1',snapshot)
            performance='place:'+owner+':'
        path=[]
        if kind=='placement':
            _,_,path,leaf=next(v for v in leaves(place['base_snapshot']) if place['start_tick']+v[0]<=a<b<=place['start_tick']+v[1])
            performance='place:'+owner+':'+':'.join(path)
        emotion=place['emotion'] if place else 'calm'
        key=snapshot['provenance'].get('key_context') if snapshot else None
        if key is None:key=dict(tonic=0,mode='major',confidence=0.,method='fixture')
        segments.append(dict(id='segment:%s:%s:%s'%(kind,a,b),performance_id=performance,owner_ref=ref(owner,fp),
            start_tick=a,end_tick=b,phrase_id=snapshot['id'] if snapshot else None,component_path=path,emotion=emotion,
            key_context=copy.deepcopy(key),intensity_start=m.intensity_at(base,a),intensity_end=m.intensity_at(base,b),kind=kind))
    layout=dict(total_ticks=base['total_ticks'],bpm=base['bpm'],base_project=base,notes=copy.deepcopy(outcome['notes']),segments=segments,
        coverage_ranges=copy.deepcopy(old['request']['resolved_ranges']),remaining_gaps=outcome['remaining_gaps'],
        protections=old['protections'],blank_regions=base['blank_regions'],emission_ledger=ledger)
    project=previous['input_project'];fingerprint=m.fingerprint(project)
    result=dict(schema='emoblocks.boundary-request.v1',spec_rev=m.SPEC_REV,contract_rev=music.REV,id=None,
        token=dict(project_id=project['project_id'],session_id='boundary-session',request_id='recommendation-request',snapshot_id='recommendation-snapshot',
            spec_rev=m.SPEC_REV,contract_rev=music.REV,edit_revision=0,input_fingerprint=fingerprint),
        input_contract_rev=project['contract_rev'],input_fingerprint=fingerprint,candidate_ref=None,
        connection_ref=dict(attempt_id=previous['request_id'],request=previous,plan=plan,results=raw['results'],outcome=outcome),
        actual_layout=layout,layout_fingerprint=None,protection_summary=None,plan_id='boundary-plan',plan_version=1,
        seed=seed,algorithm_version=music.ALGORITHM,parameters=dict(music.DEFAULTS,**(parameters or {})))
    return rehash(result)


def actual_notes(req,proposal):
    notes=music._splice(req['actual_layout']['notes'],proposal['operations'])
    hints={h['note_id']:h['velocity_delta'] for h in proposal['performance_hints']}
    return [dict(n,velocity=n['velocity']+hints.get(n['id'],0)) for n in notes]


def shape_check(req,proposal):
    m.shape(proposal,'schema spec_rev contract_rev request_fingerprint decision none_reason boundaries operations joints join_groups performance_hints assessments reasons search')
    assert proposal['request_fingerprint']==m.digest('emoblocks.boundary-request.v1',req)
    notes=actual_notes(req,proposal);assert music._monotone(notes)
    before=req['actual_layout']['notes'];consumed={i for o in proposal['operations'] for i in o['consumed_note_ids']}
    assert len(consumed)==sum(len(o['consumed_note_ids']) for o in proposal['operations'])
    forbidden=music._guards(req)+req['actual_layout']['blank_regions']+req['actual_layout']['remaining_gaps']+req['connection_ref']['plan']['windows']
    for op in proposal['operations']:
        m.shape(op,'id boundary_ids kind input_refs consumed_note_ids outputs permitted_ranges')
        for ident in op['consumed_note_ids']:
            n=next(n for n in before if n['id']==ident);assert not any(m.intersects(music._support(n),r) for r in forbidden)
        for out in op['outputs']:
            m.shape(out,'note parent_note_ids performance_id');n=out['note']
            assert not any(m.intersects(music._support(n),r) for r in forbidden)
            parent=next(n for n in before if n['id']==out['parent_note_ids'][0])
            assert n['origin']==parent['origin'] and n['lineage']==list(dict.fromkeys(parent['lineage']+[parent['id']])) and n['slice'] is None
    for hint in proposal['performance_hints']:
        m.shape(hint,'id boundary_id note_id performance_id velocity_delta tone_hint accompaniment_hint')
        assert hint['note_id'] not in consumed and -12<=hint['velocity_delta']<=12
    return notes


class BoundaryMusicTests(unittest.TestCase):
    def public_roundtrip(self,frame):
        import curve_final as final
        req=final.make_request(frame['connection_ref'],token=frame['token'],seed=frame['seed'],
            values=frame['parameters'],plan_id='owner-scope-gate')
        original=copy.deepcopy(req);final.validate_request(req)
        plan=final.make_plan(req,music.plan_boundaries(req));result=final.apply_boundaries(req,plan)
        final.validate_result(req,plan,result);self.assertEqual(original,req)
        return req,plan,result

    def test_short_owners_one_tick_and_short_tail_fit_public_gate(self):
        for lengths in ((120,120),(120,1,120),(60,60,60),(1800,120)):
            with self.subTest(lengths=lengths):
                req,plan,result=self.public_roundtrip(request(short_project(lengths)))
                first=next(b for b in plan['boundaries'] if b['tick']==0)
                self.assertEqual([dict(start_tick=0,end_tick=min(240,lengths[0]))],first['editable_ranges'])
                self.assertEqual(req['actual_layout']['remaining_gaps'],result['remaining_gaps'])
                if lengths==(120,120):
                    end=next(b for b in plan['boundaries'] if b['tick']==240)
                    self.assertEqual([dict(start_tick=120,end_tick=240)],end['editable_ranges'])
                    self.assertTrue(plan['joints']);ids={n['id'] for n in result['notes']}
                    for joint in plan['joints']:
                        for row in joint['final_endpoints']:
                            for endpoint in (row['left'],row['right']):
                                if endpoint:self.assertIn(endpoint['note_id'],ids)

    def test_nested_short_component_owners_fit_public_gate(self):
        p=short_project((120,1,120));first,second,third=p['materials']
        inner=combination('short-inner',[first,second]);outer=combination('short-outer',[inner,third])
        p['materials'] += [inner,outer];place=copy.deepcopy(p['placements'][0])
        place.update(material_id=outer['id'],length_ticks=outer['length_ticks'],base_snapshot=outer)
        p['placements']=[place]
        req,plan,result=self.public_roundtrip(request(p))
        self.assertEqual(3,len({e['performance_id'] for e in req['actual_layout']['emission_ledger']}))
        edge=next(b for b in plan['boundaries'] if b['tick']==120)
        self.assertEqual([dict(start_tick=0,end_tick=121)],edge['editable_ranges'])
        self.assertEqual(1920,req['actual_layout']['total_ticks'])

    def test_selected_completion_beside_real_remaining_gap_fits_public_gate(self):
        import curve_candidates as completion
        import curve_final as final
        import curve_bridge_music as bridge_music
        from test_curve_candidates import fixture as gap_fixture
        controller=gap_fixture()
        controller.edit('set_intensity',points=[dict(tick=0,level=.1),dict(tick=3840,level=.9)])
        captured=controller.capture_completion(controller.gap_items()[0]['id'],seed=31,budget=dict(max_candidates=1))
        completed=completion.prepare_completion(captured['request'])
        self.assertTrue(completed['candidates']);self.assertTrue(controller.finish_completion(captured['token'],completed))
        bridge=controller.capture_bridge(completed['candidates'][0]['id'],captured['attempt_id'],parameters=dict(policy='none'))
        bp=controller.lock_bridge(bridge['token'],bridge_music.decide(bridge['request']))
        controller.begin_bridge_generation(bridge['token'],bp)
        self.assertTrue(controller.finish_bridge(bridge['token'],bridge_music.generate(bridge['request'],bp)))
        con=controller.capture_connection(parameters=dict(policy='none'))
        cp=controller.plan_connection(con['token'],connection_music.plan(con['request']))
        controller.begin_connection_generation(con['token'],cp)
        raw=connection_music.generate(con['request'],cp,con['request']['actual_layout'])
        self.assertTrue(controller.finish_connection(con['token'],raw))
        attempt=controller._connection_attempt(con['attempt_id'])
        reference=dict(attempt_id=attempt['id'],**{k:copy.deepcopy(attempt['connection'][k]) for k in ('request','plan','results','outcome')})
        req=final.make_request(reference,plan_id='selected-gap-owner-scope');original=copy.deepcopy(req)
        plan=final.make_plan(req,music.plan_boundaries(req));result=final.apply_boundaries(req,plan);final.validate_result(req,plan,result)
        self.assertEqual([(3360,3840)],[(r['start_tick'],r['end_tick']) for r in result['remaining_gaps']])
        self.assertEqual(req['actual_layout']['remaining_gaps'],result['remaining_gaps'])
        self.assertFalse(any(m.intersects(music._support(n),result['remaining_gaps'][0]) for n in result['notes']))
        self.assertEqual(original,req)

    def short_pair(self):
        p=fixture(1,rough=False);cells(p,0,[(0,120,60)])
        first=p['materials'][0];first['length_ticks']=120
        second=copy.deepcopy(first);second.update(id='second');second['notes'][0].update(id='second-note',pitch=64)
        p['materials'].append(second)
        placement=copy.deepcopy(p['placements'][0]);placement.update(length_ticks=120,base_snapshot=copy.deepcopy(first))
        other=copy.deepcopy(placement);other.update(id='second-place',material_id='second',start_tick=120,base_snapshot=copy.deepcopy(second))
        p['placements']=[placement,other]
        p['blank_regions']=[dict(id='rest',start_tick=240,end_tick=1920,reason='主动留白')]
        return p

    def test_short_shared_endpoints_have_real_joint_and_one_writer(self):
        req=request(self.short_pair());proposal=music.plan_boundaries(req);notes=shape_check(req,proposal)
        self.assertTrue(proposal['joints']);self.assertTrue(proposal['operations'])
        actual_ids={n['id'] for n in notes}
        for joint in proposal['joints']:
            for row in joint['final_endpoints']:
                for endpoint in (row['left'],row['right']):
                    if endpoint:self.assertIn(endpoint['note_id'],actual_ids)
        ledger={e['note_id']:e for e in req['actual_layout']['emission_ledger']}
        op=proposal['operations'][0]
        self.assertFalse(music._feasible(req,op,[op],ledger))
        collision=copy.deepcopy(op);collision['outputs'][0]['note']['id']=req['actual_layout']['notes'][0]['id']
        self.assertFalse(music._feasible(req,collision,[],ledger))

    def test_repeated_nested_combinations_keep_occurrence_performances(self):
        p=fixture(4,rough=False);leaf=copy.deepcopy(p['materials'][0])
        inner=combination('inner',[leaf,leaf]);outer=combination('outer',[inner,inner])
        p['materials'].append(outer);place=copy.deepcopy(p['placements'][0])
        place.update(material_id=outer['id'],length_ticks=outer['length_ticks'],base_snapshot=outer)
        p['placements']=[place]
        req=request(p,parameters=dict(policy='none'));proposal=music.plan_boundaries(req)
        self.assertEqual(4,len({e['performance_id'] for e in req['actual_layout']['emission_ledger']}))
        self.assertTrue(all(len(e['parent_ref']['component_path'])==2 for e in req['actual_layout']['emission_ledger']))
        self.assertEqual([],proposal['join_groups']);self.assertEqual(req['actual_layout']['notes'],actual_notes(req,proposal))
        bad=copy.deepcopy(req)
        for entry in bad['actual_layout']['emission_ledger']:entry['performance_id']='collapsed-occurrences'
        for segment in bad['actual_layout']['segments']:segment['performance_id']='collapsed-occurrences'
        rehash(bad)
        with self.assertRaises(m.ProjectError) as exc:music.plan_boundaries(bad)
        self.assertEqual('INVALID_SOURCE',exc.exception.code)

    def test_actual_repeated_placements_do_not_tie_matching_slice_parents(self):
        p=self.short_pair()
        for index,place in enumerate(p['placements']):
            n=place['base_snapshot']['notes'][0];n.update(pitch=60,slice=dict(parent_emission_id='held',offset_tick=index*120,parent_duration_tick=240))
            p['materials'][index]['notes']=copy.deepcopy(place['base_snapshot']['notes'])
        p['sources'][0]['notes'][0]['duration_tick']=240
        req=request(p,parameters=dict(policy='none'));proposal=music.plan_boundaries(req)
        self.assertEqual([],proposal['join_groups']);self.assertEqual(2,len(actual_notes(req,proposal)))

    def test_partial_coverage_intersects_local_window_and_preserves_gap(self):
        # P6's legacy helper rejects partial current projects. This frozen
        # layout unit models a selected-gap candidate; full P7 capture is lead.
        req=request(self.short_pair());layout=req['actual_layout']
        layout['base_project']['blank_regions']=[];layout['blank_regions']=[]
        layout['segments']=[s for s in layout['segments'] if s['kind']!='blank']
        gap=dict(start_tick=240,end_tick=1920)
        layout['remaining_gaps']=[gap];req['connection_ref']['outcome']['remaining_gaps']=[gap]
        layout['coverage_ranges']=[dict(start_tick=0,end_tick=240)]
        req['connection_ref']['request']['bridge_ref']['request']['resolved_ranges']=layout['coverage_ranges']
        rehash(req);proposal=music.plan_boundaries(req);shape_check(req,proposal)
        self.assertTrue(proposal['operations'])
        self.assertTrue(any(b['tick']==240 for b in proposal['boundaries']))
        self.assertEqual([dict(start_tick=240,end_tick=1920)],req['actual_layout']['remaining_gaps'])
        for op in proposal['operations']:
            self.assertTrue(all(r['end_tick']<=240 for r in op['permitted_ranges']))

    def test_failed_trials_at_budget_are_not_fake_none(self):
        req=request(fixture(4),parameters=dict(max_operations=1))
        with patch.object(music,'_feasible',return_value=False),patch.object(music,'_hint',return_value=None):
            with self.assertRaises(m.ProjectError) as exc:music.plan_boundaries(req)
        self.assertEqual('SEARCH_BUDGET_EXHAUSTED',exc.exception.code)

    def test_accepted_leaf_parent_must_resolve_captured_actual_note(self):
        # Frozen captured_music branch unit: P7 registry and P6 source re-auth
        # remain independent lead integration; this does not claim that gate.
        req=request();layout=req['actual_layout'];entry=layout['emission_ledger'][0];note=layout['notes'][0]
        score_ref=ref('old-score','old-score-fingerprint')
        layout['base_project']['records'].append(dict(kind='captured_music',payload=dict(
            source_score_ref=score_ref,source_input_fingerprint='old-input',source_notes=[copy.deepcopy(note)],
            performance_map=[],base_binding_fingerprint='captured-base',added_placement_ids=[])))
        entry['parent_ref'].update(stage='final_score',owner_id=score_ref['id'],note_id=note['id'],
            material_snapshot_id=None,content_fingerprint=score_ref['fingerprint'])
        rehash(req);music.plan_boundaries(req)
        for mutate in (lambda r:r['actual_layout']['emission_ledger'][0]['parent_ref'].update(owner_id='foreign-score'),
                       lambda r:r['actual_layout']['base_project']['records'][-1]['payload']['source_notes'][0].update(pitch=61)):
            bad=copy.deepcopy(req);mutate(bad);rehash(bad)
            with self.assertRaises(m.ProjectError) as exc:music.plan_boundaries(bad)
            self.assertEqual('INVALID_SOURCE',exc.exception.code)

    def test_memory_protects_whole_long_support_before_nominal_range(self):
        import curve_memory
        p=fixture(4);whole=copy.deepcopy(p['materials'][0]);whole.update(id='whole',length_ticks=7680)
        whole['notes']=[dict(n,id='whole:'+str(i)) for i,n in enumerate([n for place in p['placements'] for n in m.placed_notes(place)])]
        whole['notes']=[n for n in whole['notes'] if not 1680<=n['start_tick']<=1920]
        whole['notes'].append(dict(copy.deepcopy(p['materials'][0]['notes'][0]),id='long',start_tick=1800,duration_tick=300))
        whole['notes'].sort(key=lambda n:n['start_tick']);p['materials'].append(whole)
        p['placements']=[dict(id='whole-use',material_id='whole',base_snapshot=whole,start_tick=0,length_ticks=7680,emotion='calm',emotion_variant=None)]
        p['intensity_points']=[dict(tick=0,level=.2),dict(tick=1920,level=1.),dict(tick=7680,level=.1)]
        p['protections']=[curve_memory.expected_protection(p)]
        req=request(p);proposal=music.plan_boundaries(req);notes=shape_check(req,proposal)
        self.assertEqual(1800,music._guards(req)[0]['start_tick'])
        original=next(n for n in req['actual_layout']['notes'] if n['start_tick']==1800)
        self.assertEqual(m.structural_notes([original]),m.structural_notes([n for n in notes if n['id']==original['id']]))

    def test_edge_pitches_and_midsearch_cancel_preserve_input(self):
        p=fixture(2,rough=False);cells(p,0,[(0,240,12),(1680,240,12)]);cells(p,1,[(0,240,119),(1680,240,119)])
        req=request(p);notes=shape_check(req,music.plan_boundaries(req));self.assertTrue(all(12<=n['pitch']<=119 for n in notes))
        before=copy.deepcopy(req);calls=[]
        def cancel():calls.append(1);return len(calls)>=3
        with self.assertRaises(m.ProjectError) as exc:music.plan_boundaries(req,should_cancel=cancel)
        self.assertEqual('CANCELLED',exc.exception.code);self.assertEqual(before,req)

    def test_natural_none_and_internal_fourbeat_is_not_new_boundary(self):
        p=fixture(1,rough=False);cells(p,0,[(0,1920,60)])
        req=request(p);before=copy.deepcopy(req);proposal=music.plan_boundaries(req)
        self.assertEqual('none',proposal['decision']);self.assertEqual('NOT_NEEDED',proposal['none_reason']);self.assertEqual(before,req)
        cells(p,0,[(0,480,60),(1440,480,60)]);req=request(p)
        original=req['actual_layout']['segments'][0];split=copy.deepcopy(original);split.update(id='split-second',start_tick=960)
        original['end_tick']=960;req['actual_layout']['segments'].append(split);rehash(req)
        proposal=music.plan_boundaries(req);self.assertNotIn(960,[b['tick'] for b in proposal['boundaries']])

    def test_five_methods_have_actual_notes_or_performance(self):
        import curve_final as final
        cases=[]
        p=fixture(2,rough=False);cells(p,0,[(0,240,60),(1680,240,60,100)]);cells(p,1,[(0,240,62,60),(1680,240,60)])
        cases.append(('natural_continuation',request(p),1920))
        p=fixture(2,rough=False);cells(p,0,[(0,240,60),(1680,240,60)]);cells(p,1,[(0,240,64),(1680,240,60)])
        cases.append(('motif_reply',request(p),1920))
        p['intensity_points']=[dict(tick=0,level=.2),dict(tick=3840,level=.8)]
        cases.append(('gradual_build',request(p),1920))
        p=fixture(3,rough=False);cells(p,0,[(0,240,60),(1680,240,60)]);cells(p,2,[(0,240,60),(1680,240,60)])
        p['placements'].pop(1);p['blank_regions']=[dict(id='blank',start_tick=1920,end_tick=3840,reason='主动留白')]
        cases.append(('blank_entry',request(p),3840))
        p=fixture(2,rough=False);cells(p,0,[(0,240,60),(1680,240,60)]);cells(p,1,[(0,240,60),(1680,240,62)])
        cases.append(('resolve_close',request(p),3840))
        for method,req,tick in cases:
            with self.subTest(method=method):
                proposal=music.plan_boundaries(req);notes=shape_check(req,proposal)
                boundary=next(b for b in proposal['boundaries'] if b['tick']==tick)
                self.assertEqual(method,boundary['method']);self.assertTrue(boundary['operation_ids'] or any(h['boundary_id']==boundary['id'] for h in proposal['performance_hints']))
                self.assertNotEqual(req['actual_layout']['notes'],notes)
                # Reconstruct the public frame from genuine P6 facts rather
                # than submit this test's hand-built ledger as authority.
                real=final.make_request(req['connection_ref'],token=req['token'],seed=req['seed'],plan_id='five-method-gate')
                untouched=copy.deepcopy(real);final.validate_request(real)
                plan=final.make_plan(real,music.plan_boundaries(real))
                result=final.apply_boundaries(real,plan);final.validate_result(real,plan,result)
                actual=next(b for b in plan['boundaries'] if b['tick']==tick)
                self.assertEqual(method,actual['method']);self.assertNotEqual(real['actual_layout']['notes'],result['notes'])
                self.assertEqual(untouched,real)

    def test_policy_none_preserves_music_and_reports_no_operations(self):
        req=request(parameters=dict(policy='none'));p=music.plan_boundaries(req)
        self.assertEqual('POLICY_NONE',p['none_reason']);self.assertEqual([],p['operations']);self.assertEqual([],p['performance_hints'])
        self.assertEqual(req['actual_layout']['notes'],actual_notes(req,p))

    def test_bridge_and_fixed_rest_supports_only_allow_performance(self):
        req=request(fixture(4),bridge_ranges=[(1920,5760)]);before=copy.deepcopy(req);p=music.plan_boundaries(req);notes=shape_check(req,p)
        guards=music._guards(req)
        self.assertEqual(m.structural_notes([n for n in before['actual_layout']['notes'] if any(m.intersects(music._support(n),r) for r in guards)]),
                         m.structural_notes([n for n in notes if any(m.intersects(music._support(n),r) for r in guards)]))
        self.assertEqual(before,req)

    def test_long_note_support_cannot_be_shortened_to_fit_window(self):
        p=fixture(2,rough=False);cells(p,0,[(0,1620,60),(1620,300,62)]);cells(p,1,[(0,300,67),(1620,300,60)])
        req=request(p);proposal=music.plan_boundaries(req);shape_check(req,proposal)
        self.assertEqual([],proposal['operations']);self.assertTrue(proposal['performance_hints'])

    def test_three_intrusions_and_connection_structures_are_forbidden(self):
        req=request();boundary=dict(id='unit',editable_ranges=[dict(start_tick=0,end_tick=240)])
        ledger={e['note_id']:e for e in req['actual_layout']['emission_ledger']};n=req['actual_layout']['notes'][0]
        op=music._candidate(req,boundary,'motif_reply',None,n,None,req['actual_layout']['segments'][0],ledger,__import__('random').Random(1))
        self.assertIsNotNone(op)
        for a,b in ((0,240),(100,200),(0,100)):
            bad=copy.deepcopy(req);bad['protection_summary']['ranges']=[dict(start_tick=a,end_tick=b)]
            # A real lock is used, not the self-reported summary.
            bad['actual_layout']['protections']=[dict(id='guard',kind='manual',owner_id='user',placement_id=None,component_path=[],start_tick=a,end_tick=b,
                status='RANGE_LOCKED',origin='manual',plan_id=None,plan_version=None,input_fingerprint='fixed',notes=[],structure_fingerprint=None,blank_mask=[])]
            self.assertFalse(music._feasible(bad,op,[],ledger))
            removed=dict(copy.deepcopy(op),kind='remove',outputs=[])
            self.assertFalse(music._feasible(bad,removed,[],ledger))
        bad=copy.deepcopy(req);bad['connection_ref']['plan']['windows']=[dict(start_tick=0,end_tick=240)]
        self.assertFalse(music._feasible(bad,op,[],ledger))

    def test_real_pickup_keeps_blank_and_uses_developed_parent(self):
        p=fixture(1,rough=False);cells(p,0,[(120,120,60),(1680,240,60)])
        req=request(p);proposal=music.plan_boundaries(req);notes=shape_check(req,proposal)
        added=[o for o in proposal['operations'] if o['kind']=='add'];self.assertEqual(1,len(added))
        parent=next(n for n in req['actual_layout']['notes'] if n['id']==added[0]['outputs'][0]['parent_note_ids'][0])
        self.assertNotEqual(parent['pitch'],added[0]['outputs'][0]['note']['pitch']);self.assertEqual(120,parent['start_tick'])
        actual=next(n for n in notes if n['id']==parent['id'])
        self.assertEqual(m.structural_notes([parent]),m.structural_notes([actual]))

    def test_remove_weak_note_is_limited_and_last_target_support_kept(self):
        p=fixture(2,rough=False);cells(p,1,[(0,240,60),(1800,120,62)])
        req=request(p);p1=music.plan_boundaries(req);self.assertTrue(any(o['kind']=='remove' for o in p1['operations']))
        target=dict(start_tick=3720,end_tick=3840)
        req['connection_ref']['request']['bridge_ref']['request']['completion_ref']=dict(request=dict(target_gaps=[target]))
        rehash(req);proposal=music.plan_boundaries(req);notes=shape_check(req,proposal)
        self.assertTrue(any(m.intersects(music._support(n),target) for n in notes))
        self.assertFalse(any(o['kind']=='remove' for o in proposal['operations']))

    def test_joint_endpoints_use_final_notes_and_shared_writers_are_unique(self):
        p=fixture(3,rough=False)
        for i in range(3):cells(p,i,[(0,240,64 if i else 60),(1680,240,62)])
        req=request(p);proposal=music.plan_boundaries(req);notes=shape_check(req,proposal)
        for joint in proposal['joints']:
            self.assertEqual(sorted(joint['boundary_ids']),[r['boundary_id'] for r in joint['final_endpoints']])
            for row in joint['final_endpoints']:
                boundary=next(b for b in proposal['boundaries'] if b['id']==row['boundary_id'])
                self.assertEqual([music._endpoint(n) for n in music._endpoints(notes,boundary['tick'])],[row['left'],row['right']])
        operations=proposal['operations']
        if operations:
            ledger={e['note_id']:e for e in req['actual_layout']['emission_ledger']}
            self.assertFalse(music._feasible(req,operations[0],operations,ledger))

    def test_exact_short_tail_and_tick_are_preserved_not_quantized(self):
        p=fixture(1,rough=False);cells(p,0,[(0,120,60),(1801,119,62)])
        req=request(p);proposal=music.plan_boundaries(req);shape_check(req,proposal)
        for out in [n for o in proposal['operations'] for n in o['outputs']]:
            self.assertEqual(1801,out['note']['start_tick'])
        self.assertEqual(1801,req['actual_layout']['notes'][-1]['start_tick'])

    def test_same_performance_slices_join_but_independent_uses_retrigger(self):
        p=fixture(1,rough=False);cells(p,0,[(0,120,60),(120,120,60),(1680,240,60)])
        for snapshot in (p['materials'][0],p['placements'][0]['base_snapshot']):
            for i,n in enumerate(snapshot['notes'][:2]):
                n['origin']=copy.deepcopy(snapshot['notes'][0]['origin'])
                n['slice']=dict(parent_emission_id='held',offset_tick=i*120,parent_duration_tick=240)
        p['sources'][0]['notes']=[n for n in p['sources'][0]['notes'] if n['id']!='source:0:1']
        p['sources'][0]['notes'][0].update(duration_tick=240,slice=None)
        req=request(p);proposal=music.plan_boundaries(req);self.assertEqual(1,len(proposal['join_groups']))
        group=proposal['join_groups'][0];self.assertEqual(240,group['render_event']['duration_tick']);self.assertIsNone(group['render_event']['slice'])
        self.assertEqual(req['actual_layout']['notes'],actual_notes(req,proposal))
        # Only the preauthenticated performance ledger is changed for this unit
        # counterexample; no source ID or slice parent is used as a use identity.
        req['actual_layout']['emission_ledger'][1]['performance_id']='independent-use'
        self.assertEqual([],music._joins(req['actual_layout']['notes'],{e['note_id']:e for e in req['actual_layout']['emission_ledger']},None))

    def test_cancel_callbacks_and_finite_budget_are_honest(self):
        req=request(fixture(4));before=copy.deepcopy(req)
        with self.assertRaises(m.ProjectError) as exc:music.plan_boundaries(req,should_cancel=lambda:True)
        self.assertEqual('CANCELLED',exc.exception.code);self.assertEqual(before,req)
        with self.assertRaises(RuntimeError):music.plan_boundaries(req,on_progress=lambda m:(_ for _ in ()).throw(RuntimeError('queue')))
        events=[];music.plan_boundaries(req,on_progress=events.append);self.assertTrue(all(isinstance(e,str) and '%' not in e for e in events))
        req=request(fixture(4),parameters=dict(max_operations=1));proposal=music.plan_boundaries(req)
        self.assertEqual('BUDGET_EXHAUSTED',proposal['search']['termination']);self.assertEqual(1,proposal['search']['attempted_operations'])

    def test_replay_new_request_and_reverse_input_keep_musical_content(self):
        req=request(fixture(3));before=copy.deepcopy(req);first=music.plan_boundaries(req)
        self.assertEqual(first,music.plan_boundaries(req));self.assertEqual(before,req)
        other=copy.deepcopy(req);other['token'].update(request_id='another-request',snapshot_id='another-snapshot',session_id='another-session')
        other.update(plan_id='another-plan',plan_version=2);other['actual_layout']['segments'].reverse();other['actual_layout']['emission_ledger'].reverse();rehash(other)
        second=music.plan_boundaries(other)
        projection=lambda r,p:[(n['pitch'],n['start_tick'],n['duration_tick'],n['velocity']) for n in actual_notes(r,p)]
        self.assertEqual(projection(req,first),projection(other,second))

    def test_invalid_frames_notes_parameters_and_fake_source_are_rejected(self):
        req=request()
        for mutate in (lambda r:r.update(id='borrowed'),lambda r:r.update(seed=True),lambda r:r['parameters'].update(max_pitch_shift=3),
            lambda r:r['connection_ref']['outcome'].update(status='FAILED'),lambda r:r['actual_layout']['emission_ledger'].pop(),
            lambda r:r['actual_layout']['emission_ledger'][0]['parent_ref'].update(owner_id='another-place'),
            lambda r:r['actual_layout']['emission_ledger'][0]['parent_ref'].update(content_fingerprint='self-rehashed'),
            lambda r:r['actual_layout']['emission_ledger'][0]['parent_ref'].update(component_path=['fake-occurrence']),
            lambda r:r['actual_layout']['notes'][0]['origin'].update(source_note_id='not-source')):
            bad=copy.deepcopy(req);mutate(bad)
            if bad['id']!='borrowed':rehash(bad)
            with self.assertRaises(m.ProjectError):music.plan_boundaries(bad)

    def test_pipeline_isolation_no_old_planner_or_emotion_or_connection(self):
        req=request(fixture(2))
        with patch('story_engine.plan_story',create=True,side_effect=AssertionError('legacy')), patch.object(connection_music,'generate',side_effect=AssertionError('P6')):
            music.plan_boundaries(req)

    def test_source_digest_fixed_vectors_from_frozen_contract(self):
        self.assertEqual('b7e9e8d9b68a835c5828297af15ecc977f7aa8c096059a073d598e904c87fd88',
            m.digest('emoblocks.final-source.v1',dict(kind='final',notes=[],sources=[],parents=[])))
        # Mechanical digest vector, not an authorization or completed score.
        note=dict(id='n',pitch=60,start_tick=0,duration_tick=480,velocity=80,origin=None,lineage=[],slice=None)
        material=dict(id='m',label='fixed-vector',kind='block',length_ticks=480,notes=[note],children=[],generation=None,phrase_id=None,provenance=dict(method='manual-fixed-vector'))
        parent=dict(note=dict(note,id='p:n'),parent_ref=dict(stage='placement',owner_id='p',note_id='p:n',component_path=[],material_snapshot_id='m',
            content_fingerprint='93e617d632a20c7078f33d2b870f55e2a401e904b6a2411ddc7b0d90b40dba33'),
            material_snapshots=[material],accepted_score_ref=None,accepted_source_fingerprint=None)
        self.assertEqual('9f5f557644d0f0d7e769b47cd9eb00671af1b1de6554b096ac684878c30e4e24',m.digest('emoblocks.final-source.v1',
            dict(kind='final',notes=[dict(id='p:n',origin=None,lineage=[],slice=None,parent_ids=['p:n'])],sources=[],parents=[parent])))


if __name__=='__main__':unittest.main()
