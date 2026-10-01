import unittest
import intensity_curve as c
import emotion_input as ui
import story_engine as e
import studio_model
from test_story import fixture


class IntensityTests(unittest.TestCase):
    def project(self):
        p=ui.default_story(fixture());p['continuous_intensity']=True
        return ui.normalize(p)

    def test_centers_exact_and_no_overshoot(self):
        points=[dict(time=i*2+1,level=v) for i,v in enumerate([.1,.8,.2,.4,.4])]
        for p in points:self.assertAlmostEqual(c.evaluate(points,p['time']),p['level'])
        for a,b in zip(points,points[1:]):
            for k in range(101):
                value=c.evaluate(points,a['time']+(b['time']-a['time'])*k/100)
                self.assertGreaterEqual(value,min(a['level'],b['level'])-1e-10)
                self.assertLessEqual(value,max(a['level'],b['level'])+1e-10)
        for p in points[1:-1]:
            eps=1e-5;t=p['time'];mid=c.evaluate(points,t)
            self.assertAlmostEqual((mid-c.evaluate(points,t-eps))/eps,(c.evaluate(points,t+eps)-mid)/eps,places=4)

    def test_engine_and_playback_use_curve(self):
        p=self.project();p['intensity_points'][4]['level']=1
        q=e.plan(p);self.assertEqual(e.automatic_peak_anchor(p)['memory_time'],9)
        self.assertAlmostEqual(e.state_at(p,9)['level'],1)
        score=e.compile_score(q)
        block=next(b for b in score['report']['playback_blocks'] if b['start_seconds']<=9<b['end_seconds'])
        self.assertAlmostEqual(studio_model.playback_emotion(block,9)['intensity'],1)
        self.assertAlmostEqual(e.state_at(p,8-1e-7)['level'],e.state_at(p,8+1e-7)['level'],places=6)

    def test_paint_preserves_controls_resize_and_save_data(self):
        p=self.project();p['intensity_points'][3]['level']=.72
        q=ui.paint_blocks(p,0,8,'sad',.2,.2)
        self.assertEqual(q['intensity_points'],p['intensity_points'])
        self.assertEqual(len(ui.resize_blocks(q,1)['intensity_points']),14)
        self.assertEqual(len(ui.resize_blocks(q,-1)['intensity_points']),12)
        self.assertFalse(ui.is_default_story(p))
