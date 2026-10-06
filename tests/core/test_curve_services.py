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


if __name__=='__main__':unittest.main()
