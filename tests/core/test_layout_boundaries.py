"""Visible viewport boundaries and layout-only operations must preserve editing state."""
import copy
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import ui_scale
from unified_ui import UnifiedApp
from legacy_story_fixture import restore_legacy


class LayoutBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.app=UnifiedApp(self.root);restore_legacy(self.app)
        self.page=self.app.story_page;self.resize('1020x700')

    def tearDown(self):
        self.page.preview_planner.close();self.root.after_cancel(self.app.timer);self.root.destroy();self.temp.cleanup()
        ui_scale.factor=1.

    def resize(self,size):
        self.root.geometry(size);self.root.update()
        self.app.responsive.last=None;self.app.responsive.apply();self.root.update()

    def versions(self,count):
        self.app.results=[dict(mode='快速成品',edit_summary='中文摘要 English Summary '*60,
            report=dict(output_directory=self.temp.name,duration_seconds=8,bars=4)) for _ in range(count)]
        self.app.refresh_results();self.root.update()

    def assert_visible(self,widget):
        self.assertTrue(widget.winfo_ismapped())
        x,y=widget.winfo_rootx(),widget.winfo_rooty();r,b=x+widget.winfo_width(),y+widget.winfo_height()
        parent=widget.master
        while parent:
            self.assertGreaterEqual(x,parent.winfo_rootx());self.assertGreaterEqual(y,parent.winfo_rooty())
            self.assertLessEqual(r,parent.winfo_rootx()+parent.winfo_width())
            self.assertLessEqual(b,parent.winfo_rooty()+parent.winfo_height());parent=parent.master

    def test_history_end_hit_and_resize_for_real_viewports(self):
        a=self.app
        for size in ('1020x700','1440x900','1280x800','1020x700'):
            self.resize(size)
            for count in (0,1,2,5,20):
                self.versions(count);selected=a.result_list.curselection()
                a.scroll_history(SimpleNamespace(delta=-2400))
                self.assertEqual(a.result_list.curselection(),selected)
                self.assertGreaterEqual(a.history_offset,0);self.assertLessEqual(a.history_offset,a.history_extent()[2])
                if not count:self.assertEqual(a.history_offset,0);continue
                row=a.history_rows[-1];self.assertEqual(row[2],0)
                self.assertLessEqual(row[1]*ui_scale.factor,a.history_canvas.winfo_height()+.01)
                a.choose_history(SimpleNamespace(x=40,y=(max(0,row[0])+row[1])/2*ui_scale.factor))
                self.assertEqual(a.result_list.curselection(),(0,))
                for index in (count//2,count-1):
                    a.select_history(index);row=next(r for r in a.history_rows if r[2]==index)
                    a.choose_history(SimpleNamespace(x=40,y=(row[0]+row[1])/2*ui_scale.factor))
                    self.assertEqual(a.result_list.curselection(),(index,))
                self.assertIsNone(a.playing_path)

    def test_wheel_touchpad_and_thumb_share_bounds(self):
        a=self.app;self.versions(20)
        a.scroll_history(SimpleNamespace(delta=-2400));end=a.history_offset
        a.history_offset=0
        with patch('scroll_input.touchpad_deltas',return_value=(0,-100000)):
            a.scroll_history_touchpad(SimpleNamespace())
        self.assertEqual(a.history_offset,end)
        a.history_offset=0;a.reveal_history_scroll();a.history_drag=(0,0)
        a.drag_history(SimpleNamespace(y=100000));self.assertEqual(a.history_offset,end)
        a.release_history_scroll(SimpleNamespace());self.resize('1440x900')
        self.assertLessEqual(a.history_offset,a.history_extent()[2])

    def test_long_text_failure_details_and_layout_preserve_project(self):
        a=self.app;p=self.page;self.versions(20)
        a.saved_signature=a.project_signature();signature=a.project_signature();history=copy.deepcopy(p.history)
        for size in ('1020x700','1280x800','1440x900','1020x700'):
            self.resize(size)
            for w in (p.generate_button,a.transport_play,a.stop_button,*a.export_buttons.values()):self.assert_visible(w)
            self.assertIn('…',a.selected_version_label.cget('text'))
            self.assertIn('English Summary',a.selected_version_label.full_text)
            p.generation_panel.pack(fill='x',before=p.footer)
            p.generation_failed('渲染阶段','临时错误日志 '+self.temp.name+'\\n'*30);self.root.update()
            height=p.line.winfo_height();p.toggle_generation_details();self.root.update()
            self.assertEqual(p.line.winfo_height(),height)
            self.assert_visible(p.retry_button);self.assert_visible(p.details_button)
            p.toggle_generation_details();self.root.update()
            self.assertFalse(a.dirty);self.assertEqual(a.project_signature(),signature);self.assertEqual(p.history,history)

    def test_compact_tiles_all_reachable_and_hit_correct_block(self):
        a=self.app
        a.audition_blocks=[dict(emotion='calm',name=str(i)) for i in range(20)]
        a.result_block.configure(values=[str(i) for i in range(20)])
        for size in ('1020x700','1440x900','1020x700'):
            self.resize(size);a.audition_page=0;seen=set()
            for _ in range(20):
                a.draw_result_tiles()
                for x,y,r,b,index in a.audition_boxes:
                    self.assertLessEqual(b*ui_scale.factor,a.audition_tiles.winfo_height()+.01)
                    with patch.object(a,'play_result_block') as play:
                        a.pick_result_tile(SimpleNamespace(x=(x+r)/2,y=(y+b)/2*ui_scale.factor))
                        self.assertEqual(a.result_block.current(),index);play.assert_called_once()
                    seen.add(index)
                if len(seen)==20:break
                a.pick_result_tile(SimpleNamespace(x=a.audition_tiles.winfo_width()-5,y=10*ui_scale.factor))
            self.assertEqual(seen,set(range(20)))
