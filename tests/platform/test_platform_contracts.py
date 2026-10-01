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
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(1000);f.writeframes(b'\0\0'*5000)
        self.process=Mock();self.process.poll.return_value=None;self.process.pid=123
        self.player=mac.WavePlayer()
    def tearDown(self):self.player.close();self.folder.cleanup()
    def test_segment_has_correct_frames(self):
        with patch.object(mac.subprocess,'Popen',return_value=self.process) as spawn:
            self.assertEqual(self.player.play(self.path,1,3),5)
        clip=self.player.temp
        with wave.open(str(clip),'rb') as f:self.assertEqual(f.getnframes(),2000)
        self.assertEqual(spawn.call_args[0][0],['/usr/bin/afplay',str(clip)])
        self.player.close();self.assertFalse(clip.exists());self.process.terminate.assert_called_once()
    def test_pause_resume_position(self):
        with patch.object(mac.subprocess,'Popen',return_value=self.process),patch.object(mac.time,'monotonic',return_value=10):self.player.play(self.path,1,4)
        with patch.object(mac.os,'kill') as kill,patch.object(mac.signal,'SIGSTOP',19,create=True),patch.object(mac.signal,'SIGCONT',18,create=True):
            with patch.object(mac.time,'monotonic',return_value=11):self.player.pause()
            self.assertEqual(self.player.status(),(2,'paused'));kill.assert_called_with(123,19)
            with patch.object(mac.time,'monotonic',return_value=20):self.player.resume()
            kill.assert_called_with(123,18)
        with patch.object(mac.time,'monotonic',return_value=20.5):self.assertEqual(self.player.status(),(2.5,'playing'))
    def test_failed_launch_cleans_clip(self):
        with patch.object(mac.subprocess,'Popen',side_effect=OSError('missing afplay')):
            with self.assertRaises(OSError):self.player.play(self.path)
        self.assertIsNone(self.player.temp);self.assertFalse(self.player.opened)
    def test_exit_and_errors(self):
        with patch.object(mac.subprocess,'Popen',return_value=self.process):self.player.play(self.path)
        self.process.poll.return_value=0;self.assertEqual(self.player.status(),(5,'stopped'))
        self.process.poll.return_value=1
        with self.assertRaises(ValueError):self.player.status()

if __name__=='__main__':unittest.main()
