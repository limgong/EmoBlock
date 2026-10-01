import unittest
import default_melody
import block_audition as a
from audio_player import playback_range


class BlockAuditionTests(unittest.TestCase):
    def test_source_four_beat_blocks(self):
        s=default_melody.source();rows=a.source_blocks(s,120)
        self.assertEqual(len(rows),8)
        self.assertEqual(rows[1]['start_seconds'],2)
        self.assertEqual(rows[-1]['end_seconds'],16)
        self.assertTrue(all(r['end_tick']-r['start_tick']==1920 for r in rows))

    def test_tempo_conversion(self):
        rows=a.source_blocks(default_melody.source(),65)
        self.assertAlmostEqual(rows[0]['end_seconds'],240/65)

    def test_sustained_note_display_and_partial_tail(self):
        s=dict(name='test',ticks=2400,notes=[dict(pitch=60,start=0,duration=2400,velocity=80)])
        rows=a.source_blocks(s,120)
        self.assertTrue(rows[1]['notes'][0]['continuation'])
        self.assertEqual(rows[1]['notes'][0]['duration'],480)

    def test_rest_block(self):
        s=dict(name='test',ticks=3840,notes=[dict(pitch=60,start=1920,duration=480,velocity=80)])
        self.assertEqual(a.source_blocks(s,120)[0]['notes'],[])

    def test_play_range(self):
        self.assertEqual(playback_range(10,2,4),(2000,4000))
        self.assertEqual(playback_range(10),(0,10000))
        for start,end in ((-1,2),(2,2),(3,2),(0,11),(float('nan'),3)):
            with self.assertRaises(ValueError):playback_range(10,start,end)


if __name__=='__main__':unittest.main()
