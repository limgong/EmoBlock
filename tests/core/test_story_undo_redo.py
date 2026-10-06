"""Main-page undo/redo through real Tk handlers, buttons and app shortcuts (hidden window)."""
import copy
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import intensity_curve

import studio_model
import ui_platform
from unified_ui import UnifiedApp
from legacy_story_fixture import restore_legacy


class StoryUndoRedoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=tk.Tk();cls.root.withdraw();cls.app=UnifiedApp(cls.root);restore_legacy(cls.app)
        cls.root.update_idletasks();cls.page=cls.app.story_page
        cls.original=copy.deepcopy(cls.page.project)

    @classmethod
    def tearDownClass(cls):
        cls.page.cancel_drag();cls.page.preview_planner.close()
        cls.root.after_cancel(cls.app.timer);cls.root.destroy()

    def setUp(self):
        p=self.page;self.app.busy=False;p.cancel_drag();p.restore(copy.deepcopy(self.original))
        self.app.results=[];self.app.modes.select(p);p.line.xview_moveto(0)
        p.strength.set(35);p.trend.set('平稳');p.brush_changed()

    def event(self,time,y=60):
        return SimpleNamespace(x=self.page.px(time)-self.page.line.canvasx(0),y=y)

    def key(self,kind,widget=None):
        windows='<Control-y>' in ui_platform.EDIT_SHORTCUT_EVENTS
        keysym='z' if kind=='undo' else ('y' if windows else 'Z')
        return SimpleNamespace(widget=widget or self.page.line,state=0 if kind=='undo' or windows else 1,keysym=keysym)

    def paint(self,emotion,start,end):
        p=self.page;p.select_palette(emotion)
        p.press(self.event(start))
        for t in range(int(start)+1,int(end)+1):p.motion(self.event(t))
        p.release(self.event(end));p.select_palette(emotion)

    def drag_intensity(self,index,y):
        p=self.page;time=p.project['intensity_points'][index]['time'];_,_,start=p.intensity_handles[index]
        p.press(self.event(time,start))
        for step in (start-10,start-20,y):p.motion(self.event(time,step))
        p.release(self.event(time,y))

    def enabled(self,button):return not button.instate(['disabled'])

    def three_edits(self):
        p=self.page;states=[copy.deepcopy(p.project)]
        self.paint('hope',6,10);states.append(copy.deepcopy(p.project))
        self.drag_intensity(2,144);states.append(copy.deepcopy(p.project))
        p.resize_timeline(1);states.append(copy.deepcopy(p.project))
        self.assertEqual(len(p.history),3)
        self.assertEqual(len({str(s) for s in states}),4)
        return states

    def test_three_edits_undo_and_redo_in_order_with_labels(self):
        p=self.page;states=self.three_edits()
        self.assertFalse(self.enabled(p.redo_button));self.assertTrue(self.enabled(p.undo_button))
        self.assertIn('加长时间线',p.history_hint('undo'))
        for index,label in ((2,'加长时间线'),(1,'调整强度'),(0,'情绪涂色')):
            p.undo_button.invoke()
            self.assertEqual(p.project,states[index])
            self.assertEqual(self.app.notice.cget('text'),'已撤销：'+label)
        self.assertFalse(self.enabled(p.undo_button));self.assertTrue(self.enabled(p.redo_button))
        self.assertIn('没有可撤销',p.history_hint('undo'))
        for index,label in ((1,'情绪涂色'),(2,'调整强度'),(3,'加长时间线')):
            p.redo_button.invoke()
            self.assertEqual(p.project,states[index])
            self.assertEqual(self.app.notice.cget('text'),'已重做：'+label)
        self.assertFalse(self.enabled(p.redo_button))

    def test_new_edit_after_undo_discards_redo_branch(self):
        p=self.page;self.three_edits();p.undo();p.undo()
        self.assertTrue(p.history.can_redo)
        p.resize_timeline(-1)
        self.assertFalse(p.history.can_redo);self.assertFalse(self.enabled(p.redo_button))
        self.assertEqual(p.history.undo_label,'缩短时间线')
        with self.assertRaises(ValueError):p.redo()

    def test_each_complete_drag_is_one_step(self):
        p=self.page
        self.paint('crisis',0,12);self.assertEqual(len(p.history),1)
        before=copy.deepcopy(p.project)
        edge=p.project['curve'][1]['end'];p.press(self.event(edge))
        for t in (edge+.5,edge+1,edge+1.5,edge+2):p.motion(self.event(t))
        p.release(self.event(edge+2))
        self.assertEqual(len(p.history),2);self.assertEqual(p.history.undo_label,'调整段落边界')
        p.undo();self.assertEqual(p.project,before)
        p.undo();self.assertEqual(p.project,self.original)

    def test_escape_cancel_restores_display_and_keeps_redo(self):
        p=self.page;self.paint('hope',6,10);p.undo()
        redo=copy.deepcopy(p.history.redo_stack)
        p.press(self.event(4));p.motion(self.event(24))
        self.assertIsNotNone(p.drag_preview)
        self.assertTrue(p.line.bind('<Escape>'))
        p.cancel_drag()
        self.assertEqual(p.project,self.original);self.assertIsNone(p.drag_preview)
        self.assertEqual(len(p.history),0);self.assertEqual(p.history.redo_stack,redo)
        # Intensity drag cancelled: handles return to the saved curve.
        time=p.project['intensity_points'][2]['time'];_,_,y=p.intensity_handles[2]
        p.press(self.event(time,y));p.motion(self.event(time,144));p.cancel_drag()
        self.assertEqual([h[2] for h in p.intensity_handles][2],y)
        self.assertEqual(p.project,self.original);self.assertEqual(p.history.redo_stack,redo)
        # Undo pressed mid-drag only cancels the drag.
        p.press(self.event(4));p.motion(self.event(24));p.undo()
        self.assertEqual(p.project,self.original);self.assertEqual(p.history.redo_stack,redo)
        p.redo();self.assertEqual(p.history.undo_label,'情绪涂色')

    def test_unchanged_operations_do_not_touch_history(self):
        p=self.page;self.paint('hope',6,10);p.undo()
        redo=copy.deepcopy(p.history.redo_stack)
        time=p.project['intensity_points'][2]['time'];_,_,y=p.intensity_handles[2]
        p.press(self.event(time,y));p.release(self.event(time,y))      # click a handle
        p.press(self.event(4));p.release(self.event(4))                # select a block
        edge=p.project['curve'][1]['end'];p.press(self.event(edge));p.motion(self.event(edge+.3));p.release(self.event(edge+.3))
        self.assertFalse(p.commit(p.snapshot(),'无变化'))
        p.set_region_source(1,p.project['curve'][1].get('source_id'))
        self.assertEqual(p.project,self.original)
        self.assertEqual(len(p.history),0);self.assertEqual(p.history.redo_stack,redo)
        self.assertTrue(self.enabled(p.redo_button))

    def test_clicking_intensity_dot_at_integer_pixels_keeps_level_and_redo(self):
        p=self.page;p.resize_timeline(1);p.undo()
        redo=copy.deepcopy(p.history.redo_stack)
        fractional=[(i,x,y) for i,x,y in p.intensity_handles if abs(y-round(y))>.05]
        self.assertTrue(fractional)
        for i,x,y in fractional[:3]:
            for jitter in (0,1,-2):
                with self.subTest(handle=i,jitter=jitter):
                    raw=SimpleNamespace(x=round(x-p.line.canvasx(0)),y=round(y)+jitter)
                    p.press(p.timeline_event(raw));p.motion(p.timeline_event(raw));p.release(p.timeline_event(raw))
                    self.assertEqual(p.project,self.original)
                    self.assertEqual(len(p.history),0);self.assertEqual(p.history.redo_stack,redo)
        # Leaving the dead zone and returning to the pressed pixel restores the level exactly.
        for i,x,y in fractional[:3]:
            with self.subTest(round_trip=i):
                raw=lambda dy:p.timeline_event(SimpleNamespace(x=round(x-p.line.canvasx(0)),y=round(y)+dy))
                p.press(raw(0))
                for dy in (4,12,30,12,0):p.motion(raw(dy))
                p.release(raw(0))
                self.assertEqual(p.project,self.original)
                self.assertEqual(len(p.history),0);self.assertEqual(p.history.redo_stack,redo)
        # A real vertical move past the dead zone still records exactly one step.
        i,x,y=fractional[0]
        p.press(self.event(p.project['intensity_points'][i]['time'],y));p.motion(self.event(p.project['intensity_points'][i]['time'],y-20))
        p.release(self.event(p.project['intensity_points'][i]['time'],y-20))
        self.assertEqual(p.history.undo_label,'调整强度');self.assertFalse(p.history.can_redo)

    def test_restored_state_matches_controls_and_generated_version(self):
        p=self.page;app=self.app
        p.melody_only.set(True);p.commit(p.snapshot(),'切换仅主旋律')
        generated=p.snapshot()
        app.results=[dict(mode='快速成品',report=dict(output_directory='kept-version',duration_seconds=1),story_fingerprint=app.story_fingerprint(generated))]
        kept=copy.deepcopy(app.results);app.update_edit_status()
        self.assertEqual(app.edit_status_label.cget('text'),'当前编辑与最新成品一致')
        p.resize_timeline(1)
        self.assertIn('尚未生成',app.edit_status_label.cget('text'))
        p.undo()
        self.assertEqual(app.edit_status_label.cget('text'),'当前编辑与最新成品一致')
        self.assertEqual(float(p.duration.get()),p.project['duration']);self.assertTrue(p.melody_only.get())
        self.assertEqual(p.snapshot(),generated)
        controls=intensity_curve.controls(p.project)
        self.assertEqual([round(y,6) for _,_,y in p.intensity_handles],[round(206-62*c['level'],6) for c in controls])
        p.undo()
        self.assertFalse(p.melody_only.get());self.assertIn('尚未生成',app.edit_status_label.cget('text'))
        p.redo();self.assertEqual(app.edit_status_label.cget('text'),'当前编辑与最新成品一致')
        p.redo();self.assertEqual(float(p.duration.get()),p.project['duration'])
        self.assertIn('尚未生成',app.edit_status_label.cget('text'))
        self.assertEqual(app.results,kept)

    def test_shortcuts_follow_platform_and_skip_text_fields(self):
        p=self.page;app=self.app
        for sequence in ui_platform.EDIT_SHORTCUT_EVENTS:self.assertTrue(self.root.bind(sequence))
        self.assertIn(ui_platform.UNDO_LABEL,p.history_hint('undo'));self.assertIn(ui_platform.REDO_LABEL,p.history_hint('redo'))
        self.paint('hope',6,10);painted=copy.deepcopy(p.project)
        entry=ttk.Entry(p);combo=ttk.Combobox(p);text=tk.Text(p)
        for widget in (entry,combo,text):
            self.assertIsNone(app.edit_shortcut(self.key('undo',widget)))
        self.assertEqual(p.project,painted)
        readonly=ttk.Combobox(p,state='readonly')
        self.assertEqual(app.edit_shortcut(self.key('undo',readonly)),'break');self.assertEqual(p.project,self.original)
        self.assertEqual(app.edit_shortcut(self.key('redo')),'break');self.assertEqual(p.project,painted)
        app.modes.select(1)
        self.assertIsNone(app.edit_shortcut(self.key('undo')));self.assertEqual(p.project,painted)
        for widget in (entry,combo,text,readonly):widget.destroy()

    def test_busy_blocks_buttons_and_shortcuts_alike(self):
        p=self.page;app=self.app;self.paint('hope',6,10);p.undo();p.redo()
        self.assertTrue(self.enabled(p.undo_button))
        app.busy=True;p.update_history_controls()
        self.assertFalse(self.enabled(p.undo_button));self.assertFalse(self.enabled(p.redo_button))
        app.edit_shortcut(self.key('undo'));p.undo_button.invoke();app.safe(p.undo)
        self.assertEqual(len(p.history),1)
        app.busy=False;p.update_history_controls();self.assertTrue(self.enabled(p.undo_button))

    def test_new_and_opened_projects_start_with_empty_history(self):
        p=self.page;app=self.app
        with patch.object(app,'save_project'):
            self.paint('hope',6,10);self.paint('sad',0,4);p.undo()
            self.assertTrue(p.history.can_undo and p.history.can_redo)
            app.new_project()
            self.assertFalse(p.history.can_undo or p.history.can_redo)
            self.assertFalse(self.enabled(p.undo_button) or self.enabled(p.redo_button))
            p.restore(copy.deepcopy(self.original));self.paint('hope',6,10);p.undo()
            data=dict(pool=studio_model.materials.new_pool(),doc=None,curve=copy.deepcopy(app.curve),results=[],settings=dict(story=copy.deepcopy(self.original)))
            with patch.object(studio_model,'load_project',return_value=data):app.load_project('ignored.json')
            self.assertFalse(p.history.can_undo or p.history.can_redo)

    def test_undoing_an_import_drops_its_audition_state(self):
        p=self.page;project=p.snapshot()
        source=copy.deepcopy(project['sources'][0]);source.update(id='undo-import',name='Imported')
        project['sources'].append(source);p.commit(project,'导入旋律')
        p.source_audio=dict(id='undo-import',path='x.wav',rows=[dict(end_seconds=1.)],bpm=p.project['bpm'])
        p.undo()
        self.assertIsNone(p.source_audio)
        self.assertNotIn('undo-import',[s['id'] for s in p.project['sources']])


if __name__=='__main__':unittest.main()
