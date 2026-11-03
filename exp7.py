import sys,math,itertools; sys.path.insert(0,'.')
from research2 import *
import src.backtest.orb_engine as E
d=load(); cands,info=build_candidates(d); cp=cost_pct()
E.TARGET_RRR=3.0
fams={"F breakout or6":dict(entry_mode="breakout",or_n=6,stop_floor_atr=0.4,breakeven_rrr=1.5),
      "R retest or6":dict(entry_mode="retest",or_n=6,stop_floor_atr=0.4,breakeven_rrr=1.5)}
gates={"no gate":lambda t:True,
 "VIX<14":lambda t:t['m_vix'] is not None and t['m_vix']<14,
 "VIX<13":lambda t:t['m_vix'] is not None and t['m_vix']<13,
 "nifty trend aligned >0":lambda t:t['ntrend']>0,
 "nifty trend aligned >1":lambda t:t['ntrend']>1,
 "VIX<14 & trend>0":lambda t:t['m_vix'] is not None and t['m_vix']<14 and t['ntrend']>0,
 "VIX<14 & trend>1":lambda t:t['m_vix'] is not None and t['m_vix']<14 and t['ntrend']>1}
def tstat(rs):
    n=len(rs); m=sum(rs)/n; sd=(sum((x-m)**2 for x in rs)/(n-1))**.5; return m/(sd/math.sqrt(n))
print(HEADER)
store={}
for fname,eng in fams.items():
    tr=simulate(cands,**eng); add_breakout_volume(tr,d)
    tr=[t for t in tr if (t['rel_bvol'] or 0)>=1.5 and (t['rel_vol'] or 0)>=1.0]
    for t in tr:
        sg=1 if t['direction']=='LONG' else -1; t['ntrend']=(t['m_nifty_trend'] or 0)*sg
    print("\n=====",fname)
    for gname,g in gates.items():
        sel=cap_per_day([t for t in tr if g(t)],3); store[(fname,gname)]=sel
        report(gname,sel,cp)
# detail on a few
for key in [("F breakout or6","VIX<14 & trend>0"),("R retest or6","VIX<14 & trend>0"),("F breakout or6","VIX<14")]:
    sel=store[key]; print("\n#### detail",key,"trades",len(sel),"days",len({t['date'] for t in sel}),"avg stop%",round(sum(t['risk_pct'] for t in sel)/len(sel),2))
    for label,c in (("gross",0),("cost 0.06",cost_pct(notional=200000)),("cost 0.124",cost_pct()),("cost 0.20",cost_pct(slippage_pct=0.11))):
        rs=[net_r(t,c) for t in sel]; print(f"   {label:<11} E={sum(rs)/len(rs):+.3f}R t={tstat(rs):+.2f} netR/yr={sum(rs)/3.64:+.1f}")
    print("   by year:",{y:(round(sum(net_r(t,cp) for t in sel if t['date'].startswith(y)),1),sum(1 for t in sel if t['date'].startswith(y))) for y in ('2023','2024','2025','2026')})
    print("   long/short:",{dr:(round(sum(net_r(t,cp) for t in sel if t['direction']==dr)/max(1,sum(1 for t in sel if t['direction']==dr)),3),sum(1 for t in sel if t['direction']==dr)) for dr in ('LONG','SHORT')})
