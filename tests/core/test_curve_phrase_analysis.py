"""Global bridge analysis: actual source/ownership, arithmetic and pure gates."""
import copy
import itertools
import unittest
from unittest.mock import patch

import curve_bridges as b
import curve_bridge_music as bridge
import curve_phrase_analysis as analysis
import curve_project as m
import curve_workflow as workflow
from test_curve_bridge_music import fixture


def global_request(project,parameters=None):
    return b.make_request(project,values=parameters,algorithm_version=b.GLOBAL_ALGORITHM)


def far_theme(alternative=False):
    p=m.new_project(10);p['project_id']='far-theme'
    pitches=[[84,72,60] if alternative else [60,64,67],[72,60,48],[60,62,64],[60,64,67],[52,40,28]]
    source=[]
    for i,ps in enumerate(pitches):
        start=i*3840;notes=[]
        for j,pitch in enumerate(ps):
            sid='source:%d:%d'%(i,j)
            note=dict(id='local:%d:%d'%(i,j),pitch=pitch,start_tick=j*1200,duration_tick=960,velocity=80,
                origin=dict(source_id='S',track_id='track',source_note_id=sid),lineage=[],slice=None)
            notes.append(note);source.append(dict(copy.deepcopy(note),id=sid,start_tick=start+j*1200))
        material=dict(id='phrase:%d'%i,label='phrase',kind='phrase',length_ticks=3840,notes=notes,
            provenance=dict(source_id='S',source_start_tick=start,key_context=dict(tonic=0,mode='major',confidence=1.,method='fixture-explicit')),
            generation=None,phrase_id=None,children=[])
        p['materials'].append(material)
        p['placements'].append(dict(id='place:%d'%i,material_id=material['id'],base_snapshot=copy.deepcopy(material),
                                    start_tick=start,length_ticks=3840,emotion='calm',emotion_variant=None))
    p['sources']=[dict(id='S',label='source',length_ticks=19200,notes=source,provenance=dict(track_id='track'))]
    p['intensity_points']=[dict(tick=0,level=.25),dict(tick=19200,level=.25)]
    for ident,a,z in [('left',0,7680),('right',11520,19200)]:
        lock=dict(id=ident,kind='manual',owner_id=ident,placement_id=None,component_path=[],start_tick=a,end_tick=z,
                  status='CONTENT_READY',origin='manual',plan_id=None,plan_version=None,input_fingerprint=m.fingerprint(p),
                  notes=[n for n in m.current_notes(p) if a<=n['start_tick']<z],structure_fingerprint=None,blank_mask=[])
        lock['structure_fingerprint']=m.structure_fingerprint(lock);p['protections'].append(lock)
    m.validate(p);return p


def far_request(alternative=False):
    return global_request(far_theme(alternative),dict(max_windows=1,max_window_blocks=2,max_window_tests=2048))


class AnalysisTests(unittest.TestCase):
    def test_far_theme_changes_actual_range_not_local_music(self):
        a,x=far_request(),far_request(True)
        window=dict(start_tick=7680,end_tick=11520)
        self.assertEqual([n for n in a['base_notes'] if 6000<=n['start_tick']<=12000],
                         [n for n in x['base_notes'] if 6000<=n['start_tick']<=12000])
        for req,expected,gain in [(a,'selected',.48904718),(x,'none',-.49793199)]:
            before=copy.deepcopy(req);facts=analysis.analyze(req);proposal=bridge.decide(req)
            row=next(r for r in proposal['assessments'] if r['range']==window)
            self.assertEqual(gain,row['benefit']);self.assertEqual(expected,proposal['decision'])
            self.assertEqual([window] if expected=='selected' else [],[{k:w[k] for k in window} for w in proposal['windows']])
            self.assertTrue(proposal['search']['coverage']['coverage_complete'])
            self.assertEqual('EXHAUSTED',proposal['search']['termination'])
            analysis.validate(req,facts);analysis.validate_search(req,proposal)
            self.assertEqual(before,req)
            legacy=copy.deepcopy(req);legacy['algorithm_version']=b.ALGORITHM
            self.assertEqual('none',bridge.decide(legacy)['decision'])
            self.assertEqual({'tested_windows','termination'},set(bridge.decide(legacy)['search']))

    def test_boundary_weights_full_support_and_no_fourbeat_split(self):
        req=global_request(fixture(4,rough=False));facts=analysis.analyze(req)
        self.assertEqual(1,len(facts['phrases']))
        self.assertLess(next(v for v in facts['boundaries'] if v['tick']==1920)['confidence'],.60)
        p=fixture(4,rough=False)
        # One unchanged long actual source note crosses the fourbeat grid.
        for v in p['placements']:v['base_snapshot']['notes']=v['base_snapshot']['notes'][:1]
        for v in p['materials']:v['notes']=v['notes'][:1]
        for v in p['placements']:v['base_snapshot']['notes'][0]['duration_tick']=1920
        for v in p['materials']:v['notes'][0]['duration_tick']=1920
        req=global_request(p);facts=analysis.analyze(req)
        self.assertTrue(all(not any(n['start_tick']<v['tick']<n['start_tick']+n['duration_tick'] for n in req['base_notes']) for v in facts['boundaries']))
        self.assertEqual([n['id'] for n in req['base_notes']],[i for v in facts['phrases'] for i in v['note_ids']])

    def test_repeated_nested_occurrences_count_once(self):
        p=fixture(4,rough=False);leaf=copy.deepcopy(p['materials'][0]);p['placements']=[]
        combined=workflow.combine(p,[leaf,leaf]);p=m.edit(p,'add_material',material=combined)
        nested=workflow.combine(p,[combined,combined]);p=m.edit(p,'add_material',material=nested)
        p=m.edit(p,'place',material_id=nested['id'],start_tick=0,placement_id='nested')
        req=global_request(p);facts=analysis.analyze(req)
        terminal=[o for o in facts['occurrences'] if o['role']=='terminal']
        self.assertEqual(4,len(terminal));self.assertEqual(4,len({tuple(o['component_path']) for o in terminal}))
        self.assertEqual(len(req['base_notes']),sum(len(o['note_ids']) for o in terminal))
        self.assertEqual(len(req['base_notes']),len(set(i for o in terminal for i in o['note_ids'])))
        self.assertEqual(1,len([o for o in facts['occurrences'] if o['role']=='aggregate']))
        analysis.validate(req,facts)

    def test_order_uuid_and_phrase_label_independence(self):
        req=far_request();old=bridge.decide(req)
        p=copy.deepcopy(req['base_project']);p['placements'].reverse();p['materials'].reverse();p['sources'][0]['notes'].reverse()
        for v in p['materials']:v['label']='renamed'
        other=global_request(p,req['parameters']);new=bridge.decide(other)
        self.assertEqual([(w['start_tick'],w['end_tick']) for w in old['windows']],[(w['start_tick'],w['end_tick']) for w in new['windows']])
        self.assertEqual([a.get('benefit') for a in old['assessments']],[a.get('benefit') for a in new['assessments']])
        changed=copy.deepcopy(req);changed.update(request_id='new',snapshot_id='new-snapshot',session_id='new-session',plan_id='new-plan')
        replay=bridge.decide(changed)
        self.assertEqual(old['assessments'],replay['assessments'])
        self.assertEqual([(w['start_tick'],w['end_tick']) for w in old['windows']],[(w['start_tick'],w['end_tick']) for w in replay['windows']])

    def test_signed_trajectory_plateau_and_no_resampled_controls(self):
        req=far_request();p=req['base_project'];p['intensity_points']=[dict(tick=t,level=v) for t,v in [(0,.1),(7680,.1),(11520,.9),(19200,.9)]]
        rising=global_request(p,req['parameters']);a=analysis.analyze(rising)
        p=copy.deepcopy(p);p['intensity_points']=[dict(tick=t,level=1-v) for t,v in [(0,.1),(7680,.1),(11520,.9),(19200,.9)]]
        falling=global_request(p,req['parameters']);x=analysis.analyze(falling)
        window=dict(start_tick=7680,end_tick=11520)
        self.assertGreater(analysis.window_features(a,window)['trajectory_alignment'],0)
        self.assertLess(analysis.window_features(x,window)['trajectory_alignment'],0)
        self.assertEqual([dict(tick=0,level=.1,kind='trough'),dict(tick=11520,level=.9,kind='peak')],a['trajectory']['peaks'])
        for facts in (a,x):
            for segment in facts['trajectory']['segments']:
                self.assertEqual(segment['end_level']-segment['start_level'],segment['signed_delta'])
        self.assertEqual([],analysis.analyze(far_request())['trajectory']['peaks'])

    def test_limit_and_cancel_do_not_return_partial_success(self):
        req=far_request()
        with patch.dict(analysis.LIMITS,notes=14),self.assertRaises(m.ProjectError) as error:analysis.analyze(req)
        self.assertEqual('ANALYSIS_LIMIT',error.exception.code)
        with patch.dict(analysis.LIMITS,phrases=2),self.assertRaises(m.ProjectError):analysis.analyze(req)
        with self.assertRaises(m.ProjectError) as error:analysis.analyze(req,lambda:True)
        self.assertEqual('CANCELLED',error.exception.code)
        count=iter([False]*8+[True])
        with self.assertRaises(m.ProjectError):analysis.analyze(req,lambda:next(count,True))

    def test_forged_analysis_hash_cannot_authenticate_facts(self):
        req=far_request();facts=analysis.analyze(req)
        mutations=[lambda a:a['occurrences'][0]['owner_ref'].update(placement_id='other'),
                   lambda a:a['occurrences'][0]['note_ids'].pop(),
                   lambda a:a['motif_relations'][0].update(contour_similarity=1.),
                   lambda a:a['boundaries'][1].update(confidence=1.),
                   lambda a:a['trajectory']['samples'][0].update(level=.75)]
        for mutate in mutations:
            bad=copy.deepcopy(facts);mutate(bad)
            bad['analysis_fingerprint']=m.digest(analysis.SCHEMA,{k:v for k,v in bad.items() if k!='analysis_fingerprint'})
            with self.subTest(mutation=mutate),self.assertRaises(m.ProjectError):analysis.validate(req,bad)

    def test_pure_validation_never_calls_analysis_or_any_music_provider(self):
        req=far_request();facts=analysis.analyze(req);proposal=bridge.decide(req)
        with patch.object(analysis,'analyze',side_effect=AssertionError('no analysis entrypoint')),\
             patch.object(bridge,'decide',side_effect=AssertionError('no decide')),\
             patch.object(bridge,'generate',side_effect=AssertionError('no generation')):
            analysis.validate(req,facts);analysis.validate_search(req,proposal)

    def test_real_final_score_accepted_owner_and_added_ordinary_mix(self):
        # Real P5/P6/final pure gates and final provider; no renderer/assets/UI.
        # Record assembly here tests source ownership, not application permission.
        import curve_application as application
        import curve_boundary_music as boundary
        import curve_final as final
        from test_curve_final import boundary_request
        p=fixture(4);controller=workflow.Controller(p)
        req=boundary_request(controller=controller)
        plan=final.make_plan(req,boundary.plan_boundaries(req))
        score=final.make_score(req,plan,final.apply_boundaries(req,plan))
        final.validate_final_score(req,plan,score)
        p=copy.deepcopy(controller.project);p['contract_rev']=final.REV
        overlay=dict(schema='emoblocks.accepted-overlay.v1',candidate_ref=dict(id='candidate',version=1,fingerprint='candidate'),
                     final_score=score,score_ref=final.ref(score),binding_fingerprint=application.binding_fingerprint(p),
                     mode='arranged',bridge_overlays=[],connection_overlays=[],boundary_operations=copy.deepcopy(plan['operations']),write_ranges=[])
        p['records'] += [dict(id='score-record',kind='final_score',version=1,status='READY',input_fingerprint=m.fingerprint(p),dependencies=[],
                             payload=dict(total_ticks=p['total_ticks'],notes=copy.deepcopy(score['notes']),protection_summary_fingerprint=m.protection_summary(p['protections']),validation={},p7=overlay)),
                         dict(id='accepted-record',kind='accepted_candidate',version=1,status='READY',input_fingerprint=m.fingerprint(p),dependencies=[dict(id='score-record',version=1)],
                             payload=dict(final_score_id='score-record',transaction_id='transaction',input_snapshot_id='snapshot',result_id='result',mode='arranged',
                                          candidate_ref=overlay['candidate_ref'],score_ref=final.ref(score),application_ref=dict(id='transaction',version=1,fingerprint='fixture')))]
        p['accepted_candidate_id']='accepted-record';m.validate(p)
        global_req=global_request(p);facts=analysis.analyze(global_req)
        accepted=[o for o in facts['occurrences'] if o['owner_ref']['kind']=='accepted_score']
        self.assertTrue(accepted,score)
        for occurrence in accepted:
            self.assertIsNone(occurrence['placement_id']);self.assertEqual(score['id'],occurrence['owner_ref']['owner_id'])
            for ident in occurrence['note_ids']:
                rows=[r for r in score['performance_map'] if ident in r['logical_note_ids']]
                self.assertEqual(1,len(rows));self.assertEqual(rows[0]['performance_id'],occurrence['performance_id'])
                self.assertEqual(b.parent_ref(global_req,ident)['component_path'],occurrence['component_path'])
        # Preserve old score as explicit captured source, add an independent use.
        future=m.edit(p,'resize',grid_count=5)
        future=m.edit(future,'place',material_id=future['materials'][0]['id'],start_tick=7680,placement_id='added')
        application.capture_private_music(p,future,['added']);m.validate(future)
        mixed=global_request(future);facts=analysis.analyze(mixed);analysis.validate(mixed,facts)
        self.assertTrue(any(o['note_ids'] and o['owner_ref'].get('placement_id')=='added' for o in facts['occurrences']))
        self.assertTrue(any(o['owner_ref']['kind']=='accepted_score' for o in facts['occurrences']))
        self.assertEqual(set(n['id'] for n in mixed['base_notes']),set(i for o in facts['occurrences'] if o['role']=='terminal' for i in o['note_ids']))

    def test_terminal_turn_guard_and_old_analysis_version_forgery(self):
        req=far_request();facts=analysis.analyze(req)
        for tick in (5040,12720):
            row=next(b for b in facts['boundaries'] if b['tick']==tick)
            self.assertEqual(.4,row['confidence']);self.assertNotIn('contour_turn',[e['kind'] for e in row['evidence']])
        turning=analysis.analyze(global_request(fixture(4)))
        self.assertTrue(any(e['kind']=='contour_turn' for b in turning['boundaries'] for e in b['evidence']))
        for bad in (copy.deepcopy(facts),copy.deepcopy(facts)):
            bad['algorithm_version']='curve-phrase-analysis-v1'
            bad['analysis_fingerprint']=m.digest(analysis.SCHEMA,{k:v for k,v in bad.items() if k!='analysis_fingerprint'})
            with self.assertRaises(m.ProjectError):analysis.validate(req,bad)
        bad=copy.deepcopy(facts);row=next(b for b in bad['boundaries'] if b['tick']==5040)
        row['evidence'].append(dict(kind='contour_turn',weight=.2,details=dict(note_ids=req['base_notes'][2:5])))
        row['confidence']=.6;bad['analysis_fingerprint']=m.digest(analysis.SCHEMA,{k:v for k,v in bad.items() if k!='analysis_fingerprint'})
        with self.assertRaises(m.ProjectError):analysis.validate(req,bad)

    def test_real_import_phrase_hints_are_soft_and_source_bound(self):
        import curve_melody as melody
        from test_curve_melody import source
        src=source(events=[(60,0,240),(64,480,240),(62,960,240),(67,1440,480)],length=1920)
        p=m.new_project(2);p['sources']=[src];p['materials']=melody.prepare_source(src)['materials']
        parent=next(v for v in p['materials'] if v['kind']=='phrase')
        p=m.edit(p,'place',material_id=parent['id'],start_tick=0,placement_id='source-use1')
        p=m.edit(p,'place',material_id=parent['id'],start_tick=1920,placement_id='source-use2')
        facts=analysis.analyze(global_request(p));terminals=[o for o in facts['occurrences'] if o['role']=='terminal']
        self.assertEqual(2,len(terminals))
        for o in terminals:self.assertEqual(dict(source_id=src['id'],phrase_id=parent['id'],relative_start_tick=0),o['source_phrase_ref'])
        self.assertTrue(any(e['kind']=='source_hint' for b in facts['boundaries'] for e in b['evidence']))
        # A source ID/name/phrase-shaped material by itself creates no hint.
        fake=far_request();self.assertTrue(all(o['source_phrase_ref'] is None for o in analysis.analyze(fake)['occurrences']))

    def test_reordered_actual_phrases_recompute_remote_relation(self):
        p=far_theme();first,second=p['placements'][:2]
        first['start_tick'],second['start_tick']=second['start_tick'],first['start_tick']
        for lock in p['protections']:
            lock['notes']=[n for n in m.current_notes(p) if lock['start_tick']<=n['start_tick']<lock['end_tick']]
            lock['structure_fingerprint']=m.structure_fingerprint(lock)
        changed=global_request(p,dict(max_windows=1,max_window_blocks=2,max_window_tests=2048))
        normal=analysis.analyze(far_request());reordered=analysis.analyze(changed)
        window=dict(start_tick=7680,end_tick=11520)
        self.assertEqual(1,analysis.window_features(normal,window)['return_preparation'])
        self.assertEqual(0,analysis.window_features(reordered,window)['return_preparation'])
        proposal=bridge.decide(changed);analysis.validate_search(changed,proposal)
        self.assertTrue(proposal['search']['coverage']['coverage_complete'])

    def test_empty_music_and_bounds_all_refuse_fake_material_or_truncation(self):
        p=fixture(2)
        for v in p['materials']:v['notes']=[]
        for v in p['placements']:v['base_snapshot']['notes']=[]
        req=global_request(p);facts=analysis.analyze(req);proposal=bridge.decide(req)
        self.assertEqual([],facts['motif_relations']);self.assertEqual('none',proposal['decision'])
        self.assertEqual('NO_WRITABLE_WINDOW',proposal['reasons'][0]['code']);analysis.validate_search(req,proposal)
        for name in ('placements','occurrences','terminals','endpoints','controls','samples','json_bytes','depth'):
            with self.subTest(limit=name),patch.dict(analysis.LIMITS,{name:0}),self.assertRaises(m.ProjectError) as error:
                analysis.analyze(far_request())
            self.assertEqual('ANALYSIS_LIMIT',error.exception.code)

    def test_missing_tonal_metadata_uses_whole_actual_terminal(self):
        p=fixture(2,rough=False)
        for v in p['materials']:v['provenance'].pop('key_context')
        for v in p['placements']:v['base_snapshot']['provenance'].pop('key_context')
        req=global_request(p);keys=analysis.note_keys(req)
        for place in p['placements']:
            tonal={(keys[n['id']]['tonic'],keys[n['id']]['mode']) for n in m.placed_notes(place)}
            self.assertEqual(1,len(tonal))
        proposal=bridge.decide(req)
        self.assertTrue(all(a['features']['key_changes']==0 for a in proposal['assessments'] if a['benefit'] is not None))
        analysis.validate_search(req,proposal)

    def test_boolean_numeric_alias_cannot_bypass_content_authentication(self):
        req=far_request();facts=analysis.analyze(req)
        bad=copy.deepcopy(facts);bad['boundaries'][0]['confidence']=True
        # Python dict equality aliases True and 1.0; serialized facts do not.
        self.assertEqual(bad,facts)
        with self.assertRaises(m.ProjectError):analysis.validate(req,bad)
        proposal=bridge.decide(req);bad=copy.deepcopy(proposal)
        bad['search']['coverage']['coverage_complete']=1
        self.assertEqual(bad,proposal)
        with self.assertRaises(m.ProjectError):analysis.validate_search(req,bad)
