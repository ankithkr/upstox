import sys,pickle,itertools,statistics; sys.path.insert(0,'.')
from research2 import *
import src.backtest.orb_engine as E
d=load(); cands,info=build_candidates(d); cp=cost_pct()
res=[]
for mode,orn in itertools.product(("breakout","retest"),(3,6)):
  for k in (0.4,0.5,0.7,1.0):
    for en,ex in (("BE1.5",dict(breakeven_rrr=1.5)),("noBE",dict(breakeven_rrr=None))):
      for tgt in (2.0,3.0):
        E.TARGET_RRR=tgt
        tr=simulate(cands,entry_mode=mode,or_n=orn,stop_floor_atr=k,**ex); add_breakout_volume(tr,d)
        for bv,vol in itertools.product((0,1.5),(0,1.0)):
          sel=cap_per_day([t for t in tr if (t['rel_bvol'] or 0)>=bv and (t['rel_vol'] or 0)>=vol],3)
          a=stats([t for t in sel if t['date']<=TRAIN_END],cp); b=stats([t for t in sel if t['date']>TRAIN_END],cp)
          if a and b and a['n']>=150 and b['n']>=150:
            res.append(dict(mode=mode,orn=orn,k=k,exit=en,tgt=tgt,bv=bv,vol=vol,a=a,b=b))
E.TARGET_RRR=2.0
print(len(res),"configs")
print("\nFamily medians (train E / test E / n configs / %positive in BOTH):")
for key in ("mode","orn","k","exit","tgt","bv","vol"):
    for v in sorted({r[key] for r in res},key=str):
        rs=[r for r in res if r[key]==v]
        print(f"  {key}={v!s:<9} trainE {statistics.median(r['a']['E'] for r in rs):+.3f}  testE {statistics.median(r['b']['E'] for r in rs):+.3f}  n={len(rs):3d}  both+ {100*sum(1 for r in rs if r['a']['E']>0 and r['b']['E']>0)/len(rs):4.0f}%")
res.sort(key=lambda r:-r['a']['E'])
print("\nTop 10 by TRAIN E, with TEST:")
print(HEADER)
for r in res[:10]:
    l=f"{r['mode']} or{r['orn']} floor{r['k']} {r['exit']} T{r['tgt']:g} bv{r['bv']} vol{r['vol']}"
    print(line(l+" | train",r['a'])); print(line(l+" | test",r['b']))
pickle.dump(res,open("data_cache/exp5_res.pkl","wb"))
