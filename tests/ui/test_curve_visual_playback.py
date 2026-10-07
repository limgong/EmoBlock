"""Adversarial UI binding to the frozen DTO; fixture audio is not device evidence."""
import copy
import unittest
from unittest.mock import patch
import test_curve_p7_ui as p7
from test_curve_ui import MappedUIFixture


class VisualPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.harness=p7.RecommendationMappedTests()
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.addCleanup(self.harness.tearDown)

    def __getattr__(self,name):
        harness=self.__dict__.get('harness')
        if harness is None:raise AttributeError(name)
        return getattr(harness,name)

    def facts(self,ident,kind='final',mode='melody_only'):
        candidate=self.rec.candidate(ident)
        asset=self.controller.recommendation_asset(ident,kind=kind,mode=mode)
        project=candidate['preview']['project']
        return dict(schema='emoblocks.ui-playback.v1',target=dict(kind='recommendation',id=ident,side=kind,mode=mode),
            asset=asset,score_ref=copy.deepcopy(asset['score_ref']),bpm=project['bpm'],total_ticks=project['total_ticks'],
            notes=copy.deepcopy(candidate['preview']['notes']),segments=[dict(start_tick=0,end_tick=project['total_ticks'],
                kind='placement',owner_ref=p7.ref(project['placements'][0]['id']))],mapping_available=True,mapping_reason=None)

    def test_exact_final_view_only_comparison_mode_and_changed_notes_do_not_highlight(self):
        self.ready();self.select()
        with patch.object(self.controller,'recommendation_playback',side_effect=self.facts,create=True):
            self.rec.play('final');self.root.update()
            self.assertTrue(self.app.page.timeline.canvas.find_withtag('playing-block'))
            playing=copy.deepcopy(self.app.playing_target);before=self.controller.state()
            # Same base project does not prove equal actually displayed processing.
            self.controller.rec['candidates'][0]['preview']['notes'][0]['pitch']+=1;self.app.refresh();self.root.update()
            self.assertFalse(self.app.page.timeline.canvas.find_withtag('playing-block'))
            self.assertEqual(self.controller.state(),before);self.assertEqual(self.app.playing_target,playing)
            self.rec.select();self.rec.play('comparison');self.root.update()
            self.assertFalse(self.app.page.timeline.canvas.find_withtag('playing-block'))
            self.assertEqual(self.app.playing_target['context']['target']['side'],'comparison')
            self.rec.mode.set(p7.ui.MODES['arranged']);self.rec.mode_changed();self.root.update()
            self.app.seek_value.set(.25);self.app.seek_release()
            self.assertEqual(self.controller.assets_called[-1],('candidate-A','comparison','melody_only'))
            self.assertFalse(self.app.page.timeline.canvas.find_withtag('playing-block'))

    def test_seek_validates_original_ref_before_device_and_keeps_captured_context(self):
        self.ready();self.select()
        captured=self.facts('candidate-A')
        current=copy.deepcopy(captured)
        with patch.object(self.controller,'recommendation_playback',side_effect=lambda *a,**k:copy.deepcopy(current),create=True):
            self.rec.play('final');playing=copy.deepcopy(self.app.playing_target);calls=list(self.app.player.calls)
            self.app.select_target('material','phrase')
            current['score_ref']['fingerprint']='different'
            self.app.seek_value.set(.3)
            with self.assertRaisesRegex(ValueError,'身份已变化'):self.app.seek_release()
            self.assertEqual(self.app.player.calls,calls);self.assertEqual(self.app.playing_target,playing)
            self.assertEqual(playing['context'],captured)

    def test_native_material_button_name_keyboard_disabled_and_no_card_activation(self):
        self.root.update()
        cards=self.app.page.cards;row=next(iter(cards.rows.values()))
        controls=[w for w in row.winfo_children()[0].winfo_children() if w.winfo_class()=='Frame'][0]
        button=controls.winfo_children()[0]
        self.assertEqual(button.winfo_class(),'Button');self.assertEqual(button.cget('text'),'试听')
        self.assertTrue(button.cget('command'));self.assertGreaterEqual(button.winfo_height(),44)
        calls=[];button.configure(command=lambda:calls.append('play'))
        before=self.music_state();button.focus_force();self.root.update()
        for key in ('<Return>','<space>','<KeyRelease-space>'):button.event_generate(key);self.root.update()
        self.assertEqual(calls,['play','play']);self.assertEqual(before,self.music_state())
        button.state(['disabled']);button.event_generate('<Return>');button.invoke();self.root.update()
        self.assertEqual(calls,['play','play']);self.assertEqual(button.cget('state'),'disabled')
        self.assertEqual(before,self.music_state())

    def changed_wav(self):
        import wave
        with wave.open(str(self.wav),'wb') as output:
            output.setparams((1,2,8000,0,'NONE','not compressed'))
            output.writeframes(b'\x80\x00'*8000)

    def test_asset_bytes_changed_before_open_preserve_playing_identity_and_project(self):
        self.ready();self.select();self.rec.play('final')
        playing=copy.deepcopy(self.app.playing_target);before=self.music_state()
        asset=self.controller.recommendation_asset('candidate-A',kind='final',mode='melody_only')
        calls=list(self.app.player.calls)
        self.changed_wav()
        from curve_recommendation_ui import playback_asset
        self.assertFalse(self.app.start_playback(playback_asset(asset),('recommendation','candidate-A','melody_only','final'),'已变化文件',context=self.facts('candidate-A')))
        self.assertEqual(self.app.playing_target,playing);self.assertEqual(self.app.player.calls,calls)
        self.assertEqual(before,self.music_state())

    def test_file_mutation_during_device_read_stops_and_never_certifies_score_ref(self):
        self.ready();self.select();before=self.music_state()
        asset=self.controller.recommendation_asset('candidate-A',kind='final',mode='melody_only')
        original=self.app.player.play
        def mutate(path,start=0.):
            duration=original(path,start=start)
            self.changed_wav()
            return duration
        from curve_recommendation_ui import playback_asset
        with patch.object(self.app.player,'play',side_effect=mutate):
            self.assertFalse(self.app.start_playback(playback_asset(asset),('recommendation','candidate-A','melody_only','final'),'读取期间变化',context=self.facts('candidate-A')))
        self.assertIsNone(self.app.playing_target);self.assertEqual(self.app.player.status()[1],'closed')
        self.assertIn('读取期间变化',self.app.full_status)
        self.assertEqual(before[:-1],self.music_state()[:-1])
        self.assertEqual(len(self.app.player.calls),len(before[-1])+1)
