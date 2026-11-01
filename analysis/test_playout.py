"""Hand-computed cases for analysis/playout.py.

  analysis/.venv/bin/python -m unittest analysis/test_playout.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import playout as p  # noqa: E402

MS = 1000


def fr(spec):
    """spec: list of (type, capture_ms, complete_ms or None)."""
    return [{"frame_type": t, "capture_ts_us": c * MS,
             "complete_ts_us": None if d is None else d * MS} for t, c, d in spec]


class Lags(unittest.TestCase):
    def test_intra_late_frame_delays_all_later(self):
        # 40 ms frames; frame 1 completes late (at 300), so frames 2 and 3,
        # which depend on it, cannot be shown before 300 either.
        f = fr([("I", 0, 50), ("P", 40, 300), ("P", 80, 120), ("P", 120, 160)])
        self.assertEqual(p.lags_us(f, "intra"), [50 * MS, 260 * MS, 220 * MS, 180 * MS])

    def test_gop2_keyframe_resets_chain(self):
        # Frame 1 late; frame 2 is an I-frame, so it and frame 3 do not wait.
        f = fr([("I", 0, 50), ("P", 40, 300), ("I", 80, 130), ("P", 120, 160)])
        self.assertEqual(p.lags_us(f, "gop2"), [50 * MS, 260 * MS, 50 * MS, 40 * MS])
        # The same frames as intra-refresh: frame 1 holds back everything after.
        self.assertEqual(p.lags_us(f, "intra"), [50 * MS, 260 * MS, 220 * MS, 180 * MS])

    def test_missing_frame_is_never_decodable(self):
        f = fr([("I", 0, 50), ("P", 40, None), ("P", 80, 120)])
        self.assertEqual(p.lags_us(f, "intra")[1:], [math.inf, math.inf])
        self.assertEqual(p.lags_us(f, "intra")[0], 50 * MS)

    def test_out_of_order_completion(self):
        # Frame 2 completes before frame 1: its lag is set by frame 1.
        f = fr([("I", 0, 60), ("P", 40, 200), ("P", 80, 100)])
        self.assertEqual(p.lags_us(f, "intra"), [60 * MS, 160 * MS, 120 * MS])


class Metrics(unittest.TestCase):
    def setUp(self):
        # 10 frames at 25 fps (40 ms); every frame takes 100 ms except frames
        # 4 and 5 (captured 160 and 200), which complete at 500.
        spec = [("P", 40 * i, 40 * i + 100) for i in range(10)]
        spec[0] = ("I", 0, 100)
        spec[4] = ("P", 160, 500)
        spec[5] = ("P", 200, 500)
        self.f = fr(spec)
        self.lags = p.lags_us(self.f, "intra")

    def test_lags(self):
        # Frames 4-9 all wait for 500 (intra: every earlier frame is a
        # dependency): lags 340, 300, 260, 220, 180, 140.
        self.assertEqual([l // MS for l in self.lags], [100, 100, 100, 100, 340, 300, 260, 220, 180, 140])

    def test_on_time_ratio(self):
        self.assertEqual(p.on_time_ratio(self.lags, 100 * MS), 0.4)   # 0-3
        self.assertEqual(p.on_time_ratio(self.lags, 250 * MS), 0.7)   # + 7, 8, 9
        self.assertEqual(p.on_time_ratio(self.lags, 340 * MS), 1.0)

    def test_freeze_threshold_25fps(self):
        self.assertEqual(p.freeze_threshold_us(40 * MS), 190 * MS)
        self.assertEqual(p.freeze_threshold_us(100 * MS), 300 * MS)  # 3 intervals

    def test_freezes(self):
        # D = 100: shown 0, 40, 80, 120, then nothing until the timeline ends
        # at 360 + 40 = 400: one gap of 280 >= 190.
        self.assertEqual(p.freezes(self.f, self.lags, 100 * MS), (1, 280 * MS))
        # D = 250: shown 0..120, 280, 320, 360: gap 120 -> 280 = 160 < 190.
        self.assertEqual(p.freezes(self.f, self.lags, 250 * MS), (0, 0))

    def test_freeze_at_the_ends(self):
        # Last 5 frames never complete: timeline ends at 360 + 40 = 400; the
        # last shown frame is at 160, gap 240 counts.
        spec = [("P", 40 * i, 40 * i + 50 if i < 5 else None) for i in range(10)]
        f = fr(spec)
        lags = p.lags_us(f, "intra")
        self.assertEqual(p.freezes(f, lags, 100 * MS), (1, 240 * MS))

    def test_required_delay(self):
        # 99% of 10 frames = 10 frames on time: the largest lag, 340 ms.
        self.assertEqual(p.required_delay_us(self.lags), 340 * MS)
        # 50%: 5th smallest lag = 140 ms.
        self.assertEqual(p.required_delay_us(self.lags, 0.5), 140 * MS)
        self.assertEqual(p.required_delay_us([1, math.inf]), math.inf)

    def test_run_metrics(self):
        m, _ = p.run_metrics(self.f, "intra", deadlines_ms=(100,))
        self.assertEqual(m["on_time_100"], 0.4)
        self.assertEqual(m["freeze_ms_100"], 280)
        self.assertAlmostEqual(m["freeze_frac_100"], 280 / 400)
        self.assertEqual(m["required_delay_ms"], 340)


if __name__ == "__main__":
    unittest.main()
