"""Programmatic real Tk assembly interactions; not human GUI or listening acceptance."""
import copy
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch
import assembly
import story_engine
import studio_model
import ui_scale
from unified_ui import UnifiedApp
from test_assembly import scenario


class AssemblyUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.storage=patch.object(story_engine.flow.structure,'ROOT',self.folder);self.storage.start()
        self.root=tk.Tk();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=UnifiedApp(self.root);self.page=self.app.story_page
        self.root.geometry('1020x700');self.root.update()

    def tearDown(self):
        self.page.cancel_drag();self.page.preview_planner.close();self.root.after_cancel(self.app.timer);self.app.stop_playback();self.root.destroy();self.storage.stop();self.temp.cleanup()
        self.assertEqual(self.errors,[])

    def event(self,time,y=60,**extra):
        p=self.page
        return SimpleNamespace(x=p.px(time)-p.line.canvasx(0),y=y,state=0,**extra)

    def test_new_empty_state_no_implicit_play_and_drag_cancel(self):
        p=self.page;a=self.app;self.assertTrue(p.is_assembly());self.assertEqual(p.project['uses'],[])
        self.assertTrue(p.generate_button.instate(['disabled']));self.assertTrue(any('拖入旋律分块' in p.line.itemcget(i,'text') for i in p.line.find_all() if p.line.type(i)=='text'))
        before=copy.deepcopy(p.project);history=copy.deepcopy(p.history)
        card=p.source_cards.winfo_children()[0];ident=p.project['library'][0]['id']
        event=SimpleNamespace(widget=card,x_root=card.winfo_rootx()+10,y_root=card.winfo_rooty()+10)
        with patch.object(a,'job') as job:
            p.begin_material_drag(event,ident);p.material_drag_release(event);job.assert_not_called()
        event.widget=p.source_cards.winfo_children()[0]
        p.begin_material_drag(event,ident);p.cancel_drag()
        self.assertEqual(before,p.project);self.assertEqual(history,p.history);self.assertFalse(a.dirty)
        self.assertIsNone(self.root.grab_current())

    def test_material_drag_insert_outside_and_escape(self):
        p=self.page;card=p.source_cards.winfo_children()[0];ident=p.project['library'][0]['id']
        begin=SimpleNamespace(widget=card,x_root=card.winfo_rootx()+10,y_root=card.winfo_rooty()+10)
        end=SimpleNamespace(x_root=p.line.winfo_rootx()+60,y_root=p.line.winfo_rooty()+60*p.timeline_scale)
        p.begin_material_drag(begin,ident);p.material_drag_release(end)
        self.assertEqual(len(p.project['uses']),1);self.assertEqual(len(p.history),1);self.assertEqual(p.project['duration'],2)
        before=copy.deepcopy(p.project);card=p.source_cards.winfo_children()[0];begin.widget=card
        p.begin_material_drag(begin,ident);p.material_drag_release(SimpleNamespace(x_root=0,y_root=0))
        self.assertEqual(p.project,before);self.assertEqual(len(p.history),1)
        p.insert_material(ident,0);self.assertNotEqual(p.project['uses'][0]['id'],p.project['uses'][1]['id'])
        p.undo();self.assertEqual(p.project,before);p.redo();self.assertEqual(len(p.project['uses']),2)

    def test_combo_draft_cancel_save_once_and_strip_entry(self):
        p=self.page;p.restore(scenario());before=p.snapshot();history=copy.deepcopy(p.history)
        A=p.project['library'][:3];B=next(m for m in p.project['library'] if m['name']=='B1')
        p.open_combination([A[1],B,A[1]]);p.combination_window.items.reverse();p.combination_window.destroy()
        self.assertEqual(before,p.snapshot());self.assertEqual(history,p.history)
        p.save_combination([A[1],B,A[1]],'C重复');self.assertEqual(len(p.history),1)
        m=p.project['library'][-1];self.assertEqual(assembly.composition(m),'A2＋B1＋A2');self.assertNotIn('emotion',m)
        for use in p.project['uses']:self.assertNotIn('emotion',use['material'])
        p.assembly_selection={0,1,2};p.save_selected_combination();win=p.combination_window
        self.assertEqual([m['name'] for m in win.items],['A1','C','A3']);win.destroy()
        p.undo();self.assertEqual(before,p.snapshot());p.redo();self.assertEqual(p.project['library'][-1]['name'],'C重复')

    def test_whole_paint_reorder_curve_absolute_and_cancel(self):
        p=self.page;p.restore(scenario());p.project['intensity_points']=[dict(time=0,level=.2),dict(time=3,level=.9),dict(time=8,level=.3)]
        p.draw();p.select_palette('crisis');p.press(self.event(3));p.release(self.event(3))
        self.assertEqual([v['emotion'] for v in p.project['uses']],['calm','crisis','calm']);self.assertEqual(len(p.project['curve']),3)
        p.select_palette('crisis');old=p.snapshot();p.press(self.event(3));p.motion(self.event(7.9));p.cancel_drag();self.assertEqual(p.snapshot(),old)
        p.press(self.event(3));p.release(self.event(7.9));self.assertEqual([u['material']['name'] for u in p.project['uses']],['A1','A3','C'])
        self.assertEqual(p.project['intensity_points'],old['intensity_points']);self.assertEqual(p.project['uses'][-1]['emotion'],'crisis')
        p.undo();self.assertEqual(p.snapshot(),old);p.redo();self.assertEqual(p.project['uses'][-1]['material']['name'],'C')
        p.assembly_selection={2};p.delete_uses();self.assertEqual(p.project['duration'],4);p.undo();self.assertEqual(p.project['duration'],8)

    def test_preview_ratio_center_and_resize_preserve_state(self):
        p=self.page;p.restore(scenario());p.project['intensity_points']=[dict(time=0,level=0),dict(time=4,level=1),dict(time=8,level=0)]
        p.draw();before=p.snapshot();history=copy.deepcopy(p.history);self.app.saved_signature=self.app.project_signature()
        for theme in ('light','dark'):
            self.app.set_theme(theme)
            for size in ('1020x700','1280x800','1440x900','1020x700'):
                self.root.geometry(size);self.root.update();p.draw()
                boxes=p.preview_boxes;self.assertEqual(len(boxes),3)
                widths=[v[3]-v[1] for v in boxes];self.assertAlmostEqual(widths[1]/widths[0],2);self.assertAlmostEqual(widths[2]/widths[0],1)
                self.assertAlmostEqual((boxes[1][2]+boxes[1][4])/2,248)
                self.assertEqual(boxes[1][-1],4)
                for w in (p.generate_button,self.app.transport_play,self.app.stop_button,*self.app.export_buttons.values()):
                    self.assertTrue(w.winfo_ismapped());self.assertLessEqual(w.winfo_rootx()+w.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
                p.line.xview_moveto(.5);p.draw();self.assertEqual(p.snapshot(),before);self.assertEqual(history,p.history);self.assertFalse(self.app.dirty)

    def test_intensity_drag_empty_selection_and_short_tail_hit_after_scaling(self):
        p=self.page;p.restore(scenario());p.draw();_,x,y=p.intensity_handles[0]
        p.press(SimpleNamespace(x=x,y=y));p.release(SimpleNamespace(x=x,y=144))
        self.assertEqual(p.project['intensity_points'][0]['level'],1);self.assertEqual(p.assembly_selection,set());p.undo()
        p.insert_material(p.project['library'][0]['id']);p.draw();self.root.geometry('1280x800');self.root.update()
        event=self.event(3);physical=SimpleNamespace(x=event.x,y=event.y*p.timeline_scale,state=0)
        p.press(p.timeline_event(physical));p.release(p.timeline_event(physical));self.assertEqual(p.assembly_selection,{1})

    def test_save_reopen_missing_original_history_and_export_state(self):
        p=self.page;a=self.app;p.restore(scenario());p.project['sources'][1]['source']={'path':str(self.folder/'missing.mid')}
        path=a.save_project();saved=p.snapshot();p.insert_material(p.project['library'][0]['id']);a.load_project(path)
        self.assertEqual(p.snapshot(),saved);self.assertFalse(a.dirty);self.assertEqual(len(p.history),0)
        self.assertIn('素材快照',a.notice.cget('text'));self.assertEqual(p.generation_state,'idle')
        p.assembly_selection={1};p.delete_uses();p.undo();self.assertFalse(a.dirty);self.assertEqual(p.snapshot(),saved)

    def test_busy_blocks_canvas_keyboard_and_combinations(self):
        p=self.page;p.restore(scenario());before=p.snapshot();self.app.busy=True
        p.press(self.event(3));self.assertIsNone(p.drag);self.assertFalse(p.insert_material(p.project['library'][0]['id']))
        p.assembly_selection={1};p.delete_uses();p.save_combination([p.project['library'][0]],'忙碌')
        p.open_combination();self.assertEqual(p.snapshot(),before);self.app.busy=False

    def test_generation_failure_callback_recovery_and_retry_snapshot(self):
        import json
        import threading
        import wave
        p=self.page;a=self.app;p.restore(scenario());p.insert_material(p.project['library'][0]['id']);p.undo()
        history=copy.deepcopy(p.history);before=p.snapshot();calls=[];gate=threading.Event()
        def wait():
            deadline=time.monotonic()+8
            while a.busy:
                if time.monotonic()>deadline:self.fail('job timeout')
                self.root.update();time.sleep(.005)
        def fail(project,progress):
            calls.append(copy.deepcopy(project));progress('测试组装渲染失败');gate.wait(5);raise OSError('injected render error')
        with patch('story_ui.engine.generate',side_effect=fail):
            p.generate();ident=a.active_job['id'];p.generate();self.assertTrue(a.busy);gate.set();wait()
        self.assertEqual(len(calls),1);self.assertEqual(p.snapshot(),before);self.assertEqual(p.history,history)
        self.assertEqual(p.generation_state,'failed');self.assertFalse(p.generate_button.instate(['disabled']));self.assertFalse(p.redo_button.instate(['disabled']))
        p.insert_material(p.project['library'][1]['id'])
        def result(project,progress):
            calls.append(copy.deepcopy(project));planned=story_engine.plan(project);folder=self.folder/'render';folder.mkdir(exist_ok=True)
            report=dict(status='complete',output_directory=str(folder),bars=5,duration_seconds=project['duration'])
            for name,data in (('story.json',project),('story-plan.json',planned),('report.json',report)):(folder/name).write_text(json.dumps(data))
            for name in ('composition.mid','composition.mmp'):(folder/name).write_bytes(b'fixture')
            with wave.open(str(folder/'preview.wav'),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\x01\x00'*8000)
            return planned,report
        with patch('story_ui.engine.generate',side_effect=result),patch.object(a,'add_result',side_effect=RuntimeError('injected callback error')):
            p.generate();wait()
        self.assertEqual(p.generation_state,'failed');self.assertFalse(a.busy);self.assertEqual(a.results,[])
        self.assertEqual(len(calls[-1]['uses']),4);self.assertEqual(calls[-1],p.snapshot())
        with patch('story_ui.engine.generate',side_effect=result):p.generate();wait()
        self.assertEqual(p.generation_state,'success');self.assertEqual(len(a.results),1);self.assertIsNone(a.playing_path)
        a.messages.put((ident,'progress','迟到失败消息'));self.root.after_cancel(a.timer);a.poll()
        self.assertEqual(p.generation_state,'success');self.assertIn('V01',p.generation_status.get())

    def test_shift_selection_strip_combination_and_end_scroll(self):
        p=self.page;p.restore(scenario());A=p.project['library'][:3];B=next(m for m in p.project['library'] if m['name']=='B1')
        project=assembly.delete(p.snapshot(),range(3))
        for m in (A[1],B,A[1]):project=assembly.insert(project,m['id'])
        p.restore(project);p.draw()
        p.press(self.event(1));p.release(self.event(1))
        e=self.event(5);e.state=1;p.press(e);p.release(e)
        self.assertEqual(p.assembly_selection,{0,1,2});self.assertFalse(p.combine_use_button.instate(['disabled']))
        p.save_selected_combination();draft=p.combination_window.items;self.assertEqual([m['name'] for m in draft],['A2','B1','A2'])
        p.combination_window.destroy();p.save_combination(draft,'条组合');self.assertEqual(assembly.composition(p.project['library'][-1]),'A2＋B1＋A2')
        for _ in range(18):p.insert_material(A[0]['id'])
        p.line.xview_moveto(0);p.draw();self.assertGreater(p.timeline_width,p.line.winfo_width())
        p.press(self.event(1));p.pointer=(p.line.winfo_width()-2,60);p.assembly_scroll()
        self.assertGreater(p.line.canvasx(0),0);p.cancel_drag();self.assertIsNone(p.scroll_timer)
        p.line.xview_moveto(1);p.draw();last=p.project['curve'][-1];e=self.event((last['start']+last['end'])/2)
        p.press(e);p.release(e);self.assertEqual(p.assembly_selection,{len(p.project['uses'])-1})

    def test_rounded_physical_point_click_preserves_edit_and_redo(self):
        p=self.page;p.restore(scenario());p.insert_material(p.project['library'][0]['id']);p.undo()
        before=p.snapshot();history=copy.deepcopy(p.history);self.app.saved_signature=self.app.project_signature()
        for size in ('1020x700','1280x800','1440x900'):
            self.root.geometry(size);self.root.update();p.draw()
            for _,x,y in p.intensity_handles:
                physical=SimpleNamespace(x=round(x-p.line.canvasx(0)),y=round(y*p.timeline_scale),state=0)
                p.press(p.timeline_event(physical));p.release(p.timeline_event(physical))
                self.assertEqual(p.snapshot(),before);self.assertEqual(p.history,history);self.assertTrue(p.history.can_redo);self.assertFalse(self.app.dirty)

    def test_undo_redo_during_card_drag_only_cancel_it(self):
        p=self.page;p.restore(scenario());p.insert_material(p.project['library'][0]['id'])
        for action in ('undo','redo'):
            if action=='redo':p.undo()
            before=p.snapshot();history=copy.deepcopy(p.history)
            card=p.source_cards.winfo_children()[0];asset=p.project['library'][0]
            begin=SimpleNamespace(widget=card,x_root=card.winfo_rootx()+10,y_root=card.winfo_rooty()+10)
            end=SimpleNamespace(x_root=p.line.winfo_rootx()+60,y_root=p.line.winfo_rooty()+60*p.timeline_scale)
            p.begin_material_drag(begin,asset['id']);p.material_drag_motion(end)
            getattr(p,action)();self.assertIsNone(p.library_drag);self.assertIsNone(self.root.grab_current());self.assertIsNone(p.scroll_timer)
            p.material_drag_release(end);self.assertEqual(p.snapshot(),before);self.assertEqual(p.history,history)

    def test_failed_switch_restores_selection_controls_and_drafts(self):
        p=self.page;a=self.app;p.restore(scenario());p.assembly_selection={0,1};p.selected_material_id=p.project['library'][1]['id'];p.update_generation_controls()
        p.open_combination([p.project['library'][1]]);win=p.combination_window;before=p.snapshot();history=copy.deepcopy(p.history);selected=p.selected_material_id
        original=a.apply_project
        def fail(*args):original(*args);raise RuntimeError('injected after-restore failure')
        with patch.object(a,'apply_project',side_effect=fail):
            with self.assertRaises(ValueError):a.new_project()
        self.assertEqual(p.snapshot(),before);self.assertEqual(p.history,history);self.assertEqual(p.assembly_selection,{0,1});self.assertEqual(p.selected_material_id,selected)
        self.assertFalse(p.combine_use_button.instate(['disabled']));self.assertTrue(win.winfo_exists());self.assertEqual(win.items[0]['name'],'A2')
        a.new_project();self.assertFalse(win.winfo_exists());self.assertFalse(p.project['uses'])

    def test_successful_open_discards_all_old_drafts_including_legacy_switch(self):
        from legacy_story_fixture import restore_legacy
        a=self.app;p=self.page;restore_legacy(a);legacy=a.save_project();p.restore(scenario())
        p.open_combination([p.project['library'][0]]);first=p.combination_window
        p.open_combination([p.project['library'][1]]);second=p.combination_window
        a.load_project(legacy);self.assertFalse(p.is_assembly());self.assertFalse(first.winfo_exists());self.assertFalse(second.winfo_exists())
        self.assertEqual(p.combination_windows,[])
