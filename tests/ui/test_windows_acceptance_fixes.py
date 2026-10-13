import os
import tkinter as tk
from test_curve_ui import MappedUIFixture


class AcceptanceFixTests(MappedUIFixture):
    def test_windows_chrome_is_borderless_with_working_controls(self):
        if os.name!='nt':self.skipTest('Windows chrome')
        self.assertTrue(self.root.overrideredirect())
        self.assertEqual(len(self.app.window_chrome.buttons),3)

    def test_large_window_scales_rails_and_fits_short_score(self):
        self.root.geometry('1280x800');self.root.update()
        before=self.app.page.middle.winfo_width()
        self.root.geometry('2400x1300');self.root.update()
        self.app.apply_workspace_scale();self.root.update()
        self.assertGreater(self.app.page.middle.winfo_width(),before*1.3)
        timeline=self.app.page.timeline
        self.assertGreater(timeline.x(timeline.project['total_ticks']),timeline.canvas.winfo_width()*.9)
        self.assertLessEqual(timeline.x(timeline.project['total_ticks'])+timeline.margin,timeline.canvas.winfo_width()+1)

    def test_transport_uses_block_choices_instead_of_native_popups(self):
        self.assertNotEqual(self.app.block_selector.winfo_class(),'TCombobox')
        self.assertNotEqual(self.app.version_selector.winfo_class(),'TCombobox')

    def test_material_library_has_page_navigation_without_side_scrollbar(self):
        cards=self.app.page.cards
        self.assertFalse(cards.scrollbar.winfo_manager())
        self.assertTrue(cards.pager.winfo_ismapped())

    def test_keyboard_focus_reveals_offscreen_block_choice(self):
        from curve_choices import BlockChoices
        choices=BlockChoices(self.root,self.app,textvariable=tk.StringVar(self.root))
        choices.place(x=0,y=0)
        choices.configure(values=['one','two','three','four'],state='readonly')
        self.root.update()
        choices.canvas.xview_moveto(0)
        previous=choices.variable.get()
        choices.buttons[3].focus_force();self.root.update()
        self.assertEqual(choices.variable.get(),previous)
        button=choices.buttons[3]
        self.assertGreaterEqual(button.winfo_rootx(),choices.canvas.winfo_rootx())
        self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),
                             choices.canvas.winfo_rootx()+choices.canvas.winfo_width())
        button.event_generate('<Left>');self.root.update()
        self.assertEqual(choices.current(),2)

    def test_destroy_cancels_pending_resize_layout(self):
        from types import SimpleNamespace
        self.app.resized(SimpleNamespace(widget=self.root,width=1280,height=800))
        timer=self.app.layout_timer
        self.assertIsNotNone(timer)
        self.root.destroy()
        self.assertNotIn(timer,self.root.tk.call('after','info'))

    def test_block_choice_canvases_follow_theme_without_resizing(self):
        for _ in range(2):
            self.app.toggle_theme();self.root.update()
            for choices in (self.app.block_selector,self.app.version_selector,self.app.page.history_mode):
                self.assertEqual(choices.canvas.cget('bg'),self.app.theme.colors['panel'])

    def test_minimize_restore_rebinds_native_file_drop(self):
        if os.name!='nt':self.skipTest('Windows native file drop')
        from file_drop import FileDrop
        self.app.file_drop.close()
        original=self.app.file_drop=FileDrop(self.root,self.app.drop_files)
        self.app.window_chrome.minimize();self.root.update()
        self.root.deiconify();self.root.update()
        self.assertTrue(original.closed)
        current=self.app.file_drop
        self.assertIsNot(current,original)
        self.assertFalse(current.closed)
        self.assertEqual(current.hwnd,current.user.GetParent(self.root.winfo_id()))
        self.assertTrue(self.root.overrideredirect())
