"""Universe + window for the 5-stock 15-minute-range breakout strategy."""
from datetime import date

# Tata Motors demerged (Oct 2025): TMPV is the continuing passenger-vehicle
# company (old ISIN INE155A01022), TMCV the new commercial-vehicle company
# which the instrument master names "TATA MOTORS LIMITED". Both are fetched;
# the headline universe uses TMPV and TMCV is analysed as an alternative.
UNIVERSE = {
    "RELIANCE": "NSE_EQ|INE002A01018",
    "TMPV": "NSE_EQ|INE155A01022",
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "ITC": "NSE_EQ|INE154A01025",
    "ADANIENT": "NSE_EQ|INE423A01024",
}
ALT_TATA = {"TMCV": "NSE_EQ|INE1TAE01010"}

START = date(2026, 4, 6)
END = date(2026, 10, 4)
DAILY_START = date(2026, 2, 20)
