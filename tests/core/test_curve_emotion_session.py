"""Actual emotion rules through the lead's transaction and persistence gates."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import curve_emotion
import curve_melody
import curve_project as m
import curve_workflow as w
from test_curve_memory import points
from test_curve_melody import source, base


def controller():
    src=source('actual-rules')
    item=curve_melody.derive(base(src),'answer',seed=31)
    p=m.new_project();p['sources']=[src];p['materials']=[item]
    c=w.Controller(p)
    c.edit('place',material_id=item['id'],start_tick=0,placement_id='first')
    c.edit('place',material_id=item['id'],start_tick=5000,placement_id='second')
    return c


class IntegratedEmotion(unittest.TestCase):
    def test_repeated_uses_a_b_a_are_independent_from_current_base(self):
        c=controller();library=copy.deepcopy(c.project['materials']);sources=copy.deepcopy(c.project['sources'])
        c.edit('set_emotion',placement_ids=['first'],emotion='hope')
        first=copy.deepcopy(c.project['placements'][0]['emotion_variant'])
        c.edit('set_emotion',placement_ids=['second'],emotion='hope')
        second=copy.deepcopy(c.project['placements'][1]['emotion_variant'])
        self.assertTrue(second['generation']['melody_changed'])
        self.assertEqual(second['generation']['base_notes'],c.project['placements'][1]['base_snapshot']['notes'])
        c.edit('set_emotion',placement_ids=['second'],emotion='sad')
        self.assertNotEqual(second,c.project['placements'][1]['emotion_variant'])
        c.edit('set_emotion',placement_ids=['second'],emotion='hope')
        self.assertEqual(second,c.project['placements'][1]['emotion_variant'])
        self.assertEqual(first,c.project['placements'][0]['emotion_variant'])
        self.assertEqual(c.project['materials'],library);self.assertEqual(c.project['sources'],sources)
        before=c.project
        self.assertFalse(c.edit('set_emotion',placement_ids=['second'],emotion='hope'))
        self.assertEqual(c.project,before)

    def test_peak_transfer_recomputes_complete_current_variant_protection_and_undo(self):
        c=controller();c.edit('set_emotion',placement_ids=['first','second'],emotion='crisis')
        before=c.project
        c.edit('set_intensity',points=points(c.project['total_ticks'],7000))
        info=c.state()['memory_info'];self.assertEqual(info['placement_id'],'second')
        lock=next(p for p in c.project['protections'] if p['kind']=='memory')
        self.assertEqual((lock['start_tick'],lock['end_tick']),(6920,8840))
        actual={n['id']:n for p in c.project['placements'] for n in m.placed_notes(p)}
        for n in lock['notes']:
            self.assertEqual({k:v for k,v in n.items() if k!='velocity'},
                             {k:v for k,v in actual[n['id']].items() if k!='velocity'})
        m.validate(c.project)
        self.assertTrue(c.undo());self.assertEqual(c.project,before)
        with tempfile.TemporaryDirectory() as tmp:
            saved=c.save_snapshot(Path(tmp)/'emotion.json');loaded=w.Controller();loaded.load(saved)
            self.assertEqual(loaded.project,c.project)

    def test_corrupt_algorithm_result_cannot_cross_protection_or_touch_saved_history(self):
        c=controller();c.edit('set_emotion',placement_ids=['first','second'],emotion='hope')
        c.session.mark_saved();before=c.project
        token=c.capture_job('AUDITION',dict(kind='placement',id='first'))['token']
        original=curve_emotion.emotion_variant
        def corrupt(*args,**kwargs):
            result=original(*args,**kwargs)
            protected={n['id'] for n in args[4]}
            note=next((n for n in result['notes'] if n['id'] in protected),None)
            if note:note['pitch']+=1
            return result
        with patch.object(curve_emotion,'emotion_variant',corrupt):
            with self.assertRaises(m.ProjectError):
                c.edit('set_intensity',points=points(c.project['total_ticks'],700))
        self.assertEqual(c.project,before);self.assertTrue(c.state()['is_saved'])
        self.assertTrue(c.accepts(token));self.assertTrue(c.state()['can_undo'])

    def test_emotion_change_then_undo_rejects_late_canceled_and_duplicate_batches(self):
        c=controller();material_id=c.project['materials'][0]['id']
        job=c.capture_job('DERIVE',dict(kind='material',id=material_id))
        batch=w.prepare_generation(job['snapshot']['project'],material_id,'rhythm')
        before=c.project
        c.edit('set_emotion',placement_ids=['second'],emotion='sad');c.undo()
        self.assertEqual(c.project,before);self.assertFalse(c.accepts(job['token']))
        self.assertFalse(c.cancel_job(job['token']));self.assertFalse(c.apply_batch(batch,job['token'])['changed'])
        current=c.capture_job('DERIVE',dict(kind='material',id=material_id))
        result=c.apply_batch(batch,current['token']);self.assertTrue(result['changed'])
        count=len(c.project['materials'])
        self.assertFalse(c.apply_batch(batch,current['token'])['changed'])
        self.assertEqual(len(c.project['materials']),count)


if __name__=='__main__':unittest.main()
