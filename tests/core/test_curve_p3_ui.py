"""Mapped P3 gestures against an injected frozen Facade; no render/device use.

Memory decisions and trace normalization are service fixtures, not frontend
implementations of those algorithms. Integration with real services is separate.
"""
import copy
from pathlib import Path
import threading
import tkinter as tk
from unittest.mock import patch

import curve_canvas
import curve_ui
import intensity_curve
from curve_theme import EMOTION_NAMES
from test_curve_ui import MappedUIFixture


class CurveP3Tests(MappedUIFixture):
    def setUp(self):
        super().setUp()
        self.capabilities = dict(intensity_edit=True,emotion=True,memory=True)
        self.memory = None
        self.protections = []
        self.bpm = 120
        state = self.controller.state
        capture = self.controller.capture_job
        def exposed_state():
            result = state()
            result['capabilities'].update(self.capabilities)
            result['memory_info'] = copy.deepcopy(self.memory)
            if result['project']:
                result['project']['bpm'] = self.bpm
                result['project']['protections'] = copy.deepcopy(self.protections)
            return result
        def captured(kind,target=None):
            result = capture(kind,target)
            result['snapshot']['project']['bpm'] = self.bpm
            return result
        for name,fn in (('state',exposed_state),('capture_job',captured)):
            patcher = patch.object(self.controller,name,side_effect=fn)
            patcher.start();self.addCleanup(patcher.stop)
        # The fake preserves samples. Peak simplification belongs to curve_memory.
        self.real_normalize = curve_canvas._normalize_trace
        patcher = patch.object(curve_canvas,'_normalize_trace',side_effect=lambda points,total:copy.deepcopy(points))
        self.normalize = patcher.start();self.addCleanup(patcher.stop)
        self.app.refresh();self.root.update()

    def place(self,material='block',start=480):
        self.app.edit('place',material_id=material,start_tick=start)
        self.root.update()
        return self.controller.state()['project']['placements'][-1]['id']

    def at(self,tick,level):
        c = self.app.page.timeline
        return self.event(c.canvas,c.x(tick)-c.canvas.canvasx(0),c.y(level)-c.canvas.canvasy(0))

    def state_bundle(self):
        return copy.deepcopy((self.controller.state(),self.controller.history_items(),self.app.playing_target,
                              self.app.player.calls,self.app.player.status()))

    def edits(self,action):
        return [args for name,args in self.controller.calls if name==action]

    def test_normalizer_lazy_import_uses_frozen_ticks_and_tolerance(self):
        points = [dict(tick=0,level=.25),dict(tick=15360,level=.25)]
        with patch.object(curve_canvas.importlib,'import_module') as load:
            helper = load.return_value.normalize_trace
            helper.return_value = points
            self.assertEqual(self.real_normalize(points,15360),points)
            load.assert_called_once_with('curve_memory')
            helper.assert_called_once_with(points,15360,tolerance=.02)

    def stroke(self,points):
        c = self.app.page.timeline
        c.press(self.at(*points[0]))
        for point in points[1:]:c.motion(self.at(*point))
        c.release(self.at(*points[-1]));self.root.update()

    def test_point_add_drag_once_undo_and_escape_preserve_player_and_selection(self):
        ident = self.place()
        self.app.select_target('placement',ident)
        self.app.prepare_selected();self.finish_jobs();self.app.play_selected()
        player = copy.deepcopy((self.app.playing_target,self.app.player.calls,self.app.player.status()))
        before = self.controller.state()['project']['intensity_points']
        c = self.app.page.timeline
        self.root.update()
        self.stroke([(3840,.7)])
        added = self.controller.state()['project']['intensity_points']
        self.assertEqual(len(added),3)
        self.assertEqual(len(self.edits('set_intensity')),1)
        point = added[1]
        start = self.at(point['tick'],point['level'])
        end = self.event(c.canvas,start.x+42,start.y-10)
        c.press(start);c.motion(end)
        self.assertEqual(added,self.controller.state()['project']['intensity_points'])
        c.release(end)
        self.assertEqual(len(self.edits('set_intensity')),2)
        self.app.undo()
        self.assertEqual(self.controller.state()['project']['intensity_points'],added)
        c.press(start);c.motion(end)
        c.canvas.focus_force();self.root.update()
        self.assertEqual(self.root.focus_get(),c.canvas)
        c.canvas.event_generate('<Escape>');self.root.update();c.release(end)
        self.assertEqual(self.controller.state()['project']['intensity_points'],added)
        self.assertTrue(self.controller.state()['can_redo'])
        self.assertEqual(self.app.selected_target,('placement',ident))
        self.assertEqual((self.app.playing_target,self.app.player.calls,self.app.player.status()),player)
        self.app.undo()
        self.assertEqual(self.controller.state()['project']['intensity_points'],before)

    def test_control_point_roundtrip_noop_keeps_redo_saved_and_endpoint_tick(self):
        self.app.edit('set_intensity',points=[dict(tick=0,level=.25),dict(tick=4800,level=.6),dict(tick=15360,level=.25)])
        self.app.undo();self.controller.save_snapshot();self.app.refresh()
        before = self.state_bundle()
        count = len(self.edits('set_intensity'))
        c = self.app.page.timeline
        start = self.at(0,.25)
        away = self.event(c.canvas,start.x+40,start.y-25)
        c.press(start);c.motion(away);c.motion(start);c.release(start)
        self.assertEqual(self.state_bundle(),before)
        self.assertEqual(len(self.edits('set_intensity')),count)
        c.press(start);c.motion(away);c.release(away)
        self.assertEqual(self.controller.state()['project']['intensity_points'][0]['tick'],0)

    def test_trace_keeps_local_extrema_outside_points_and_one_undo(self):
        original = [dict(tick=t,level=l) for t,l in [(0,.25),(240,.4),(3840,.3),(15360,.25)]]
        self.app.edit('set_intensity',points=original)
        before = self.controller.state()['project']
        count = len(self.edits('set_intensity'))
        c = self.app.page.timeline;c.set_mode('trace')
        samples = [(960,.3),(1440,.9),(1920,.2),(2400,.8),(2880,.4)]
        self.normalize.side_effect = lambda points,total:[p for p in points if p['tick'] not in (240,3840)]
        expected_ticks = [c.root_point(self.at(t,l).x_root,self.at(t,l).y_root)['tick'] for t,l in samples]
        c.press(self.at(*samples[0]))
        for point in samples[1:]:c.motion(self.at(*point))
        self.assertEqual(self.controller.state()['project'],before)
        self.assertEqual(len(self.edits('set_intensity')),count)
        c.release(self.at(*samples[-1]));self.root.update()
        points = self.controller.state()['project']['intensity_points']
        self.assertEqual(len(self.edits('set_intensity')),count+1)
        self.normalize.assert_called_once()
        ticks = [p['tick'] for p in points]
        self.assertEqual(ticks,sorted(set(ticks)))
        for original_point in original:self.assertIn(original_point,points)
        for tick in expected_ticks:self.assertTrue(any(p['tick']==tick for p in points))
        curve = [dict(time=p['tick'],level=p['level']) for p in points]
        for a,b in zip(points,points[1:]):
            for i in range(11):
                value = intensity_curve.evaluate(curve,a['tick']+(b['tick']-a['tick'])*i/10)
                self.assertLessEqual(value,max(a['level'],b['level'])+1e-9)
                self.assertGreaterEqual(value,min(a['level'],b['level'])-1e-9)
        self.app.undo();self.assertEqual(self.controller.state()['project'],before)

    def test_trace_cancel_outside_and_helper_failure_never_write(self):
        c = self.app.page.timeline;c.set_mode('trace')
        before = self.state_bundle()
        start,end = self.at(960,.8),self.at(2400,.2)
        c.press(start);c.motion(end);c.cancel();c.release(end)
        self.assertEqual(self.state_bundle(),before)
        c.press(start);c.motion(end)
        outside = self.event(c.canvas,end.x,-10)
        c.release(outside)
        self.assertEqual(self.state_bundle(),before)
        self.normalize.side_effect = ValueError('bad trace')
        self.stroke([(960,.8),(2400,.2)])
        self.assertEqual(self.state_bundle(),before)
        self.assertIn('失败',self.app.status_text.get())
        self.assertFalse(self.edits('set_intensity'))

    def test_explicit_modes_point_priority_and_trace_do_not_move_blocks(self):
        ident = self.place()
        c = self.app.page.timeline
        before = self.controller.state()['project']
        # A control point inside the music rectangle wins in point mode.
        self.app.edit('set_intensity',points=[dict(tick=0,level=.25),dict(tick=960,level=.25),dict(tick=15360,level=.25)])
        start = self.at(960,.25);end = self.event(c.canvas,start.x,start.y-20)
        c.press(start);c.motion(end);c.release(end)
        self.assertFalse(self.edits('move'))
        self.assertEqual(self.app.selected_target,None)
        c.set_mode('trace')
        self.stroke([(720,.25),(1200,.75),(1680,.2)])
        self.assertFalse(self.edits('move'))
        self.assertEqual(self.controller.state()['project']['placements'],before['placements'])
        # Explicit cross-column drag still places material while in draw mode.
        card = c.app.page.cards.rows['block']
        start = self.event(card,24,20)
        c.app.begin_material_drag(start,c.app.resolve('material','block'),card)
        end = self.at(3840,.5)
        c.app.material_motion(end);c.app.material_release(end)
        self.assertEqual(len(self.controller.state()['project']['placements']),2)
        self.assertEqual(self.controller.state()['project']['placements'][0]['id'],ident)

    def test_mapped_scroll_and_shrink_coordinates_and_block_line_independence(self):
        ident = self.place(start=5760)
        c = self.app.page.timeline
        self.app.edit('set_intensity',points=[dict(tick=0,level=.25),dict(tick=7200,level=.8),dict(tick=15360,level=.25)])
        for geometry in ('1440x900','1020x700'):
            self.root.geometry(geometry);self.root.update()
            c.canvas.xview_moveto(.35);self.root.update()
            self.assertGreaterEqual(c.canvas.winfo_height(),160)
            self.assertLessEqual(c.y(0),c.scene_height)
            start = self.at(7200,self.controller.state()['project']['intensity_points'][1]['level'])
            before = self.controller.state()['project']['intensity_points']
            end = self.event(c.canvas,start.x+20,start.y+15)
            c.press(start);c.motion(end);c.release(end)
            point = self.controller.state()['project']['intensity_points'][1]
            self.assertEqual(point['tick'],before[1]['tick']+round(20/c.scale))
            self.app.undo();self.root.update()
        c.canvas.xview_moveto(.25);self.root.update()
        a,t,b,d = c.boxes[ident]
        start = self.event(c.canvas,a-c.canvas.canvasx(0)+20,(t+d)/2)
        end = self.event(c.canvas,start.x+41,start.y+20)
        before = self.controller.state()['project']['intensity_points']
        c.press(start);c.motion(end);c.release(end)
        after = self.controller.state()['project']
        self.assertEqual(after['intensity_points'],before)
        self.assertEqual(after['placements'][0]['start_tick'],6240)

    def test_six_emotions_bind_selected_placement_only_and_gate_busy_readonly(self):
        first = self.place();second = self.place(start=3840)
        original = self.controller.state()['project']
        self.app.select_target('placement',first);self.root.update()
        self.assertEqual(set(self.app.page.emotion_buttons),set(EMOTION_NAMES))
        for emotion in ('hope','sad','hope','calm'):
            self.app.page.emotion_buttons[emotion].invoke();self.root.update()
            project = self.controller.state()['project']
            self.assertEqual(project['placements'][0]['emotion'],emotion)
            self.assertEqual(project['placements'][1]['emotion'],'calm')
            self.assertEqual(project['materials'],original['materials'])
            self.assertEqual(project['placements'][0]['base_snapshot'],original['placements'][0]['base_snapshot'])
        self.assertTrue(all(args['placement_ids']==[first] for args in self.edits('set_emotion')))
        self.app.select_target('placement',second)
        self.provider.gate = threading.Event()
        self.app.prepare_selected()
        before = self.state_bundle()
        self.assertFalse(self.app.set_emotion('crisis'))
        self.assertEqual(self.state_bundle(),before)
        self.assertTrue(all(b.instate(['disabled']) for b in self.app.page.emotion_buttons.values()))
        self.assertTrue(all(b.instate(['disabled']) for b in self.app.page.timeline.mode_buttons.values()))
        self.app.cancel_jobs();self.provider.gate.set()
        self.capabilities['emotion'] = False;self.app.refresh()
        self.assertFalse(self.app.set_emotion('crisis'))
        self.controller.readonly = True;self.app.refresh()
        self.assertFalse(self.app.set_emotion('crisis'))
        self.assertFalse(self.app.page.emotion_panel.winfo_manager())
        self.assertFalse(self.app.can_edit('intensity_edit'))

    def test_full_protection_emotion_warning_is_visible_without_claiming_rendered_arrangement(self):
        ident = self.place()
        self.app.select_target('placement',ident)
        before = self.controller.state()['project']
        message = '全部基础音符受保护，无法合法改变旋律；保留其音高和节奏。'
        generation = dict(warnings=[dict(code='FULLY_PROTECTED',message=message,details={})],
                          melody_changed=False,accompaniment_hints=dict(status='suggested-not-rendered'))
        # The service fixture returns unchanged protected notes plus its warning.
        state = self.controller.state
        def warning_state():
            result = state()
            placement = result['project']['placements'][0]
            if placement['emotion']!='calm':
                placement['emotion_variant'] = dict(copy.deepcopy(placement['base_snapshot']),
                                                    id='emotion-fixture',generation=copy.deepcopy(generation))
            return result
        self.memory = dict(peak_tick=960,lookup_tick=960,state='BOUND',placement_id=ident,
                           component_path=[],range=dict(start_tick=480,end_tick=2400),protection_id='memory-fixture')
        base_notes = before['placements'][0]['base_snapshot']['notes']
        self.protections = [dict(id='memory-fixture',kind='memory',placement_id=ident,status='CONTENT_READY',
                                start_tick=480,end_tick=2400,notes=[dict(n,start_tick=n['start_tick']+480) for n in base_notes])]
        with patch.object(self.controller,'state',side_effect=warning_state):
            self.app.refresh();self.root.update()
            self.app.page.emotion_buttons['hope'].invoke();self.root.update()
            text = self.app.status_text.get()
            self.assertIn(message,text);self.assertIn(message,self.app.detail_text.get())
            self.assertIn('旋律未改变',text)
            self.assertIn('编配仅为建议，尚未渲染',self.app.detail_text.get())
            self.assertIn('中性单旋律',self.app.detail_text.get());self.assertNotIn('工程已更新',text)
            placement = self.controller.state()['project']['placements'][0]
            self.assertEqual(placement['emotion_variant']['notes'],base_notes)
            self.assertEqual(placement['base_snapshot'],before['placements'][0]['base_snapshot'])
            self.assertEqual(self.controller.state()['project']['materials'],before['materials'])
            self.assertFalse(self.app.player.calls)
            self.app.toggle_theme();self.root.update()
            self.assertIn(message,self.app.status_text.get())
            self.root.geometry('1020x700');self.app.refresh();self.root.update()
            self.assertGreaterEqual(self.app.page.timeline.canvas.winfo_height(),160)

    def test_memory_bound_actual_range_complete_note_support_and_no_false_lock(self):
        ident = self.place('phrase',480)
        self.memory = dict(peak_tick=3000,lookup_tick=3000,state='BOUND',placement_id=ident,
                           component_path=[],range=dict(start_tick=2400,end_tick=4320),protection_id=None)
        self.app.refresh();self.root.update()
        c = self.app.page.timeline
        self.assertIn('目标未落保护',self.app.page.memory_label.cget('text'))
        self.assertTrue(c.canvas.itemcget(c.canvas.find_withtag('memory-range')[0],'dash'))
        self.memory['protection_id'] = 'memory-fixture'
        self.protections = [dict(id='memory-fixture',kind='memory',placement_id=ident,status='CONTENT_READY',
                                start_tick=2400,end_tick=4320,notes=[dict(start_tick=2280,duration_tick=300)])]
        self.app.refresh();self.root.update()
        self.assertIn('音高与节奏已保护',self.app.page.memory_label.cget('text'))
        self.assertIn('5–9拍',self.app.page.memory_label.cget('text'))
        self.assertIn('2400–4320',self.app.memory_description())
        rect = c.canvas.coords(c.canvas.find_withtag('memory-range')[0])
        self.assertAlmostEqual(rect[0],c.x(2400));self.assertAlmostEqual(rect[2],c.x(4320))
        support = c.canvas.coords(c.canvas.find_withtag('memory-support')[0])
        self.assertAlmostEqual(support[0],c.x(2280));self.assertAlmostEqual(support[2],c.x(2580))
        self.assertEqual(len(c.boxes),1)
        c.hover(self.at(2880,.25))
        self.assertIn('音高与节奏已保护',self.app.detail_text.get())
        self.app.show_detail('outside the protected range')
        c.hover(self.at(960,.25))
        self.assertEqual(self.app.detail_text.get(),'outside the protected range')
        self.capabilities['memory'] = False;self.app.refresh()
        self.assertFalse(c.canvas.find_withtag('memory-range'))

    def test_memory_gap_blank_endpoint_and_combo_shorttail_are_service_states(self):
        material = self.provider.combine(self.controller.state()['project'],['block','child2'],'组合短尾')
        captured = self.controller.capture_job('COMBINE')
        self.controller.apply_batch(dict(sources=[],materials=[material],warnings=[]),captured['token'])
        self.app.refresh();ident = self.place(material['id'],480)
        self.memory = dict(peak_tick=2500,lookup_tick=2500,state='BOUND',placement_id=ident,
                           component_path=['occ1'],range=dict(start_tick=2400,end_tick=2640),protection_id=None)
        self.app.refresh();self.root.update()
        c = self.app.page.timeline
        self.assertEqual(len(c.boxes),1)
        self.assertIn('occ1',self.app.memory_description())
        rect = c.canvas.coords(c.canvas.find_withtag('memory-range')[0])
        self.assertAlmostEqual(rect[2]-rect[0],240*c.scale)
        for state,text in (('PENDING_GAP','待落位'),('PRESERVE_BLANK','保留留白')):
            self.memory = dict(peak_tick=15360,lookup_tick=15359,state=state,placement_id=None,
                               component_path=[],range=None,protection_id=None)
            self.app.refresh();self.root.update()
            self.assertIn(text,self.app.page.memory_label.cget('text'))
            self.assertTrue(self.app.page.memory_label.winfo_ismapped())
            self.assertFalse(c.canvas.find_withtag('memory-range'))
            self.assertIsNone(self.app.playing_target)

    def test_bpm_cache_capture_binding_combo_and_ready_never_autoplay(self):
        bpms = []
        original = self.provider.render_audition
        def render(snapshot,bpm=120):
            bpms.append(bpm)
            asset = original(snapshot,bpm)
            asset['body_seconds'] = snapshot['length_ticks']/480*60/bpm
            return asset
        self.bpm = 90;self.app.refresh();self.app.select_target('material','block')
        with patch.object(self.provider,'render_audition',side_effect=render):
            self.provider.gate = threading.Event()
            self.app.prepare_selected()
            self.bpm = 110;self.app.refresh()
            self.provider.gate.set();self.finish_jobs()
            self.assertEqual(bpms,[90])
            key = curve_ui.audition_key('material',self.app.resolve('material','block'),90)
            self.assertIn(key,self.app.ready_assets)
            self.assertFalse(self.app.play_selected())
            self.app.prepare_selected();self.finish_jobs()
            self.assertEqual(bpms,[90,110])
            self.app.prepare_selected();self.assertFalse(self.app.jobs)
            self.assertEqual(bpms,[90,110])
            self.assertIn('预计正文',self.app.status_text.get())
            self.assertIn('实际音频',self.app.status_text.get())
            self.assertIsNone(self.app.playing_target);self.assertFalse(self.app.player.calls)
            self.app.play_selected()
            self.assertIn('预计正文',self.app.transport_description())
            self.assertIn('实际音频',self.app.transport_description())
            player = copy.deepcopy((self.app.playing_target,self.app.player.calls))
            self.app.add_combo(self.app.resolve('material','block'),'phrase','right')
            self.app.prepare_combo();self.finish_jobs()
            self.assertEqual(bpms,[90,110,110])
            self.assertEqual((self.app.playing_target,self.app.player.calls),player)

    def test_late_audition_after_emotion_edit_is_inert(self):
        ident = self.place();self.app.select_target('placement',ident)
        self.provider.gate = threading.Event()
        self.app.prepare_selected()
        self.controller.edit('set_emotion',placement_ids=[ident],emotion='sad')
        self.app.refresh()
        before = self.state_bundle()
        self.provider.gate.set();self.finish_jobs()
        self.assertFalse(self.app.ready_assets)
        self.assertEqual(self.state_bundle(),before)
        self.assertIn('过期',self.app.status_text.get())

    def test_export_receipt_bound_id_format_full_path_and_cancel_noop(self):
        destination = Path(self.folder.name)/'a long export folder'/'song.mid'
        self.controller.histories = [dict(id='H',label='历史版本 2026',generated_at='2026',body_seconds=2.,audio_seconds=4.5,
            availability=dict(wav=True,mid=True,mmp=True),paths=dict(wav=str(self.wav),mid='old.mid',mmp='old.mmp'),edit_fingerprint=None)]
        self.app.refresh();self.app.select_target('history','H');self.app.play_selected()
        before = self.state_bundle()
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=str(destination)):
            self.app.export_history('mid')
        receipt = self.app.export_receipt.get('1.0','end')
        self.assertIn('历史版本 2026 [H]',receipt);self.assertIn('MID',receipt);self.assertIn(str(destination),receipt)
        self.assertIn(('export',('H','mid',str(destination))),self.controller.calls)
        with patch('curve_ui.ui_platform.open_folder') as opened:
            self.app.open_export_folder();opened.assert_called_once_with(destination.parent.resolve())
        with patch('curve_ui.filedialog.asksaveasfilename',return_value=''):
            self.app.export_history('wav')
        self.app.toggle_theme();self.app.refresh();self.root.update()
        self.assertEqual(receipt,self.app.export_receipt.get('1.0','end'))
        self.assertEqual(self.state_bundle(),before)
        self.assertEqual(self.app.selected_target,('history','H'))
        # A persistent export receipt must not steal the P3 editing viewport.
        ident = self.place()
        self.app.select_target('placement',ident)
        self.root.geometry('1020x700');self.app.refresh();self.root.update()
        self.assertGreaterEqual(self.app.page.timeline.canvas.winfo_height(),160)
        if not self.app.details_expanded:self.app.toggle_details()
        self.root.update()
        for widget in (self.app.detail_label,self.app.export_folder_button,self.app.play_button):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())

    def test_emotion_and_trace_controls_fit_sizes_and_themes_keep_scroll_state(self):
        ident = self.place();self.app.select_target('placement',ident)
        self.app.prepare_selected();self.finish_jobs();self.app.play_selected()
        c = self.app.page.timeline
        c.set_mode('trace');c.canvas.xview_moveto(.2)
        self.memory = dict(peak_tick=15360,lookup_tick=15359,state='PENDING_GAP',placement_id=None,
                           component_path=[],range=None,protection_id=None)
        before = self.state_bundle()
        for geometry in ('1020x700','1280x800','1440x900'):
            self.root.geometry(geometry);self.app.refresh();self.root.update()
            scroll = c.canvas.xview()[0]
            self.app.toggle_theme();self.root.update()
            self.assertEqual(self.state_bundle()[0]['project'],before[0]['project'])
            self.assertEqual(self.state_bundle()[1:],before[1:])
            self.assertEqual(c.mode,'trace');self.assertEqual(self.app.selected_target,('placement',ident))
            self.assertAlmostEqual(c.canvas.xview()[0],scroll,places=2)
            self.assertGreaterEqual(c.canvas.winfo_height(),160)
            self.assertIsInstance(c.canvas,tk.Canvas)
            self.memory = dict(peak_tick=960,lookup_tick=960,state='BOUND',placement_id=ident,
                               component_path=['a very long nested occurrence path'],
                               range=dict(start_tick=480,end_tick=2400),protection_id=None)
            self.app.refresh();self.root.update()
            self.assertGreaterEqual(c.canvas.winfo_height(),160)
            for button in [c.mode_buttons[m] for m in ('arrange','points','trace')]+list(self.app.page.emotion_buttons.values())+[self.app.play_button]:
                self.assertTrue(button.winfo_ismapped());self.assertGreaterEqual(button.winfo_height(),44)
                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.root.winfo_rooty()+self.root.winfo_height())
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())

    def test_tk_generated_trace_events_and_resize_mid_draft_cancel(self):
        c = self.app.page.timeline;c.set_mode('trace')
        before = self.controller.state()['project']
        for name,point in [('<ButtonPress-1>',(960,.3)),('<B1-Motion>',(1440,.8)),('<B1-Motion>',(1920,.2)),('<ButtonRelease-1>',(2400,.6))]:
            event = self.at(*point)
            c.canvas.event_generate(name,x=event.x,y=event.y);self.root.update()
        self.assertEqual(len(self.edits('set_intensity')),1)
        self.app.undo();self.assertEqual(self.controller.state()['project'],before)
        c.press(self.at(960,.8));c.motion(self.at(2400,.2))
        self.root.geometry('1020x700');self.root.update()
        self.assertIsNone(c.intensity_draft)
        self.assertEqual(self.controller.state()['project'],before)

    def test_trace_after_scroll_uses_canvasx_and_edge_scroll_recomputes_tick(self):
        c = self.app.page.timeline;c.set_mode('trace')
        self.root.geometry('1020x700');self.root.update()
        c.canvas.xview_moveto(.3);self.root.update()
        before = self.controller.state()['project']
        start = self.at(7200,.8)
        end = self.event(c.canvas,c.canvas.winfo_width()-8,c.y(.4))
        c.press(start);c.motion(end)
        old_tick = c.root_point(end.x_root,end.y_root)['tick']
        c.after_cancel(c.edge_timer);c.edge_timer = None
        c._edge_step()
        expected_tick = c.root_point(end.x_root,end.y_root)['tick']
        self.assertGreater(expected_tick,old_tick)
        self.assertEqual(self.controller.state()['project'],before)
        c.release(end)
        points = self.controller.state()['project']['intensity_points']
        self.assertIn(expected_tick,[p['tick'] for p in points])
        self.assertEqual(len(self.edits('set_intensity')),1)
        self.app.undo();self.assertEqual(self.controller.state()['project'],before)

    def test_subpixel_block_integer_mapped_hit_with_scroll_scale_and_neighbors(self):
        material = copy.deepcopy(self.app.resolve('material','block'))
        material.update(id='single-tick',label='单 tick 休止块',length_ticks=1,notes=[])
        captured = self.controller.capture_job('COMBINE')
        self.controller.apply_batch(dict(sources=[],materials=[material],warnings=[]),captured['token'])
        self.app.refresh()
        first = self.place('single-tick',1)
        c = self.app.page.timeline
        a,t,b,d = c.boxes[first]
        x = round((a+b)/2-c.canvas.canvasx(0));y = int((t+d)/2+18)
        self.assertFalse(a<=c.canvas.canvasx(x)<=b)
        before = self.controller.state()['project']
        c.canvas.event_generate('<ButtonPress-1>',x=x,y=y)
        c.canvas.event_generate('<ButtonRelease-1>',x=x,y=y)
        self.root.update()
        self.assertEqual(self.app.selected_target,('placement',first))
        self.assertEqual(self.controller.state()['project'],before)
        second = self.place('single-tick',2)
        neighbor = self.place('block',3)
        distant = self.place('single-tick',7201)
        distant_neighbor = self.place('block',7202)
        for geometry,scale,scroll,target,next_id in (
            ('1020x700',.085,0.,second,neighbor),
            ('1280x800',.17,.35,distant,distant_neighbor),
            ('1440x900',.04,.1,distant,distant_neighbor)):
            with self.subTest(geometry=geometry,scale=scale):
                self.root.geometry(geometry);self.root.update()
                c.scale = scale;c.draw();c.canvas.xview_moveto(scroll);self.root.update()
                a,t,b,d = c.boxes[target]
                self.assertLess(b-a,1)
                # The nearest integer pointer hits the visible 1px outline,
                # even when no integer canvas coordinate is inside the geometry.
                x = round((a+b)/2-c.canvas.canvasx(0))
                # The scene may extend below the dock; reveal the short block
                # before generating a real integer viewport event.
                c.canvas.yview_moveto(max(0,((t+d)/2+18-c.canvas.winfo_height()/2)/c.scene_height));self.root.update()
                y = int((t+d)/2+18-c.canvas.canvasy(0))
                event = self.event(c.canvas,x,y)
                canvas_x = c.canvas.canvasx(event.x_root-c.canvas.winfo_rootx())
                self.assertFalse(a<=canvas_x<=b)
                self.assertTrue(c.contains_root(event.x_root,event.y_root))
                self.assertTrue(all(abs(canvas_x-px)>10 or abs(c.canvas.canvasy(y)-py)>10
                                    for _,px,py in c.point_boxes))
                self.assertEqual(c.hit(canvas_x,c.canvas.canvasy(y)),target)
                before = self.controller.state()['project']
                c.canvas.event_generate('<ButtonPress-1>',x=x,y=y)
                c.canvas.event_generate('<ButtonRelease-1>',x=x,y=y)
                self.root.update()
                self.assertEqual(self.app.selected_target,('placement',target))
                self.assertEqual(self.controller.state()['project'],before)
                self.assertAlmostEqual(c.boxes[target][2]-c.boxes[target][0],scale)
                # An integer pointer in the adjacent ordinary block still selects
                # that block; its ordinary hit bounds are never widened.
                na,nt,nb,nd = c.boxes[next_id]
                nx = round(na-c.canvas.canvasx(0))+2
                ny = int((nt+nd)/2+18-c.canvas.canvasy(0))
                self.assertEqual(c.hit(c.canvas.canvasx(nx),c.canvas.canvasy(ny)),next_id)
                c.canvas.event_generate('<ButtonPress-1>',x=nx,y=ny)
                c.canvas.event_generate('<ButtonRelease-1>',x=nx,y=ny)
                self.root.update()
                self.assertEqual(self.app.selected_target,('placement',next_id))
                self.assertEqual(self.controller.state()['project'],before)
        # Adjacent subpixel outlines sharing an integer pointer follow the same
        # back-to-front order as drawing; outside the 0.5px stroke there is no hit.
        c.scale = .085;c.draw();c.canvas.xview_moveto(0);self.root.update()
        a,t,b,d = c.boxes[first]
        x = round(a);y = int((t+d)/2+18)
        self.assertEqual(c.hit(x,y),second)
        self.assertIsNone(c.hit(a-.501,y))
        self.assertEqual(c.hit(c.boxes[neighbor][2]+.1,y),None)
        self.assertFalse(self.edits('set_intensity'))
        self.assertFalse(self.edits('move'))
        self.assertFalse(self.app.player.calls)
