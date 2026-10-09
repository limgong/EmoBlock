import copy
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import brick_model
import story_engine
from unified_ui import UnifiedApp

class ComposerTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.app=UnifiedApp(self.root);self.page=self.app.story_page
        self.root.update_idletasks()
    def tearDown(self):
        self.page.cancel_assembly();self.page.preview_planner.close();self.root.after_cancel(self.app.timer)
        self.root.update_idletasks();self.root.destroy()
    def compose(self):
        p=self.page;p.input_blocks.selection_set('0','1','2');p.compose_selection();return p.selected_brick
    def test_details_are_inline_not_toplevel(self):
        p=self.page
        self.assertNotIsInstance(p.source_details,tk.Toplevel)
        self.assertIs(p.source_details.master,p.source_panel.content)
        p.toggle_source_details();self.assertTrue(p.source_details_open);self.assertEqual(p.source_details.winfo_manager(),'pack')
        p.toggle_source_details();self.assertFalse(p.source_details_open);self.assertFalse(p.source_details.winfo_manager())
    def test_multiple_selection_does_not_launch_audio(self):
        p=self.page;p.clear_part_selection()
        with patch.object(p,'play_source_block') as play:
            p.select_part(1);p.select_part(2);self.assertEqual(p.input_blocks.selection(),('1','2'));play.assert_not_called()
        p.select_part(5,SimpleNamespace(state=1));self.assertEqual(p.input_blocks.selection(),('1','2','3','4','5'))
    def test_compose_refreshes_tray_and_is_undoable(self):
        ident=self.compose();p=self.page
        self.assertEqual(p.project['melody_bricks'][0]['id'],ident)
        self.assertEqual(p.tray_boxes[0][2],ident);p.undo();self.assertEqual(p.project.get('melody_bricks',[]),[])
    def test_place_inspect_edit_remove(self):
        self.compose();p=self.page;p.insert_selected_brick();ident=p.selected_placement
        self.assertEqual(p.project['brick_placements'][0]['start_bar'],0)
        p.brick_emotion.set(story_engine.music.EMOTIONS['resolve']);p.variant_choice.set('简单变体');p.update_selected_assembly()
        v=p.project['brick_placements'][0];self.assertEqual(v['emotion'],'resolve');self.assertEqual(v['variant'],'simple')
        p.remove_selected_assembly();self.assertEqual(p.project['brick_placements'],[])
        p.undo();self.assertEqual(p.project['brick_placements'][0]['id'],ident)
    def test_empty_selection_stays_empty_after_preview(self):
        p=self.page;p.clear_part_selection();p.accept_preview(story_engine.plan(p.project))
        self.assertEqual(p.input_blocks.selection(),())
    def test_freehand_and_point_drag_are_separate(self):
        p=self.page;p.tool_mode.set('draw');p.pick_emotion('hope');p.draw()
        before=copy.deepcopy(p.project);p.press(SimpleNamespace(x=p.px(1),y=180));self.assertEqual(p.drag[0],'sketch')
        p.motion(SimpleNamespace(x=p.px(5),y=150));p.release(SimpleNamespace(x=p.px(5),y=150))
        self.assertNotEqual(p.project,before);self.assertTrue(p.project['emotion_drawn'])
        p.tool_mode.set('edit');p.draw();i,x,y=p.intensity_handles[0];p.press(SimpleNamespace(x=x,y=y))
        self.assertEqual(p.drag[0],'intensity');p.cancel_drag()
    def test_cancel_drop_has_no_project_mutation(self):
        ident=self.compose();p=self.page;before=copy.deepcopy(p.project)
        event=SimpleNamespace(widget=p.brick_tray,x=4,x_root=4,y_root=4)
        p.start_assembly(event,ident);p.cancel_assembly();self.assertEqual(p.project,before)
    def test_drop_snaps_and_collision_does_not_mutate(self):
        ident=self.compose();p=self.page
        # Withdrawn Tk roots have a 1-pixel viewport; keep the test windowless.
        with patch.object(p.line,'winfo_width',return_value=900):
            p.draw();origin=SimpleNamespace(widget=p.brick_tray,x=4,x_root=0,y_root=0)
            p.start_assembly(origin,ident)
            target=SimpleNamespace(x_root=p.line.winfo_rootx()+p.px(4.3),y_root=p.line.winfo_rooty()+265*p.timeline_scale)
            p.assembly_motion(target);self.assertEqual(p.assembly_drag['preview']['brick_placements'][0]['start_bar'],2)
            p.assembly_release(target);self.assertEqual(p.project['brick_placements'][0]['start_bar'],2)
            placed=copy.deepcopy(p.project);p.start_assembly(origin,ident);p.assembly_release(target)
            self.assertEqual(p.project,placed);self.assertIsNone(p.assembly_drag)
    def test_audition_does_not_clear_multiple_selection(self):
        p=self.page;p.input_blocks.selection_set('0','1','2')
        with patch.object(self.app,'job'),patch.object(self.app,'stop_playback'):
            p.toggle_block_card(1)
        self.assertEqual(p.input_blocks.selection(),('0','1','2'))
    def test_escape_cancels_placement_drag(self):
        ident=self.compose();p=self.page
        p.start_assembly(SimpleNamespace(widget=p.brick_tray,x=4,x_root=0,y_root=0),ident)
        p.composer_escape();self.assertIsNone(p.assembly_drag)

if __name__=='__main__':unittest.main()
