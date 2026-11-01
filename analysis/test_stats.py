"""Checks for analysis/stats.py against hand-computed or textbook values.

  analysis/.venv/bin/python -m unittest analysis/test_stats.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import stats as s  # noqa: E402


class Stats(unittest.TestCase):
    def test_holm(self):
        # Sorted p: 0.01 (x3 = 0.03), 0.02 (x2 = 0.04), 0.04 (x1 = 0.04).
        self.assertEqual([round(v, 6) for v in s.holm([0.04, 0.01, 0.02])], [0.04, 0.03, 0.04])
        # Monotone: a later raw p cannot get a smaller adjusted p.
        self.assertEqual([round(v, 6) for v in s.holm([0.03, 0.01])], [0.03, 0.02])

    def test_wilcoxon_all_better(self):
        # 8 pairs, all differences positive and distinct: exact two-sided
        # p = 2 / 2^8 = 0.0078125 (the "min p 0.008" in the proposal).
        x = [10, 11, 12, 13, 14, 15, 16, 17]
        y = [9.5, 10.4, 11.3, 12.2, 13.1, 14.0, 14.9, 15.8]
        self.assertAlmostEqual(s.wilcoxon_p(x, y), 0.0078125)

    def test_tost(self):
        y = [100.0] * 8
        same = [100.5, 99.5, 100.2, 99.8, 100.1, 99.9, 100.3, 99.7]
        self.assertTrue(s.tost_paired(same, y, 0.05)[1])      # within 5 of 100
        off = [110.5, 109.5, 110.2, 109.8, 110.1, 109.9, 110.3, 109.7]
        self.assertFalse(s.tost_paired(off, y, 0.05)[1])      # 10 above

    def test_bootstrap(self):
        mean, lo, hi = s.bootstrap_ci([1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(mean, 4.5)
        self.assertTrue(lo < 4.5 < hi)


if __name__ == "__main__":
    unittest.main()
