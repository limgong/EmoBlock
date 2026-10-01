import copy
import unittest
import story_engine as e
import emotion_input
from test_story import fixture


def sustained():
    p=fixture();p['duration']=8
    s=p['sources'][0];s['ticks']=16*480
    s['notes']=[dict(pitch=60,start=0,duration=8*480,velocity=80),
                dict(pitch=60,start=8*480,duration=4*480,velocity=80),
                dict(pitch=60,start=12*480,duration=4*480,velocity=80)]
    return emotion_input.normalize(p)


class MelodyContinuityTests(unittest.TestCase):
    def test_long_note_tied_repeated_notes_separate(self):
        q=e.plan(sustained());events,joined=e.continuous_melody(q)
        self.assertEqual(joined,1);self.assertEqual(len(events),3)
        self.assertEqual([n['duration'] for n in events],[3840,1920,1920])

    def test_solo_same_structure_one_instrument(self):
        p=sustained();q=e.plan(p);baseline=copy.deepcopy(q['blocks'])
        q['project']['melody_only']=True;score=e.compile_score(q)
        self.assertEqual(q['blocks'],baseline);self.assertEqual(len(score['layers']),1)
        self.assertEqual(score['layers'][0]['preset'],'soft')
        self.assertEqual(len(score['layers'][0]['notes']),3)
        self.assertEqual(score['report']['render_mode'],'melody_only')
        self.assertTrue(all(n.velocity==80 for n in score['layers'][0]['notes']))

    def test_timbre_change_does_not_retrigger_long_note(self):
        q=e.plan(sustained());q['blocks'][1]['emotion']='resolve'
        score=e.compile_score(q)
        notes=[n for l in score['layers'] if l['name'].startswith('melody_') for n in l['notes']]
        self.assertEqual(len(notes),3);self.assertTrue(any(n.start==0 and n.duration==3840 for n in notes))

    def test_generated_connection_not_tied_to_source(self):
        q=e.plan(sustained());q['blocks'][1]['notes']=[dict(pitch=60,start=0,duration=1920,velocity=80)]
        events,joined=e.continuous_melody(q)
        self.assertEqual(joined,0);self.assertEqual(len(events),4)

    def test_distinct_repetition_not_merged(self):
        p=sustained();p['duration']=16;q=e.plan(p)
        events,_=e.continuous_melody(q)
        self.assertTrue(any(n['start']==7680 for n in events))

    def test_compile_does_not_mutate_plan(self):
        q=e.plan(sustained());before=copy.deepcopy(q);e.compile_score(q)
        self.assertEqual(q,before)


if __name__=='__main__':unittest.main()
