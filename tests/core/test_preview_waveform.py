import tempfile
from pathlib import Path
import unittest
import wave
import numpy as np
from preview_ui import waveform


class WaveformTests(unittest.TestCase):
    def test_waveform_matches_real_audio_and_preserves_silence(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.wav'
            tone=(np.sin(np.arange(800)*2*np.pi/40)*16000).astype('<i2')
            samples=np.concatenate([np.zeros(800,dtype='<i2'),tone])
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(samples.tobytes())
            values=waveform(path,8)
            self.assertEqual(len(values),8)
            self.assertEqual(values[:4],[0.]*4)
            self.assertTrue(all(.3<v<.4 for v in values[4:]))

    def test_short_unsigned_stereo_file_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'short.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(2);wav.setsampwidth(1);wav.setframerate(8000);wav.writeframes(bytes([128,128,255,255]))
            values=waveform(path,10)
            self.assertEqual(len(values),10)
            self.assertGreater(max(values),.9)
            self.assertTrue(all(0<=v<=1 for v in values))

if __name__=='__main__':unittest.main()
