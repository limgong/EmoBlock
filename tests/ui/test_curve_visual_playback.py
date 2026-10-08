"""Adversarial UI binding to the frozen DTO; fixture audio is not device evidence."""
import copy
from collections import OrderedDict
import hashlib
import io
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import test_curve_p7_ui as p7
from test_curve_ui import MappedUIFixture
from curve_canvas import CurveCanvas
import curve_player_ui as player_ui


class InlineThread:
    def __init__(self,target,**kwargs):self.target=target
    def start(self):self.target()


class BoundaryAvoidanceTests(unittest.TestCase):
    def test_measured_bridge_text_avoids_boundaries_without_moving_exact_lines(self):
        # Actual R3 minimum-window bboxes, without a Tk/display dependency.
        for tag in ('bridge-label','manual-bridge-label','accepted-bridge'):
            with self.subTest(tag=tag):
                boxes={1:[203,50,230,67],2:[234,50,261,67],3:[218,56,292,72]}
                states={};links={}
                def move(item,dx,dy):
                    box=boxes[item];boxes[item]=[box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy]
                canvas=SimpleNamespace(canvasx=lambda x:x,winfo_width=lambda:400,
                    find_withtag=lambda value:(3,) if value==tag else (),type=lambda item:'text',
                    bbox=lambda item:boxes[item],move=move,
                    itemconfigure=lambda item,**kw:states.update({item:kw}),
                    coords=lambda item,*xy:links.update({item:xy}))
                exact={'first':(196,43,204,300),'second':(227,43,235,300)}
                timeline=SimpleNamespace(canvas=canvas,range_badges=[],number_badges=[],
                    boundary_labels={'first':(1,10),'second':(2,20)},boundary_boxes=copy.deepcopy(exact))
                CurveCanvas.layout_boundary_labels(timeline)
                placed=list(timeline.boundary_label_boxes.values())+[boxes[3]]
                for i,a in enumerate(placed):
                    for b in placed[i+1:]:
                        self.assertFalse(max(a[0],b[0])<min(a[2],b[2]) and
                                         max(a[1],b[1])<min(a[3],b[3]))
                self.assertEqual(timeline.boundary_boxes,exact)
                self.assertEqual(boxes[3],[218,56,292,72])
                self.assertEqual(links[10][:2],(200,43));self.assertEqual(links[20][:2],(231,43))


class WaveformAuthenticationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'actual-pcm.wav'
        self.original=self.pcm(1000);self.foreign=self.pcm(20000)
        self.path.write_bytes(self.original)
        self.digest=hashlib.sha256(self.original).hexdigest()
        self.expected,self.duration=player_ui.waveform(self.path)
        self.target=dict(asset=dict(wav_path=str(self.path),id='immutable',version=1),
            wav_digest=self.digest,target=('material','captured'),context={})
        self.widget=SimpleNamespace(key=None,pending=None,error=None,values=[],results=queue.Queue(),
            cache=OrderedDict(),alive=True,draw=lambda:None)

    @staticmethod
    def pcm(amplitude,frames=80000):
        output=io.BytesIO()
        with wave.open(output,'wb') as stream:
            stream.setparams((1,2,8000,0,'NONE','not compressed'))
            stream.writeframes(amplitude.to_bytes(2,'little',signed=True)*frames)
        return output.getvalue()

    def load(self):
        with patch.object(player_ui.threading,'Thread',InlineThread):
            player_ui.Waveform.set_target(self.widget,self.target)
        player_ui.Waveform.drain(self.widget)

    def test_replace_restore_during_actual_pcm_read_never_caches_foreign_values(self):
        real_read=wave.Wave_read.readframes;reads=[]
        def replace_restore(stream,count):
            self.path.write_bytes(self.foreign)
            try:
                data=real_read(stream,count);reads.append(data)
                return data
            finally:self.path.write_bytes(self.original)
        # This same real PCM interleaving fails the old parse-path/hash-path worker.
        with patch.object(wave.Wave_read,'readframes',replace_restore):self.load()
        self.assertTrue(reads);self.assertEqual(self.path.read_bytes(),self.original)
        self.assertIsNone(self.widget.error);self.assertEqual(self.widget.values,self.expected)
        self.assertEqual(list(self.widget.cache.values()),[self.expected])

    def test_replace_restore_during_copy_fails_authentication_without_cache(self):
        real_open=Path.open;counts=[];sizes=[]
        test=self
        class ReplacingReader:
            def __init__(self,source):self.source=source
            def __enter__(self):return self
            def __exit__(self,*args):self.source.close()
            def read(self,size):
                sizes.append(size);test.path.write_bytes(test.foreign)
                try:return self.source.read(size)
                finally:test.path.write_bytes(test.original)
        def opening(path,*args,**kwargs):
            source=real_open(path,*args,**kwargs)
            if path==self.path and args==('rb',):
                counts.append(path);return ReplacingReader(source)
            return source
        with patch.object(Path,'open',opening):self.load()
        self.assertEqual(counts,[self.path]);self.assertTrue(sizes)
        self.assertLessEqual(max(sizes),65536)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertIn('音频文件已变化',self.widget.error)
        self.assertEqual(self.widget.values,[]);self.assertFalse(self.widget.cache)

    def test_changed_path_after_authenticated_copy_keeps_exact_snapshot(self):
        real_parse=player_ui._waveform_stream;snapshots=[]
        def changing(source,bins):
            snapshots.append(source);self.path.write_bytes(self.foreign)
            return real_parse(source,bins)
        with patch.object(player_ui,'_waveform_stream',changing):self.load()
        self.assertEqual(self.widget.values,self.expected);self.assertIsNone(self.widget.error)
        self.assertEqual(list(self.widget.cache.values()),[self.expected])
        self.assertTrue(snapshots[0].closed)
        self.assertEqual(self.path.read_bytes(),self.foreign)

    def test_persistent_mismatch_and_invalid_authenticated_wav_do_not_cache(self):
        self.path.write_bytes(self.foreign);self.load()
        self.assertIn('音频文件已变化',self.widget.error);self.assertFalse(self.widget.cache)
        invalid=b'not a PCM WAV';self.path.write_bytes(invalid)
        self.target['wav_digest']=hashlib.sha256(invalid).hexdigest();self.load()
        self.assertIsNotNone(self.widget.error);self.assertEqual(self.widget.values,[])
        self.assertFalse(self.widget.cache)

    def test_large_snapshot_rolls_to_disk_and_pcm_reads_are_bounded(self):
        raw=self.pcm(1000,frames=600000);self.path.write_bytes(raw)
        real_read=wave.Wave_read.readframes;real_parse=player_ui._waveform_stream
        counts=[];rolled=[]
        def bounded_read(stream,count):
            counts.append(count*stream.getnchannels()*stream.getsampwidth())
            return real_read(stream,count)
        def parse(source,bins):
            rolled.append(source._rolled)
            return real_parse(source,bins)
        with patch.object(player_ui,'_waveform_stream',parse),patch.object(wave.Wave_read,'readframes',bounded_read):
            values,duration=player_ui._authenticated_waveform(self.path,hashlib.sha256(raw).hexdigest(),bins=2)
        self.assertEqual(rolled,[True]);self.assertLessEqual(max(counts),65536)
        self.assertEqual(values,[1000/32768]*2);self.assertEqual(duration,75)

    def test_public_waveform_preserves_unsigned_stereo_and_24_32_bit_pcm(self):
        for width,channels,amplitude in ((1,1,100),(2,2,1234),(3,1,-100000),(4,1,100000000)):
            with self.subTest(width=width,channels=channels):
                sample=bytes([amplitude+128]) if width==1 else amplitude.to_bytes(width,'little',signed=True)
                with wave.open(str(self.path),'wb') as output:
                    output.setparams((channels,width,8000,0,'NONE','not compressed'))
                    output.writeframes(sample*channels*100000)
                values,duration=player_ui.waveform(self.path,bins=3)
                self.assertEqual(values,[abs(amplitude)/2**(8*width-1)]*3)
                self.assertEqual(duration,12.5)

    def test_stale_destroyed_results_and_cache_bound_remain_enforced(self):
        work=[]
        class HeldThread:
            def __init__(self,target,**kwargs):work.append(target)
            def start(self):pass
        with patch.object(player_ui.threading,'Thread',HeldThread):
            player_ui.Waveform.set_target(self.widget,self.target)
            newer=copy.deepcopy(self.target);newer['asset']['id']='newer'
            player_ui.Waveform.set_target(self.widget,newer)
        work[0]();player_ui.Waveform.drain(self.widget)
        self.assertEqual(self.widget.values,[]);self.assertFalse(self.widget.cache)
        work[1]();player_ui.Waveform.drain(self.widget)
        self.assertEqual(self.widget.values,self.expected)
        for number in range(10):
            self.target['asset']['id']=str(number);self.load()
        self.assertEqual(len(self.widget.cache),8)
        player_ui.Waveform.dispose(self.widget)
        self.widget.results.put((self.widget.key,self.expected,None))
        player_ui.Waveform.drain(self.widget)
        self.assertEqual(self.widget.cache,{});self.assertFalse(self.widget.alive)


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

    def test_mapped_ready_bridge_and_boundary_labels_clear_at_small_window_and_scroll(self):
        self.ready()
        preview=self.controller.rec['candidates'][0]['preview']
        preview['project']['intensity_points']=[dict(tick=p['tick'],level=.75)
                                               for p in preview['project']['intensity_points']]
        region=preview['bridge_overlays'][0]['range']
        template=copy.deepcopy(preview['boundary_overlays'][0])
        ticks=[region['start_tick'],region['start_tick']+180,region['end_tick'],preview['project']['total_ticks']]
        preview['boundary_overlays']=[dict(template,id='measured-boundary-'+str(i),tick=tick)
                                      for i,tick in enumerate(ticks)]
        self.select();self.root.update()
        before=self.music_state();captured=copy.deepcopy(self.rec.preview);selected=self.rec.selected_id
        timeline=self.app.page.timeline;canvas=timeline.canvas
        inspected=0
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            for size in ('1020x700','1280x800','1440x900'):
                self.root.geometry(size);self.app.source_user_collapsed=False
                self.app.layout_sources();self.app.refresh();self.root.update()
                self.assertTrue(canvas.winfo_ismapped())
                for scroll in (0.,.25,1.):
                    timeline.scrollbar.command('moveto',scroll);self.root.update()
                    bridge_text=[canvas.bbox(i) for i in canvas.find_withtag('bridge-label')
                                 if canvas.type(i)=='text']
                    self.assertTrue(bridge_text)
                    left,right=canvas.canvasx(0),canvas.canvasx(canvas.winfo_width())
                    for ident,box in timeline.boundary_label_boxes.items():
                        self.assertGreaterEqual(box[0],left+4);self.assertLessEqual(box[2],right-4)
                        for other in bridge_text:
                            self.assertFalse(max(box[0],other[0])<min(box[2],other[2]) and
                                             max(box[1],other[1])<min(box[3],other[3]))
                        x,y=(box[0]+box[2])//2,(box[1]+box[3])//2
                        lx,ly=round(x-left),round(y-canvas.canvasy(0))
                        coords=dict(x=lx,y=ly,rootx=canvas.winfo_rootx()+lx,rooty=canvas.winfo_rooty()+ly)
                        with patch.object(self.rec,'describe_overlay',return_value='exact boundary detail') as describe:
                            canvas.event_generate('<ButtonPress-1>',**coords)
                            canvas.event_generate('<ButtonRelease-1>',**coords);self.root.update()
                        self.assertEqual(describe.call_args.args[0]['id'],ident)
                        inspected+=1
                    lines=[canvas.coords(i)[0] for i in canvas.find_withtag('final-boundary') if canvas.type(i)=='line']
                    self.assertEqual(lines,[timeline.x(o['tick']) for o in captured['boundary_overlays']])
                    self.assertEqual(captured,self.rec.preview);self.assertEqual(before,self.music_state())
                    self.assertEqual(selected,self.rec.selected_id)
        self.assertGreater(inspected,0)

    def test_mapped_strength_stroke_keeps_exact_curve_visible_across_block_and_canvas(self):
        timeline=self.app.page.timeline;canvas=timeline.canvas
        timeline.set_mode('arrange');self.root.update()
        before=self.music_state();points=copy.deepcopy(timeline.project['intensity_points'])
        def contrast(a,b):
            def luminance(color):
                rgb=[v/65535 for v in canvas.winfo_rgb(color)]
                return sum((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)*weight
                           for v,weight in zip(rgb,(.2126,.7152,.0722)))
            a,b=sorted((luminance(a),luminance(b)))
            return (b+.05)/(a+.05)
        for theme in ('light','dark'):
            if self.app.theme.name!=theme:self.app.toggle_theme()
            self.root.geometry('1020x700');self.app.refresh();self.root.update()
            curve=canvas.find_withtag('strength-line');self.assertEqual(len(curve),1)
            coords=canvas.coords(curve[0]);strokes=canvas.find_withtag('strength')
            self.assertTrue(timeline.boxes)
            # Both strokes describe one curve, with exactly the same samples.
            for item in strokes:self.assertEqual(canvas.coords(item),coords)
            if theme=='dark':
                outline=canvas.find_withtag('strength-outline');self.assertEqual(len(outline),1)
                self.assertGreater(float(canvas.itemcget(outline[0],'width')),float(canvas.itemcget(curve[0],'width')))
                self.assertLess(canvas.find_all().index(outline[0]),canvas.find_all().index(curve[0]))
            else:self.assertFalse(canvas.find_withtag('strength-outline'))
            surfaces={canvas.cget('background')}
            crossing=False
            for item in canvas.find_all():
                if canvas.type(item)!='polygon':continue
                box=canvas.bbox(item)
                if any(box[0]<=x<=box[2] and box[1]<=y<=box[3] for x,y in zip(coords[::2],coords[1::2])):
                    surfaces.add(canvas.itemcget(item,'fill'));crossing=True
            self.assertTrue(crossing)
            for surface in surfaces:
                self.assertGreaterEqual(max(contrast(canvas.itemcget(item,'fill'),surface) for item in strokes),3.)
            self.assertEqual(points,timeline.project['intensity_points']);self.assertEqual(before,self.music_state())

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
        import curve_melody
        phrase=self.controller._project['materials'][0]
        self.controller._project['materials'].extend(curve_melody.split_phrase(phrase))
        self.app.refresh();self.root.update()
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

    def test_mapped_waveform_replace_restore_draws_authorized_pcm_without_player_change(self):
        original=WaveformAuthenticationTests.pcm(1000)
        foreign=WaveformAuthenticationTests.pcm(20000)
        self.wav.write_bytes(original)
        expected,_=player_ui.waveform(self.wav)
        target=dict(asset=dict(wav_path=str(self.wav),id='mapped-snapshot'),
            wav_digest=hashlib.sha256(original).hexdigest(),target=('material','captured'),context={})
        before=self.music_state();playing=copy.deepcopy(self.app.playing_target)
        # The app's own footer correctly clears when no object is playing.
        # Map the real component separately to inspect a captured read without
        # fabricating an active player identity or disabling the app's polling.
        window=player_ui.tk.Toplevel(self.root);window.geometry('500x150')
        self.addCleanup(window.destroy)
        widget=player_ui.Waveform(window,self.app);widget.pack(fill='both',expand=True)
        self.root.update()
        real_read=wave.Wave_read.readframes;reads=[]
        def replace_restore(stream,count):
            self.wav.write_bytes(foreign)
            try:
                data=real_read(stream,count);reads.append(data)
                return data
            finally:self.wav.write_bytes(original)
        with patch.object(wave.Wave_read,'readframes',replace_restore),patch.object(player_ui.threading,'Thread',InlineThread):
            widget.set_target(target)
        widget.drain();self.root.update()
        self.assertTrue(reads);self.assertTrue(widget.winfo_ismapped())
        self.assertTrue(widget.find_withtag('pcm-wave'))
        self.assertEqual(widget.values,expected);self.assertIsNone(widget.error)
        self.assertEqual(list(widget.cache.values()),[expected])
        self.assertEqual(self.music_state(),before);self.assertEqual(self.app.playing_target,playing)

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
