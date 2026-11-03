"""Run with:  python -m unittest discover -s tests -v"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orb15.data import OPEN_MIN
from src.orb15.engine import LONG, SHORT, ExitRule, find_entry, opening_range, run_day


def day(overrides=None, base=100.0, n=375):
    """Flat 1-minute day at `base`; candles 15-44 (09:30-09:59) span 99..101. overrides: {idx: (o,h,l,c)}."""
    cs = [(OPEN_MIN + i, base, base, base, base, 1000) for i in range(n)]
    for i in range(15, 45):
        cs[i] = (OPEN_MIN + i, base, 101.0 if i == 20 else base, 99.0 if i == 21 else base, base, 1000)
    for i, (o, h, l, c) in (overrides or {}).items():
        cs[i] = (OPEN_MIN + i, o, h, l, c, 1000)
    return cs


class OrbTests(unittest.TestCase):
    def test_range_is_candles_2_and_3(self):
        cs = day({5: (100, 150, 50, 100)})            # candle 1 spike must be ignored
        hi, lo, start = opening_range(cs)
        self.assertEqual((hi, lo, start), (101.0, 99.0, 45))

    def test_long_touch_fills_at_level(self):
        cs = day({50: (100.5, 101.4, 100.4, 101.2)})
        e = find_entry(cs, 101.0, 99.0, 45, 300)
        self.assertEqual((e.idx, e.side, e.price), (50, LONG, 101.0))

    def test_gap_through_level_fills_at_open(self):
        cs = day({50: (102.0, 102.5, 101.8, 102.2)})
        self.assertEqual(find_entry(cs, 101.0, 99.0, 45, 300).price, 102.0)

    def test_short_breakout_and_target(self):
        cs = day({50: (99.5, 99.6, 98.9, 99.0), 51: (99.0, 99.0, 96.9, 97.0)})
        (hi, lo, _), tr = run_day(cs, ExitRule(stop="opp", target_r=1.0))
        self.assertEqual(len(tr), 1)
        t = tr[0]
        self.assertEqual((t.side, t.entry, t.stop, t.reason), (SHORT, 99.0, 101.0, "TARGET"))
        self.assertAlmostEqual(t.exit, 97.0)
        self.assertAlmostEqual(t.r, 1.0)

    def test_stop_checked_before_target_in_same_candle(self):
        cs = day({50: (100.5, 101.5, 100.4, 101.2), 51: (101.2, 104.0, 98.5, 100.0)})
        t = run_day(cs, ExitRule(stop="opp", target_r=1.0))[1][0]
        self.assertEqual(t.reason, "STOP")
        self.assertAlmostEqual(t.r, -1.0)

    def test_hold_to_cutoff_exits_at_open_of_1515(self):
        cs = day({50: (100.5, 101.5, 100.4, 101.2)})
        cs[15 * 60 + 15 - OPEN_MIN] = (15 * 60 + 15, 103.0, 103.0, 103.0, 103.0, 1000)
        t = run_day(cs, ExitRule())[1][0]
        self.assertEqual((t.reason, t.exit), ("EOD", 103.0))
        self.assertAlmostEqual(t.r, 1.0)

    def test_close_confirmation_waits_for_bar_close(self):
        # wick above 101 inside the 10:00-10:04 5-min bar but it closes back inside -> no entry yet
        cs = day({46: (100.5, 101.4, 100.4, 100.6)})
        self.assertIsNone(find_entry(cs, 101.0, 99.0, 45, 60, kind="close5"))
        cs[49] = (OPEN_MIN + 49, 100.6, 101.6, 100.5, 101.5, 1000)
        e = find_entry(cs, 101.0, 99.0, 45, 60, kind="close5")
        self.assertEqual((e.idx, e.price, e.touch), (49, 101.5, False))

    def test_reversal_only_after_stop(self):
        cs = day({50: (100.5, 101.5, 100.4, 101.2), 60: (101.0, 101.0, 98.9, 99.0), 70: (99.0, 99.0, 98.0, 98.1)})
        tr = run_day(cs, ExitRule(), max_trades=2)[1]
        self.assertEqual([t.side for t in tr], [LONG, SHORT])
        self.assertEqual(tr[0].reason, "STOP")


if __name__ == "__main__":
    unittest.main()
