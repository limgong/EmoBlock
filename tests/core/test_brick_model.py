import copy
import json
import math
import unittest
import brick_model as b
import default_melody
import emotion_input
import story_engine as e
import intensity_curve

def fixture():
    p=emotion_input.default_story();p['sources']=[default_melody.source()];p['continuous_intensity']=True
    return e.automatic_memory_project(p)

class BrickTests(unittest.TestCase):
    def create(self,indices=(0,1,2)):
        self.p=fixture();self.sid=self.p['sources'][0]['id']
        self.p,self.ident=b.create(self.p,self.sid,list(indices),emotion='resolve');return self.p
    def test_create_snapshot_and_source_immutable(self):
        p=fixture();before=copy.deepcopy(p);q,i=b.create(p,p['sources'][0]['id'],[2,0,1])
        self.assertEqual(p,before);self.assertEqual(b.brick(q,i)['block_indices'],[0,1,2])
        self.assertEqual(b.brick(q,i)['ticks'],3*1920)
    def test_nonadjacent_parts(self):
        self.create((0,3));v=b.brick(self.p,self.ident)
        original=self.p['sources'][0]['notes']
        self.assertEqual(v['notes'][4]['pitch'],next(n['pitch'] for n in original if n['start']==3*1920))
        self.assertEqual(v['notes'][4]['start'],1920)
    def test_rest_and_partial_last_block_padding(self):
        source=dict(ticks=2200,notes=[dict(pitch=60,start=1900,duration=300,velocity=80)])
        self.assertEqual(b.compose(source,[1]),[dict(pitch=60,start=0,duration=280,velocity=80)])
        self.assertEqual(b.compose(source,[0])[0]['duration'],20)
    def test_adjacent_sustained_note_tied(self):
        source=dict(ticks=3840,notes=[dict(pitch=60,start=0,duration=3840,velocity=80)])
        self.assertEqual(len(b.compose(source,[0,1])),1)
        self.assertEqual(b.compose(source,[0,1])[0]['duration'],3840)
    def test_reject_bad_indices(self):
        p=self.create()
        for indices in ([],[-1],[99],[True]):
            with self.assertRaises(ValueError):b.create(p,self.sid,indices)
    def test_place_collision_and_bounds_are_transactional(self):
        self.create();self.p,i=b.place(self.p,self.ident,2);before=copy.deepcopy(self.p)
        for start in (-1,3,12):
            with self.assertRaises(ValueError):b.place(self.p,self.ident,start)
        self.assertEqual(before,self.p)
        q,_=b.place(self.p,self.ident,6,placement_id=i);self.assertEqual(len(q['brick_placements']),1)
    def test_first_gap_and_reuse(self):
        self.create();self.p,i=b.place(self.p,self.ident,0)
        self.assertEqual(b.first_gap(self.p,self.ident),3)
        q,i=b.place(self.p,self.ident,3);self.assertEqual(b.summary(q),dict(total=13,fixed=6,empty=7))
    def test_fixed_original_at_exact_requested_slot(self):
        self.create((2,3));self.p,i=b.place(self.p,self.ident,4,'sad',edge_connect=False)
        planned=e.plan(self.p);rows=[r for r in planned['blocks'] if r.get('placement_id')==i]
        self.assertEqual(len(rows),2);self.assertTrue(all(r['kind']=='content' and r['pinned'] and r['emotion']=='sad' for r in rows))
        self.assertEqual(rows[0]['notes'][0]['pitch'],b.brick(self.p,self.ident)['notes'][0]['pitch'])
        self.assertEqual(rows[0]['start_tick'],4*1920);self.assertEqual(rows[0]['source_spans'][0]['start'],2*1920)
    def test_long_brick_core_never_bridge(self):
        self.create((0,1,2,3,4));self.p,i=b.place(self.p,self.ident,1,'suspense')
        q=e.plan(self.p);core=[r for r in q['blocks'] if 2*1920<=r['start_tick']<5*1920]
        self.assertTrue(all(r.get('placement_id')==i and r['kind']=='content' for r in core))
    def test_simple_variation_keeps_rhythm(self):
        self.create((0,1));a,_=b.place(self.p,self.ident,0,'resolve',edge_connect=False)
        c=copy.deepcopy(a);c['brick_placements'][0]['variant']='simple'
        a=e.plan(a);c=e.plan(c)
        an=[n for r in a['blocks'][:2] for n in r['notes']];cn=[n for r in c['blocks'][:2] for n in r['notes']]
        self.assertEqual([(n['start'],n['duration']) for n in an],[(n['start'],n['duration']) for n in cn])
        self.assertNotEqual([n['pitch'] for n in an],[n['pitch'] for n in cn])
    def emotional_brick_score(self,emotion,level,variant='original'):
        p=fixture();p['anchors']=[];p['automatic_memory']=False;p['melody_only']=False
        p['curve']=[dict(start=0.,end=p['duration'],emotion='calm',level=level)]
        p['intensity_points']=[dict(time=t,level=level) for t in range(1,26,2)]
        p,ident=b.create(p,p['sources'][0]['id'],[0,1])
        p,placed=b.place(p,ident,2,emotion,variant=variant,edge_connect=False)
        planned=e.plan(p);score=e.compile_score(planned)
        rows=[r for r in planned['blocks'] if r.get('placement_id')==placed]
        self.assertTrue(all(r['pinned'] and r['emotion']==emotion for r in rows))
        melody=[];backing={}
        for layer in score['layers']:
            ns=[n for n in layer['notes'] if 2*1920<=n.start<4*1920]
            if layer['name'].startswith('melody_'):
                melody.extend((layer['preset'],n.pitch,n.start,n.duration,n.velocity) for n in ns)
            elif ns:backing[layer['name']]=ns
        melody.sort(key=lambda n:(n[2],n[1]))
        return rows,melody,backing
    def test_specified_lead_melody_still_receives_emotional_arrangement(self):
        presets=dict(calm='soft',hope='bell',sad='dark',suspense='pluck',crisis='pluck',resolve='brass')
        for variant in ('original','simple'):
            reference=None
            for emotion,preset in presets.items():
                with self.subTest(variant=variant,emotion=emotion):
                    rows,melody,backing=self.emotional_brick_score(emotion,.85,variant)
                    self.assertTrue(melody);self.assertEqual({n[0] for n in melody},{preset})
                    signature=[n[1:4] for n in melody]
                    if reference is None:reference=signature
                    self.assertEqual(signature,reference)
                    self.assertIn('harmony_'+('dark' if emotion in ('sad','suspense') else 'pad'),backing)
                    self.assertEqual('kick' in backing,emotion in ('crisis','resolve'))
    def test_specified_lead_melody_still_follows_intensity(self):
        for variant in ('original','simple'):
            with self.subTest(variant=variant):
                _,low,low_backing=self.emotional_brick_score('resolve',.2,variant)
                _,high,high_backing=self.emotional_brick_score('resolve',.9,variant)
                self.assertEqual([n[1:4] for n in low],[n[1:4] for n in high])
                self.assertTrue(all(a[4]<z[4] for a,z in zip(low,high)))
                self.assertNotIn('pulse',low_backing);self.assertIn('pulse',high_backing)
                self.assertNotIn('kick',low_backing);self.assertIn('kick',high_backing)
    def test_empty_slots_filled_and_musical_length_unchanged(self):
        self.create((1,2));self.p,i=b.place(self.p,self.ident,6)
        q=e.plan(self.p);self.assertEqual(len(q['blocks']),13)
        self.assertEqual(q['total_ticks'],13*1920);self.assertTrue(all(r['notes'] for r in q['blocks']))
        score=e.compile_score(q);self.assertEqual(score['report']['duration_seconds'],26)
        self.assertEqual(score['report']['composition_summary']['empty'],11)
        self.assertEqual(sum(r['manual_brick'] for r in score['report']['playback_blocks']),2)
    def test_roundtrip_and_delete_source_cascade(self):
        self.create();self.p,i=b.place(self.p,self.ident,2)
        restored=json.loads(json.dumps(self.p));e.validate(restored)
        q=b.remove_source(restored,self.sid);self.assertEqual(q['melody_bricks'],[]);self.assertEqual(q['brick_placements'],[])
    def test_memory_does_not_override_fixed_brick(self):
        self.create((0,1));self.p,i=b.place(self.p,self.ident,8,'sad')
        self.assertIsNone(e.automatic_peak_anchor(self.p))
        self.assertEqual(next(r for r in e.plan(self.p)['blocks'] if r['start_tick']==8*1920)['emotion'],'sad')
    def test_corrupt_saved_snapshot_rejected(self):
        self.create();self.p['melody_bricks'][0]['notes'][0]['pitch']+=1
        with self.assertRaises(ValueError):e.validate(self.p)
    def test_drawn_curve_on_grid_and_smooth_controls(self):
        p=fixture();before=copy.deepcopy(p)
        q=b.draw_emotion(p,[(.1,.1),(2,.8),(4,.3),(5.8,.7)],'hope')
        self.assertEqual(p,before);self.assertTrue(q['emotion_drawn'])
        self.assertEqual([e.raw_state_at(q,t)['emotion'] for t in (1,3,5)],['hope']*3)
        self.assertTrue(all(0<=intensity_curve.level_at(q,t/10)<=1 for t in range(260)))
        self.assertEqual(q['curve'][0]['start'],0);self.assertEqual(q['curve'][0]['end'],6)
    def test_reverse_stroke_and_single_point(self):
        p=fixture();q=b.draw_emotion(p,[(5.9,.6),(4,.9),(2.1,.2)],'sad')
        self.assertEqual(e.raw_state_at(q,3)['emotion'],'sad')
        q=b.draw_emotion(p,[(1,.9)],'resolve');self.assertEqual(intensity_curve.level_at(q,1),.9)

if __name__=='__main__':unittest.main()
