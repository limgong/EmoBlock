"""Mapped P2 UI tests with the frozen injected Facade, no render/device calls."""
import copy
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import curve_project as model
import curve_ui


def fixture(extra=0):
    project = model.new_project()
    source = dict(id='source',label='原始来源 中文 MIDI',length_ticks=4080,provenance=dict(track_id='track',path='missing.mid'),notes=[])
    for ident,start,duration,pitch in [('long',1800,300,60),('tail',4000,80,64)]:
        source['notes'].append(dict(id=ident,pitch=pitch,start_tick=start,duration_tick=duration,velocity=80,
            origin=dict(source_id='source',track_id='track',source_note_id=ident),lineage=[],slice=None))
    project['sources'] = [source]
    phrase = dict(id='phrase',label='完整乐句 中文 original',kind='phrase',length_ticks=4080,
                  notes=copy.deepcopy(source['notes']),provenance=dict(source_id='source'),
                  generation=None,phrase_id=None,children=[])
    project['materials'] = [phrase]
    for index,(start,end) in enumerate([(0,1920),(1920,3840),(3840,4080)]):
        notes = []
        for original in source['notes']:
            a,b = max(start,original['start_tick']),min(end,original['start_tick']+original['duration_tick'])
            if b>a:
                note = dict(copy.deepcopy(original),id=f'{original["id"]}:{index}',start_tick=a-start,duration_tick=b-a,
                    slice=dict(parent_emission_id=original['id'],offset_tick=a-original['start_tick'],parent_duration_tick=original['duration_tick']))
                notes.append(note)
        project['materials'].append(dict(id='child'+str(index),label='四拍子块 '+str(index+1),kind='block',
            length_ticks=end-start,notes=notes,provenance=dict(source_id='source',relative_start_tick=start,source_start_tick=start),
            generation=None,phrase_id='phrase',children=[]))
    leaf = copy.deepcopy(project['materials'][2]);leaf.update(id='block',label='独立分块',phrase_id=None)
    project['materials'].append(leaf)
    for i in range(extra):
        material = copy.deepcopy(leaf);material.update(id='extra'+str(i),label='长名称素材 '+str(i)+' · '+('可查看全文 '*12))
        project['materials'].append(material)
    model.validate(project)
    return project


class FakeController:
    """Only the documented Facade is consumed by the application."""
    def __init__(self, project=None):
        self._project = copy.deepcopy(project or fixture())
        self._undo = [];self._redo = [];self._requests = {};self._revision = 0
        self._saved = model.fingerprint(self._project)
        self.readonly = False
        self.histories = []
        self.calls = []
        self.save_error = None
        self.main_thread = threading.get_ident()

    def state(self):
        return dict(access_mode='legacy_readonly' if self.readonly else 'editable',
            project=None if self.readonly else copy.deepcopy(self._project),capabilities=dict(edit=not self.readonly,plan=False),
            is_saved=self._saved==model.fingerprint(self._project),saved_path=None,
            can_undo=bool(self._undo),can_redo=bool(self._redo),memory_info=None)

    def _set(self, project):
        if self.readonly:raise ValueError('旧工程只读')
        model.validate(project)
        if project==self._project:return False
        self._undo.append(copy.deepcopy(self._project));self._redo.clear();self._project=copy.deepcopy(project)
        self._revision+=1;self._requests.clear()
        return True

    def edit(self, action, **args):
        self.calls.append((action,copy.deepcopy(args)))
        return self._set(model.edit(self._project,action,**args))

    def undo(self):
        if not self._undo:return False
        self._redo.append(self._project);self._project=self._undo.pop();self._revision+=1;self._requests.clear()
        return True

    def redo(self):
        if not self._redo:return False
        self._undo.append(self._project);self._project=self._redo.pop();self._revision+=1;self._requests.clear()
        return True

    def capture_job(self, kind, target=None):
        if self.readonly:raise ValueError('旧工程只读')
        ident = 'request'+str(len(self.calls))+'-'+str(time.monotonic_ns())
        token = dict(request_id=ident,edit_revision=self._revision,input_fingerprint=model.fingerprint(self._project))
        self._requests[ident]=copy.deepcopy(token)
        value=None
        if target:
            if target['kind']=='draft':value=target['snapshot']
            elif target['kind']=='placement':
                placement=next(p for p in self._project['placements'] if p['id']==target['id'])
                value=placement['emotion_variant'] or placement['base_snapshot']
            else:
                value=next(v for v in self._project['sources' if target['kind']=='source' else 'materials'] if v['id']==target['id'])
        self.calls.append(('capture',kind))
        return dict(token=copy.deepcopy(token),snapshot=dict(project=copy.deepcopy(self._project),target=copy.deepcopy(value)))

    def accepts(self, token):
        return self._requests.get(token['request_id'])==token and token['edit_revision']==self._revision

    def cancel_job(self, token):
        return self._requests.pop(token['request_id'],None) is not None

    def finish_job(self, token):
        return self.cancel_job(token)

    def apply_batch(self, batch, token):
        assert threading.get_ident()==self.main_thread
        if not self.accepts(token):raise ValueError('STALE_SNAPSHOT')
        project=copy.deepcopy(self._project)
        project['sources'].extend(copy.deepcopy(batch['sources']))
        project['materials'].extend(copy.deepcopy(batch['materials']))
        changed=self._set(project)
        self.finish_job(token)
        self.calls.append(('apply',copy.deepcopy(batch)))
        return dict(changed=changed,added_source_ids=[s['id'] for s in batch['sources']],added_material_ids=[m['id'] for m in batch['materials']])

    def history_items(self):return copy.deepcopy(self.histories)
    def export_history(self, result_id, format_, destination):
        self.calls.append(('export',(result_id,format_,destination)));return Path(destination)
    def autosave_if_needed(self):
        if self.save_error:raise self.save_error
        if not self.state()['is_saved']:
            self._saved=model.fingerprint(self._project)
            self.calls.append(('autosave',None));return Path('/tmp/fake-snapshot.json')
    def save_snapshot(self, path=None):
        if self.save_error:raise self.save_error
        self._saved=model.fingerprint(self._project);return Path('/tmp/fake-snapshot.json')
    def new(self, grid_count=8):
        self.autosave_if_needed();self._project=model.new_project(grid_count);self._revision+=1;self._requests.clear()
        self._undo.clear();self._redo.clear();self.readonly=False;self.histories=[];self._saved=None
    def load(self, path):
        if path=='invalid':raise ValueError('损坏的快照')
        self.autosave_if_needed();self._revision+=1;self._requests.clear();self.readonly=True


class FakePlayer:
    def __init__(self):self.calls=[];self.mode='closed';self.position=0.
    def play(self,path,start=0.,end=None):self.calls.append((str(path),start,end));self.position=start;self.mode='playing';return 4.5
    def status(self):return self.position,self.mode
    def pause(self):self.mode='paused'
    def resume(self):self.mode='playing'
    def close(self):self.mode='closed';self.position=0.


class FakeDrop:
    def __init__(self,root,callback):pass
    def close(self):pass


class FakeProvider:
    def __init__(self, wav):self.wav=wav;self.gate=None;self.methods=[];self.worker_threads=[]
    def render_audition(self, snapshot,bpm=120):
        self.worker_threads.append(threading.get_ident())
        if self.gate and not self.gate.wait(5):raise RuntimeError('test gate timeout')
        return dict(wav_path=str(self.wav),midi_path='fake.mid',mmp_path='fake.mmp',body_ticks=snapshot['length_ticks'],
                    body_seconds=snapshot['length_ticks']/960,audio_seconds=4.5,fingerprint='fake',renderer_version='fixture-only')
    def prepare_generation(self, project,material_id,method,seed=31,parameters=None):
        self.methods.append(method)
        material=copy.deepcopy(next(m for m in project['materials'] if m['id']==material_id))
        material.update(id='derived-'+method,label='新旋律 '+method,phrase_id=None,generation=dict(method=method))
        for note in material['notes']:note['pitch']+=1
        return dict(sources=[],materials=[material],warnings=[])
    def prepare_import(self, path,track=0,seed=31):
        if path=='invalid.mid':raise ValueError('导入失败')
        project=fixture()
        return dict(sources=project['sources'],materials=project['materials'],warnings=[])
    def combine(self, project,inputs,label='组合素材'):
        parts=[];notes=[];offset=0
        for i,value in enumerate(inputs):
            m=copy.deepcopy(value if isinstance(value,dict) else next(m for m in project['materials'] if m['id']==value))
            parts.append(dict(occurrence_id='occ'+str(i),offset_tick=offset,snapshot=m))
            notes.extend(dict(n,id='combined:'+str(i)+':'+n['id'],start_tick=n['start_tick']+offset) for n in m['notes'])
            offset+=m['length_ticks']
        return dict(id='combined'+str(time.monotonic_ns()),label=label,kind='combination',length_ticks=offset,
                    notes=notes,provenance={},generation=None,phrase_id=None,children=parts)


class MappedUIFixture(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.wav=Path(self.folder.name)/'fixture.wav'
        with wave.open(str(self.wav),'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000);audio.writeframes(b'\0\0'*36000)
        self.provider=FakeProvider(self.wav)
        self.controller=FakeController(fixture(extra=16))
        for name,value in [('WavePlayer',FakePlayer),('FileDrop',FakeDrop)]:
            patcher=patch.object(curve_ui,name,value);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(curve_ui,'_provider',return_value=self.provider);patcher.start();self.addCleanup(patcher.stop)
        self.root=tk.Tk()
        self.app=curve_ui.CurveApplication(self.root,self.controller)
        self.root.update()
        self.addCleanup(self.cleanup_ui)

    def cleanup_ui(self):
        if self.provider.gate:self.provider.gate.set()
        if self.app.closed:return
        if self.root.winfo_exists():
            self.app.closed=True
            self.root.after_cancel(self.app.timer)
            self.app.cancel_interaction()
            self.app.player.close()
            self.root.destroy()

    def finish_jobs(self):
        deadline=time.monotonic()+5
        while self.app.jobs and time.monotonic()<deadline:
            self.root.update();self.app.drain_jobs();time.sleep(.005)
        self.assertFalse(self.app.jobs,'job did not finish')
        self.root.update()

    def event(self, widget,x,y):
        return SimpleNamespace(widget=widget,x=int(x),y=int(y),x_root=widget.winfo_rootx()+int(x),
                               y_root=widget.winfo_rooty()+int(y),delta=-120,state=0)


class CurveApplicationTests(MappedUIFixture):
    def test_import_source_and_all_children_are_one_atomic_batch(self):
        self.app.new_project()
        before=self.controller.state()['project']
        self.app.import_file('fixture.mid');self.finish_jobs()
        project=self.controller.state()['project']
        self.assertEqual(len(project['sources']),1)
        self.assertIn('child2',{m['id'] for m in project['materials']})
        self.app.undo();self.assertEqual(before,self.controller.state()['project'])
        self.app.import_file('invalid.mid');self.finish_jobs()
        self.assertEqual(before,self.controller.state()['project'])
        self.assertIn('导入失败',self.app.status_text.get())

    def test_ready_selection_and_history_do_not_autoplay(self):
        before=self.controller.state()['project']
        self.app.select_target('material','block')
        self.app.prepare_selected();self.finish_jobs()
        self.assertEqual(self.app.player.calls,[])
        self.assertEqual(self.controller.state()['project'],before)
        self.assertTrue(all(t!=threading.get_ident() for t in self.provider.worker_threads))
        self.assertTrue(self.app.play_selected())
        playing=copy.deepcopy(self.app.playing_target)
        self.app.select_target('material','extra0')
        self.app.prepare_selected();self.finish_jobs()
        self.assertEqual(len(self.app.player.calls),1)
        self.assertEqual(self.app.playing_target,playing)
        self.app.toggle_pause();self.assertEqual(self.app.player.mode,'paused')
        self.app.toggle_pause();self.assertEqual(self.app.player.mode,'playing')

    def test_cancel_and_stale_completion_cannot_cache_or_play(self):
        self.provider.gate=threading.Event()
        self.app.prepare_target('material','block')
        token=next(iter(self.app.jobs.values()))['token']
        self.app.cancel_jobs()
        self.provider.gate.set()
        self.app.messages.put((token,True,self.provider.render_audition(self.app.resolve('material','block'))))
        self.app.drain_jobs()
        self.assertFalse(self.app.ready_assets);self.assertFalse(self.app.player.calls)
        self.provider.gate=threading.Event()
        self.app.prepare_target('material','extra0')
        self.controller.edit('set_melody_only',value=True)
        self.provider.gate.set();self.finish_jobs()
        self.assertFalse(self.app.ready_assets)

    def test_all_six_methods_and_one_batch_undo(self):
        self.app.select_target('material','block')
        for method,label in curve_ui.METHODS:
            self.app.page.method.set(label)
            self.app.derive_selected();self.finish_jobs()
            self.assertIn('derived-'+method,{m['id'] for m in self.controller.state()['project']['materials']})
            self.assertEqual(self.app.selected_material_id,'block')
            self.app.undo()
            self.assertNotIn('derived-'+method,{m['id'] for m in self.controller.state()['project']['materials']})
        self.assertEqual(self.provider.methods,[m for m,_ in curve_ui.METHODS])

    def test_readonly_export_and_failed_switch_preserve_playback(self):
        self.app.prepare_target('material','block');self.finish_jobs();self.app.play_target('material','block')
        playing=copy.deepcopy(self.app.playing_target)
        self.app.safe(lambda:self.app.open_project('invalid'))
        self.assertEqual(self.app.playing_target,playing);self.assertEqual(self.app.player.mode,'playing')
        self.controller.histories=[dict(id='H',label='旧成品',generated_at='',body_seconds=4.,audio_seconds=4.5,
            availability=dict(wav=False,mid=True,mmp=False),paths=dict(wav='missing.wav',mid='existing.mid',mmp='missing.mmp'),edit_fingerprint=None)]
        self.app.open_project('legacy');self.root.update()
        self.assertFalse(self.app.editable)
        self.assertTrue(self.app.page.derive_button.instate(['disabled']))
        self.app.page.history_list.selection_set(0);self.app.history_selected()
        self.assertTrue(self.app.page.export_buttons['wav'].instate(['disabled']))
        self.assertFalse(self.app.page.export_buttons['mid'].instate(['disabled']))
        with patch('curve_ui.filedialog.asksaveasfilename',return_value='/tmp/export.mid'):
            self.app.export_history('mid')
        self.assertIn(('export',('H','mid','/tmp/export.mid')),self.controller.calls)
        self.assertFalse(self.app.edit('place',material_id='block',start_tick=0))

    def test_busy_blocks_edit_and_autosave_failure_does_not_close(self):
        self.provider.gate=threading.Event()
        self.app.prepare_target('material','block')
        before=self.controller.state()['project']
        self.assertFalse(self.app.edit('place',material_id='block',start_tick=0))
        self.assertEqual(before,self.controller.state()['project'])
        self.controller.save_error=OSError('disk full')
        self.assertFalse(self.app.close());self.assertFalse(self.app.closed)
        self.assertTrue(self.app.jobs);self.assertTrue(self.root.winfo_exists())
        self.provider.gate.set();self.finish_jobs()

    def test_seek_keeps_paused_object_and_close_autosaves(self):
        self.app.prepare_target('material','block');self.finish_jobs();self.app.play_target('material','block')
        self.app.toggle_pause()
        before=copy.deepcopy(self.app.playing_target)
        self.app.seek_value.set(1.25);self.app.seek_release()
        self.assertEqual(self.app.player.mode,'paused')
        self.assertEqual(self.app.player.position,1.25)
        self.assertEqual(self.app.playing_target,before)
        self.app.edit('place',material_id='block',start_tick=480)
        self.assertTrue(self.app.close())
        self.assertIn(('autosave',None),self.controller.calls)

    def test_file_selection_cancel_is_inert(self):
        before=self.controller.state()['project']
        with patch('curve_ui.filedialog.askopenfilename',return_value=''):
            self.app.open_project();self.app.import_file()
        self.assertEqual(before,self.controller.state()['project']);self.assertFalse(self.app.jobs)


if __name__=='__main__':unittest.main()
