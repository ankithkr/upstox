import sys,math,itertools; sys.path.insert(0,'.')
from research2 import *
import src.backtest.orb_engine as E
d=load(); cands,info=build_candidates(d); cp=cost_pct()
E.TARGET_RRR=3.0
def mk(**eng):
    tr=simulate(cands,or_n=6,stop_floor_atr=0.4,breakeven_rrr=1.5,**eng); add_breakout_volume(tr,d)
    tr=[t for t in tr if (t['rel_bvol'] or 0)>=1.5 and (t['rel_vol'] or 0)>=1.0]
    for t in tr:
        sg=1 if t['direction']=='LONG' else -1; t['ntrend']=(t['m_nifty_trend'] or 0)*sg
    return tr
def row(label,sel):
    a=stats([t for t in sel if t['date']<=TRAIN_END],cp); b=stats([t for t in sel if t['date']>TRAIN_END],cp); s=stats(sel,cp)
    f=lambda x:f"n={x['n']:3d} E={x['E']:+.3f} PF={x['pf']:.2f}" if x else "-"
    print(f"  {label:<26} train {f(a)} | test {f(b)} | all {f(s)}")
F=mk(entry_mode="breakout"); R=mk(entry_mode="retest")
print("== threshold sensitivity (cap3). rows: VIX max, cols: trend min")
for name,tr in (("F breakout",F),("R retest",R)):
    print("\n",name)
    for vmax in (12,13,14,15,16,99):
        for tmin in (-99,0,0.5,1.0):
            row(f"VIX<{vmax} trend>{tmin}",cap_per_day([t for t in tr if (t['m_vix'] or 99)<vmax and t['ntrend']>tmin],3))
print("\n== retest fill realism: need price to trade THROUGH the level by x% (gate VIX<14 & trend>0)")
for buf in (0,0.05,0.1,0.2):
    tr=mk(entry_mode="retest",retest_fill_buffer_pct=buf)
    row(f"fill buffer {buf}%",cap_per_day([t for t in tr if (t['m_vix'] or 99)<14 and t['ntrend']>0],3))
print("\n== retest window (candles to wait for pullback)")
for w in (3,6,12):
    tr=mk(entry_mode="retest",retest_window=w)
    row(f"window {w}",cap_per_day([t for t in tr if (t['m_vix'] or 99)<14 and t['ntrend']>0],3))
print("\n== universe size: top-N most-liquid stocks only (R retest, gate)")
with open("data_cache/research_universe.txt") as f: uni=f.read().split()
for n in (40,60,120):
    keep=set(uni[:n]); sel=cap_per_day([t for t in R if t['symbol'] in keep and (t['m_vix'] or 99)<14 and t['ntrend']>0],3)
    row(f"top {n} stocks",sel)
print("\n== per-day cap sensitivity (R retest gate)")
for cap in (1,2,3,5,99):
    row(f"cap {cap}/day",cap_per_day([t for t in R if (t['m_vix'] or 99)<14 and t['ntrend']>0],cap))
print("\n== combined F+R (R preferred, F fills gaps), cap3")
both=[t for t in R if (t['m_vix'] or 99)<14 and t['ntrend']>0]+[t for t in F if (t['m_vix'] or 99)<14 and t['ntrend']>0]
seen=set(); uniq=[]
for t in sorted(both,key=lambda t:t['entry_time']):
    k=(t['date'],t['symbol'])
    if k in seen: continue
    seen.add(k); uniq.append(t)
row("F+R union",cap_per_day(uniq,3))
