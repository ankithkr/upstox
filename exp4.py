import sys,math; sys.path.insert(0,'.')
from research2 import *
import src.backtest.orb_engine as E
d=load(); cands,info=build_candidates(d)
def pick(tr,bv,vol): return cap_per_day([t for t in tr if (t['rel_bvol'] or 0)>=bv and (t['rel_vol'] or 0)>=vol],3)
E.TARGET_RRR=3.0
cfgs={"A: floor0.5ATR BE1.5 T3 bvol>=1.5 vol>=1":(dict(stop_floor_atr=0.5,breakeven_rrr=1.5),1.5,1.0),
      "B: floor0.4ATR BE1.5 T3 bvol>=1.5 vol>=1":(dict(stop_floor_atr=0.4,breakeven_rrr=1.5),1.5,1.0),
      "C: skip risk/ATR<0.3 BE1.5 T3 vol>=1":(dict(breakeven_rrr=1.5),0,1.0)}
for name,(eng,bv,vol) in cfgs.items():
    tr=simulate(cands,**eng); add_breakout_volume(tr,d)
    sel=pick(tr,bv,vol)
    if name.startswith("C"): sel=[t for t in sel if t['risk_pct']/t['atr_pct']>=0.3]
    print("\n",name, "trades:",len(sel),"days traded:",len({t['date'] for t in sel}),"of",len(info))
    print("  avg stop %:",round(sum(t['risk_pct'] for t in sel)/len(sel),2))
    for label,cpv in (("gross (no cost)",0),("cost 0.06% (big notional)",cost_pct(notional=200000)),("cost 0.124% (assumed)",cost_pct()),("cost 0.20% (poor fills)",cost_pct(slippage_pct=0.11))):
        rs=[net_r(t,cpv) for t in sel]; n=len(rs); m=sum(rs)/n; sd=(sum((x-m)**2 for x in rs)/(n-1))**.5
        print(f"  {label:<28} E[R]={m:+.3f}  t-stat={m/(sd/math.sqrt(n)):+.2f}  netR/yr={sum(rs)/3.64:+.1f}")
    print("  by year:",{y:(round(sum(net_r(t,cost_pct()) for t in sel if t['date'].startswith(y)),1),sum(1 for t in sel if t['date'].startswith(y))) for y in ('2023','2024','2025','2026')})
    print("  long/short E:",{dr:round(sum(net_r(t,cost_pct()) for t in sel if t['direction']==dr)/max(1,sum(1 for t in sel if t['direction']==dr)),3) for dr in ('LONG','SHORT')})
