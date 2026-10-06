"""Phrase children, real cross-widget drag/drop, and inline combination commits."""
import copy
import tkinter as tk
from test_curve_ui import MappedUIFixture


class CurveCardsTests(MappedUIFixture):
    def test_phrase_expands_equal_cards_and_child_remains_independent(self):
        cards=self.app.page.cards
        self.assertIsInstance(cards.canvas,tk.Canvas)
        self.assertNotIn('child1',cards.rows)
        cards.toggle('phrase');self.root.update()
        self.assertIn('child1',cards.rows)
        self.assertEqual({row.winfo_height() for row in cards.rows.values()},{cards.CARD_HEIGHT})
        child=self.app.resolve('material','child1')
        cards.select(child)
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
        self.drag('phrase',x,y)
        project=self.controller.state()['project']
        self.assertEqual(project['placements'][0]['start_tick'],960)
        self.assertEqual(project['placements'][0]['length_ticks'],4080)
        before=copy.deepcopy(project)
        card=cards.rows['phrase']
        start=self.event(card,18,18)
        self.app.begin_material_drag(start,self.app.resolve('material','phrase'),card)
        self.app.material_motion(self.event(card,100,100))
        self.app.cancel_interaction()
        self.app.material_release(self.event(card,150,100))
        self.assertEqual(before,self.controller.state()['project'])

    def test_expanded_child_real_drag_retains_parent_and_note_origin(self):
        cards=self.app.page.cards
        cards.toggle('phrase');self.root.update()
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

    def test_left_right_draft_cancel_confirm_and_one_undo(self):
        cards=self.app.page.cards
        target=cards.rows['block'];self.root.update()
        before=self.controller.state()['project']
        self.drag('phrase',target.winfo_rootx()+8,target.winfo_rooty()+30)
        self.assertEqual([m['id'] for m in self.app.combo_inputs],['phrase','block'])
        self.assertEqual(before,self.controller.state()['project'])
        self.app.cancel_combo();self.assertEqual(before,self.controller.state()['project'])
        cards.canvas.yview_moveto(0);self.root.update()
        target=cards.rows['block']
        self.drag('phrase',target.winfo_rootx()+target.winfo_width()-8,target.winfo_rooty()+30)
        self.assertEqual([m['id'] for m in self.app.combo_inputs],['block','phrase'])
        self.app.prepare_combo();self.finish_jobs()
        self.assertFalse(self.app.player.calls)
        self.assertEqual(before,self.controller.state()['project'])
        self.app.confirm_combo();self.finish_jobs()
        after=self.controller.state()['project']
        self.assertEqual(len(after['materials']),len(before['materials'])+1)
        self.assertEqual(after['materials'][-1]['kind'],'combination')
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
        source=cards.rows['phrase']
        canvas=self.app.page.timeline
        source.event_generate('<ButtonPress-1>',x=18,y=18)
        x=int(canvas.canvas.winfo_rootx()+canvas.x(960)+18-source.winfo_rootx())
        y=int(canvas.canvas.winfo_rooty()+canvas.y(.25)-source.winfo_rooty())
        source.event_generate('<B1-Motion>',x=x,y=y,state=256)
        source.event_generate('<ButtonRelease-1>',x=x,y=y)
        self.root.update()
        self.assertEqual(self.controller.state()['project']['placements'][0]['start_tick'],960)
        source=cards.rows['phrase']
        start=self.event(source,18,18)
        self.app.begin_material_drag(start,self.app.resolve('material','phrase'),source)
        x=cards.canvas.winfo_rootx()+30
        y=cards.canvas.winfo_rooty()+cards.canvas.winfo_height()-5
        self.app.material_motion(self.event(source,x-source.winfo_rootx(),y-source.winfo_rooty()))
        before=cards.canvas.yview()[0]
        self.root.after_cancel(self.app.card_scroll_timer)
        self.app.card_scroll_timer=None
        self.app.cards_edge_step()
        self.assertGreater(cards.canvas.yview()[0],before)
        self.app.cancel_interaction()
