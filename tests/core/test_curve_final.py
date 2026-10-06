"""P7 independent music gates. Synthetic WAV is only a renderer fault fixture."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import uuid

import curve_project as m
import curve_final as f
import curve_final_render as audio
import curve_recommendations as rec
import curve_workflow as w
import curve_store as store
import curve_boundary_music as algorithm
from test_curve_bridges import complete
from test_curve_connections import ready_bridge,begin
from test_curve_candidates import fixture


def boundary_request(manual=False,ranges=()):
    controller=ready_bridge(complete(manual),ranges)
    captured,plan=begin(controller,())
    import curve_connections as connection
    controller.finish_connection(captured['token'],connection.raw_outcome(captured['request'],plan,[]))
    attempt=controller._connection_attempt(captured['attempt_id'])
    reference=dict(attempt_id=attempt['id'],**{k:copy.deepcopy(attempt['connection'][k]) for k in ('request','plan','results','outcome')})
    return f.make_request(reference)


def simulated_render(folder):
    def render(score,candidate_ref,version=1,should_cancel=None,on_progress=None):
        import engine
        root=Path(folder)/uuid.uuid4().hex;root.mkdir()
        audio.export_score(score,root)
        seconds=score['total_ticks']/m.PPQ*60/score['bpm']+1
        with wave.open(str(root/'preview.wav'),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(8000);stream.writeframes(b'\x01\x00'*round(seconds*8000))
        asset=dict(f.header('emoblocks.audio-asset.v1'),version=version,candidate_ref=copy.deepcopy(candidate_ref),score_ref=f.ref(score),kind=score['kind'],mode=score['mode'],
            renderer_version=audio.RENDERER,files={k:audio._file(root/name) for k,name in [('wav','preview.wav'),('mid','composition.mid'),('mmp','composition.mmp')]},
            body_ticks=score['total_ticks'],body_seconds=seconds-1,audio_seconds=seconds,tail_policy='fixed-1s-existing-finish-audio')
        asset['asset_fingerprint']=audio.asset_fingerprint(asset);asset['id']=asset['asset_fingerprint'];return asset
    return render


class FinalGateTests(unittest.TestCase):
    def test_validation_scope_never_authenticates_changed_bytes_or_leaks(self):
        request=boundary_request();plan=f.make_plan(request,algorithm.plan_boundaries(request));score=f.make_score(request,plan,f.apply_boundaries(request,plan))
        with m.validation_scope():
            f.validate_final_score(request,plan,score)
            bad=copy.deepcopy(score);bad['notes'][0]['pitch']+=1;bad['score_fingerprint']=f.score_fingerprint(bad);bad['id']=bad['score_fingerprint']
            with self.assertRaises(m.ProjectError):f.validate_final_score(request,plan,bad)
            p=copy.deepcopy(request['actual_layout']['base_project']);m.validate(p);p['bpm']=0
            with self.assertRaises(m.ProjectError):m.validate(p)
        self.assertIsNone(m._VALIDATION_CONTEXT.get())

    def test_accepted_bridge_material_reuse_registers_manual_protection(self):
        source=ready_bridge(complete(),[(3840,7680)])
        material=source._bridge_attempt(source._bridge_id)['bridge']['results'][0]['material']
        project=m.new_project();project['contract_rev']=f.REV;project['sources']=copy.deepcopy(source.project['sources'])
        controller=w.Controller(project);controller.edit('add_material',material=material)
        controller.edit('place',material_id=material['id'],start_tick=0,placement_id='manual-reuse')
        lock=next(p for p in controller.project['protections'] if p['kind']=='bridge')
        self.assertEqual(lock['origin'],'manual');self.assertEqual(lock['notes'],m.placed_notes(controller.project['placements'][0]))
        controller.edit('move',placement_id='manual-reuse',start_tick=3840)
        lock=next(p for p in controller.project['protections'] if p['kind']=='bridge')
        self.assertEqual(lock['start_tick'],3840);self.assertEqual(lock['plan_version'],2)

    def test_encoded_expression_tampering_is_rejected(self):
        import mido
        import xml.etree.ElementTree as ET
        request=boundary_request();plan=f.make_plan(request,algorithm.plan_boundaries(request));score=f.make_score(request,plan,f.apply_boundaries(request,plan))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);audio.export_score(score,root)
            files={k:audio._file(root/name) for k,name in [('mid','composition.mid'),('mmp','composition.mmp')]}
            audio.validate_outputs(score,files)
            midi=mido.MidiFile(root/'composition.mid');next(e for t in midi.tracks for e in t if e.type=='note_on' and e.velocity).velocity+=1;midi.save(root/'composition.mid')
            with self.assertRaises(m.ProjectError):audio.validate_outputs(score,files)
            audio.export_score(score,root);xml=ET.parse(root/'composition.mmp');xml.find('.//note').set('vol','1');xml.write(root/'composition.mmp')
            with self.assertRaises(m.ProjectError):audio.validate_outputs(score,files)

    def test_active_blank_has_real_handoffs_without_filling_silence(self):
        controller=complete();controller.edit('delete',placement_id='use2');controller.edit('mark_blank',start_tick=3840,end_tick=5760)
        ready_bridge(controller);cap,cp=begin(controller,())
        import curve_connections as c
        controller.finish_connection(cap['token'],c.raw_outcome(cap['request'],cp,[]))
        a=controller._connection_attempt(cap['attempt_id']);request=f.make_request(dict(attempt_id=a['id'],**{k:copy.deepcopy(a['connection'][k]) for k in ('request','plan','results','outcome')}))
        plan=f.make_plan(request,algorithm.plan_boundaries(request));score=f.make_score(request,plan,f.apply_boundaries(request,plan))
        self.assertFalse(any(m.intersects(f.support(n),dict(start_tick=3840,end_tick=5760)) for n in score['notes']))
        self.assertEqual(f.validate_final_score(request,plan,score)['status'],'VALID')

    def test_true_ready_dependency_and_atomic_score_validation(self):
        request=boundary_request(manual=True);plan=f.make_plan(request,algorithm.plan_boundaries(request));result=f.apply_boundaries(request,plan)
        score=f.make_score(request,plan,result)
        self.assertEqual(f.validate_final_score(request,plan,score)['status'],'VALID')
        for field in ('pitch','start_tick','duration_tick'):
            damaged=copy.deepcopy(score);protected=request['protection_summary']['ranges']
            note=next(n for n in damaged['notes'] if any(m.intersects(f.support(n),r) for r in protected));note[field]+=1
            damaged['score_fingerprint']=f.score_fingerprint(damaged);damaged['id']=damaged['score_fingerprint']
            with self.subTest(field=field),self.assertRaises(m.ProjectError):f.validate_final_score(request,plan,damaged)
        damaged=copy.deepcopy(request);damaged['connection_ref']['results'].append({})
        with self.assertRaises(m.ProjectError):f.validate_request(damaged)

    def test_source_tampering_with_rehashed_score_is_rejected(self):
        request=boundary_request();plan=f.make_plan(request,algorithm.plan_boundaries(request));score=f.make_score(request,plan,f.apply_boundaries(request,plan))
        for field,value in [('origin',None),('lineage',['unrelated-legitimate-looking-parent']),('slice',dict(parent_emission_id='fake',offset_tick=0,parent_duration_tick=999999))]:
            damaged=copy.deepcopy(score);damaged['notes'][0][field]=value
            if damaged['notes']==score['notes']:continue
            damaged['source_fingerprint']=m.digest('emoblocks.final-source.v1',dict(kind=damaged['kind'],notes=damaged['notes'],parents=[],sources=[]))
            damaged['score_fingerprint']=f.score_fingerprint(damaged);damaged['id']=damaged['score_fingerprint']
            with self.subTest(field=field),self.assertRaises(m.ProjectError):f.validate_final_score(request,plan,damaged)

    def test_same_planned_music_two_modes_and_no_disguised_accompaniment(self):
        request=boundary_request();plan=f.make_plan(request,algorithm.plan_boundaries(request));result=f.apply_boundaries(request,plan)
        arranged=f.make_score(request,plan,result);solo=f.make_score(request,plan,result,'melody_only')
        self.assertEqual(arranged['notes'],solo['notes']);self.assertEqual(arranged['music_fingerprint'],solo['music_fingerprint'])
        self.assertEqual(len(solo['layers']),1);self.assertEqual(solo['layers'][0]['preset'],'soft')
        damaged=copy.deepcopy(arranged);damaged['layers'][0]['notes'].append(copy.deepcopy(arranged['notes'][0]))
        damaged['score_fingerprint']=f.score_fingerprint(damaged);damaged['id']=damaged['score_fingerprint']
        with self.assertRaises(m.ProjectError):f.validate_final_score(request,plan,damaged)

    def test_exact_output_failure_does_not_mutate_score(self):
        request=boundary_request();plan=f.make_plan(request,algorithm.plan_boundaries(request));score=f.make_score(request,plan,f.apply_boundaries(request,plan))
        score['notes'][0]['duration_tick']+=1;before=copy.deepcopy(score)
        with self.assertRaises(m.ProjectError) as error:audio.output_arrangement(score)
        self.assertEqual(error.exception.code,'OUTPUT_TIME_UNREPRESENTABLE');self.assertEqual(score,before)

    def test_duplicate_material_uses_are_not_joined(self):
        request=boundary_request();notes=copy.deepcopy(request['actual_layout']['notes'][:2])
        for i,note in enumerate(notes):
            note.update(start_tick=i*240,duration_tick=240,pitch=60,slice=dict(parent_emission_id='same',offset_tick=i*240,parent_duration_tick=480))
        ledger=[dict(note_id=notes[i]['id'],performance_id='use'+str(i)) for i in range(2)]
        events,groups=f.joined_events(notes,ledger);self.assertEqual(len(events),2);self.assertEqual(groups,[])
        ledger[1]['performance_id']=ledger[0]['performance_id'];notes[1]['origin']=notes[0]['origin']
        events,groups=f.joined_events(notes,ledger);self.assertEqual(len(events),1);self.assertEqual(events[0]['duration_tick'],480)

    def test_source_fixed_hash_vectors(self):
        self.assertEqual(m.digest('emoblocks.final-source.v1',dict(kind='final',notes=[],sources=[],parents=[])),
            'b7e9e8d9b68a835c5828297af15ecc977f7aa8c096059a073d598e904c87fd88')
        note=dict(id='n',pitch=60,start_tick=0,duration_tick=480,velocity=80,origin=None,lineage=[],slice=None)
        snapshot=dict(id='m',label='fixed-vector',kind='block',length_ticks=480,notes=[note],provenance=dict(method='manual-fixed-vector'),generation=None,phrase_id=None,children=[])
        projection=dict(kind='final',notes=[dict(id='p:n',origin=None,lineage=[],slice=None,parent_ids=['p:n'])],sources=[],parents=[dict(note=dict(note,id='p:n'),
            parent_ref=dict(stage='placement',owner_id='p',note_id='p:n',component_path=[],material_snapshot_id='m',content_fingerprint='93e617d632a20c7078f33d2b870f55e2a401e904b6a2411ddc7b0d90b40dba33'),
            material_snapshots=[snapshot],accepted_score_ref=None,accepted_source_fingerprint=None)])
        self.assertEqual(m.digest('emoblocks.final-source.v1',projection),'9f5f557644d0f0d7e769b47cd9eb00671af1b1de6554b096ac684878c30e4e24')


class RecommendationTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.render=patch.object(audio,'render',side_effect=simulated_render(self.tmp.name));self.render.start();self.addCleanup(self.render.stop)
        self.paths=patch('curve_store.data_root',return_value=Path(self.tmp.name));self.paths.start();self.addCleanup(self.paths.stop)

    def ready(self,controller=None,selected=None):
        controller=controller or complete();cap=controller.capture_recommendations(selected)
        out=rec.prepare_recommendations(cap['request'],source_facts=controller._bundle.get('final_facts'),on_progress=lambda e:controller.record_recommendation_progress(cap['token'],e))
        self.assertTrue(out['candidates'],out['failures']);self.assertTrue(controller.finish_recommendations(cap['token'],out))
        return controller,cap,out

    def test_rehashed_stage_and_mode_bindings_cannot_borrow_another_result(self):
        controller,cap,out=self.ready()
        bad=copy.deepcopy(out);bad['candidates'][0]['stage_refs']['bridge_attempt_id']='borrowed-other-plan'
        bad['outcome_fingerprint']=rec.outcome_fingerprint(bad)
        with self.assertRaises(m.ProjectError):rec.validate_outcome(cap['request'],bad)
        bundle=controller._current_bundle();candidate=out['candidates'][0]
        bundle['attempts'][-1]['recommendation']['mode_bindings'][candidate['id']]['arranged']['asset_version']+=1
        with self.assertRaises(m.ProjectError):store.validate_bundle(bundle)
        missing=copy.deepcopy(out);row=next(r for r in missing['facts'] if r['kind']=='final_score' and r['data']['kind']=='final');row['dependencies']=row['dependencies'][:-1]
        missing['outcome_fingerprint']=rec.outcome_fingerprint(missing)
        with self.assertRaises(m.ProjectError):rec.validate_outcome(cap['request'],missing)

    def test_late_authentic_progress_cannot_replace_finished_connection_audit(self):
        import curve_connections as c
        controller,cap,out=self.ready();old=copy.deepcopy(controller._recommendation_attempt()['recommendation']['partial_stage_bundle'])
        changed=copy.deepcopy(old);child=next(a for a in changed['attempts'] if 'connection' in a);stage=child['connection']
        self.assertFalse(stage['results']);stage['plan']['reasons'][0]['message']='另一条仍合法的理由'
        stage['plan']['plan_fingerprint']=c.plan_fingerprint(stage['plan'])
        stage['outcome']=c.make_outcome(stage['request'],stage['plan'],[],'SUCCEEDED')
        store.validate_bundle(changed)  # Valid independently, but cannot replace a published fact.
        value=controller._recommendation_attempt()['recommendation']
        with self.assertRaises(m.ProjectError):controller.record_recommendation_progress(cap['token'],dict(seq=value['last_seq']+1,phase='CONNECTIONS',message='late',candidate_id=None,stage_bundle=changed))
        self.assertEqual(value['partial_stage_bundle'],old)

    def test_missing_other_format_does_not_disable_available_audio_or_export(self):
        controller,cap,out=self.ready();candidate=out['candidates'][0];cid=candidate['id']
        Path(candidate['assets']['final']['files']['mid']['path']).unlink()
        self.assertEqual(controller.recommendation_asset(cid)['score_ref'],candidate['final_score_ref'])
        applied=controller.apply_recommendation(cid);rid=applied['receipt']['result_id']
        self.assertTrue(controller.history()[0]['availability']['wav']);self.assertFalse(controller.history()[0]['availability']['mid'])
        self.assertEqual(controller.history_asset(rid)['score_ref'],candidate['final_score_ref'])
        destination=Path(self.tmp.name)/'valid.mmp';controller.export_history(rid,'mmp',destination);self.assertTrue(destination.is_file())
        with self.assertRaises(m.ProjectError):controller.export_history(rid,'mid',Path(self.tmp.name)/'missing.mid')

    def test_no_gap_full_same_audition_apply_undo_redo_and_pure_reopen(self):
        controller=complete();before=controller.project;saved=controller.state()['is_saved'];undo=copy.deepcopy(controller.session._undo)
        controller,cap,out=self.ready(controller)
        self.assertEqual(controller.project,before);self.assertEqual(controller.session._undo,undo);self.assertEqual(controller.state()['is_saved'],saved)
        self.assertEqual(out['status'],'INSUFFICIENT');cid=out['candidates'][0]['id'];selected_score=controller.recommendation_asset(cid)['score_ref']
        confirmation=controller.confirmation_ref(cid);applied=controller.apply_recommendation(cid,confirmation_ref=confirmation)
        self.assertEqual(applied['receipt']['score_ref'],selected_score);self.assertTrue(applied['changed'])
        self.assertFalse(controller.apply_recommendation(cid)['changed']);future=controller.project
        with patch.object(algorithm,'plan_boundaries',side_effect=AssertionError('redo must not compose')):
            self.assertTrue(controller.undo());self.assertEqual(controller.project,before)
            with self.assertRaises(m.ProjectError):controller.apply_recommendation(cid)
            self.assertTrue(controller.redo());self.assertEqual(controller.project,future)
        path=controller.save_snapshot(Path(self.tmp.name)/'accepted.json')
        with patch.object(rec,'prepare_recommendations',side_effect=AssertionError('load must be pure')),patch.object(audio,'render',side_effect=AssertionError('load must not render')),patch.object(f,'arrange',side_effect=AssertionError('load must not arrange')):
            loaded=w.Controller();loaded.load(path);self.assertEqual(loaded.project,future);self.assertEqual(loaded.accepted_state()['status'],'ACTIVE')
            self.assertEqual(loaded.effective_music()['notes'],controller.effective_music()['notes'])

    def test_selected_exact_gap_keeps_other_gaps_and_blocks_formal_export(self):
        controller=fixture();before=controller.project;controller,cap,out=self.ready(controller,controller.gap_items()[0]['id'])
        cid=out['candidates'][0]['id'];self.assertTrue(out['candidates'][0]['remaining_gaps'])
        applied=controller.apply_recommendation(cid);self.assertEqual(controller.project['placements'][:2],before['placements']);self.assertEqual(controller.project['total_ticks'],before['total_ticks'])
        self.assertEqual(controller.history()[0]['scope'],'LOCAL')
        with self.assertRaises(m.ProjectError):controller.export_history(applied['receipt']['result_id'],'wav',Path(self.tmp.name)/'must-not.wav')
        self.assertFalse((Path(self.tmp.name)/'must-not.wav').exists())

    def test_all_gaps_two_actual_recommendations_after_final_processing(self):
        controller,cap,out=self.ready(fixture())
        self.assertEqual(out['status'],'SUCCEEDED',out['failures']);self.assertGreaterEqual(len(out['candidates']),2)
        self.assertEqual(len(set(c['music_fingerprint'] for c in out['candidates'])),len(out['candidates']))
        for candidate in out['candidates']:self.assertEqual(candidate['remaining_gaps'],[])

    def test_duplicate_submission_edit_undo_and_late_callbacks(self):
        controller=complete();cap=controller.capture_recommendations()
        with self.assertRaises(m.ProjectError):controller.capture_recommendations()
        out=rec.prepare_recommendations(cap['request'])
        controller.edit('set_melody_only',value=True);controller.undo()
        self.assertFalse(controller.finish_recommendations(cap['token'],out));self.assertEqual(controller.recommendation_state()['status'],'STALE')
        self.assertEqual(controller._bundle['results'],[])

    def test_save_failure_missing_audio_and_render_failure_leave_original(self):
        controller,cap,out=self.ready();before=controller.project;undo=copy.deepcopy(controller.session._undo);cid=out['candidates'][0]['id']
        with patch.object(controller,'save_snapshot',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):controller.apply_recommendation(cid)
        self.assertEqual(controller.project,before);self.assertEqual(controller.session._undo,undo);self.assertEqual(controller._bundle['results'],[])
        Path(controller.recommendation_asset(cid)['files']['wav']['path']).unlink()
        with self.assertRaises(OSError):controller.apply_recommendation(cid)
        failed=complete();capture=failed.capture_recommendations()
        with patch.object(audio,'render',side_effect=OSError('render failed')):result=rec.prepare_recommendations(capture['request'])
        self.assertEqual(result['status'],'FAILED');self.assertTrue(failed.finish_recommendations(capture['token'],result));self.assertEqual(failed.recommendation_state()['status'],'FAILED')
        self.assertFalse(failed._jobs)

    def test_cancel_after_lock_preserves_audit_and_never_applies(self):
        controller=complete();cap=controller.capture_recommendations();before=controller.project
        def progress(event):
            reply=controller.record_recommendation_progress(cap['token'],event)
            if event['phase']=='BRIDGE_LOCKED':controller.cancel_recommendations(cap['token'])
            return reply
        result=rec.prepare_recommendations(cap['request'],should_cancel=lambda:controller._recommendation_attempt()['recommendation']['cancel_requested'],on_progress=progress)
        self.assertEqual(result['status'],'CANCELLED');self.assertTrue(controller.finish_recommendations(cap['token'],result));self.assertEqual(controller.project,before)
        self.assertTrue(result['stage_bundle']['attempts']);self.assertEqual(controller.recommendation_state()['status'],'CANCELLED')

    def test_mode_only_render_does_not_rerun_music(self):
        controller,cap,out=self.ready();cid=out['candidates'][0]['id'];captured=controller.capture_recommendation_mode(cid,'melody_only')
        with patch.object(algorithm,'plan_boundaries',side_effect=AssertionError('mode must not compose')),patch.object(w,'decide_bridge',side_effect=AssertionError('mode must not decide')):
            mode=rec.prepare_candidate_mode(captured['request'],cid,'melody_only',captured['source_facts']);self.assertTrue(controller.finish_recommendation_mode(captured['token'],mode))
        a=controller.recommendation_asset(cid,mode='arranged');b=controller.recommendation_asset(cid,mode='melody_only')
        self.assertNotEqual(a['score_ref'],b['score_ref']);self.assertEqual(rec.resolve(controller._bundle['final_facts'],a['score_ref'])['music_fingerprint'],rec.resolve(controller._bundle['final_facts'],b['score_ref'])['music_fingerprint'])

    def test_accepted_local_input_carries_actual_music_and_original_snapshots(self):
        controller=fixture();controller,_,first=self.ready(controller,controller.gap_items()[0]['id'])
        controller.apply_recommendation(first['candidates'][0]['id']);before=controller.project
        request=controller.capture_recommendations();self.assertEqual(set(request),{'token','request','attempt_id','source_facts'})
        snapshots=rec.source_snapshots(before,request['source_facts']);self.assertTrue(snapshots)
        with patch.object(w,'decide_bridge',side_effect=AssertionError('missing closure must fail before music')):
            with self.assertRaises(m.ProjectError):rec.prepare_recommendations(request['request'],source_facts=[])
        result=rec.prepare_recommendations(request['request'],source_facts=request['source_facts'])
        self.assertTrue(result['candidates'],result['failures']);self.assertEqual(controller.project,before)
        self.assertTrue(controller.finish_recommendations(request['token'],result));self.assertTrue(controller.apply_recommendation(result['candidates'][0]['id'])['changed'])
        self.assertEqual(controller.accepted_state()['status'],'ACTIVE');self.assertEqual(controller.accepted_state()['remaining_gaps'],[])

    def test_one_captured_request_is_reproducible_after_full_pipeline(self):
        controller=fixture();capture=controller.capture_recommendations()
        a=rec.prepare_recommendations(capture['request'],source_facts=capture['source_facts'])
        b=rec.prepare_recommendations(capture['request'],source_facts=capture['source_facts'])
        self.assertTrue(a['candidates'],a['failures'])
        self.assertEqual([x['music_fingerprint'] for x in a['candidates']],[x['music_fingerprint'] for x in b['candidates']])
        self.assertEqual([x['stage_refs'] for x in a['candidates']],[x['stage_refs'] for x in b['candidates']])

    def test_library_append_preserves_accepted_layers_and_source_ref_is_unique(self):
        from curve_application import source_score
        from test_curve_workflow import material
        controller,_,result=self.ready();cid=result['candidates'][0]['id'];controller.apply_recommendation(cid)
        before=controller.effective_music()['notes'];current=controller.project;reference=controller.accepted_state()['score_ref']
        record=next(r for r in current['records'] if r['kind']=='final_score');other=copy.deepcopy(record);other['id']='historical-other'
        other['payload']['p7']['final_score']['notes'][0]['velocity']+=1
        current['records'].append(other)
        self.assertEqual(source_score(current,before[0]['id'])['id'],reference['id'])
        job=controller.capture_job('COMBINE');controller.apply_batch(dict(sources=[],materials=[material('additional',240)],warnings=[]),job['token'])
        self.assertEqual(controller.accepted_state()['status'],'ACTIVE');self.assertEqual(controller.effective_music()['notes'],before)

    def test_running_reopen_interrupts_child_tasks_and_mode_jobs(self):
        controller=complete();capture=controller.capture_recommendations()
        def stop(event):
            controller.record_recommendation_progress(capture['token'],event)
            if event['phase']=='BRIDGE_LOCKED':
                path=controller.save_snapshot(Path(self.tmp.name)/'running.json')
                loaded=store.load(path)
                attempt=loaded['bundle']['attempts'][-1]
                self.assertEqual(attempt['state'],'INTERRUPTED')
                self.assertTrue(all(a['state']!='RUNNING' for a in attempt['recommendation']['partial_stage_bundle']['attempts']))
                controller.cancel_recommendations(capture['token'])
            return dict(accepted=True,continue_processing=True)
        value=rec.prepare_recommendations(capture['request'],source_facts=capture['source_facts'],on_progress=stop,
            should_cancel=lambda:controller._recommendation_attempt()['recommendation']['cancel_requested'])
        self.assertEqual(value['status'],'CANCELLED')


if __name__=='__main__':unittest.main()
