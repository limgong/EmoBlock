"""Portable contract tests; mocked afplay is NOT a Mac hardware/audio test."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import wave
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import check_frontends
import runtime_config

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

mac=load('test_macos_player','frontend/macos/audio_player.py')
mac_ui=load('test_macos_ui','frontend/macos/ui_platform.py')
win_ui=load('test_windows_ui','frontend/windows/ui_platform.py')

class PlatformContracts(unittest.TestCase):
    def test_shared_contracts(self):self.assertEqual(check_frontends.check(),[])
    def test_font_and_wheel(self):
        self.assertEqual(mac_ui.font_family('Microsoft YaHei UI'),'PingFang SC')
        self.assertEqual(win_ui.font_family('Microsoft YaHei UI'),'Microsoft YaHei UI')
        self.assertEqual(win_ui.wheel_units(120),-1)
        self.assertEqual(mac_ui.wheel_units(2),-2)
        self.assertEqual(mac_ui.wheel_units(-.2),1)
    def test_context_and_window(self):
        self.assertTrue(mac_ui.NATIVE_CHROME);self.assertFalse(win_ui.NATIVE_CHROME)
        self.assertIn('<Control-Button-1>',mac_ui.CONTEXT_EVENTS)
        root=Mock();app=Mock();mac_ui.setup_window(root,app)
        self.assertEqual(root.bind.call_count,3)
        root.createcommand.assert_called_once_with('tk::mac::Quit',app.close)
    def test_range_rejects_invalid(self):
        for a,b in ((2,1),(-1,1),(0,11),(1,1),(float('nan'),2)):
            with self.assertRaises(ValueError):mac.playback_range(10,a,b)
        self.assertEqual(mac.playback_range(10,2,4),(2000,4000))
    def test_backend_imports_without_gui(self):
        code='from emoblocks_bootstrap import configure; configure(include_frontend=False); import story_engine; import sys; assert "tkinter" not in sys.modules; assert "audio_player" not in sys.modules'
        subprocess.run([sys.executable,'-c',code],cwd=str(ROOT),check=True,capture_output=True)
    def test_sample_discovery_mac_bundle(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{},clear=True):
            bundle=Path(folder)/'LMMS.app/Contents'
            sample=bundle/'Resources/samples/drums/snare01.ogg';sample.parent.mkdir(parents=True);sample.touch()
            self.assertEqual(runtime_config.sample_path(bundle/'MacOS/lmms','snare01.ogg'),sample)
    def test_explicit_lmms_and_missing_samples(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'EMOBLOCKS_LMMS':folder+'/lmms','EMOBLOCKS_LMMS_DATA':folder},clear=True):
            self.assertEqual(runtime_config.find_lmms('darwin'),Path(folder)/'lmms')
            with self.assertRaises(ValueError):runtime_config.sample_path(Path(folder)/'lmms','does-not-exist.ogg')

class MacPlaybackSimulation(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'source.wav'
        with wave.open(str(self.path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(1000)
            f.writeframes(np.full(5000,16000,dtype='<i2').tobytes())
        self.stream=Mock()
        self.device=Mock(OutputStream=Mock(return_value=self.stream),CallbackStop=type('CallbackStop',(Exception,),{}))
        self.output=patch.object(mac,'_sounddevice',return_value=self.device)
        self.output.start()
        self.player=mac.WavePlayer()
    def tearDown(self):
        self.player.quiet.set();self.player.close();self.output.stop();self.folder.cleanup()

    def output_frames(self,count):
        frames=np.empty((count,1),dtype=np.float32)
        self.player._output(frames,count,None,None)
        return frames[:,0]

    def test_segment_and_playback_position(self):
        self.assertEqual(self.player.play(self.path,1,3),5)
        self.assertEqual(len(self.player.samples),2000)
        self.device.OutputStream.assert_called_once()
        self.stream.start.assert_called_once()
        first=self.output_frames(20)
        self.assertLess(abs(first[0]),abs(first[-1]))
        self.assertEqual(self.player.status(),(1.02,'playing'))

    def test_pause_resume_fades_without_advancing_silent_position(self):
        self.player.play(self.path,1,4)
        before=self.output_frames(20)
        self.player.pause();fade=self.output_frames(20)
        self.assertGreater(abs(fade[0]),abs(fade[-1]))
        self.assertLess(np.max(np.abs(np.diff(np.r_[before,fade]))),.05)
        position=self.player.status()[0]
        self.assertEqual(self.player.status()[1],'paused')
        self.assertTrue(np.all(self.output_frames(20)==0))
        self.assertEqual(self.player.status()[0],position)
        self.player.resume();ramp=self.output_frames(20)
        self.assertLess(abs(ramp[0]),abs(ramp[-1]))
        self.assertLess(np.max(np.abs(np.diff(np.r_[fade[-1],ramp]))),.05)
        self.assertEqual(self.player.status()[1],'playing')

    def test_replay_closes_previous_stream(self):
        self.player.play(self.path)
        self.player.quiet.set()
        self.player.play(self.path,2,3)
        self.stream.close.assert_called_once()
        self.assertEqual(self.player.status(),(2,'playing'))

    def test_failed_device_open_cleans_player(self):
        self.stream.start.side_effect=OSError('missing output device')
        with self.assertRaises(OSError):self.player.play(self.path)
        self.assertIsNone(self.player.stream);self.assertFalse(self.player.opened)

    def test_end_fades_to_silence(self):
        self.player.play(self.path,4.98,5)
        with self.assertRaises(self.device.CallbackStop):self.output_frames(20)
        self.player._finished()
        self.assertEqual(self.player.status(),(5,'stopped'))

if __name__=='__main__':unittest.main()
