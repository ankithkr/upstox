"""Fetch (and cache) 1-minute + daily candles for the ORB-15 universe."""
from src.integrations.upstox_history import get_candles
from src.orb15.config import ALT_TATA, DAILY_START, END, START, UNIVERSE

for sym, key in {**UNIVERSE, **ALT_TATA}.items():
    m = get_candles(key, "minutes", "1", START, END)
    d = get_candles(key, "days", "1", DAILY_START, END)
    print(f"{sym:9s} 1m={len(m):6d} days={len({c[0][:10] for c in m}):4d} daily={len(d)}")
