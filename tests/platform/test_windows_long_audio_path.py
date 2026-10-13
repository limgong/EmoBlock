"""Exercise the native player with Unicode paths beyond MCI string limits."""
import os
from pathlib import Path
import tempfile
import unittest
import wave
from audio_player import WavePlayer


@unittest.skipUnless(os.name == 'nt', 'Windows native MCI')
class LongAudioPathTests(unittest.TestCase):
    def test_long_unicode_path_plays_and_releases_private_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)/('较长音频目录'*12)/('nested English '*4).rstrip()
            directory.mkdir(parents=True)
            path=directory/'试听 成品.wav'
            with wave.open(str(path),'wb') as out:
                out.setparams((1,2,44100,0,'NONE','not compressed'))
                out.writeframes(b'\0\0'*44100)
            self.assertGreater(len(str(path)),160)
            player=WavePlayer()
            try:
                self.assertAlmostEqual(player.play(path),1.,places=2)
                private=Path(player.playback_copy.name)
                player.pause()
                self.assertEqual(player.status()[1],'paused')
                player.resume()
            finally:player.close()
            self.assertTrue(path.is_file())
            self.assertFalse(player.opened)
            self.assertFalse(private.exists())
