import sys,pickle,itertools; sys.path.insert(0,'.')
from research2 import *
import src.backtest.orb_engine as E
d=load(); cands,info=build_candidates(d); cp=cost_pct()
exits={"BE1.5":dict(breakeven_rrr=1.5),"noBE":dict(breakeven_rrr=None),"trail":dict(trail=True),"BE1":dict()}
res=[]
for k in (0,0.25,0.3,0.4,0.5):
  for en,ex in exits.items():
    for tgt in (2.0,3.0):
      E.TARGET_RRR=tgt
      tr=simulate(cands,stop_floor_atr=k,**ex); add_breakout_volume(tr,d)
      for bv,vol in itertools.product((0,1.5),(0,1.0)):
        sel=cap_per_day([t for t in tr if (t['rel_bvol'] or 0)>=bv and (t['rel_vol'] or 0)>=vol],3)
        a=stats([t for t in sel if t['date']<=TRAIN_END],cp); b=stats([t for t in sel if t['date']>TRAIN_END],cp)
        if a and b and a['n']>=150 and b['n']>=100:
            res.append((a['E'],f"floor{k}ATR {en} T{tgt:g} bvol>={bv} openvol>={vol}",a,b))
E.TARGET_RRR=2.0
res.sort(key=lambda r:-r[0])
print(HEADER)
for e,l,a,b in res[:12]:
    print(line(l+" | train",a)); print(line(l+" | test",b))
# how many configs have both train and test E>0
both=[r for r in res if r[2]['E']>0 and r[3]['E']>0]
print(f"\n{len(both)} of {len(res)} configs positive in BOTH train and test")
for k in (0,0.25,0.3,0.4,0.5):
    rk=[r for r in res if r[1].startswith(f'floor{k}ATR')]
    if rk: print(f"floor {k}: median train E {sorted(r[2]['E'] for r in rk)[len(rk)//2]:+.3f}  median test E {sorted(r[3]['E'] for r in rk)[len(rk)//2]:+.3f}  ({len(rk)} cfgs)")
pickle.dump(res,open("data_cache/exp3_res.pkl","wb"))
