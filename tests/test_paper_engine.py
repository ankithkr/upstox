"""Run with:  python -m unittest discover -s tests -v"""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.indices import NIFTY_50_INSTRUMENT_KEY, SECTOR_INDEX_INSTRUMENT_KEYS
from src.paper.charges import round_trip_charges
from src.paper.engine import (
    CLOSED, EXPIRED, OPEN, PENDING, SKIPPED, DaySelection, ExecutionRules, Plan, Setup,
    build_trades, closed, run_day, walk,
)  # fmt: skip
from src.paper.store import SheetsStore
from src.paper.summary import closed_pnl_before

DAY = "2026-08-21"
RULES = ExecutionRules(gap_fills=False)


def candle(hhmm, o, h, l, c, day=DAY):
    return (f"{day}T{hhmm}:00+05:30", o, h, l, c, 1000)


def opening(high=100.0, low=99.0):
    """First three 5-min candles (09:15-09:30) spanning [low, high]."""
    return [candle("09:15", 99.5, high, low, 99.8), candle("09:20", 99.8, high, low, 99.9), candle("09:25", 99.9, high, low, 99.9)]


def setup(direction="LONG", order=0, symbol="INFY", high=100.0, low=99.0):
    return Setup(symbol, f"KEY_{symbol}", "NIFTY IT", direction, high, low, 1.0, 1.0, order)


class ChargesTest(unittest.TestCase):
    def test_round_trip_is_positive_and_scales_with_size(self):
        small = round_trip_charges("LONG", 10, 100, 101)
        big = round_trip_charges("LONG", 1000, 100, 101)
        self.assertGreater(small, 0)
        self.assertGreater(big, small)

    def test_brokerage_capped_at_flat_fee(self):
        # 2 orders x Rs 20 flat dominates for a big position; charges ~ 40 + taxes.
        c = round_trip_charges("LONG", 1000, 100, 100)
        self.assertGreater(c, 40)
        self.assertLess(c, 40 + 0.00031 * 200_000 * 1.2 + 60)


class WalkTest(unittest.TestCase):
    # breakout candle 09:30: close 100.5 > 100 -> entry 101.0 (its high), SL = 99.5 - 0.075%
    breakout = candle("09:30", 100.0, 101.0, 99.5, 100.5)

    def run_walk(self, later, direction="LONG", rules=RULES, **kw):
        return walk(setup(direction, **kw), opening() + [self.breakout] + later, rules)

    def test_no_breakout_stays_watching(self):
        plan = walk(setup(), opening() + [candle("09:30", 99.9, 100.0, 99.5, 99.9)], RULES)
        self.assertEqual(plan.state, "WATCHING")

    def test_breakout_close_alone_does_not_fill(self):
        plan = self.run_walk([])
        self.assertEqual(plan.state, PENDING)
        self.assertEqual(plan.entry_price, None)

    def test_long_hits_target(self):
        risk = 101.0 - 99.5 * (1 - 0.00075)
        plan = self.run_walk([candle("09:35", 100.9, 101.2, 100.8, 101.1), candle("09:40", 101.1, 101 + 2 * risk + 0.1, 101.2, 103.9)])
        self.assertEqual((plan.state, plan.outcome), (CLOSED, "TARGET_HIT"))
        self.assertAlmostEqual(plan.exit_price, 101 + 2 * risk)

    def test_breakeven_then_stopped_flat(self):
        risk = 101.0 - 99.5 * (1 - 0.00075)
        plan = self.run_walk([
            candle("09:35", 100.9, 101.2, 100.8, 101.1),                # fills
            candle("09:40", 101.1, 101 + risk + 0.05, 101.0, 101.5),    # reaches 1R -> stop to entry
            candle("09:45", 101.5, 101.6, 100.9, 101.0),                # falls back through entry
        ])
        self.assertEqual(plan.outcome, "STOPPED_BREAKEVEN")
        self.assertAlmostEqual(plan.exit_price, 101.0)

    def test_short_mirrors_long(self):
        breakout = candle("09:30", 99.0, 99.5, 98.0, 98.5)  # close < 99 -> entry 98.0
        candles = opening() + [breakout, candle("09:35", 98.1, 98.2, 97.9, 98.0), candle("09:40", 98.0, 99.7, 97.9, 99.6)]
        plan = walk(setup("SHORT"), candles, RULES)
        self.assertEqual((plan.outcome, plan.exit_price > 98.0), ("STOPPED_LOSS", True))

    def test_gap_open_fills_at_open_when_enabled(self):
        later = [candle("09:35", 101.5, 101.8, 101.4, 101.6)]  # opens above the 101.0 trigger
        plan = self.run_walk(later, rules=ExecutionRules(gap_fills=True))
        self.assertAlmostEqual(plan.entry_price, 101.5)
        plan = self.run_walk(later, rules=ExecutionRules(gap_fills=False))
        self.assertAlmostEqual(plan.entry_price, 101.0)

    def test_open_position_is_marked_to_last_close(self):
        plan = self.run_walk([candle("09:35", 100.9, 101.2, 100.6, 100.8)])
        self.assertEqual(plan.state, OPEN)
        self.assertEqual(plan.last_price, 100.8)

    def test_force_exit_at_last_candle(self):
        filler = [candle("09:35", 100.9, 101.2, 100.6, 100.8)]
        filler += [candle(f"{h:02d}:{m:02d}", 100.8, 101.1, 100.6, 100.9) for h in range(9, 16) for m in range(0, 60, 5) if "09:40" <= f"{h:02d}:{m:02d}" <= "15:10"]
        plan = self.run_walk(filler)
        self.assertEqual((plan.outcome, plan.exit_time[11:16]), ("EOD_EXIT", "15:15"))

    def test_no_entry_in_last_candle(self):
        plan = self.run_walk([candle("15:10", 100.9, 101.2, 100.8, 101.1)])
        self.assertEqual(plan.state, EXPIRED)


class SizingTest(unittest.TestCase):
    def selection(self):
        return DaySelection(DAY, "BULLISH", 0.5, "LONG", {}, ["NIFTY IT"], [])

    def plan(self, symbol, order, entry, stop, entry_ts, exit_ts=None, exit_price=None, state=None):
        p = Plan(setup=setup("LONG", order, symbol), breakout_time=entry_ts, entry_ts=entry_ts, entry_price=entry, stop_loss=stop, target=entry + 2 * (entry - stop), last_price=entry)
        if exit_ts:
            p.state, p.outcome, p.exit_ts, p.exit_time, p.exit_price = CLOSED, "TARGET_HIT", exit_ts, exit_ts, exit_price
        else:
            p.state = state or OPEN
        return p

    def ts(self, hhmm):
        return f"{DAY}T{hhmm}:00+05:30"

    def test_risk_sizing_when_cash_is_plentiful(self):
        # risk/share = 2 -> 1% of 100k = 1000 -> 500 shares @ 100 = Rs 50k, fits.
        [t] = build_trades([self.plan("INFY", 0, 100.0, 98.0, self.ts("09:35"))], self.selection(), 100_000)
        self.assertEqual((t["qty"], t["position_value"], t["note"]), (500, 50_000.0, ""))
        self.assertAlmostEqual(t["risk_amount"], 1000.0)

    def test_qty_capped_by_free_cash(self):
        # risk/share 0.5 -> 2000 shares wanted (Rs 200k) but only Rs 100k of cash -> 1000 shares.
        [t] = build_trades([self.plan("INFY", 0, 100.0, 99.5, self.ts("09:35"))], self.selection(), 100_000)
        self.assertEqual(t["qty"], 1000)
        self.assertIn("cash-limited", t["note"])

    def test_second_concurrent_trade_is_skipped_when_cash_is_gone(self):
        plans = [self.plan("INFY", 0, 100.0, 99.5, self.ts("09:35")), self.plan("TCS", 1, 100.0, 99.5, self.ts("09:40"))]
        first, second = build_trades(plans, self.selection(), 100_000)
        self.assertEqual((first["status"], second["status"]), (OPEN, SKIPPED))

    def test_cash_is_reused_only_after_an_earlier_candle_exit(self):
        exited = self.plan("INFY", 0, 100.0, 99.5, self.ts("09:35"), self.ts("09:40"), 102.0)
        same_candle = self.plan("TCS", 1, 100.0, 99.5, self.ts("09:40"))
        later = self.plan("HCLTECH", 2, 100.0, 99.5, self.ts("09:45"))
        trades = {t["symbol"]: t for t in build_trades([exited, same_candle, later], self.selection(), 100_000)}
        self.assertEqual(trades["TCS"]["status"], SKIPPED)      # INFY exits in this same candle
        self.assertEqual(trades["HCLTECH"]["status"], OPEN)     # INFY's cash + profit is free by now
        self.assertGreater(trades["HCLTECH"]["qty"], 1000)      # profit released -> a bit more cash

    def test_pnl_signs_and_net_of_charges(self):
        win = self.plan("INFY", 0, 100.0, 98.0, self.ts("09:35"), self.ts("09:40"), 104.0)
        [t] = build_trades([win], self.selection(), 100_000)
        self.assertAlmostEqual(t["gross_pnl"], 2000.0)
        self.assertAlmostEqual(t["net_pnl"], 2000.0 - t["charges"], places=2)
        self.assertAlmostEqual(t["r_multiple"], 2.0)


class FakeFeed:
    """A bullish day: NIFTY +0.5%, NIFTY IT +1%, and INFY qualifying (+1.5%) and breaking out."""

    def __init__(self):
        self.data = {
            (NIFTY_50_INSTRUMENT_KEY, "15"): [candle("09:15", 100, 100.6, 99.9, 100.5)],
            (SECTOR_INDEX_INSTRUMENT_KEYS["NIFTY IT"], "15"): [candle("09:15", 100, 101.2, 99.9, 101.0)],
        }
        stock = opening(high=101.6, low=100.4)
        stock[2] = candle("09:25", 101.0, 101.6, 100.4, 101.5)  # 09:30 close 101.5 vs prev 100 => +1.5%
        stock += [candle("09:30", 101.5, 102.0, 101.4, 101.9)]  # closes > 101.6 -> breakout, entry 102.0
        stock += [candle("09:35", 101.9, 102.1, 101.8, 102.0)]  # fills
        self.data[("KEY_INFY", "5")] = stock

    def candles(self, key, unit, interval, day):
        return self.data.get((key, interval), [])

    def prev_close(self, key, day):
        return 100.0

    def symbol_key(self, symbol):
        return f"KEY_{symbol}"


class DayFlowTest(unittest.TestCase):
    def at(self, hhmm, sec=0):
        return datetime.fromisoformat(f"{DAY}T{hhmm}:{sec:02d}+05:30")

    def test_nothing_before_first_candle_closes(self):
        self.assertIsNone(run_day(DAY, FakeFeed(), self.at("09:29", 59), 100_000).selection)

    def test_selects_bullish_sector_and_qualifying_stock(self):
        result = run_day(DAY, FakeFeed(), self.at("09:31"), 100_000)
        self.assertEqual(result.selection.market_bias, "BULLISH")
        self.assertEqual(result.selection.sectors, ["NIFTY IT"])
        self.assertEqual([s.symbol for s in result.selection.setups], ["INFY"])

    def test_no_lookahead(self):
        """A candle only counts once it has fully closed."""
        feed = FakeFeed()
        # 09:30 breakout candle ends 09:35: still forming at 09:34:59 -> nothing known yet.
        early = run_day(DAY, feed, self.at("09:34", 59), 100_000)
        self.assertEqual((early.trades, early.pending, early.watching), ([], [], ["INFY"]))
        # 09:35:01: breakout confirmed, but the 09:35 candle (the fill) is still forming.
        confirmed = run_day(DAY, feed, self.at("09:35", 1), 100_000)
        self.assertEqual((confirmed.trades, confirmed.pending), ([], ["INFY"]))
        # 09:40:01: the 09:35 candle has closed with the fill.
        filled = run_day(DAY, feed, self.at("09:40", 1), 100_000)
        self.assertEqual([t["status"] for t in filled.trades], [OPEN])

    def test_recompute_is_idempotent(self):
        feed, now = FakeFeed(), self.at("09:41")
        self.assertEqual(run_day(DAY, feed, now, 100_000).trades, run_day(DAY, feed, now, 100_000).trades)

    def test_closed_helper_excludes_forming_candle(self):
        cs = [candle("09:30", 1, 1, 1, 1), candle("09:35", 1, 1, 1, 1)]
        self.assertEqual(len(closed(cs, 5, self.at("09:35"))), 1)
        self.assertEqual(len(closed(cs, 5, self.at("09:40"))), 2)


class FakeWorksheet:
    id = 7

    def __init__(self):
        self.rows = []

    def row_values(self, n):
        return self.rows[0] if self.rows else []

    def update(self, values, range_name=None, **kw):
        self.rows = [list(values[0])] if range_name == "A1" and len(values) == 1 else self.rows

    def col_values(self, n):
        return [r[n - 1] for r in self.rows]

    def batch_update(self, updates):
        for u in updates:
            self.rows[int(u["range"][1:]) - 1] = list(u["values"][0])

    def append_rows(self, values, table_range=None):
        self.rows.extend(list(v) for v in values)

    def get_all_records(self, expected_headers=None):
        head = self.rows[0]
        return [dict(zip(head, r)) for r in self.rows[1:]]


class FakeSpreadsheet:
    def __init__(self):
        self.ws = FakeWorksheet()
        self.batches = []

    def worksheet(self, title):
        return self.ws

    def batch_update(self, body):
        self.batches.append(body)


class SheetsStoreTest(unittest.TestCase):
    def test_upsert_updates_in_place_and_round_trips(self):
        store = SheetsStore(FakeSpreadsheet())
        sel = DaySelection(DAY, "BULLISH", 0.5, "LONG", {}, [], [])
        plan = SizingTest().plan("INFY", 0, 100.0, 98.0, f"{DAY}T09:35:00+05:30")
        [open_trade] = build_trades([plan], sel, 100_000)

        store.upsert_trades([open_trade])
        self.assertEqual(len(store.trades_ws.rows), 2)

        closed_plan = SizingTest().plan("INFY", 0, 100.0, 98.0, f"{DAY}T09:35:00+05:30", f"{DAY}T09:40:00+05:30", 104.0)
        [closed_trade] = build_trades([closed_plan], sel, 100_000)
        store.upsert_trades([closed_trade])
        self.assertEqual(len(store.trades_ws.rows), 2, "same trade_id must update, not append")

        [loaded] = store.load_trades()
        self.assertEqual(loaded["status"], CLOSED)
        self.assertAlmostEqual(loaded["net_pnl"], closed_trade["net_pnl"])
        self.assertIsNone(loaded["note"] or None)
        self.assertEqual(closed_pnl_before([loaded], "2026-08-22"), loaded["net_pnl"])
        self.assertEqual(closed_pnl_before([loaded], DAY), 0)


if __name__ == "__main__":
    unittest.main()
