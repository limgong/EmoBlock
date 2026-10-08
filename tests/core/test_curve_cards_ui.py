"""Phrase children, real cross-widget drag/drop, and inline combination commits."""
import copy
import tkinter as tk
from unittest.mock import Mock, patch
from test_curve_ui import MappedUIFixture, fixture


class CurveCardsTests(MappedUIFixture):
    def test_large_library_mounts_viewport_and_hits_first_last_real_coordinates(self):
        self.controller._project=fixture(extra=198)
        self.app.refresh();self.root.update();cards=self.app.page.cards
        self.assertEqual(len(list(cards.visible_materials())),201)
        self.assertLess(len(cards.rows),12)
        before=copy.deepcopy(self.controller.state())
        for fraction,ident in ((0,'child0'),(1,'extra197')):
            cards.canvas.yview_moveto(fraction);self.root.update()
            row=cards.rows[ident]
            y=max(cards.canvas.winfo_rooty()+1,row.winfo_rooty()+10)
            hit=cards.at_root(row.winfo_rootx()+10,y)
            self.assertEqual(hit,(ident,'left'))
            cards.select(self.app.resolve('material',ident));self.root.update()
            self.assertEqual(self.app.selected_material_id,ident)
            self.assertLess(len(cards.rows),12)
        self.assertEqual(self.controller.state(),before)
        self.assertFalse(self.app.player.calls)

    def test_same_id_changed_snapshot_selection_theme_and_scroll_rebind(self):
        cards=self.app.page.cards
        material=self.app.resolve('material','block')
        old=cards.rows['block']
        self.app.select_target('material','block');self.root.update()
        selected=cards.rows['block'];self.assertIsNot(old,selected)
        # Immutable full DTO comparison, including provenance fields, not just ID/name.
        self.controller._project['materials'][4]['provenance']['ui_fixture_revision']=2
        self.app.refresh();self.root.update();fresh=cards.rows['block']
        self.assertIsNot(selected,fresh)
        event=self.event(fresh,18,18)
        capture=Mock()
        self.app.begin_material_drag=capture
        fresh.event_generate('<ButtonPress-1>',x=18,y=18);self.root.update()
        self.assertEqual(capture.call_args.args[1]['provenance']['ui_fixture_revision'],2)
        view=cards.canvas.yview()[0]
        self.app.toggle_theme();self.root.update()
        self.assertIsNot(fresh,cards.rows['block'])
        self.assertAlmostEqual(cards.canvas.yview()[0],view,places=5)
        self.assertEqual(self.app.selected_material_id,'block')

    def test_dragged_card_survives_viewport_scroll_until_cancel(self):
        self.controller._project=fixture(extra=198)
        self.app.refresh();self.root.update();cards=self.app.page.cards
        for use_title in (False,True):
            cards.canvas.yview_moveto(0);self.root.update()
            card=cards.rows['child0']
            widget=card.winfo_children()[0].winfo_children()[0] if use_title else card
            start=self.event(widget,18,18)
            self.app.begin_material_drag(start,self.app.resolve('material','child0'),card)
            self.app.material_motion(self.event(widget,40,40))
            cards.canvas.yview_moveto(1);self.root.update()
            self.assertIs(cards.rows['child0'],card)
            self.assertTrue(widget.winfo_exists())
            self.assertEqual(self.root.grab_current(),widget)
            self.app.cancel_interaction();cards.render();self.root.update()
            self.assertNotIn('child0',cards.rows)
            self.assertIsNone(self.root.grab_current())

    def test_only_leaf_cards_and_generated_phrase_children_remain_independent(self):
        cards=self.app.page.cards
        self.assertIsInstance(cards.canvas,tk.Canvas)
        self.assertNotIn('phrase',cards.rows)
        # child1 duplicates the independent standard block and is hidden.
        self.assertNotIn('child1',cards.rows)
        self.assertIn('child0',cards.rows)
        self.controller._project['materials'][0]['generation']={'method':'answer'}
        self.app.refresh();self.root.update()
        self.assertNotIn('phrase',cards.rows)
        self.assertIn('child1',cards.rows)
        self.assertEqual({row.winfo_height() for row in cards.rows.values()},{cards.CARD_HEIGHT})
        child=self.app.resolve('material','child1');cards.select(child)
        self.assertEqual(self.app.selected_material_id,'child1')
        self.assertEqual(child['phrase_id'],'phrase')
        self.assertEqual(child['provenance']['relative_start_tick'],1920)
        self.assertFalse(self.app.player.calls)

    def drag(self, source_id, x_root, y_root):
        cards=self.app.page.cards
        card=cards.rows[source_id]
        event=self.event(card,18,18)
        self.app.begin_material_drag(event,self.app.resolve('material',source_id),card)
        end=self.event(card,x_root-card.winfo_rootx(),y_root-card.winfo_rooty())
        self.app.material_motion(end);self.app.material_release(end)

    def test_real_card_to_canvas_grab_offset_and_cancel(self):
        cards=self.app.page.cards
        cards.canvas.yview_moveto(0);self.root.update()
        canvas=self.app.page.timeline
        x=canvas.canvas.winfo_rootx()+canvas.x(960)+18
        y=canvas.canvas.winfo_rooty()+canvas.y(.25)
        self.drag('child0',x,y)
        project=self.controller.state()['project']
        self.assertEqual(project['placements'][0]['start_tick'],960)
        self.assertEqual(project['placements'][0]['length_ticks'],1920)
        before=copy.deepcopy(project)
        card=cards.rows['child0']
        start=self.event(card,18,18)
        self.app.begin_material_drag(start,self.app.resolve('material','child0'),card)
        self.app.material_motion(self.event(card,100,100))
        self.app.cancel_interaction()
        self.app.material_release(self.event(card,150,100))
        self.assertEqual(before,self.controller.state()['project'])

    def test_expanded_child_real_drag_retains_parent_and_note_origin(self):
        cards=self.app.page.cards
        self.controller._project['materials'][0]['generation']={'method':'answer'}
        self.app.refresh();self.root.update()
        row=cards.rows['child1']
        cards.canvas.yview_moveto(row.winfo_y()/cards.body.winfo_height());self.root.update()
        self.assertGreaterEqual(row.winfo_rooty(),cards.canvas.winfo_rooty()-2)
        canvas=self.app.page.timeline
        self.drag('child1',canvas.canvas.winfo_rootx()+canvas.x(480)+18,
                  canvas.canvas.winfo_rooty()+canvas.y(.25))
        placed=self.controller.state()['project']['placements'][0]
        self.assertEqual(placed['start_tick'],480)
        self.assertEqual(placed['base_snapshot']['phrase_id'],'phrase')
        self.assertEqual(placed['base_snapshot']['notes'][0]['origin']['source_note_id'],'long')
        self.assertEqual(placed['base_snapshot']['notes'][0]['slice']['offset_tick'],120)

    def test_left_right_modal_cancel_confirm_and_one_undo(self):
        cards=self.app.page.cards;before=self.controller.state()['project']
        target=cards.rows['block'];self.root.update()
        with patch('curve_ui.messagebox.askokcancel',return_value=False) as confirm:
            self.drag('child0',target.winfo_rootx()+8,target.winfo_rooty()+30)
        self.assertEqual(before,self.controller.state()['project'])
        self.assertFalse(self.app.combo_inputs)
        self.assertFalse(self.app.page.combo_panel.winfo_ismapped())
        self.assertIn('8拍',confirm.call_args.args[1])
        cards.canvas.yview_moveto(0);self.root.update();target=cards.rows['block']
        with patch('curve_ui.messagebox.askokcancel',return_value=True):
            self.drag('child0',target.winfo_rootx()+target.winfo_width()-8,target.winfo_rooty()+30)
        self.finish_jobs();after=self.controller.state()['project']
        self.assertEqual(len(after['materials']),len(before['materials'])+1)
        combo=after['materials'][-1]
        self.assertEqual(combo['kind'],'combination')
        self.assertEqual([c['snapshot']['id'] for c in combo['children']],['block','child0'])
        self.assertFalse(self.app.player.calls)
        self.app.undo();self.assertEqual(before,self.controller.state()['project'])

    def test_repeated_nested_draft_keeps_snapshots_and_cancelled_job_is_inert(self):
        before=self.controller.state()['project']
        source=self.app.resolve('material','block')
        self.app.add_combo(source,'block','left')
        self.assertEqual([m['id'] for m in self.app.combo_inputs],['block','block'])
        self.app.confirm_combo();self.finish_jobs()
        combination=self.controller.state()['project']['materials'][-1]
        self.assertNotEqual(combination['children'][0]['occurrence_id'],combination['children'][1]['occurrence_id'])
        self.app.add_combo(combination,'block','right')
        self.app.confirm_combo();self.finish_jobs()
        nested=self.controller.state()['project']['materials'][-1]
        self.assertEqual(nested['children'][1]['snapshot']['kind'],'combination')
        self.app.undo();self.app.undo();self.assertEqual(before,self.controller.state()['project'])

    def test_tk_generated_drag_events_and_edge_scroll(self):
        cards=self.app.page.cards
        source=cards.rows['child0']
        canvas=self.app.page.timeline
        source.event_generate('<ButtonPress-1>',x=18,y=18)
        x=int(canvas.canvas.winfo_rootx()+canvas.x(960)+18-source.winfo_rootx())
        y=int(canvas.canvas.winfo_rooty()+canvas.y(.25)-source.winfo_rooty())
        source.event_generate('<B1-Motion>',x=x,y=y,state=256)
        source.event_generate('<ButtonRelease-1>',x=x,y=y)
        self.root.update()
        self.assertEqual(self.controller.state()['project']['placements'][0]['start_tick'],960)
        source=cards.rows['child0']
        start=self.event(source,18,18)
        self.app.begin_material_drag(start,self.app.resolve('material','child0'),source)
        x=cards.canvas.winfo_rootx()+30
        y=cards.canvas.winfo_rooty()+cards.canvas.winfo_height()-5
        self.app.material_motion(self.event(source,x-source.winfo_rootx(),y-source.winfo_rooty()))
        before=cards.canvas.yview()[0]
        self.root.after_cancel(self.app.card_scroll_timer)
        self.app.card_scroll_timer=None
        self.app.cards_edge_step()
        self.assertGreater(cards.canvas.yview()[0],before)
        self.app.cancel_interaction()
