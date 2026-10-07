"""Mapped layout checks; these exercise shared widgets, not physical input."""
import unittest
from test_curve_ui import MappedUIFixture


class WorkspaceLayoutTests(MappedUIFixture):
    def test_two_themes_sizes_source_visibility_and_player_column(self):
        before=self.controller.state()['project']
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for width,height in ((1020,700),(1280,800),(1440,900)):
                self.root.geometry(f'{width}x{height}')
                for collapsed in (False,True):
                    self.app.source_user_collapsed=collapsed;self.app.layout_sources();self.root.update()
                    canvas=self.app.page.timeline.canvas
                    self.assertGreaterEqual(canvas.winfo_height(),320)
                    self.assertEqual(bool(self.app.page.source_panel.winfo_ismapped()),not collapsed)
                    self.assertEqual(self.app.page.middle.winfo_width(),252)
                    for widget in (self.app.play_button,self.app.stop_button,self.app.pause_button):
                        self.assertTrue(widget.winfo_ismapped())
                        self.assertGreaterEqual(widget.winfo_height(),44)
                        self.assertGreaterEqual(widget.winfo_rootx(),self.app.page.right.winfo_rootx())
                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),self.root.winfo_rootx()+width)
                    self.assertEqual(before,self.controller.state()['project'])

    def test_card_geometry_notes_and_real_focus_tooltip(self):
        cards=self.app.page.cards;card=cards.rows['phrase']
        self.assertEqual(card.winfo_height(),96)
        content=card.winfo_children()[0]
        thumbnails=[w for w in content.winfo_children() if w.winfo_class()=='Canvas']
        self.assertTrue(thumbnails[0].find_all())
        title=content.winfo_children()[0]
        tip=title.curve_tooltip
        title.focus_force();self.root.update();tip.show();self.root.update()
        self.assertTrue(tip.window.winfo_ismapped())
        self.assertIn('完整乐句',tip.window.winfo_children()[0].cget('text'))
        tip.hide();self.root.update();self.assertIsNone(tip.window)
