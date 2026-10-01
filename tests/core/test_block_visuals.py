import unittest
from unittest.mock import Mock,patch
from block_visuals import BlockMotion
from ui_scale import ratio


class BlockVisualTests(unittest.TestCase):
    def test_motion_interpolates_then_finishes_and_cancels_pending_callback(self):
        widget=Mock();widget.after.return_value='animation'
        motion=BlockMotion(widget,Mock())
        with patch('block_visuals.time.perf_counter',return_value=10):
            self.assertEqual(motion.boxes({'a':(0,20)},False)['a'],(0,20))
            self.assertEqual(motion.boxes({'a':(100,120)},True)['a'],(0,20))
        with patch('block_visuals.time.perf_counter',return_value=10.08):
            self.assertGreater(motion.boxes({'a':(100,120)},True)['a'][0],50)
        with patch('block_visuals.time.perf_counter',return_value=10.2):
            self.assertEqual(motion.boxes({'a':(100,120)},True)['a'],(100,120))
        motion.cancel();widget.after_cancel.assert_called_once_with('animation')
        self.assertEqual(motion.positions,{})

    def test_scaling_respects_both_window_dimensions(self):
        self.assertEqual(ratio(1300,870),1)
        self.assertEqual(ratio(1020,700),1)
        self.assertAlmostEqual(ratio(1950,1305),1.5)
        self.assertLess(ratio(2560,1080),1.25)
