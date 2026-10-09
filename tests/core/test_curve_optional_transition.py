"""无需过渡也是有效结果 applies independently to all three musical layers."""
import copy
import unittest

import curve_bridge_music as bridge_music
import curve_bridges as bridges
import curve_connection_music as connection_music
import curve_connections as connections
import curve_boundary_music as boundary_music
import curve_final as final
import curve_project as model
from test_curve_bridge_music import fixture
from test_curve_phrase_analysis import global_request, far_request
from test_curve_connection_music import request as connection_request
from test_curve_boundary_music import request as boundary_request, cells


class OptionalTransitionRuleTests(unittest.TestCase):
    def test_natural_none_preserves_music_in_each_layer(self):
        # Long stable tonic notes also avoid implying a fourbeat seam needs an edit.
        p=fixture(2,rough=False)
        for i in range(2): cells(p,i,[(0,1920,60)])
        before=copy.deepcopy(p)
        req=global_request(p);proposal=bridge_music.decide(req)
        self.assertEqual('none',proposal['decision']);self.assertEqual([],proposal['windows'])
        self.assertEqual('EXHAUSTED',proposal['search']['termination'])
        plan=bridges.make_plan(req,proposal);raw=bridge_music.generate(req,plan)
        bridges.validate_raw(req,plan,raw)
        self.assertEqual('SUCCEEDED',raw['status']);self.assertEqual([],raw['results'])
        out=bridges.make_outcome(req,plan,raw['results'],raw['status'],raw['error'])
        self.assertEqual(req['base_notes'],out['notes'])

        req=connection_request(p);proposal=connection_music.plan(req)
        self.assertEqual(('none','NOT_NEEDED'),(proposal['decision'],proposal['none_reason']))
        plan=connections.make_plan(req,proposal);raw=connection_music.generate(req,plan,req['actual_layout'])
        connections.validate_raw(req,plan,raw)
        self.assertEqual([],raw['results']);self.assertEqual('SUCCEEDED',raw['status'])
        out=connections.make_outcome(req,plan,raw['results'],raw['status'],raw['error'])
        self.assertEqual(req['actual_layout']['notes'],out['notes'])

        frame=boundary_request(p)
        req=final.make_request(frame['connection_ref'],token=frame['token'],seed=frame['seed'],values=frame['parameters'])
        proposal=boundary_music.plan_boundaries(req)
        self.assertEqual(('none','NOT_NEEDED'),(proposal['decision'],proposal['none_reason']))
        plan=final.make_plan(req,proposal);result=final.apply_boundaries(req,plan)
        self.assertEqual(req['actual_layout']['notes'],result['notes'])
        score=final.make_score(req,plan,result)
        final.validate_final_score(req,plan,score)
        self.assertEqual(before['total_ticks'],score['total_ticks']);self.assertEqual(before,p)

    def test_global_music_relation_keeps_a_real_positive_and_negative_case(self):
        # Same local window, different distant themes; no forced Bridge for negative.
        for alternative, expected in ((False,'selected'),(True,'none')):
            req=far_request(alternative);before=copy.deepcopy(req)
            proposal=bridge_music.decide(req);self.assertEqual(expected,proposal['decision'])
            bridges.make_plan(req,proposal)
            self.assertEqual(before,req)

    def test_cancellation_is_not_a_valid_no_transition(self):
        p=fixture(2)
        calls=((bridge_music.decide,global_request(p)),
               (connection_music.plan,connection_request(p)),
               (boundary_music.plan_boundaries,boundary_request(p)))
        for fn,request in calls:
            before=copy.deepcopy(request)
            with self.subTest(layer=fn.__module__), self.assertRaises(model.ProjectError) as error:
                fn(request,should_cancel=lambda:True)
            self.assertEqual('CANCELLED',error.exception.code);self.assertEqual(before,request)
