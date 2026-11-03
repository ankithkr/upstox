import os
from datetime import timedelta, timezone

# NSE runs on IST; a fixed offset avoids needing tzdata on Windows.
IST = timezone(timedelta(hours=5, minutes=30))

STARTING_CAPITAL = float(os.getenv("PAPER_CAPITAL", "100000"))

# PDF section 5: risk a fixed % of capital per trade (1%), qty = risk / (entry - SL).
RISK_PER_TRADE_PCT = 1.0

# No leverage: a position's value (long or short) must fit in free cash.
# Set >1 only if you want to simulate MIS margin.
LEVERAGE = 1.0

# Adverse slippage applied to entries and to stop / market exits (not to
# resting target limits). 0 matches the backtest's perfect fills.
SLIPPAGE_PCT = 0.0

# Candle-start times (HH:MM). The candle starting here is the last one
# traded; anything still open at its close (15:15) is force-exited, per
# PDF section 6. No new entries fill in or after that candle either.
FORCE_EXIT_CANDLE_START = "15:10"
LAST_ENTRY_CANDLE_START = "15:10"

# Live loop: seconds to wait after a 5-min boundary for Upstox to publish
# the just-closed candle.
CANDLE_PUBLISH_DELAY_SECONDS = 15

# Sheets worksheets the engine writes to.
TRADES_SHEET = "Paper Trades"
SUMMARY_SHEET = "Paper Summary"

LOCAL_DIR = "data_cache/paper"
