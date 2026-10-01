import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from unittest.mock import patch

from engine import *


def write_fixture(path,pitches=(60,62,63,68,67),ppq=480,bpm=120,bars=4):
    mid=mido.MidiFile(ticks_per_beat=ppq)
    conductor=mido.MidiTrack();mid.tracks.append(conductor)
    conductor.append(mido.MetaMessage('set_tempo',tempo=mido.bpm2tempo(bpm)))
    conductor.append(mido.MetaMessage('time_signature',numerator=4,denominator=4))
    track=mido.MidiTrack();mid.tracks.append(track)
    track.append(mido.MetaMessage('track_name',name='Theme'))
    events=[]
    for bar in range(bars):
        for start,duration,pitch in [(0,2,pitches[bar%len(pitches)]),(2.5,.25,pitches[bar%len(pitches)]+12),(3.5,.25,pitches[(bar+1)%len(pitches)])]:
            t=round((bar*4+start)*ppq)
            events.extend([(t,1,pitch),(t+round(duration*ppq),0,pitch)])
    prev=0
    for t,on,pitch in sorted(events):
        track.append(mido.Message('note_on' if on else 'note_off',note=pitch,velocity=75 if on else 0,time=t-prev));prev=t
    track.append(mido.MetaMessage('end_of_track',time=bars*4*ppq-prev))
    mid.save(path)


def examples():
    folder=ROOT/'examples';folder.mkdir(exist_ok=True)
    write_fixture(folder/'theme-c.mid')
    write_fixture(folder/'theme-d-major.mid',(62,66,69,67,64),ppq=960,bpm=100,bars=8)
    write_fixture(folder/'theme-a-minor.mid',(69,72,76,74,71),ppq=96,bpm=90)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.path=self.folder/'theme.mid';write_fixture(self.path)
        self.source=load_source(self.path)
    def tearDown(self):self.temp.cleanup()

    def test_import(self):
        self.assertEqual(self.source.bpm,120)
        self.assertEqual(select_melody(self.source)[1],4)
        self.assertEqual(len(self.source.tracks[0].notes),12)

    def test_ppq_conversion(self):
        p=self.folder/'other.mid';write_fixture(p,ppq=960)
        self.assertEqual(self.source.tracks[0].notes,load_source(p).tracks[0].notes)

    def test_six_distinct(self):
        signatures=[]
        for emotion in EMOTIONS:
            a=arrange(self.source,0,Options(emotion=emotion))
            self.assertEqual(a['report']['bars'],4)
            signatures.append([(l['preset'],len(l['notes']),l['volume']) for l in a['layers']])
            for l in a['layers']:
                for n in l['notes']:
                    self.assertLessEqual(n.start+n.duration,a['total_ticks'])
                    self.assertIsInstance(n.duration,int)
        self.assertEqual(len({str(x) for x in signatures}),6)

    def test_deterministic_seed(self):
        a=arrange(self.source,0,Options(emotion='hope',variation=.9,seed=42))
        b=arrange(self.source,0,Options(emotion='hope',variation=.9,seed=42))
        self.assertEqual(a,b)

    def test_new_seed_produces_candidates(self):
        candidates=[arrange(self.source,0,Options(emotion='hope',variation=1,seed=i)) for i in range(5)]
        self.assertGreater(len({str(a['layers']) for a in candidates}),1)

    def test_zero_variation_preserves_notes(self):
        a=arrange(self.source,0,Options(variation=0))
        rendered=[(n.pitch,n.start,n.duration) for l in a['layers'][:2] for n in l['notes']]
        source=[(n.pitch,n.start,n.duration) for n in self.source.tracks[0].notes]
        self.assertEqual(sorted(rendered),sorted(source))
        self.assertEqual(a['report']['theme_edits'],[])

    def test_variation_limited_to_tails(self):
        a=arrange(self.source,0,Options(variation=1,seed=1))
        self.assertTrue(a['report']['theme_edits'])
        for edit in a['report']['theme_edits']:
            self.assertGreaterEqual(edit['start_tick']%BAR,1200)
            self.assertLessEqual(abs(edit['to']-edit['from']),3)

    def test_context_changes_arrangement(self):
        solo=arrange(self.source,0,Options())
        context=arrange(self.source,0,Options(previous='sad',following='crisis'))
        self.assertNotEqual(solo['layers'],context['layers'])
        self.assertEqual(len(context['report']['context']),2)

    def test_intensity_changes_arrangement(self):
        a=arrange(self.source,0,Options(emotion='crisis',intensity=.1))
        b=arrange(self.source,0,Options(emotion='crisis',intensity=.9))
        self.assertNotEqual(a['layers'],b['layers'])

    def test_no_input_mutation(self):
        before=copy.deepcopy(self.source)
        digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        arrange(self.source,0,Options(variation=1))
        self.assertEqual(self.source,before)
        self.assertEqual(digest,hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_roundtrip_midi_and_mmp(self):
        a=arrange(self.source,0,Options(emotion='resolve'))
        export_midi(a,self.folder/'out.mid')
        exported=mido.MidiFile(self.folder/'out.mid')
        self.assertAlmostEqual(exported.length,8,places=2)
        # XML round-trip only: fake resource files, no native LMMS/audio claims.
        sample=self.folder/'test-drum.ogg';sample.touch()
        with patch('engine.sample_path',return_value=sample):
            export_mmp(a,self.folder/'out.mmp')
        root=ET.parse(self.folder/'out.mmp')
        for n in root.findall('.//note'):
            self.assertGreater(int(n.get('len')),0)
        imported=load_source(self.folder/'out.mmp')
        self.assertTrue(imported.tracks)

    def test_reject_tempo_changes(self):
        mid=mido.MidiFile(self.path)
        mid.tracks[0].append(mido.MetaMessage('set_tempo',tempo=600000,time=480));mid.save(self.path)
        with self.assertRaisesRegex(ValueError,'速度变化'):load_source(self.path)

    def test_reject_meter(self):
        mid=mido.MidiFile(self.path)
        mid.tracks[0][1]=mido.MetaMessage('time_signature',numerator=3,denominator=4);mid.save(self.path)
        with self.assertRaisesRegex(ValueError,'4/4'):load_source(self.path)

    def test_reject_short(self):
        write_fixture(self.path,bars=2)
        with self.assertRaisesRegex(ValueError,'4～8'):select_melody(load_source(self.path))

    def test_reject_unknown_format(self):
        with self.assertRaisesRegex(ValueError,'暂不支持'):load_source(self.folder/'x.wav')

    def test_invalid_options(self):
        for opt in [Options(emotion='bad'),Options(intensity=2),Options(variation=-1),Options(following='bad')]:
            with self.assertRaises(ValueError):arrange(self.source,0,opt)

    def test_polyphony_is_not_silently_dropped(self):
        source=copy.deepcopy(self.source)
        source.tracks[0].notes.append(Note(67,0,480,80))
        a=arrange(source,0,Options(variation=0))
        self.assertEqual(sum(len(l['notes']) for l in a['layers'][:2]),13)

    def test_empty_input(self):
        mid=mido.MidiFile();mid.tracks.append(mido.MidiTrack());mid.save(self.path)
        with self.assertRaisesRegex(ValueError,'没有可用'):load_source(self.path)

    def test_postprocessing(self):
        raw=np.zeros((44100,2),dtype='<i2');raw[100,0]=12000
        with wave.open(str(self.folder/'dry.wav'),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100);f.writeframes(raw.tobytes())
        stats=postprocess(self.folder/'dry.wav',self.folder/'wet.wav',1,.2)
        self.assertEqual(stats['seconds'],2)
        self.assertEqual(stats['clipped_samples'],0)


if __name__=='__main__':
    examples()
    unittest.main(verbosity=2)
