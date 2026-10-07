"""P8 UI identity/failure behavior. Fixture files are not music/audio evidence."""
import copy
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import curve_ui
import curve_workflow
import curve_project
from test_curve_ui import MappedUIFixture, fixture


class CurveP8HeadlessTests(unittest.TestCase):
    def bare_app(self, controller):
        app = object.__new__(curve_ui.CurveApplication)
        app.controller = controller
        app.jobs = {};app.messages = queue.Queue()
        app.ready_assets = {};app.ready_file_digests = {}
        app.cancel_interaction = Mock();app.tell = Mock();app.refresh = Mock()
        app.playing_target = {'label':'already playing'}
        app.selected_target = ('material','block')
        return app

    def test_thread_start_failure_releases_real_facade_token_and_preserves_music(self):
        controller = curve_workflow.Controller(fixture())
        app = self.bare_app(controller)
        before = copy.deepcopy(controller.state())
        tokens = []
        capture = controller.capture_job
        def captured(*args):
            value = capture(*args);tokens.append(value['token']);return value
        work = Mock();done = Mock()
        with patch.object(controller,'capture_job',side_effect=captured), patch.object(curve_ui.threading.Thread,'start',side_effect=RuntimeError('no thread resource')):
            self.assertFalse(app._start_job('AUDITION',dict(kind='material',id='block'),work,done))
        self.assertFalse(app.jobs)
        self.assertFalse(controller.accepts(tokens[0]))
        self.assertEqual(controller.state(),before)
        self.assertEqual(app.playing_target,{'label':'already playing'})
        self.assertEqual(app.selected_target,('material','block'))
        work.assert_not_called();done.assert_not_called()
        self.assertIn('no thread resource',app.tell.call_args.args[0])
        # Late work cannot revive the consumed token or invoke the callback.
        for stage in ('completion','bridge','connection','recommendation'):
            setattr(app,stage,SimpleNamespace(drain=lambda:None))
        app.messages.put((tokens[0],True,{}));app.drain_jobs()
        done.assert_not_called()

    def test_start_failure_only_removes_its_own_job(self):
        controller=curve_workflow.Controller(fixture());app=self.bare_app(controller)
        other=[]
        def fail():
            captured=controller.capture_job('DERIVE',dict(kind='material',id='block'))
            token=captured['token'];other.append(token)
            app.jobs[token['request_id']]=dict(token=token,kind='DERIVE')
            raise RuntimeError('start failed')
        with patch.object(curve_ui.threading.Thread,'start',side_effect=fail):
            app._start_job('AUDITION',dict(kind='material',id='block'),Mock(),Mock())
        self.assertEqual(list(app.jobs),[other[0]['request_id']])
        self.assertTrue(controller.accepts(other[0]))
        controller.cancel_job(other[0])

    def test_callback_failure_releases_real_token_without_changing_music(self):
        controller=curve_workflow.Controller(fixture());app=self.bare_app(controller)
        captured=controller.capture_job('AUDITION',dict(kind='material',id='block'))
        token=captured['token'];before=copy.deepcopy(controller.state())
        app.jobs[token['request_id']]=dict(kind='AUDITION',token=token,snapshot=captured['snapshot'],done=Mock(side_effect=ValueError('ACK callback failure')))
        for stage in ('completion','bridge','connection','recommendation'):
            setattr(app,stage,SimpleNamespace(drain=lambda:None))
        app.messages.put((token,True,{}));app.drain_jobs()
        self.assertFalse(app.jobs);self.assertFalse(controller.accepts(token))
        self.assertEqual(controller.state(),before)
        self.assertEqual(app.playing_target,{'label':'already playing'})

    def test_cache_profile_and_each_file_byte_change_are_mechanical(self):
        current=['curve-neutral-lmms-v2']
        app=self.bare_app(SimpleNamespace(audition_renderer_profile=lambda:current[0]))
        with tempfile.TemporaryDirectory() as tmp:
            asset=dict(renderer_version=current[0])
            for name in ('wav','midi','mmp'):
                path=Path(tmp)/name;path.write_bytes((name+' unchanged').encode())
                asset[name+'_path']=str(path)
            for field in ('wav_path','midi_path','mmp_path'):
                app._cache_asset('key',asset,current[0]);self.assertIsNotNone(app._ready_asset('key'))
                path=Path(asset[field]);original=path.read_bytes()
                path.write_bytes(b'X'*len(original))  # same length, real content mutation
                self.assertIsNone(app._ready_asset('key'))
                self.assertTrue(path.exists());path.write_bytes(original)
            app._cache_asset('key',asset,current[0]);current[0]='different-profile'
            self.assertIsNone(app._ready_asset('key'))
            self.assertEqual(app.playing_target,{'label':'already playing'})
            self.assertTrue(all(Path(asset[f]).exists() for f in ('wav_path','midi_path','mmp_path')))
            with self.assertRaisesRegex(ValueError,'版本'):
                app._cache_asset('key',asset,'curve-neutral-lmms-v2')
            self.assertFalse(app.ready_assets)


class CurveP8MappedTests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.profile='fixture-p8-profile'
        self.controller.audition_renderer_profile=lambda:self.profile
        self.mid=self.wav.with_suffix('.mid');self.mid.write_bytes(b'fixture MIDI identity')
        self.mmp=self.wav.with_suffix('.mmp');self.mmp.write_bytes(b'fixture MMP identity')
        self.real_prepare=self.provider.render_audition
        def prepare(snapshot,bpm=120):
            result=self.real_prepare(snapshot,bpm)
            result.update(renderer_version=self.profile,midi_path=str(self.mid),mmp_path=str(self.mmp))
            return result
        self.provider.render_audition=prepare

    def invariant(self):
        return copy.deepcopy((self.controller.state(),self.app.selected_target,self.app.playing_target,self.app.player.calls))

    def test_mapped_busy_recovers_with_real_controller(self):
        self.controller=curve_workflow.Controller(fixture())
        self.app.controller=self.controller;self.app.refresh();self.root.update()
        self.app.select_target('material','block');before=self.invariant()
        with patch.object(curve_ui.threading.Thread,'start',side_effect=RuntimeError('mapped start fault')):
            self.app.prepare_selected()
        self.root.update()
        self.assertEqual(self.invariant(),before)
        self.assertFalse(self.app.jobs)
        self.assertTrue(self.app.editable)
        self.assertIn('mapped start fault',self.app.status_text.get())
        self.assertTrue(self.app.cancel_button.instate(['disabled']))
        self.app.edit('place',material_id='block',start_tick=480)
        self.assertEqual(len(self.controller.project['placements']),1)

    def test_profile_change_and_late_result_do_not_publish_or_autoplay(self):
        self.app.select_target('material','block');before=self.invariant()
        self.provider.gate=threading.Event()
        self.app.prepare_selected();self.profile='new-profile'
        self.provider.gate.set();self.finish_jobs()
        self.assertFalse(self.app.ready_assets)
        self.assertEqual(self.invariant(),before)
        self.assertIn('版本',self.app.status_text.get())
        self.app.prepare_selected();self.finish_jobs()
        self.assertTrue(self.app.ready_assets)
        self.assertEqual(self.invariant(),before)

    def test_source_placement_draft_file_mutation_never_reuses_or_autoplays(self):
        self.app.edit('place',material_id='block',start_tick=480)
        placement=self.controller.state()['project']['placements'][0]['id']
        for kind,ident in (('source','source'),('placement',placement),('material','block')):
            self.app.select_target(kind,ident);self.app.prepare_selected();self.finish_jobs()
            before=self.invariant();self.mid.write_bytes(self.mid.read_bytes()+b' changed')
            self.assertFalse(self.app.play_selected());self.assertEqual(self.invariant(),before)
            self.assertFalse(self.app.jobs)
        self.app.add_combo(self.app.resolve('material','block'),'child0','right');self.app.prepare_combo();self.finish_jobs()
        before=self.invariant();self.mmp.unlink()
        self.assertFalse(self.app.play_selected());self.assertEqual(self.invariant(),before)
        self.assertFalse(self.app.jobs)

    def test_history_selected_mode_format_and_local_guards(self):
        item=dict(id='H',label='历史版本',version=2,scope='FULL',mode='arranged',application_status='CURRENT',
            score_ref={},generated_at='',body_seconds=4.,audio_seconds=4.5,paths={'wav':str(self.wav)},
            availability=dict(wav=False,mid=False,mmp=False))
        self.controller.histories=[item]
        availability={'arranged':dict(wav=False,mid=False,mmp=False),'melody_only':dict(wav=True,mid=True,mmp=False)}
        queries=[]
        def query(result_id,mode=None):
            queries.append((result_id,mode))
            values=availability[mode or 'arranged']
            return dict(result_id=result_id,mode=mode or 'arranged',score_ref={},asset_ref={},renderer_profile='fixture',
                availability=copy.deepcopy(values),errors={f:None if v else dict(code='MODE_NOT_READY',message='所选模式未准备 '+f,details={}) for f,v in values.items()})
        self.controller.history_output_state=query
        self.controller.history_asset=Mock(return_value=dict(files={'wav':{'path':str(self.wav)}},body_seconds=4.,audio_seconds=4.5))
        self.controller.export_history=Mock(side_effect=lambda ident,f,destination,mode=None:Path(destination))
        self.app.selected_history_id='H';self.app.select_target('history','H')
        self.app.recommendation.mode.set(curve_ui.MODES['melody_only']);self.app.recommendation.mode_changed()
        self.root.update();before=self.invariant()
        self.assertTrue(self.app.page.export_buttons['wav'].instate(['!disabled']))
        self.assertTrue(self.app.page.export_buttons['mmp'].instate(['disabled']))
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=str(self.mid)):
            self.app.export_history('mid')
        self.controller.export_history.assert_called_once_with('H','mid',str(self.mid),mode='melody_only')
        self.assertEqual(before,self.invariant())
        self.app.play_target('history','H')
        self.controller.history_asset.assert_called_once_with('H',mode='melody_only')
        playing=copy.deepcopy(self.app.playing_target)
        self.app.recommendation.mode.set(curve_ui.MODES['arranged']);self.app.recommendation.mode_changed()
        self.assertFalse(self.app.play_target('history','H'))
        self.assertEqual(self.app.playing_target,playing)
        with patch('curve_ui.filedialog.asksaveasfilename') as dialog:self.app.export_history('mid')
        dialog.assert_not_called()
        self.assertIn('所选模式未准备',self.app.detail_text.get())
        # Stored mode now valid, selected mode invalid: never fall back.
        availability['arranged']=dict.fromkeys(('wav','mid','mmp'),True)
        availability['melody_only']=dict.fromkeys(('wav','mid','mmp'),False)
        self.app.recommendation.mode.set(curve_ui.MODES['melody_only']);self.app.recommendation.mode_changed()
        self.assertFalse(self.app.play_target('history','H'))
        self.assertTrue(self.app.page.export_buttons['wav'].instate(['disabled']))
        item['scope']='LOCAL';availability['melody_only']['wav']=True
        self.app.refresh();self.assertTrue(self.app.page.export_buttons['wav'].instate(['disabled']))
        self.assertEqual(self.app.playing_target,playing)
        self.assertTrue(all(ident=='H' for ident,mode in queries))

    def test_history_export_cancel_preserves_state(self):
        self.controller.histories=[dict(id='legacy',label='旧工程',paths=dict(wav=str(self.wav)),
            availability=dict(wav=True,mid=True,mmp=True),body_seconds=4.,audio_seconds=4.5)]
        self.app.selected_history_id='legacy';self.app.select_target('history','legacy');self.app.refresh()
        before=self.invariant()
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=''):
            self.app.export_history('mid')
        self.assertEqual(before,self.invariant())

    def test_expanded_sources_three_sizes_keep_canvas_and_actions_inside_window(self):
        self.app.select_target('material','block')
        before=self.invariant()
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for width,height in ((1020,700),(1280,800),(1440,900)):
                self.root.geometry(f'{width}x{height}')
                for collapsed in (False,True):
                    self.app.source_user_collapsed=collapsed;self.app.layout_sources();self.root.update()
                    rx,ry=self.root.winfo_rootx(),self.root.winfo_rooty()
                    canvas=self.app.page.timeline.canvas
                    self.assertLessEqual(canvas.winfo_rootx()+canvas.winfo_width(),rx+width)
                    for button in (self.app.page.final_button,self.app.history_button,self.app.prepare_button,self.app.play_button,self.app.cancel_button):
                        self.assertTrue(button.winfo_ismapped())
                        self.assertGreaterEqual(button.winfo_height(),44)
                        self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),rx+width)
                        self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),ry+height)
                    self.assertEqual(self.invariant(),before)

    def test_unchanged_library_refresh_keeps_widgets_and_real_edits_rebind_cards(self):
        before=self.invariant();rows=dict(self.app.page.cards.rows)
        self.app.refresh();self.root.update()
        self.assertEqual(self.app.page.cards.rows,rows)
        self.assertEqual(self.invariant(),before)
        self.controller.edit('resize',grid_count=64)
        self.app.refresh();self.root.update()
        self.assertEqual(self.app.page.cards.rows,rows)
        self.controller._project['materials'][0]['label']='changed fixture DTO'
        self.app.refresh();self.root.update()
        self.assertNotEqual(self.app.page.cards.rows,rows)
        ident=self.controller._project['materials'][0]['id']
        self.assertIn('changed',self.app.page.cards.rows[ident].winfo_children()[0].winfo_children()[0].cget('text'))

    def test_long_transport_name_is_compact_but_focus_displays_full_object(self):
        name='完整对象名称 '*40
        self.controller._project['materials'][-1]['label']=name
        ident=self.controller._project['materials'][-1]['id']
        self.app.refresh();self.app.select_target('material',ident);self.root.geometry('1020x700');self.root.update()
        before=self.invariant()
        self.assertLess(self.app.transport_label.winfo_height(),80)
        self.assertNotIn(name,self.app.transport_label.cget('text'))
        self.app.transport_label.focus_force();self.root.update()
        self.app.transport_label.event_generate('<Return>');self.root.update()
        self.assertIn(name,self.app.detail_text.get())
        self.assertEqual(self.invariant(),before)

    def test_older_injected_job_registry_does_not_crash_elapsed_timer(self):
        self.app.jobs['legacy-work']={'token':{'request_id':'legacy-work'}}
        try:
            self.assertIsNone(self.app.recommendation.active_job())
            self.app.recommendation.update_elapsed()
        finally:self.app.jobs.clear()

    def short_protection_setup(self):
        project=curve_project.new_project()
        notes=[dict(id='n'+str(i),pitch=60+i,start_tick=i,duration_tick=1,velocity=80,
            origin=dict(source_id='s',track_id='t',source_note_id='n'+str(i)),lineage=[],slice=None) for i in range(3)]
        project['sources']=[dict(id='s',label='short source',length_ticks=3,notes=notes,provenance=dict(track_id='t'))]
        for i,(kind,length) in enumerate((('block',1),('bridge',1),('block',480))):
            project['materials'].append(dict(id='m'+str(i),label='short '+kind,kind=kind,length_ticks=length,
                notes=[dict(copy.deepcopy(notes[i]),start_tick=0)],provenance=dict(source_id='s',source_start_tick=i),
                generation=None,phrase_id=None,children=[]))
        self.controller=curve_workflow.Controller(project)
        for i in range(3):self.controller.edit('place',material_id='m'+str(i),start_tick=960+i)
        self.controller.edit('set_intensity',points=[dict(tick=0,level=.25),dict(tick=960,level=.85),
            dict(tick=project['total_ticks'],level=.25)])
        self.app.controller=self.controller;self.app.refresh();self.root.geometry('1020x700');self.root.update()

    def test_exact_short_memory_and_manual_bridge_have_distinct_readable_callouts(self):
        self.short_protection_setup()
        timeline=self.app.page.timeline;before=self.invariant()
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for scale,scroll in ((.085,0),(.5,.04)):
                timeline.scale=scale;timeline.draw();timeline.canvas.xview_moveto(scroll);timeline.draw();self.root.update()
                self.assertEqual(len(timeline.range_badges),2)
                a,t,b,d=timeline.boxes[self.controller.project['placements'][0]['id']]
                self.assertAlmostEqual(b-a,scale)  # Callout never extends the musical range.
                memory,bridge=[badge[0] for badge in timeline.range_badges]
                self.assertLess(memory[3],bridge[1])
                self.assertTrue(timeline.canvas.find_withtag('manual-bridge-range'))
                for box,detail in timeline.range_badges:
                    x,y=int((box[0]+box[2])/2-timeline.canvas.canvasx(0)),int((box[1]+box[3])/2)
                    event=self.event(timeline.canvas,x,y)
                    timeline.press(event);timeline.release(event)
                    self.assertEqual(self.app.detail_text.get(),detail)
                    self.assertIsNone(timeline.intensity_draft)
                    self.assertIsNone(timeline.drag)
                    self.assertEqual(self.invariant(),before)

    def test_editable_points_and_trace_win_badge_overlap_readonly_keeps_detail(self):
        self.short_protection_setup();timeline=self.app.page.timeline
        (a,t,b,d),_=timeline.range_badges[0]
        x,y=(a+b)/2,(t+d)/2
        point=dict(tick=round(timeline.tick(x)),level=1-(y-36)/max(1,timeline.canvas.winfo_height()-80))
        points=copy.deepcopy(self.controller.project['intensity_points']);points.insert(2,point)
        self.controller.edit('set_intensity',points=points);self.app.refresh();self.root.update()
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            self.root.update();before=self.invariant()
            index,x,y=next(v for v in timeline.point_boxes if timeline.points()[v[0]]['tick']==point['tick'])
            self.assertTrue(any(a<=x<=b and t<=y<=d for (a,t,b,d),_ in timeline.range_badges))
            def click(x,y):
                event=self.event(timeline.canvas,round(x-timeline.canvas.canvasx(0)),round(y))
                timeline.canvas.event_generate('<ButtonPress-1>',x=event.x,y=event.y,
                    rootx=event.x_root,rooty=event.y_root);self.root.update()
            timeline.set_mode('points');click(x,y)
            self.assertEqual(timeline.intensity_draft['index'],index)
            timeline.cancel();self.assertEqual(self.invariant(),before)
            timeline.set_mode('trace');(a,t,b,d),_=timeline.range_badges[1];click((a+b)/2,(t+d)/2)
            self.assertIsNotNone(timeline.intensity_draft)
            self.assertIsNone(timeline.intensity_draft['index'])
            timeline.cancel();self.assertEqual(self.invariant(),before)
            timeline.set_mode('points')
            info=self.controller.state()['memory_info']
            # Standalone readonly canvas callback fixture; no private candidate/service auth claim.
            with patch.object(self.app,'preview_memory_description',return_value=self.app.memory_description()):
                timeline.set_project(self.controller.project,readonly=True,memory_info=info)
                index,x,y=next(v for v in timeline.point_boxes if timeline.points()[v[0]]['tick']==point['tick'])
                click(x,y)
                self.assertIsNone(timeline.intensity_draft)
                self.assertIn('记忆',self.app.detail_text.get())
                self.assertEqual(self.invariant(),before)
                timeline.set_project(self.controller.project,memory_info=info)


class CurveP8NativeCloseTests(unittest.TestCase):
    """Real mapped Aqua/TkDND + Facade; no render or device playback in this suite."""
    def setUp(self):
        import os
        import sys
        if sys.platform != 'darwin' or not curve_ui.ui_platform.NATIVE_CHROME:
            self.skipTest('Actual Aqua/TkDND close needs the macOS adapter and desktop')
        self.tmp = tempfile.TemporaryDirectory(prefix='curve-native-close-')
        self.addCleanup(self.tmp.cleanup)
        self.environment = patch.dict(os.environ, {'EMOBLOCKS_DATA_DIR': self.tmp.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.root = curve_ui.ui_platform.create_root()
        self.addCleanup(self.destroy_root)
        if not hasattr(self.root, 'drop_target_register'):
            self.skipTest('Existing TkDND dependency is not available; not an actual DND check')
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.controller = curve_workflow.Controller(fixture())
        self.app = curve_ui.CurveApplication(self.root, self.controller)
        self.root.geometry('1020x700+20+40')
        self.root.update()
        self.assertIsNotNone(self.app.file_drop)
        self.assertTrue(self.root.winfo_ismapped())

    def destroy_root(self):
        if hasattr(self, 'app') and not self.app.closed:
            self.app.close()
        else:
            try:self.root.destroy()
            except tk.TclError:pass

    def test_real_public_close_autosaves_destroys_root_and_repeated_teardown_is_safe(self):
        before = copy.deepcopy(self.controller.project)
        drop = self.app.file_drop
        callback = Mock(wraps=drop.callback)
        drop.callback = callback
        self.assertTrue(self.app.close())
        self.assertTrue(self.app.closed)
        self.assertTrue(drop.closed)
        self.assertEqual(self.controller.project, before)
        saved = sorted(Path(self.tmp.name).rglob('*.json'))
        self.assertTrue(saved)
        self.assertTrue(self.app.close())
        drop.close()
        self.assertEqual(sorted(Path(self.tmp.name).rglob('*.json')), saved)
        self.assertEqual(drop.drop(SimpleNamespace(data='late input.mid')), 'refuse_drop')
        callback.assert_not_called()
        self.assertFalse(self.errors)
        try:
            exists = self.root.winfo_exists()
        except tk.TclError as exc:
            self.assertIn('application has been destroyed', str(exc))
            exists = False
        self.assertFalse(exists)

    def test_autosave_failure_keeps_real_window_drop_bindings_and_player_target_alive(self):
        drop = self.app.file_drop
        bindings = (self.root.bind('<<Drop>>'), self.root.bind('<<DropTargetTypes>>'))
        target = dict(label='tracked playback', target=('material', 'block'), asset={})
        self.app.playing_target = copy.deepcopy(target)
        before = copy.deepcopy(self.controller.state())
        with patch.object(self.controller, 'autosave_if_needed', side_effect=OSError('owned autosave failure')), \
             patch.object(self.app.player, 'close', wraps=self.app.player.close) as close_player:
            self.assertFalse(self.app.close())
            close_player.assert_not_called()
        self.root.update()
        self.assertFalse(self.app.closed)
        self.assertFalse(drop.closed)
        self.assertTrue(self.root.winfo_ismapped())
        self.assertEqual((self.root.bind('<<Drop>>'), self.root.bind('<<DropTargetTypes>>')), bindings)
        self.assertEqual(self.controller.state(), before)
        self.assertEqual(self.app.playing_target, target)
        self.assertIn('owned autosave failure', self.app.status_text.get())
        # The same live target still accepts a callback; no import/render is invoked.
        with patch.object(drop, 'callback') as callback:
            self.assertEqual(drop.drop(SimpleNamespace(data='{source with spaces.mid}')), 'copy')
            callback.assert_called_once_with(['source with spaces.mid'])
        self.assertTrue(self.app.close())
        self.assertFalse(self.errors)
