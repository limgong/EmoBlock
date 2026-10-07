"""Lead P2 facade behavior: no real LMMS/device calls in automated tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import curve_project as m
import curve_store as store
import curve_workflow as w
import curve_audition
import studio_model
from test_curve_workflow import project, material, manual_bridge


class FacadeTests(unittest.TestCase):
    def test_atomic_append_batch_and_undo_no_side_effects_from_prepare(self):
        c=w.Controller(project());before=c.project
        combo=w.combine(before,['A1','A1'])
        self.assertEqual(c.project,before)
        job=c.capture_job('COMBINE',dict(kind='draft',snapshot=combo))
        result=c.apply_batch(dict(sources=[],materials=[combo],warnings=[]),job['token'])
        self.assertEqual(result['added_material_ids'],[combo['id']]);self.assertFalse(c.accepts(job['token']))
        self.assertEqual(len(c.project['materials']),2)
        self.assertEqual(c.project['placements'],[])
        self.assertTrue(c.undo());self.assertEqual(c.project,before)
        self.assertTrue(c.redo());self.assertEqual(c.project['materials'][-1]['length_ticks'],480)

    def test_bad_batch_does_not_consume_ids_or_clear_redo_and_duplicate_rejects(self):
        c=w.Controller(project());c.edit('place',material_id='A1',start_tick=0);c.undo()
        before=c.project;job=c.capture_job('DERIVE',dict(kind='material',id='A1'))
        bad=material('bad');bad['phrase_id']='missing'
        with self.assertRaises(m.ProjectError):c.apply_batch(dict(sources=[],materials=[bad],warnings=[]),job['token'])
        self.assertEqual(c.project,before);self.assertTrue(c.state()['can_redo']);self.assertTrue(c.accepts(job['token']))
        with self.assertRaises(m.ProjectError):c.apply_batch(dict(sources=[],materials=[material()],warnings=[]),job['token'])
        self.assertEqual(c.project,before)

    def test_cancel_stale_and_repeat_apply_no_library_or_history(self):
        c=w.Controller(project());combo=w.combine(c.project,['A1','A1']);batch=dict(sources=[],materials=[combo],warnings=[])
        job=c.capture_job('COMBINE',dict(kind='draft',snapshot=combo))
        self.assertTrue(c.cancel_job(job['token']));self.assertFalse(c.apply_batch(batch,job['token'])['changed'])
        job=c.capture_job('COMBINE');c.edit('set_melody_only',value=True);c.undo()
        self.assertFalse(c.apply_batch(batch,job['token'])['changed'])
        job=c.capture_job('COMBINE');self.assertTrue(c.apply_batch(batch,job['token'])['changed'])
        self.assertFalse(c.apply_batch(batch,job['token'])['changed']);self.assertEqual(len(c.project['materials']),2)

    def test_noop_completion_does_not_invalidate_another_request(self):
        c=w.Controller(project());first=c.capture_job('COMBINE');second=c.capture_job('AUDITION',dict(kind='material',id='A1'))
        self.assertFalse(c.apply_batch(dict(sources=[],materials=[],warnings=[]),first['token'])['changed'])
        self.assertFalse(c.accepts(first['token']));self.assertTrue(c.accepts(second['token']))
        self.assertFalse(c.state()['can_undo'])

    def test_narrow_commit_cannot_replace_protection_or_position(self):
        c=w.Controller(manual_bridge());before=c.project
        malicious=copy.deepcopy(before);malicious['protections']=[];malicious['placements']=[];malicious['records']=[]
        with self.assertRaises(m.ProjectError):c.session.commit(malicious)
        self.assertEqual(c.project,before)

    def test_p0_load_preserves_hash_save_and_first_edit_upgrades_once(self):
        p=project();p['contract_rev']='curve-workflow-v2-r3-p0';before=m.fingerprint(p)
        with tempfile.TemporaryDirectory() as tmp:
            path=store.save(store.new_bundle(p),Path(tmp)/'p0.json')
            c=w.Controller();c.load(path)
            self.assertEqual(m.fingerprint(c.project),before);self.assertTrue(c.state()['is_saved'])
            saved=c.save_snapshot(Path(tmp)/'same.json');self.assertEqual(store.load(saved)['bundle']['project'],p)
            c.edit('place',material_id='A1',start_tick=0);self.assertEqual(c.project['contract_rev'],m.CONTRACT_REV);self.assertFalse(c.state()['is_saved'])
            c.undo();self.assertEqual(c.project,p);self.assertTrue(c.state()['is_saved'])

    def test_invalid_open_and_autosave_failure_preserve_state_and_token(self):
        c=w.Controller(project());c.edit('place',material_id='A1',start_tick=0);before=c.project
        token=c.capture_job('AUDITION',dict(kind='material',id='A1'))['token']
        with tempfile.TemporaryDirectory() as tmp:
            good=store.save(store.new_bundle(project()),Path(tmp)/'good.json');bad=Path(tmp)/'bad.json';bad.write_text('{bad')
            with self.assertRaises(ValueError):c.load(bad)
            self.assertEqual(c.project,before)
            with patch.object(c,'save_snapshot',side_effect=OSError('unwritable')):
                for action in (lambda:c.new(),lambda:c.load(good),lambda:c.autosave_if_needed()):
                    with self.assertRaises(OSError):action()
                    self.assertEqual(c.project,before);self.assertTrue(c.accepts(token));self.assertTrue(c.state()['can_undo'])

    def test_empty_new_does_not_claim_autosave(self):
        c=w.Controller()
        with patch.object(c,'save_snapshot',side_effect=AssertionError('should not save')):
            self.assertIsNone(c.autosave_if_needed());c.new()
        self.assertFalse(c.state()['is_saved'])

    def test_save_then_undo_to_loaded_content_still_requires_autosave(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            a = store.save(store.new_bundle(project()), folder / 'a.json')
            c = w.Controller(); c.load(a)
            c.edit('place', material_id='A1', start_tick=0)
            c.save_snapshot(folder / 'b.json')
            c.undo()
            self.assertFalse(c.state()['is_saved'])
            before = c.project
            token = c.capture_job('AUDITION', dict(kind='material', id='A1'))['token']
            with patch.object(c, 'save_snapshot', side_effect=OSError('not writable')) as save:
                for switch in (c.new, lambda: c.load(a), c.autosave_if_needed):
                    with self.assertRaises(OSError): switch()
                    self.assertEqual(c.project, before)
                    self.assertTrue(c.accepts(token))
                    self.assertTrue(c.state()['can_redo'])
                self.assertEqual(save.call_count, 3)

    def test_undo_of_edited_new_project_does_not_claim_it_was_untouched(self):
        c = w.Controller(); c.edit('set_melody_only', value=True); c.undo()
        with patch.object(c, 'save_snapshot', side_effect=OSError('not writable')):
            with self.assertRaises(OSError): c.new()
        self.assertTrue(c.state()['can_redo'])

    def test_history_metadata_and_aliases_are_protected_by_facade_export(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); generated = folder / 'history'; generated.mkdir()
            (generated / 'composition.mid').write_bytes(b'MIDI actual')
            metadata = generated / 'report.json'; metadata.write_bytes(b'original metadata')
            nested = generated / 'source'; nested.mkdir()
            resource = nested / 'snapshot.json'; resource.write_bytes(b'original snapshot')
            report = dict(mode='story', report=dict(output_directory=str(generated), duration_seconds=2, bars=1))
            path = studio_model.save_project(studio_model.materials.new_pool(), None,
                [dict(emotion='calm', start=.3, end=.5)], [report], path=folder / 'old.json')
            c = w.Controller(); c.load(path); row = c.history_items()[0]
            candidates = [metadata, resource]
            symlink = folder / 'metadata-link'
            try:
                symlink.symlink_to(metadata); candidates.append(symlink)
            except OSError:
                pass  # Windows can require a privilege for creating symlinks.
            hardlink = folder / 'metadata-hardlink'; os.link(metadata, hardlink)
            candidates.append(hardlink)
            for target in candidates:
                with self.assertRaises(ValueError): c.export_history(row['id'], 'mid', target)
            self.assertEqual(metadata.read_bytes(), b'original metadata')
            self.assertEqual(resource.read_bytes(), b'original snapshot')
            self.assertEqual((generated / 'composition.mid').read_bytes(), b'MIDI actual')
            self.assertEqual(c.history_items()[0], row)

    def test_job_target_is_immutable_and_bad_target_does_not_leak_requests(self):
        c=w.Controller(project());job=c.capture_job('AUDITION',dict(kind='material',id='A1'))
        job['snapshot']['target']['notes'].clear();self.assertTrue(c.project['materials'][0]['notes'])
        self.assertTrue(c.accepts(job['token']))
        with self.assertRaises(m.ProjectError):c.capture_job('AUDITION',dict(kind='material',id='missing'))
        c.edit('place',material_id='A1',start_tick=0);self.assertFalse(c.accepts(job['token']))

    def test_readonly_history_per_format_export_and_selection_snapshot_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'composition.mid').write_bytes(b'actual version MIDI')
            report=dict(mode='story',report=dict(output_directory=str(folder),duration_seconds=2,bars=1))
            path=studio_model.save_project(studio_model.materials.new_pool(),None,[dict(emotion='calm',start=.3,end=.5)],[report],path=folder/'old.json')
            c=w.Controller();c.load(path);row=c.history_items()[0]
            self.assertEqual(c.state()['access_mode'],'legacy_readonly');self.assertIsNone(c.project)
            self.assertEqual(row['availability'],dict(wav=False,mid=True,mmp=False))
            for call in (lambda:c.edit('resize',grid_count=2),lambda:c.capture_job('IMPORT'),lambda:c.save_snapshot()):
                with self.assertRaises(m.ProjectError):call()
            exported=c.export_history(row['id'],'mid',folder/'中文 space export.mid')
            self.assertEqual(exported.read_bytes(),(folder/'composition.mid').read_bytes())
            with self.assertRaises(ValueError):c.export_history(row['id'],'mid',folder/'composition.mid')
            self.assertEqual(c.history_items()[0],row)

    def test_real_midi_import_preserves_leading_rest_cross_block_and_short_tail(self):
        import mido
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'中文 source.mid'
            midi=mido.MidiFile(ticks_per_beat=480);track=mido.MidiTrack();midi.tracks.append(track)
            track.extend([mido.Message('note_on',note=60,velocity=75,time=480),
                mido.Message('note_off',note=60,time=1920),
                mido.Message('note_on',note=64,velocity=80,time=0),
                mido.Message('note_off',note=64,time=240)])
            midi.save(path)
            batch=w.prepare_import(path);source=batch['sources'][0]
            self.assertEqual(source['length_ticks'],2640)
            self.assertEqual(source['notes'][0]['start_tick'],480)
            blocks=[i for i in batch['materials'] if i['kind']=='block' and i['phrase_id'] is None and i['generation'] is None]
            self.assertEqual([i['length_ticks'] for i in blocks],[1920,720])
            a,b=blocks[0]['notes'][0],blocks[1]['notes'][0]
            self.assertEqual(a['origin'],b['origin'])
            self.assertEqual(a['slice']['parent_emission_id'],b['slice']['parent_emission_id'])
            self.assertEqual(a['duration_tick'],1440);self.assertEqual(b['slice']['offset_tick'],1440)
            c=w.Controller();token=c.capture_job('IMPORT')['token'];c.apply_batch(batch,token)
            m.validate(c.project)
            candidates=[i for i in c.project['materials'] if i['generation'] and i['phrase_id'] is None]
            self.assertLessEqual(len(candidates),3)
            self.assertEqual(len({__import__('curve_melody').music_signature(i) for i in candidates}),len(candidates))
            with tempfile.TemporaryDirectory() as saved:
                out=c.save_snapshot(Path(saved)/'snapshot.json');d=w.Controller();d.load(out)
                self.assertEqual(c.project,d.project);self.assertTrue(d.state()['is_saved'])

    def test_actual_import_rejects_overlap_instead_of_truncating_original(self):
        import mido
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'overlap.mid';midi=mido.MidiFile();track=mido.MidiTrack();midi.tracks.append(track)
            track.extend([mido.Message('note_on',note=60,velocity=75),
                mido.Message('note_on',note=64,velocity=75,time=120),
                mido.Message('note_off',note=60,time=120),
                mido.Message('note_off',note=64,time=120)])
            midi.save(path)
            with self.assertRaises(m.ProjectError) as exc:w.prepare_import(path)
            self.assertEqual(exc.exception.code,'MONOPHONIC_IMPORT_REQUIRED')

    def test_actual_continuous_slices_tie_but_repeat_or_other_source_does_not(self):
        item=material(length=480)
        n=item['notes'][0];n.update(duration_tick=240,slice=dict(parent_emission_id='held',offset_tick=0,parent_duration_tick=480))
        second=copy.deepcopy(n);second.update(id='n2',start_tick=240)
        second['slice']['offset_tick']=240;item['notes']=[n,second]
        tied=curve_audition.playable_notes(item);self.assertEqual(len(tied),1);self.assertEqual(tied[0]['duration_tick'],480)
        other=copy.deepcopy(item);other['notes'][1]['origin']['source_id']='OTHER'
        self.assertEqual(len(curve_audition.playable_notes(other)),2)
        repeat=copy.deepcopy(item);repeat['notes'][1]['slice']['offset_tick']=0
        self.assertEqual(len(curve_audition.playable_notes(repeat)),2)
        self.assertEqual(item['notes'][0]['duration_tick'],240)

    def test_unrepresentable_audition_is_explicit_before_lmms(self):
        item=material();item['notes'][0].update(start_tick=1,duration_tick=239)
        with patch('curve_audition.subprocess.run',side_effect=AssertionError('must not render')):
            with self.assertRaises(m.ProjectError) as exc:curve_audition.render_audition(item)
        self.assertEqual(exc.exception.code,'OUTPUT_TIME_UNREPRESENTABLE')

    def test_audition_fingerprint_has_real_velocity_rhythm_and_tail_identity(self):
        item=material();fp=curve_audition.audition_fingerprint(item)
        copy_item=copy.deepcopy(item);copy_item.update(id='new',label='new')
        self.assertEqual(curve_audition.audition_fingerprint(copy_item),fp)
        copy_item['notes'][0]['velocity']+=1
        self.assertNotEqual(curve_audition.audition_fingerprint(copy_item),fp)


class AuditionOwnershipTests(unittest.TestCase):
    def sliced_phrase(self):
        item=material(length=480);item['kind']='phrase'
        item['provenance']['key_context']=dict(tonic=0,mode='major',confidence=1.,method='fixture')
        first=item['notes'][0]
        first.update(duration_tick=240,slice=dict(parent_emission_id='held',offset_tick=0,parent_duration_tick=480))
        second=copy.deepcopy(first);second.update(id='second',start_tick=240,velocity=37)
        second['slice']['offset_tick']=240;item['notes']=[first,second]
        return item

    def test_phrase_tie_uses_first_velocity_and_does_not_mutate_source(self):
        item=self.sliced_phrase();before=copy.deepcopy(item)
        emitted=curve_audition.playable_notes(item)
        self.assertEqual([(n['start_tick'],n['duration_tick'],n['velocity']) for n in emitted],[(0,480,item['notes'][0]['velocity'])])
        self.assertEqual(item,before)
        unsliced=copy.deepcopy(item);unsliced['notes']=[dict(copy.deepcopy(item['notes'][0]),duration_tick=480,slice=None)]
        self.assertEqual(curve_audition.audition_fingerprint(item),curve_audition.audition_fingerprint(unsliced))

    def test_independent_complementary_slices_and_nested_repeats_retrigger(self):
        from test_curve_melody import combination
        phrase=self.sliced_phrase();phrase['notes'][1]['velocity']=phrase['notes'][0]['velocity']
        parts=[]
        for index,note in enumerate(phrase['notes']):
            leaf=copy.deepcopy(phrase);leaf.update(id='part'+str(index),length_ticks=240)
            leaf['notes']=[dict(copy.deepcopy(note),start_tick=0)];parts.append(leaf)
        combo=combination('combo',parts);before=copy.deepcopy(combo)
        self.assertEqual([(n['start_tick'],n['duration_tick']) for n in curve_audition.playable_notes(combo)],[(0,240),(240,240)])
        self.assertNotEqual(curve_audition.audition_fingerprint(combo),curve_audition.audition_fingerprint(phrase))
        nested=combination('nested',[combo,combo])
        self.assertEqual([n['start_tick'] for n in curve_audition.playable_notes(nested)],[0,240,480,720])
        self.assertEqual(combo,before)
        renamed=copy.deepcopy(nested)
        def rename(node):
            node['id']='renamed-'+node['id'];node['label']='renamed'
            for n in node['notes']:n['id']='arbitrary-'+n['id']
            for child in node['children']:
                child['occurrence_id']='new-'+child['occurrence_id'];rename(child['snapshot'])
        rename(renamed)
        self.assertEqual(curve_audition.audition_fingerprint(nested),curve_audition.audition_fingerprint(renamed))

    def test_derived_phrase_is_one_performance_despite_combination_provenance(self):
        item=self.sliced_phrase();item['provenance']['component_snapshots']=['old-combo']
        self.assertEqual(len(curve_audition.playable_notes(item)),1)

    def test_bad_flattening_source_slice_and_occurrence_identity_reject(self):
        from test_curve_melody import combination
        item=self.sliced_phrase();combo=combination('combo',[item,item])
        bads=[]
        for field,value in [('pitch',61),('lineage',['foreign']),('origin',None)]:
            bad=copy.deepcopy(combo);bad['notes'][0][field]=value;bads.append(bad)
        bad=copy.deepcopy(combo);bad['children'][1]['occurrence_id']=bad['children'][0]['occurrence_id'];bads.append(bad)
        bad=copy.deepcopy(combo);bad['children'][1]['offset_tick']-=1;bads.append(bad)
        bad=copy.deepcopy(combo);bad['children'][0]['snapshot']['notes'][0]['slice']['offset_tick']=400;bads.append(bad)
        bad=copy.deepcopy(combo);bad['children'][0]['snapshot']=bad;bads.append(bad)
        bad=copy.deepcopy(item);bad['children']=[combo['children'][0]];bads.append(bad)
        bads.extend([None,[],{'id':'incomplete'}])
        for bad in bads:
            with self.subTest(case=type(bad).__name__):
                with self.assertRaises(m.ProjectError):curve_audition.playable_notes(bad)

    def test_source_and_rest_and_changed_slice_parent_remain_explicit(self):
        item=self.sliced_phrase()
        src={k:copy.deepcopy(item[k]) for k in ('id','label','length_ticks','notes','provenance')}
        self.assertEqual(len(curve_audition.playable_notes(src)),1)
        for field,value in [('parent_emission_id','other'),('parent_duration_tick',720),('offset_tick',0)]:
            other=copy.deepcopy(item);other['notes'][1]['slice'][field]=value
            self.assertEqual(len(curve_audition.playable_notes(other)),2)
        src['notes']=[]
        self.assertEqual(curve_audition.playable_notes(src),[])
        with self.assertRaises(m.ProjectError) as caught:curve_audition.audition_fingerprint(src)
        self.assertEqual(caught.exception.code,'EMPTY_MATERIAL')

    def test_public_3840_combo_matches_actual_final_without_renderer(self):
        import mido
        import curve_final as final
        from test_curve_boundary_music import request
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'held.mid';native=mido.MidiFile(ticks_per_beat=480);track=mido.MidiTrack();native.tracks.append(track)
            track.extend([mido.Message('note_on',note=60,velocity=80,time=0),mido.Message('note_off',note=60,time=3840)]);native.save(path)
            c=w.Controller();job=c.capture_job('IMPORT');c.apply_batch(w.prepare_import(path),job['token'])
            blocks=[i for i in c.project['materials'] if i['kind']=='block' and i['phrase_id'] is None and i['generation'] is None]
            self.assertEqual([i['length_ticks'] for i in blocks],[1920,1920])
            combo=w.combine(c.project,[i['id'] for i in blocks]);job=c.capture_job('COMBINE')
            c.apply_batch(dict(sources=[],materials=[combo],warnings=[]),job['token']);c.edit('resize',grid_count=2)
            c.edit('place',material_id=combo['id'],start_tick=0);before=copy.deepcopy(c.project)
            captured=request(c.project);auth=final.make_request(captured['connection_ref'],captured['token'])
            final.validate_request(auth);emitted,_=final.joined_events(auth['actual_layout']['notes'],auth['actual_layout']['emission_ledger'])
            projection=lambda notes:[(n['pitch'],n['start_tick'],n['duration_tick']) for n in notes]
            self.assertEqual(projection(curve_audition.playable_notes(combo)),projection(emitted))
            self.assertEqual(len(emitted),2);self.assertEqual(c.project,before)
            self.assertEqual(curve_audition.RENDERER_VERSION,'curve-neutral-lmms-v2')

    def test_old_v1_files_are_not_rewritten_by_v2_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old-asset.json';old=b'{"renderer_version":"curve-neutral-lmms-v1","fingerprint":"legacy"}'
            path.write_bytes(old);item=self.sliced_phrase()
            curve_audition.audition_fingerprint(item);curve_audition.playable_notes(item)
            self.assertEqual(path.read_bytes(),old)


if __name__=='__main__':unittest.main()
