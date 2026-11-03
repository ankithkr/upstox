# Liquid-stock universe for the v2 strategy: the 120 most-traded NSE stocks
# (median daily turnover over the trailing year, as of the 2026-10 backfill),
# restricted to names that appear in at least one sector index list.
# NOTE: chosen with hindsight (current liquidity), so historical results carry
# some survivorship bias.

LIQUID_UNIVERSE = [
    "HDFCBANK", "ICICIBANK", "RELIANCE", "BSE", "INFY", "SBIN",
    "TCS", "AXISBANK", "M&M", "MCX", "BAJFINANCE", "IDEA",
    "VEDL", "DIXON", "KOTAKBANK", "SHRIRAMFIN", "MARUTI", "TATASTEEL",
    "HINDALCO", "ITC", "HINDCOPPER", "SUNPHARMA", "HCLTECH", "TMPV",
    "ADANIENT", "COFORGE", "EICHERMOT", "HINDUNILVR", "TITAN", "PAYTM",
    "NATIONALUM", "BAJAJ-AUTO", "CANBK", "SAIL", "ONGC", "HINDZINC",
    "JIOFIN", "HEROMOTOCO", "ULTRACEMCO", "TECHM", "TVSMOTOR", "ASHOKLEY",
    "APOLLOHOSP", "PERSISTENT", "PFC", "WIPRO", "BPCL", "BANKBARODA",
    "MAXHEALTH", "POLICYBZR", "CHOLAFIN", "VBL", "INDUSINDBK", "DIVISLAB",
    "LAURUSLABS", "HDFCAMC", "INDUSTOWER", "HINDPETRO", "RECLTD", "CDSL",
    "UNIONBANK", "DLF", "MUTHOOTFIN", "DRREDDY", "MOTHERSON", "FEDERALBNK",
    "KALYANKJIL", "GRASIM", "AMBER", "SOLARINDS", "HDFCLIFE", "LUPIN",
    "BAJAJFINSV", "ANGELONE", "PNB", "JSWSTEEL", "YESBANK", "IOC",
    "IDFCFIRSTB", "SBILIFE", "CIPLA", "AUBANK", "BHARATFORG", "LODHA",
    "NESTLEIND", "NMDC", "RBLBANK", "BRITANNIA", "CHENNPETRO", "GAIL",
    "OFSS", "INDIANB", "LTM", "BANDHANBNK", "TATACONSUM", "FORTIS",
    "LTF", "HSCL", "AUROPHARMA", "ABCAPITAL", "TORNTPHARM", "GODREJPROP",
    "MARICO", "JINDALSTEL", "OIL", "UPL", "BANKINDIA", "GODREJCP",
    "VOLTAS", "GLENMARK", "LICI", "BIOCON", "MAHABANK", "MANAPPURAM",
    "MPHASIS", "APLAPOLLO", "MFSL", "PGEL", "ANANTRAJ", "RADICO",
]

# Sector indices the v2 strategy trades (the liquid ones; the mid/small-cap
# and thematic indices add no tradable names).
V2_SECTORS = [
    "NIFTY AUTO",
    "NIFTY BANK",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY FMCG",
    "NIFTY IT",
    "NIFTY MEDIA",
    "NIFTY METAL",
    "NIFTY PHARMA",
    "NIFTY PSU BANK",
    "NIFTY REALTY",
    "NIFTY PRIVATE BANK",
    "NIFTY HEALTHCARE",
    "NIFTY CONSUMER DURABLES",
    "NIFTY OIL & GAS",
    "NIFTY FINANCIAL SERVICES EX-BANK",
    "NIFTY CEMENT",
]

VIX_INSTRUMENT_KEY = "NSE_INDEX|India VIX"
