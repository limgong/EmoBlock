"""Context actions edit real projects transactionally without displaying menus."""
import copy
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import story_engine as engine
from unified_ui import UnifiedApp
from legacy_story_fixture import restore_legacy
from edit_history import EditHistory


class BlockActionTests(unittest.TestCase):
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
        p=self.page;p.cancel_drag();p.restore(copy.deepcopy(self.original))
        p.host.busy=False;p.line.xview_moveto(0)

    def event(self,time,y=60):
        return SimpleNamespace(x=self.page.px(time)-self.page.line.canvasx(0),
                               y=y,x_root=100,y_root=100)

    def add_second_source(self):
        project=copy.deepcopy(self.page.project)
        source=copy.deepcopy(project['sources'][0]);source.update(id='test-secondary',name='Second melody',role='secondary')
        project['sources'].append(source);self.page.restore(project)
        return source['id']

    def manual_project(self):
        project=copy.deepcopy(self.original)
        project['anchors']=[dict(time=8,hold=2,emotion='crisis',level=.6),
                            dict(time=12,hold=2,emotion='sad',level=.3)]
        self.page.restore(project)
        return copy.deepcopy(self.page.project)

    def assert_unchanged(self,project,history):
        self.assertEqual(self.page.project,project)
        self.assertEqual(self.page.history,history)

    def test_remove_first_middle_and_last_regions_fills_time_and_supports_undo(self):
        p=self.page
        for index in (0,1,len(self.original['curve'])-1):
            with self.subTest(index=index):
                p.restore(copy.deepcopy(self.original));p.remove_emotion_region(index)
                curve=p.project['curve']
                self.assertEqual(curve[0]['start'],0)
                self.assertEqual(curve[-1]['end'],self.original['duration'])
                self.assertTrue(all(a['end']==b['start'] for a,b in zip(curve,curve[1:])))
                self.assertEqual(len(curve),len(self.original['curve'])-1)
                self.assertEqual(p.project['intensity_points'],self.original['intensity_points'])
                self.assertEqual(len(p.history),1)
                p.undo();self.assertEqual(p.project,self.original)

    def test_region_source_changes_preserve_emotions_intensity_and_do_not_add_overrides(self):
        p=self.page;source_id=self.add_second_source();before=copy.deepcopy(p.project)
        p.set_region_source(2,source_id)
        expected=copy.deepcopy(before);expected['curve'][2]['source_id']=source_id
        expected.setdefault('melody_only',False)
        self.assertEqual(p.project,expected)
        self.assertEqual(engine.state_at(p.project,9)['source_id'],source_id)
        self.assertEqual(p.project['overrides'],[])
        assigned=copy.deepcopy(p.project)
        p.set_region_source(2,None)
        self.assertIsNone(p.project['curve'][2].get('source_id'))
        self.assertEqual(p.project['intensity_points'],before['intensity_points'])
        self.assertEqual(p.project['overrides'],[])
        p.undo();self.assertEqual(p.project,assigned)
        p.undo();self.assertEqual(p.project,before)

    def test_invalid_region_source_does_not_mutate_project_or_history(self):
        p=self.page;before=copy.deepcopy(p.project)
        with self.assertRaises(ValueError):p.set_region_source(1,'missing-source')
        self.assert_unchanged(before,EditHistory())

    def test_clear_local_changes_preserves_outside_ramps_and_can_be_undone(self):
        p=self.page;project=copy.deepcopy(self.original)
        project['overrides']=[dict(start=2,end=10,emotion='hope',level=.2,end_level=1.)]
        p.restore(project);before=copy.deepcopy(p.project)
        p.clear_local_changes(4,6)
        self.assertEqual([(v['start'],v['end']) for v in p.project['overrides']],[(2,4),(6,10)])
        left,right=p.project['overrides']
        self.assertAlmostEqual(left['end_level'],.4)
        self.assertAlmostEqual(right['level'],.6)
        self.assertEqual(p.project['curve'],before['curve'])
        self.assertEqual(p.project['intensity_points'],before['intensity_points'])
        self.assertEqual(len(p.history),1)
        p.undo();self.assertEqual(p.project,before)

    def test_invalid_clear_range_leaves_existing_edits_and_undo_history_intact(self):
        p=self.page;p.set_region_source(1,p.project['sources'][0]['id'])
        before=copy.deepcopy(p.project);history=copy.deepcopy(p.history)
        for start,end in ((6,4),(-1,2),(0,float('nan'))):
            with self.subTest(start=start,end=end):
                with self.assertRaises(ValueError):p.clear_local_changes(start,end)
                self.assert_unchanged(before,history)






    def test_context_menu_routes_emotion_actions_and_intensity_right_click(self):
        p=self.page;source_id=self.add_second_source();before=copy.deepcopy(p.project)
        with patch.object(tk.Menu,'tk_popup'),patch.object(tk.Menu,'grab_release'):
            p.context_click(self.event(8,60))
            menu=p.context_menu
            labels=[menu.entrycget(i,'label') for i in range(menu.index('end')+1)]
            self.assertIn('移除此情绪段',labels)
            source_menu=p.nametowidget(menu.entrycget(labels.index('此情绪段旋律来源'),'menu'))
            source_menu.invoke(2)
            self.assertEqual(p.project['curve'][2]['source_id'],source_id)
            self.assertEqual(p.project['anchors'],[])
            p.undo();self.assertEqual(p.project,before)
            p.context_click(self.event(8.5,190))
            self.assertEqual(p.project,before)
            self.assertEqual(len(p.history),0)

    def test_context_menu_is_ignored_while_busy_or_dragging_and_outside_regions(self):
        p=self.page;before=copy.deepcopy(p.project)
        with patch.object(tk.Menu,'tk_popup') as popup,patch.object(tk.Menu,'grab_release'):
            for y in (20,115,220,310):p.context_click(self.event(8,y))
            p.host.busy=True
            try:p.context_click(self.event(8,60))
            finally:p.host.busy=False
            p.press(self.event(4));p.context_click(self.event(8,190));p.cancel_drag()
            popup.assert_not_called()
        self.assert_unchanged(before,EditHistory())


if __name__=='__main__':unittest.main()
