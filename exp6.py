import sys,pickle,itertools,statistics; sys.path.insert(0,'.')
from research2 import *
import src.backtest.orb_engine as E
d=load(); cands,info=build_candidates(d); cp=cost_pct()
fams={"F breakout or6":dict(entry_mode="breakout",or_n=6,stop_floor_atr=0.4,breakeven_rrr=1.5),
      "R retest   or6":dict(entry_mode="retest",or_n=6,stop_floor_atr=0.4,breakeven_rrr=1.5)}
E.TARGET_RRR=3.0
data={}
for name,eng in fams.items():
    tr=simulate(cands,**eng); add_breakout_volume(tr,d)
    data[name]=[t for t in tr if (t['rel_bvol'] or 0)>=1.5 and (t['rel_vol'] or 0)>=1.0]
    for t in data[name]:
        sg=1 if t['direction']=='LONG' else -1
        t['breadth_dir']=t['m_breadth'] if sg==1 else 100-t['m_breadth']
        t['ntrend']=(t['m_nifty_trend'] or 0)*sg
print(HEADER)
for name,tr in data.items():
    print("\n=====",name)
    report("all (uncapped)",tr,cp); report("cap3",cap_per_day(tr,3),cp)
    for dr in ("LONG","SHORT"): report(dr,[t for t in tr if t['direction']==dr],cp)
    for label,key in (("vix",lambda t:t['m_vix']),("nifty trend20 (dir)",lambda t:t['ntrend']),("breadth (dir)",lambda t:t['breadth_dir']),
                      ("|nifty chg|",lambda t:abs(t['m_nifty_chg'])),("sector_rank",lambda t:t['sector_rank']),("rel_bvol",lambda t:t['rel_bvol']),("rel_vol",lambda t:t['rel_vol']),
                      ("stock_chg abs",lambda t:abs(t['stock_chg'])),("rs",lambda t:t['rs']),("gap",lambda t:t['gap']),("trend20 stock",lambda t:t['trend']),
                      ("entry minute",lambda t:int(t['entry_time'][11:13])*60+int(t['entry_time'][14:16]))):
        print("  --",label); bucket_report(tr,key,cp,nb=3)
# exits
print("\n===== exits on F (cap3)")
for tgt in (2.0,3.0,4.0,6.0):
  E.TARGET_RRR=tgt
  for en,ex in (("BE1.5",dict(breakeven_rrr=1.5)),("noBE",dict(breakeven_rrr=None)),("trail",dict(trail=True,breakeven_rrr=1.5))):
    tr=simulate(cands,entry_mode="breakout",or_n=6,stop_floor_atr=0.4,**ex); add_breakout_volume(tr,d)
    sel=cap_per_day([t for t in tr if (t['rel_bvol'] or 0)>=1.5 and (t['rel_vol'] or 0)>=1.0],3)
    report(f"T{tgt:g} {en}",sel,cp)
E.TARGET_RRR=3.0
