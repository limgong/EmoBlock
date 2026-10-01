"""Exercise real Tk event handlers without showing a test window."""
import copy
import tkinter as tk
from types import SimpleNamespace
import unittest
import intensity_curve
import story_engine as engine
from unified_ui import UnifiedApp


class BlockInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=tk.Tk();cls.root.withdraw();cls.app=UnifiedApp(cls.root)
        cls.root.update_idletasks();cls.page=cls.app.story_page
        cls.original=copy.deepcopy(cls.page.project)

    @classmethod
    def tearDownClass(cls):
        cls.page.cancel_drag();cls.root.after_cancel(cls.app.timer);cls.root.destroy()

    def setUp(self):
        self.page.cancel_drag();self.page.restore(copy.deepcopy(self.original))
        self.page.host.busy=False;self.page.line.xview_moveto(0)
        self.page.strength.set(35);self.page.trend.set('平稳');self.page.brush_changed()

    def event(self,time,y=60):
        return SimpleNamespace(x=self.page.px(time)-self.page.line.canvasx(0),y=y)

    def test_drop_reorders_once_and_undo_restores(self):
        p=self.page;p.press(self.event(4));p.motion(self.event(24))
        self.assertEqual(p.project,self.original)  # preview must never mutate saved state
        p.release(self.event(24))
        self.assertEqual(len(p.history),1)
        self.assertEqual([v['emotion'] for v in p.project['curve']],['calm','crisis','sad','resolve','suspense','calm'])
        p.undo();self.assertEqual(p.project,self.original)

    def test_cancel_discards_preview_and_mouse_capture(self):
        p=self.page;p.press(self.event(4));p.motion(self.event(24));p.cancel_drag()
        self.assertEqual(p.project,self.original);self.assertEqual(p.history,[])
        self.assertIsNone(p.line.grab_current());self.assertIsNone(p.scroll_timer)

    def test_click_selects_without_creating_undo_entry(self):
        p=self.page;p.press(self.event(4));p.release(self.event(4))
        self.assertEqual(p.selected_region,('curve',1));self.assertEqual(p.history,[])

    def test_single_click_paints_exactly_one_block(self):
        p=self.page;p.select_palette('hope');p.press(self.event(7));p.release(self.event(7))
        painted=[v for v in p.project['curve'] if v['emotion']=='hope']
        self.assertEqual([(v['start'],v['end']) for v in painted],[(6,8)])
        self.assertEqual(len(p.history),1)
        p.undo();self.assertEqual(p.project,self.original)

    def test_palette_can_switch_color_and_toggle_back_to_block_dragging(self):
        p=self.page;self.assertIsNone(p.paint_emotion)
        p.select_palette('hope');self.assertEqual(p.paint_emotion,'hope')
        p.select_palette('sad');self.assertEqual(p.paint_emotion,'sad')
        p.select_palette('sad');self.assertIsNone(p.paint_emotion)
        self.assertEqual(p.history,[])
        p.press(self.event(4));p.motion(self.event(24));p.release(self.event(24))
        self.assertEqual([v['emotion'] for v in p.project['curve']],['calm','crisis','sad','resolve','suspense','calm'])

    def test_painting_at_a_seam_colors_blocks_instead_of_resizing(self):
        p=self.page;p.select_palette('hope')
        p.press(self.event(6));p.motion(self.event(10));p.release(self.event(10))
        painted=[v for v in p.project['curve'] if v['emotion']=='hope']
        self.assertEqual([(v['start'],v['end']) for v in painted],[(6,10)])
        self.assertEqual(p.project['curve'][1],self.original['curve'][1])

    def test_boundary_drag_stays_on_grid(self):
        p=self.page;p.press(self.event(6));p.motion(self.event(7.7));p.release(self.event(7.7))
        self.assertEqual(p.project['curve'][1]['end'],8)
        self.assertEqual(p.project['curve'][2]['start'],8)

    def test_intensity_drag_preserves_emotions(self):
        p=self.page;time=p.project['intensity_points'][2]['time'];_,_,y=p.intensity_handles[2]
        p.press(self.event(time,y));p.motion(self.event(time,144))
        self.assertEqual(p.project,self.original)
        p.release(self.event(time,144))
        self.assertAlmostEqual(p.project['intensity_points'][2]['level'],1)
        self.assertEqual(p.project['curve'],self.original['curve'])
        self.assertEqual(len(p.history),1)
        p.undo();self.assertEqual(p.project,self.original)

    def test_intensity_drag_works_while_a_paint_color_is_selected(self):
        p=self.page;p.select_palette('hope')
        time=p.project['intensity_points'][2]['time'];_,_,y=p.intensity_handles[2]
        p.press(self.event(time,y));p.motion(self.event(time,206));p.release(self.event(time,206))
        self.assertAlmostEqual(p.project['intensity_points'][2]['level'],0)
        self.assertEqual(p.project['curve'],self.original['curve'])
        self.assertEqual(p.paint_emotion,'hope')
        p.press(self.event(7));p.release(self.event(7))
        self.assertTrue(any(v['start']==6 and v['end']==8 and v['emotion']=='hope' for v in p.project['curve']))

    def test_empty_intensity_area_does_not_move_or_paint_blocks(self):
        p=self.page
        for paint in (False,True):
            if paint:p.select_palette('hope')
            p.press(self.event(4,135));p.motion(self.event(24,135));p.release(self.event(24,135))
            self.assertEqual(p.project,self.original)
            self.assertEqual(p.history,[])

    def test_block_drag_crossing_intensity_area_does_not_edit_strength(self):
        p=self.page;p.press(self.event(4));p.motion(self.event(4,144));p.release(self.event(4,144))
        self.assertEqual(p.project,self.original);self.assertEqual(p.history,[])











    def test_scrolled_canvas_intensity_drag_hits_the_visible_point(self):
        p=self.page;p.select_palette('hope');p.line.xview_moveto(.5)
        self.assertGreater(p.line.canvasx(0),0)
        index=10;time=p.project['intensity_points'][index]['time'];_,_,y=p.intensity_handles[index]
        p.press(self.event(time,y));p.motion(self.event(time,144));p.release(self.event(time,144))
        self.assertAlmostEqual(p.project['intensity_points'][index]['level'],1)
        self.assertEqual(p.project['curve'],self.original['curve'])
        self.assertEqual(len(p.history),1)


if __name__=='__main__':unittest.main()
