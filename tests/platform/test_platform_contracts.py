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
    def test_open_folder_uses_platform_launcher_with_literal_path(self):
        with tempfile.TemporaryDirectory(prefix='folder with spaces ') as folder:
            with patch.object(mac_ui.subprocess,'run') as run:
                mac_ui.open_folder(folder);run.assert_called_once_with(['open',str(Path(folder).resolve())],check=True)
            with patch.object(win_ui.os,'startfile',create=True) as start:
                win_ui.open_folder(folder);start.assert_called_once_with(str(Path(folder).resolve()))
            for adapter in (mac_ui,win_ui):
                with self.assertRaises(ValueError):adapter.open_folder(Path(folder)/'missing')

    def test_windows_snapshot_shortcuts(self):
        root=Mock();app=Mock();win_ui.setup_window(root,app)
        self.assertEqual([call.args[0] for call in root.bind.call_args_list],['<Control-s>','<Control-o>'])
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
        self.assertEqual(root.bind.call_count,2)
        root.createcommand.assert_called_once_with('tk::mac::Quit',app.close)
    def test_edit_shortcuts_per_platform(self):
        from types import SimpleNamespace as E
        self.assertEqual(mac_ui.EDIT_SHORTCUT_EVENTS,('<Command-z>','<Command-Z>'))
        self.assertEqual((mac_ui.UNDO_LABEL,mac_ui.REDO_LABEL),('⌘Z','⇧⌘Z'))
        self.assertEqual(mac_ui.edit_shortcut(E(state=0,keysym='z')),'undo')
        self.assertEqual(mac_ui.edit_shortcut(E(state=0,keysym='Z')),'undo')  # Caps Lock without Shift
        self.assertEqual(mac_ui.edit_shortcut(E(state=1,keysym='Z')),'redo')
        self.assertEqual(win_ui.EDIT_SHORTCUT_EVENTS,('<Control-z>','<Control-y>'))
        self.assertEqual((win_ui.UNDO_LABEL,win_ui.REDO_LABEL),('Ctrl+Z','Ctrl+Y'))
        self.assertEqual(win_ui.edit_shortcut(E(state=4,keysym='z')),'undo')
        self.assertEqual(win_ui.edit_shortcut(E(state=4,keysym='y')),'redo')
        import tkinter as tk
        root=tk.Tk();root.withdraw()
        try:
            for sequence in mac_ui.EDIT_SHORTCUT_EVENTS+win_ui.EDIT_SHORTCUT_EVENTS:
                if 'Command' in sequence and root.tk.call('tk','windowingsystem')!='aqua':continue
                root.bind(sequence,lambda e:None)  # sequence must be valid Tk syntax
        finally:root.destroy()

    def test_canvas_delete_shortcuts_per_platform(self):
        self.assertEqual(mac_ui.DELETE_SHORTCUT_EVENTS, ('<BackSpace>', '<Delete>'))
        self.assertEqual(win_ui.DELETE_SHORTCUT_EVENTS, ('<Delete>',))
        self.assertIn('⌫', mac_ui.DELETE_LABEL)
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        try:
            canvas = tk.Canvas(root)
            for adapter in (mac_ui, win_ui):
                for sequence in adapter.DELETE_SHORTCUT_EVENTS:
                    canvas.bind(sequence, lambda event: 'break')
        finally:
            root.destroy()
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
        self.device.query_devices.return_value=dict(max_output_channels=2,default_samplerate=1000)
        self.device.PortAudioError=type('PortAudioError',(Exception,),{})
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

    def test_stereo_file_plays_on_mono_headset_without_changing_file(self):
        with wave.open(str(self.path),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(1000)
            f.writeframes(np.tile([16000,8000],(5000,1)).astype('<i2').tobytes())
        original=self.path.read_bytes()
        self.device.query_devices.return_value=dict(max_output_channels=1,default_samplerate=1000)
        self.assertEqual(self.player.play(self.path,1,3),5)
        self.assertEqual(self.player.samples.shape,(2000,1))
        self.assertAlmostEqual(float(self.player.samples[0,0]),12000/32768)
        self.assertEqual(self.device.OutputStream.call_args.kwargs['channels'],1)
        self.output_frames(20);self.assertEqual(self.player.status(),(1.02,'playing'))
        self.assertEqual(self.path.read_bytes(),original)

    def test_stereo_device_preserves_channels_and_source_rate(self):
        with wave.open(str(self.path),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(1000)
            f.writeframes(np.tile([16000,-8000],(5000,1)).astype('<i2').tobytes())
        self.player.play(self.path)
        self.assertEqual(self.player.samples.shape,(5000,2))
        np.testing.assert_allclose(self.player.samples[0],[16000/32768,-8000/32768])
        settings=self.device.OutputStream.call_args.kwargs
        self.assertEqual((settings['channels'],settings['samplerate']),(2,1000))

    def test_native_rate_fallback_preserves_segment_and_pause_position(self):
        self.device.query_devices.return_value=dict(max_output_channels=1,default_samplerate=2000)
        self.device.check_output_settings.side_effect=[self.device.PortAudioError('unsupported rate'),None]
        self.assertEqual(self.player.play(self.path,1,3),5)
        self.assertEqual(self.player.samples.shape,(4000,1))
        self.assertEqual(self.device.OutputStream.call_args.kwargs['samplerate'],2000)
        self.output_frames(40);self.assertEqual(self.player.status(),(1.02,'playing'))
        self.player.pause();self.output_frames(40)
        position=self.player.status()[0];self.output_frames(40)
        self.assertEqual(self.player.status(),(position,'paused'))
        self.player.resume();self.output_frames(40)
        self.assertGreater(self.player.status()[0],position)

    def test_unavailable_device_cleans_player_without_opening_stream(self):
        self.device.query_devices.return_value=dict(max_output_channels=0,default_samplerate=1000)
        with self.assertRaisesRegex(ValueError,'没有输出声道'):self.player.play(self.path)
        self.device.OutputStream.assert_not_called()
        self.assertIsNone(self.player.samples);self.assertFalse(self.player.opened)

    def test_native_rate_also_rejected_leaves_player_closed(self):
        self.device.query_devices.return_value=dict(max_output_channels=1,default_samplerate=2000)
        self.device.check_output_settings.side_effect=self.device.PortAudioError('device unavailable')
        with self.assertRaises(self.device.PortAudioError):self.player.play(self.path)
        self.device.OutputStream.assert_not_called()
        self.assertIsNone(self.player.samples);self.assertFalse(self.player.opened)

    def test_end_fades_to_silence(self):
        self.player.play(self.path,4.98,5)
        with self.assertRaises(self.device.CallbackStop):self.output_frames(20)
        self.player._finished()
        self.assertEqual(self.player.status(),(5,'stopped'))

if __name__=='__main__':unittest.main()
