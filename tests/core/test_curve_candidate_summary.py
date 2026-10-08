"""Actual pitch/rhythm differences survive equal titles, IDs and statistics."""
import unittest
from curve_candidate_summary import candidate_difference

class CandidateSummaryTests(unittest.TestCase):
    def candidate(self,ident,notes):return dict(id=ident,title='same',preview=dict(notes=notes))
    def test_first_musical_difference_not_names_or_velocity(self):
        notes=[dict(start_tick=0,pitch=60,duration_tick=480,velocity=80),dict(start_tick=480,pitch=64,duration_tick=240,velocity=80)]
        first=self.candidate('a',notes)
        second=self.candidate('b',[dict(notes[0],velocity=100),dict(notes[1],pitch=67)])
        self.assertEqual(candidate_difference(first,[first,second]),'差异位置·第2拍：E4·0.5拍')
        self.assertEqual(candidate_difference(second,[first,second]),'差异位置·第2拍：G4·0.5拍')
    def test_silence_and_identical_music_are_truthful(self):
        first=self.candidate('a',[dict(start_tick=480,pitch=60,duration_tick=960)])
        second=self.candidate('b',[])
        self.assertIn('留白',candidate_difference(second,[first,second]))
        same=self.candidate('c',first['preview']['notes'])
        self.assertIn('一致',candidate_difference(first,[first,same]))
