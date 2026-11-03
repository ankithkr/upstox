from app.charges import round_trip_charges


def test_long_round_trip_matches_hand_computed_value():
    # qty=100, entry=1500 (buy), exit=1530 (sell)
    # brokerage: min(20, 1500*100*0.1/100)=20 buy, min(20, 1530*100*0.1/100)=20 sell -> 40
    # turnover = 150000+153000=303000; exchange=303000*0.00297/100=8.9991; sebi=303000*0.0001/100=0.303
    # stt = 153000*0.025/100=38.25; stamp = 150000*0.003/100=4.5
    # gst = (40+8.9991+0.303)*18/100 = 49.3021*0.18 = 8.874378
    charges = round_trip_charges("LONG", 100, 1500.0, 1530.0)
    expected = round(40 + 8.9991 + 0.303 + 38.25 + 4.5 + (40 + 8.9991 + 0.303) * 0.18, 2)
    assert charges == expected


def test_short_swaps_buy_and_sell_legs():
    # SHORT: sells first at entry, buys back at exit -> buy_value uses exit, sell_value uses entry
    long_equiv = round_trip_charges("LONG", 50, 1000.0, 950.0)
    short_equiv = round_trip_charges("SHORT", 50, 1000.0, 950.0)
    # LONG(entry=1000,exit=950): buy=1000(50), sell=950(50) -> stt on sell(950*50)
    # SHORT(entry=1000,exit=950): buy=950(50), sell=1000(50) -> stt on sell(1000*50) - different stt base
    assert long_equiv != short_equiv
