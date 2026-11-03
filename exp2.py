import sys,pickle,itertools; sys.path.insert(0,'.')
import research2 as R
from research2 import *
import src.backtest.orb_engine as E
d=load()
cands,info=build_candidates(d)
cp=cost_pct()
def prep(**eng):
    tr=simulate(cands,**eng); add_breakout_volume(tr,d)
    for t in tr: t['ra']=t['risk_pct']/t['atr_pct'] if t['atr_pct'] else 0; t['rb']=t['rel_bvol'] or 0
    return tr
variants={"BE1R,T2R":dict(),"noBE,T2R":dict(breakeven_rrr=None),"BE1.5R,T2R":dict(breakeven_rrr=1.5),"trail,T2R":dict(trail=True)}
res=[]
for vname,eng in variants.items():
  for tgt in (2.0,3.0):
    E.TARGET_RRR=tgt
    tr=prep(**eng)
    for bv,ra,vol in itertools.product((0,1.5,2,3),(0,.2,.25,.3),(0,1.0)):
        sel=[t for t in tr if t['rb']>=bv and t['ra']>=ra and (t['rel_vol'] or 0)>=vol]
        sel=cap_per_day(sel,3)
        trn=stats([t for t in sel if t['date']<=TRAIN_END],cp); tst=stats([t for t in sel if t['date']>TRAIN_END],cp)
        if trn and tst and trn['n']>=100 and tst['n']>=60:
            res.append((trn['E'],f"{vname} T{tgt:g} bvol>={bv} risk/ATR>={ra} openvol>={vol}",trn,tst))
E.TARGET_RRR=2.0
res.sort(key=lambda r:-r[0])
print("Top 15 by TRAIN expectancy (net of costs), with their TEST result")
print(HEADER)
for e,l,trn,tst in res[:15]:
    print(line(l+" | train",trn)); print(line(l+" | test",tst))
print("\nBest by TEST (for reference only - not a valid pick):")
for e,l,trn,tst in sorted(res,key=lambda r:-r[3]['E'])[:5]:
    print(line(l+" | train",trn)); print(line(l+" | test",tst))
pickle.dump(res,open("data_cache/exp2_res.pkl","wb"))
