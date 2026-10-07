"""Semantic themes and mapped responsive geometry; no claims of visual acceptance."""
from test_curve_ui import MappedUIFixture
import tkinter as tk
from curve_theme import PALETTES, EMOTION_COLORS, EMOTION_INK
from tkinter import ttk


def luminance(color):
    rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))


class CurveThemeTests(MappedUIFixture):
    def test_exact_dark_surfaces_and_body_contrast(self):
        dark=PALETTES['dark']
        self.assertIsInstance(self.root,tk.Tk)
        self.assertEqual([dark[k] for k in ('bg','panel','inset','accent')],['#1c1c1e','#2c2c2e','#3a3a3c','#0a84ff'])
        for palette in PALETTES.values():
            for text in ('ink','muted'):
                for surface in ('bg','panel','inset'):
                    a,b=sorted([luminance(palette[text]),luminance(palette[surface])])
                    self.assertGreaterEqual((b+.05)/(a+.05),4.5)
        for fill in EMOTION_COLORS.values():
            a,b=sorted([luminance(EMOTION_INK),luminance(fill)])
            self.assertGreaterEqual((b+.05)/(a+.05),4.5)
        self.app.toggle_theme()
        style=ttk.Style(self.root)
        for name in ('Curve.TButton','Curve.Primary.TButton'):
            self.assertEqual(style.lookup(name,'background'),'#3a3a3c')
            foreground=style.lookup(name,'foreground')
            a,b=sorted([luminance(foreground),luminance('#3a3a3c')])
            self.assertGreaterEqual((b+.05)/(a+.05),4.5)

    def test_window_sizes_theme_selection_scroll_model_and_player_preserved(self):
        self.app.select_target('material','extra3')
        self.app.prepare_selected();self.finish_jobs();self.app.play_selected()
        self.app.page.cards.canvas.yview_moveto(.4)
        self.app.page.timeline.canvas.xview_moveto(.2)
        before=self.controller.state()['project']
        playing=self.app.playing_target.copy()
        calls=list(self.app.player.calls)
        for width,height in ((1020,700),(1280,800),(1440,900)):
            self.root.geometry(f'{width}x{height}');self.root.update()
            self.assertEqual(bool(self.app.page.source_panel.winfo_manager()),width>=1180)
            self.assertGreater(self.app.page.timeline.canvas.winfo_width(),380)
            # Preparation is now part of one explicit audition; cancellation is
            # conditional on an active job. Check the persistent transport here.
            for button in (self.app.play_button,self.app.pause_button,self.app.stop_button,
                           self.app.page.final_button,self.app.page.derive_button,self.app.page.resize_button):
                self.assertTrue(button.winfo_ismapped())
                self.assertGreaterEqual(button.winfo_height(),40)
                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.root.winfo_rooty()+height)
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+width)
            selected=self.app.selected_target
            scroll=self.app.page.cards.canvas.yview()[0]
            self.app.toggle_theme();self.root.update()
            self.assertEqual(self.app.selected_target,selected)
            self.assertAlmostEqual(self.app.page.cards.canvas.yview()[0],scroll,places=2)
            self.assertEqual(self.controller.state()['project'],before)
            self.assertEqual(self.app.playing_target,playing)
            self.assertEqual(self.app.player.calls,calls)
        self.assertTrue(self.app.page.final_button.instate(['disabled']))

    def test_wheel_routes_once_and_text_shortcuts_keep_text_undo(self):
        canvas=self.app.page.timeline.canvas
        before=canvas.xview()[0]
        event=self.event(canvas,200,100)
        self.assertEqual(self.app.wheel(event),'break')
        self.assertGreater(canvas.xview()[0],before)
        entry=self.app.page.grid_entry
        event=self.event(entry,1,1)
        self.assertIsNone(self.app.edit_shortcut(event))
