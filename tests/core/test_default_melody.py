import unittest
import default_melody
import emotion_input as ui
import story_engine as e


class DefaultMelodyTests(unittest.TestCase):
    def test_eight_complete_bars(self):
        s=default_melody.source();self.assertEqual(s['ticks'],8*1920)
        self.assertEqual(s['notes'][-1]['start']+s['notes'][-1]['duration'],s['ticks'])
        self.assertEqual(s['notes'][-1]['pitch'],60)
        self.assertTrue(s['source']['url'].startswith('https://www.mutopiaproject.org/'))

    def test_default_generates_without_input(self):
        p=ui.default_story();p['sources']=[default_melody.source()]
        e.validate(p);q=e.plan(p);score=e.compile_score(q)
        self.assertEqual(len(q['blocks']),13);self.assertTrue(score['layers'])

    def test_snapshot_not_shared(self):
        s=default_melody.source();s['notes'][0]['pitch']=99
        self.assertEqual(default_melody.source()['notes'][0]['pitch'],64)


if __name__=='__main__':unittest.main()
