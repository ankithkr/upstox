"""Tests for the v2 strategy: gate, costs, features, engine knobs and the end-to-end day snapshot."""

import unittest
from dataclasses import replace
from datetime import date, timedelta

from src.backtest.costs import net_r_multiple, round_trip_cost_pct
from src.backtest.features import DailyIndex, VolumeProfile
from src.backtest.history import History
from src.backtest.orb_engine import (
    EOD_EXIT,
    STOPPED_BREAKEVEN,
    STOPPED_LOSS,
    TARGET_HIT,
    simulate_trade,
)
from src.backtest.snapshots import compute_day_snapshots, evaluate_gate, taken_trades
from src.data.universe import V2_SECTORS
from src.strategy.params import DEFAULT_PARAMS

TZ = "+05:30"


def ts(day: str, minutes_after_915: int) -> str:
    total = 9 * 60 + 15 + minutes_after_915
    return f"{day}T{total // 60:02d}:{total % 60:02d}:00{TZ}"


def candle(day, i, o, h, l, c, v):
    return (ts(day, 5 * i), o, h, l, c, v)


class GateTests(unittest.TestCase):
    def test_long_open_when_calm_and_trending_up(self):
        ok, reasons = evaluate_gate("LONG", 12.0, 1.5, DEFAULT_PARAMS)
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_high_vix_closes_the_gate(self):
        ok, reasons = evaluate_gate("LONG", 14.0, 1.5, DEFAULT_PARAMS)
        self.assertFalse(ok)
        self.assertIn("VIX", reasons[0])

    def test_trend_must_agree_with_direction(self):
        self.assertFalse(evaluate_gate("LONG", 12.0, -0.5, DEFAULT_PARAMS)[0])
        self.assertTrue(evaluate_gate("SHORT", 12.0, -0.5, DEFAULT_PARAMS)[0])
        self.assertFalse(evaluate_gate("SHORT", 12.0, 0.5, DEFAULT_PARAMS)[0])

    def test_no_side_or_missing_data_closes_the_gate(self):
        self.assertFalse(evaluate_gate(None, 12.0, 1.0, DEFAULT_PARAMS)[0])
        self.assertFalse(evaluate_gate("LONG", None, 1.0, DEFAULT_PARAMS)[0])
        self.assertFalse(evaluate_gate("LONG", 12.0, None, DEFAULT_PARAMS)[0])


class CostTests(unittest.TestCase):
    def test_default_round_trip_cost(self):
        self.assertAlmostEqual(round_trip_cost_pct(50_000, 12.5, 0.03), 0.124, places=3)

    def test_cost_in_r_scales_with_stop_size(self):
        # 0.124% of price on a 0.5% stop is ~0.25R; on a 1% stop ~0.12R
        self.assertAlmostEqual(net_r_multiple(1.0, 0.5, 0.124), 1.0 - 0.248, places=3)
        self.assertAlmostEqual(net_r_multiple(1.0, 1.0, 0.124), 1.0 - 0.124, places=3)


class FeatureTests(unittest.TestCase):
    def daily(self, closes):
        start = date(2026, 1, 1)
        return [((start + timedelta(days=i)).isoformat() + f"T00:00:00{TZ}", c, c * 1.01, c * 0.99, c, 1000)
                for i, c in enumerate(closes)]

    def test_prev_close_and_trend(self):
        idx = DailyIndex(self.daily([100 + i for i in range(30)]))
        day = (date(2026, 1, 1) + timedelta(days=25)).isoformat()
        self.assertEqual(idx.prev_close(day), 124)
        # mean of closes 105..124 is 114.5 -> 124 is ~8.3% above it
        self.assertAlmostEqual(idx.trend_pct(day), 100 * (124 / 114.5 - 1), places=6)

    def test_atr_uses_only_prior_sessions(self):
        idx = DailyIndex(self.daily([100] * 30))
        day = (date(2026, 1, 1) + timedelta(days=25)).isoformat()
        self.assertAlmostEqual(idx.atr_pct(day), 2.0, places=6)  # high/low are +/-1%

    def test_volume_ratios_need_history(self):
        days = {}
        for i in range(25):
            d = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
            vol = 300 if i == 24 else 100
            days[d] = [candle(d, k, 10, 11, 9, 10, vol) for k in range(10)]
        profile = VolumeProfile(days)
        last = max(days)
        self.assertAlmostEqual(profile.opening_ratio(last), 3.0)
        self.assertAlmostEqual(profile.slot_ratio(last, ts(last, 25)), 3.0)
        self.assertIsNone(profile.opening_ratio(min(days)))  # no history yet


class EngineKnobTests(unittest.TestCase):
    day = "2026-02-10"

    def candles(self, rows):
        return [candle(self.day, i, *r) for i, r in enumerate(rows)]

    def long_setup(self, after_entry):
        # range high 100; breakout candle (index 1) closes 101.8 with high 102 / low 101, so the entry
        # stop sits at 102 and the first candle after it that trades through 102 fills the order
        rows = [(100.5, 101.5, 100.2, 101.0, 100), (101, 102, 101, 101.8, 100)] + after_entry
        return self.candles(rows)

    def test_defaults_unchanged_target_at_2r(self):
        trade = simulate_trade("LONG", 100.0, 99.0, self.long_setup([(102.5, 107, 102.2, 106.5, 100)]))
        risk = trade["entry_price"] - trade["stop_loss"]
        self.assertAlmostEqual(trade["target"], trade["entry_price"] + 2 * risk)
        self.assertEqual(trade["outcome"], TARGET_HIT)
        self.assertAlmostEqual(trade["r_multiple"], 2.0, places=2)

    def test_target_rrr_parameter(self):
        trade = simulate_trade("LONG", 100.0, 99.0, self.long_setup([(101.5, 101.6, 101.4, 101.5, 100)]), target_rrr=3.0)
        risk = trade["entry_price"] - trade["stop_loss"]
        self.assertAlmostEqual(trade["target"], trade["entry_price"] + 3 * risk)

    def test_stop_floor_widens_a_tight_stop(self):
        rows = self.long_setup([(101.5, 101.6, 101.4, 101.5, 100)])
        tight = simulate_trade("LONG", 100.0, 99.0, rows)
        wide = simulate_trade("LONG", 100.0, 99.0, rows, stop_floor_pct=2.0)
        self.assertLess(tight["risk_pct"], 2.0)
        self.assertAlmostEqual(wide["risk_pct"], 2.0, places=2)
        self.assertLess(wide["stop_loss"], tight["stop_loss"])

    def test_breakeven_can_be_disabled(self):
        # reaches ~1R then falls back through the entry: stopped at breakeven by default,
        # but a plain stop-loss when the breakeven move is switched off
        after = [(101.5, 103.0, 101.4, 102.5, 100), (102.5, 102.6, 100.0, 100.1, 100)]
        with_be = simulate_trade("LONG", 100.0, 99.0, self.long_setup(after), breakeven_rrr=1.0)
        no_be = simulate_trade("LONG", 100.0, 99.0, self.long_setup(after), breakeven_rrr=None)
        self.assertEqual(with_be["outcome"], STOPPED_BREAKEVEN)
        self.assertEqual(no_be["outcome"], STOPPED_LOSS)

    def test_end_of_day_exit(self):
        rows = self.long_setup([(101.5, 102.0, 101.4, 101.8, 100)])
        self.assertEqual(simulate_trade("LONG", 100.0, 99.0, rows)["outcome"], EOD_EXIT)

    def test_retest_entry_buys_the_pullback(self):
        # breakout above 100, price pulls back to 100 two candles later, then runs
        rows = [(100.5, 101.5, 100.4, 101.2, 100), (101.2, 101.6, 100.9, 101.4, 100),
                (101.4, 101.5, 99.9, 100.6, 100), (100.6, 106.0, 100.5, 105.5, 100)]
        trade = simulate_trade("LONG", 100.0, 99.0, self.candles(rows), entry_mode="retest")
        self.assertEqual(trade["entry_price"], 100.0)
        self.assertLess(trade["stop_loss"], 99.9)


def synthetic_history(final_vix=12.0, breakout_volume=300, open_volume=200):
    """40 quiet sessions then one trending session where HDFCBANK breaks out of its 30-minute range."""
    days = [(date(2026, 1, 5) + timedelta(days=i)).isoformat() for i in range(41)]
    final = days[-1]

    def daily_series(closes):
        return [(d + f"T00:00:00{TZ}", c, c * 1.01, c * 0.99, c, 1000) for d, c in zip(days, closes)]

    nifty_closes = [100 + i for i in range(40)] + [140]  # steadily rising into the final day
    nifty_15m = {d: [(ts(d, 0), 0, 0, 0, nifty_closes[i - 1] if d == final else nifty_closes[i], 0)] for i, d in enumerate(days)}
    nifty_15m[final] = [(ts(final, 0), 139, 141, 139, 139 * 1.0 + 139 * 0.005, 0)]  # +0.5% vs prev close 139

    sector_daily = {n: DailyIndex(daily_series([100] * 41)) for n in V2_SECTORS}
    sector_15m = {n: {final: [(ts(final, 0), 100, 101.5, 100, 101.0, 0)]} for n in V2_SECTORS}  # +1.0%

    stock_5m = {}
    for i, d in enumerate(days):
        if d != final:
            stock_5m[d] = [candle(d, k, 1000, 1005, 995, 1000, 100) for k in range(75)]
    rows = [(1000, 1005, 998, 1004, open_volume)] * 2 + [(1004, 1013, 1003, 1012, open_volume)]  # 09:15-09:30, +1.2%
    rows += [(1012, 1015, 1005, 1010, 100)] * 3  # range 1005-1015 (09:30-09:45)
    rows += [(1010, 1021, 1012, 1020, breakout_volume)]  # 09:45 breakout candle closes above 1015
    rows += [(1020, 1025, 1019, 1024, 100)]  # fills the 1021 entry
    rows += [(1024, 1060, 1023, 1055, 100)]  # runs through the target
    rows += [(1055, 1056, 1054, 1055, 100)] * 60
    stock_5m[final] = [candle(final, k, *r) for k, r in enumerate(rows)]

    vix = DailyIndex(daily_series([final_vix] * 41))
    return History(
        nifty_15m=nifty_15m,
        nifty_daily=DailyIndex(daily_series(nifty_closes)),
        vix_daily=vix,
        sector_15m=sector_15m,
        sector_daily=sector_daily,
        stock_5m={"HDFCBANK": stock_5m},
        stock_daily={"HDFCBANK": DailyIndex(daily_series([1000] * 41))},
        stock_volume={"HDFCBANK": VolumeProfile(stock_5m)},
    ), final


class SnapshotTests(unittest.TestCase):
    def last_day(self, **kwargs):
        history, final = synthetic_history(**{k: v for k, v in kwargs.items() if k != "params"})
        days = compute_day_snapshots(history, kwargs.get("params", DEFAULT_PARAMS), start=final)
        self.assertEqual(len(days), 1)
        return days[0]

    def test_qualifying_breakout_is_traded_and_hits_target(self):
        day = self.last_day()
        self.assertTrue(day["gate_ok"])
        self.assertEqual(day["direction"], "LONG")
        self.assertEqual(day["trades_taken"], 1)
        trade = taken_trades([day])[0]
        self.assertEqual(trade["symbol"], "HDFCBANK")
        self.assertEqual(trade["outcome"], TARGET_HIT)
        self.assertGreater(trade["net_r"], 2.0)
        self.assertLess(trade["net_r"], trade["r_multiple"])  # costs reduce it

    def test_high_vix_skips_the_whole_day(self):
        day = self.last_day(final_vix=16.0)
        self.assertFalse(day["gate_ok"])
        self.assertEqual(day["trades_taken"], 0)
        self.assertIn("VIX", day["gate_reasons"][0])
        self.assertFalse(any(s["selected"] for s in day["sectors"]))

    def test_weak_breakout_volume_is_rejected_with_a_reason(self):
        day = self.last_day(breakout_volume=120)
        self.assertEqual(day["trades_taken"], 0)
        row = next(r for s in day["sectors"] for r in s["stocks"] if r["symbol"] == "HDFCBANK" and r["trade"])
        self.assertIn("breakout volume", row["note"])
        self.assertFalse(row["taken"])

    def test_low_opening_volume_never_reaches_simulation(self):
        day = self.last_day(open_volume=50)
        self.assertEqual(day["trades_taken"], 0)
        rows = [r for s in day["sectors"] for r in s["stocks"] if r["symbol"] == "HDFCBANK"]
        self.assertTrue(all(r["trade"] is None and not r["qualifies"] for r in rows))
        self.assertTrue(any(r["note"] and "opening volume" in r["note"] for r in rows))

    def test_daily_trade_cap(self):
        day = self.last_day(params=replace(DEFAULT_PARAMS, max_trades_per_day=0))
        self.assertEqual(day["trades_taken"], 0)


if __name__ == "__main__":
    unittest.main()
