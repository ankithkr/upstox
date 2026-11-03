"""Paper-trading (forward test) engine for the top-down ORB strategy.

    python paper_trade.py live                 run today's session, trades -> Google Sheets
    python paper_trade.py live --store local   same, but to data_cache/paper/trades.json
    python paper_trade.py replay               replay every cached day (validation, local only)
    python paper_trade.py status               account summary from the store

`live` should be started before 09:30 IST and left running until ~15:20; it
ticks after every 5-minute candle closes. It is safe to stop and restart -
each tick recomputes the day from the candles, and trades are upserted by id.
Needs a fresh Upstox token (`python upstox_auth.py`) and Google auth
(`python authenticate_google.py`) each day it runs live.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

from src.paper import config
from src.paper.engine import CLOSED, OPEN, SKIPPED, ExecutionRules, run_day, select_day, track_day
from src.paper.store import LocalStore, SheetsStore
from src.paper.summary import DAILY_HEADER, account_summary, closed_pnl_before, daily_table

MARKET_OPEN_SELECTION = "09:30:00"
LAST_TICK = "15:20:00"  # one tick after the 15:15 force exit, to catch late candles
NO_DATA_GIVE_UP = "09:45:00"


def _at(day: str, hms: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hms}+05:30")


def _sleep_until(target: datetime) -> None:
    while (remaining := (target - datetime.now(config.IST)).total_seconds()) > 0:
        time.sleep(min(remaining, 30))


def _next_boundary(now: datetime, delay: int) -> datetime:
    """The next 5-minute candle close after `now`, plus the publish delay."""
    base = now.replace(second=0, microsecond=0)
    boundary = base + timedelta(minutes=5 - base.minute % 5)
    return boundary + timedelta(seconds=delay)


def _make_store(name: str):
    return SheetsStore() if name == "sheets" else LocalStore()


def _day_line(result) -> str:
    trades = [t for t in result.trades if t["status"] in (OPEN, CLOSED)]
    net = sum(t["net_pnl"] for t in trades)
    open_n = sum(1 for t in trades if t["status"] == OPEN)
    sel = result.selection
    return (
        f"bias={sel.market_bias} nifty={sel.nifty_change:+.2f}% "
        f"sectors={','.join(sel.sectors) or '-'} | watching={len(result.watching)} "
        f"pending={len(result.pending)} open={open_n} closed={len(trades) - open_n} "
        f"skipped={sum(1 for t in result.trades if t['status'] == SKIPPED)} | day net Rs {net:,.2f}"
    )


def cmd_live(args) -> int:
    from src.paper.feed import LiveFeed

    now = datetime.now(config.IST)
    day = now.date().isoformat()
    if now.weekday() >= 5:
        print(f"{day} is a weekend - nothing to trade.")
        return 0

    store = _make_store(args.store)
    feed = LiveFeed()
    start_equity = config.STARTING_CAPITAL + closed_pnl_before(store.load_trades(), day)
    print(f"Paper trading {day} | start-of-day equity Rs {start_equity:,.2f} | store={args.store}")

    selection = None
    while True:
        _sleep_until(_at(day, MARKET_OPEN_SELECTION) + timedelta(seconds=args.delay))
        now = datetime.now(config.IST)

        try:
            if selection is None or not selection.complete:
                selection = select_day(day, feed, now)
            if selection is None:
                if now >= _at(day, NO_DATA_GIVE_UP):
                    print("No NIFTY candles for today - market holiday? Exiting.")
                    return 0
                print(f"{now:%H:%M:%S} waiting for the first 15-minute candle...")
            else:
                result = track_day(selection, feed, now, start_equity)
                store.upsert_trades(result.trades)
                store.write_summary(config.STARTING_CAPITAL)
                print(f"{now:%H:%M:%S} {_day_line(result)}", flush=True)
        except RuntimeError as e:  # expired token etc. - retrying won't help
            print(f"FATAL: {e}")
            return 1
        except Exception as e:  # transient network / Sheets hiccup: try again next tick
            print(f"{now:%H:%M:%S} tick failed ({type(e).__name__}: {e}) - retrying next candle", flush=True)

        if now >= _at(day, LAST_TICK):
            break
        _sleep_until(_next_boundary(now, args.delay))

    print("Session complete.")
    return 0


def cmd_replay(args) -> int:
    os.environ["UPSTOX_OFFLINE"] = "1"  # serve the candle cache only, never the network

    from precompute_ui import _cached_range
    from src.backtest.reference_values import trading_days
    from src.data.indices import NIFTY_50_INSTRUMENT_KEY
    from src.integrations.upstox_history import get_candles
    from src.paper.feed import ReplayFeed

    start, end = _cached_range()
    feed = ReplayFeed(start, end)
    days = trading_days(get_candles(NIFTY_50_INSTRUMENT_KEY, "minutes", "15", start, end))
    if args.start:
        days = [d for d in days if d >= args.start]
    if args.end:
        days = [d for d in days if d <= args.end]

    store = LocalStore(f"{config.LOCAL_DIR}/replay_trades.json", fresh=True)
    rules = ExecutionRules()
    print(f"Replaying {len(days)} days ({days[0]} to {days[-1]}), starting capital Rs {config.STARTING_CAPITAL:,.0f}")

    for day in days:
        equity = config.STARTING_CAPITAL + closed_pnl_before(store.load_trades(), day)
        result = run_day(day, feed, _at(day, "15:30:00"), equity, rules)
        if result.selection is None:
            continue
        store.upsert_trades(result.trades)
        if result.trades and args.verbose:
            print(f"{day} equity {equity:>11,.2f} | {_day_line(result)}")

    _print_summary(store.load_trades())
    print(f"\nTrades saved to {store.path}")
    return 0


def cmd_status(args) -> int:
    _print_summary(_make_store(args.store).load_trades())
    return 0


def _print_summary(trades: list[dict]) -> None:
    s = account_summary(trades, config.STARTING_CAPITAL)
    print("\n== Account ==")
    for label, key in [
        ("Starting capital", "starting_capital"), ("Equity", "equity"), ("Return %", "return_pct"),
        ("Realised net P&L", "realised_net_pnl"), ("Unrealised net P&L", "unrealised_net_pnl"),
        ("Gross P&L", "gross_pnl"), ("Charges", "total_charges"), ("Closed trades", "closed_trades"),
        ("Open trades", "open_trades"), ("Skipped signals", "skipped_signals"), ("Win rate %", "win_rate_pct"),
    ]:  # fmt: skip
        print(f"  {label:<20} {s[key]:>12,}")
    rows = daily_table(trades, config.STARTING_CAPITAL)
    if rows:
        print(f"\n== Last {min(len(rows), 10)} days ==")
        print("  " + " ".join(f"{h:>10}" for h in DAILY_HEADER))
        for r in rows[-10:]:
            print("  " + " ".join(f"{v:>10}" for v in r))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    live = sub.add_parser("live", help="run today's session")
    live.add_argument("--store", choices=["sheets", "local"], default="sheets")
    live.add_argument("--delay", type=int, default=config.CANDLE_PUBLISH_DELAY_SECONDS,
                      help="seconds to wait after each 5-min close for Upstox to publish the candle")
    live.set_defaults(func=cmd_live)

    replay = sub.add_parser("replay", help="replay cached history through the engine (local, offline)")
    replay.add_argument("--from", dest="start", help="first day, YYYY-MM-DD")
    replay.add_argument("--to", dest="end", help="last day, YYYY-MM-DD")
    replay.add_argument("-v", "--verbose", action="store_true", help="one line per trading day")
    replay.set_defaults(func=cmd_replay)

    status = sub.add_parser("status", help="account summary from the store")
    status.add_argument("--store", choices=["sheets", "local"], default="sheets")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
