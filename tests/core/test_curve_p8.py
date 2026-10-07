"""P8 format isolation and recovery gates. Synthetic PCM is a fault fixture only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import curve_final as final
import curve_final_render as audio
import curve_project as model
import curve_recommendations as rec
import curve_workflow as workflow
import curve_boundary_music as music
from export_safe import atomic_export
from test_curve_final import boundary_request, simulated_render
from test_curve_bridges import complete


def score(drum=False):
    controller=complete()
    if drum:
        controller.edit('set_intensity',points=[dict(tick=0,level=.75),dict(tick=controller.project['total_ticks'],level=.75)])
        controller.edit('set_emotion',placement_ids=['use1'],emotion='crisis')
    request=boundary_request(controller=controller)
    plan=final.make_plan(request,music.plan_boundaries(request))
    return final.make_score(request,plan,final.apply_boundaries(request,plan))


class OutputGateTests(unittest.TestCase):
    def test_temporary_copy_must_match_registered_bytes_before_replacing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';target=root/'target'
            source.write_bytes(b'original');expected=hashlib.sha256(source.read_bytes()).hexdigest()
            target.write_bytes(b'old export');source.write_bytes(b'changed!')
            with self.assertRaises(OSError):atomic_export(source,target,[],expected_sha256=expected)
            self.assertEqual(target.read_bytes(),b'old export')
            self.assertEqual(source.read_bytes(),b'changed!')
            self.assertFalse(list(root.glob('.emoblocks-export-*')))
            source.write_bytes(b'original');atomic_export(source,target,[],expected_sha256=expected)
            self.assertEqual(target.read_bytes(),b'original')

    def test_each_encoded_format_is_authenticated_without_opening_other_format(self):
        value=score()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);audio.export_score(value,root)
            files={k:audio._file(root/name) for k,name in [('mid','composition.mid'),('mmp','composition.mmp')]}
            (root/'composition.mmp').unlink()
            audio.validate_outputs(value,files,required_formats=('mid',))
            audio.export_score(value,root);files['mmp']=audio._file(root/'composition.mmp');(root/'composition.mid').unlink()
            audio.validate_outputs(value,files,required_formats=('mmp',))
            xml=ET.parse(root/'composition.mmp');xml.find('head').set('masterpitch','12');xml.write(root/'composition.mmp')
            with self.assertRaises(model.ProjectError):audio.validate_outputs(value,files,required_formats=('mmp',))
            for invalid in [(),('wav',)]:
                with self.assertRaises(model.ProjectError):audio.validate_outputs(value,files,required_formats=invalid)

    def test_factory_content_is_pinned_and_midi_does_not_depend_on_factory_io(self):
        import engine
        value=score(drum=True)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);resources=root/'factory'/'samples'/'drums';resources.mkdir(parents=True)
            authority={}
            for drum in audio.STOCK_RESOURCES:
                data=('unit fixture '+drum).encode();(resources/drum).write_bytes(data)
                authority[drum]=(len(data),hashlib.sha256(data).hexdigest())
            with patch.object(audio,'STOCK_RESOURCES',authority),patch.object(engine,'sample_path',side_effect=lambda _,name:resources/name):
                audio.export_score(value,root)
                files={k:audio._file(root/name) for k,name in [('mid','composition.mid'),('mmp','composition.mmp')]}
                audio.validate_outputs(value,files)
                xml=ET.parse(root/'composition.mmp');sampler=xml.find('.//audiofileprocessor')
                drum=sampler.get('src').rsplit('/',1)[-1]
                self.assertEqual(sampler.get('src'),'data:/samples/drums/'+drum)
                original=(resources/drum).read_bytes();(resources/drum).write_bytes(b'x'*len(original))
                with self.assertRaises(model.ProjectError):audio.validate_outputs(value,files,required_formats=('mmp',))
                with patch.object(engine,'sample_path',side_effect=AssertionError('MIDI must not resolve samples')):
                    audio.validate_outputs(value,files,required_formats=('mid',))
                (resources/drum).write_bytes(original)
                # A same-name absolute copy is not the new authenticated URI profile.
                sampler.set('src',str(resources/drum));xml.write(root/'composition.mmp')
                with self.assertRaises(model.ProjectError):audio.validate_outputs(value,files,required_formats=('mmp',))

    def test_history_mode_and_format_query_is_pure_and_export_uses_same_score(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(audio,'render',side_effect=simulated_render(directory)):
            controller=complete();captured=controller.capture_recommendations()
            out=rec.prepare_recommendations(captured['request'],source_facts=controller._bundle.get('final_facts'),on_progress=lambda e:controller.record_recommendation_progress(captured['token'],e))
            self.assertTrue(controller.finish_recommendations(captured['token'],out))
            candidate=out['candidates'][0];controller.apply_recommendation(candidate['id'])
            result=controller.history_items()[0];before=copy.deepcopy(controller.project)
            undo=copy.deepcopy(controller.session._undo);saved=controller.state()['is_saved'];staging=controller.state()['staging_dirty']
            state=controller.history_output_state(result['id'])
            self.assertTrue(all(state['availability'].values()))
            self.assertEqual(state['score_ref'],result['score_ref'])
            self.assertEqual(state['renderer_profile'],audio.RENDERER)
            missing='arranged' if state['mode']=='melody_only' else 'melody_only'
            unavailable=controller.history_output_state(result['id'],missing)
            self.assertFalse(any(unavailable['availability'].values()))
            self.assertEqual(unavailable['errors']['wav']['code'],'MODE_NOT_READY')
            source=Path(candidate['assets']['final']['files']['wav']['path']);source.unlink()
            state=controller.history_output_state(result['id'])
            self.assertEqual(state['availability'],dict(wav=False,mid=True,mmp=True))
            destination=Path(directory)/'中文 文件.mid';controller.export_history(result['id'],'mid',destination)
            self.assertEqual(destination.read_bytes(),Path(candidate['assets']['final']['files']['mid']['path']).read_bytes())
            self.assertEqual(controller.project,before);self.assertEqual(controller.session._undo,undo)
            self.assertEqual(controller.state()['is_saved'],saved);self.assertEqual(controller.state()['staging_dirty'],staging)

    def test_new_capture_cannot_accept_old_profile_even_when_bytes_are_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=complete();cap=controller.capture_recommendations();fake=simulated_render(directory)
            def old(score,candidate_ref,version=1,should_cancel=None,on_progress=None):
                asset=fake(score,candidate_ref,version,should_cancel,on_progress)
                root=Path(asset['files']['mid']['path']).parent;audio.export_score(score,root,profile=audio.LEGACY_RENDERER)
                for key in ('mid','mmp'):asset['files'][key]=audio._file(root/('composition.'+key))
                asset['renderer_version']=audio.LEGACY_RENDERER;asset['asset_fingerprint']=audio.asset_fingerprint(asset);asset['id']=asset['asset_fingerprint']
                return asset
            with patch.object(audio,'render',side_effect=old):out=rec.prepare_recommendations(cap['request'])
            self.assertTrue(out['candidates'])
            rec.validate_outcome(cap['request'],out)  # Existing v1 pairs remain readable.
            with self.assertRaises(model.ProjectError):controller.finish_recommendations(cap['token'],out)
            before=copy.deepcopy(out);candidate=out['candidates'][0];asset=candidate['assets']['comparison']
            asset['renderer_version']=audio.RENDERER;asset['asset_fingerprint']=audio.asset_fingerprint(asset);asset['id']=asset['asset_fingerprint']
            with self.assertRaises(model.ProjectError):rec.validate_outcome(cap['request'],out)
            self.assertNotEqual(out,before)


class LegacyLayoutTests(unittest.TestCase):
    def test_original_request_remains_pure_and_tampered_legacy_content_is_rejected(self):
        request=boundary_request();request['algorithm_version']=final.LEGACY_ALGORITHM
        final.validate_request(request)
        for field in ('notes','emission_ledger','segments'):
            altered=copy.deepcopy(request)
            if field=='notes':altered['actual_layout'][field][0]['pitch']+=1
            elif field=='emission_ledger':altered['actual_layout'][field][0]['performance_id']='unrelated'
            else:altered['actual_layout'][field][0]['emotion']='crisis'
            altered['layout_fingerprint']=model.digest('emoblocks.final-layout.v1',altered['actual_layout'])
            with self.subTest(field=field),self.assertRaises(model.ProjectError):final.validate_request(altered)

    def test_one_consistent_global_order_is_required_not_a_different_order_per_span(self):
        rows=[dict(owner=pid,stage='connection',performance_id=pid,priority=1,start_tick=0,end_tick=20) for pid in ('a','b')]
        def replay(value,retained_order=None,rows_capture=None):
            if rows_capture is not None:rows_capture.extend(copy.deepcopy(rows))
            winner=(retained_order or ['a','b'])[0]
            return dict(segments=[dict(start_tick=0,end_tick=20,owner_ref=dict(id=winner),kind='connection',performance_id=winner)])
        good=replay(None,retained_order=['b','a'])
        bad=dict(segments=[dict(good['segments'][0],end_tick=10),dict(good['segments'][0],start_tick=10,owner_ref=dict(id='a'),performance_id='a')])
        rows[0]['end_tick']=10;rows[1]['end_tick']=20
        # Add a second authentic overlapping row so the two cells impose a cycle.
        rows.extend([dict(owner='a',stage='connection',performance_id='a',priority=1,start_tick=10,end_tick=20)])
        with patch.object(final,'_layout',side_effect=replay):
            self.assertEqual(final._legacy_layout({},good),good)
            with self.assertRaises(model.ProjectError):final._legacy_layout({},bad)

    def test_new_layout_and_old_validation_do_not_depend_on_python_hash_seed(self):
        request=boundary_request()
        code="""import json,sys
from emoblocks_bootstrap import configure
configure()
import curve_final as f,curve_project as m
r=json.load(open(sys.argv[1]));f.validate_request(r)
print(m.digest('probe',f._layout(r['connection_ref'])))
"""
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'request.json';path.write_text(json.dumps(request))
            for version in (final.ALGORITHM,final.LEGACY_ALGORITHM):
                request['algorithm_version']=version;path.write_text(json.dumps(request))
                answers=[]
                for seed in ('1','7','21'):
                    env=dict(os.environ,PYTHONHASHSEED=seed)
                    answers.append(subprocess.check_output([sys.executable,'-c',code,str(path)],cwd=Path(__file__).resolve().parents[2],env=env,text=True).strip())
                self.assertEqual(len(set(answers)),1)
