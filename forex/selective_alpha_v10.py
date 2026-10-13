"""ALEX FX research v1.0: selective cross-sectional FX momentum/reversal.
2+ years of hourly Yahoo indicative quotes. All results are 1x-notional equity proxies.
No broker execution, no profit claims, no live orders. Fixed candidate grid.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def load():
 out={}
 for sym,(tick,_) in PAIRS.items():
  d=yf.download(tick,period="730d",interval="1h",progress=False,threads=False,auto_adjust=False)
  if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
  d=d[["Open","Close"]].dropna().sort_index()
  d.index=pd.to_datetime(d.index,utc=True)
  if len(d)<12000:raise ValueError(f"{sym} insufficient rows")
  out[sym]=d
 return out
def panel(raw):
 common=sorted(set.intersection(*(set(d.index.normalize()) for d in raw.values())))
 days=pd.DatetimeIndex(common,tz="UTC")
 opens={}; closes={}
 for p,d in raw.items():
  opens[p]=d.Open[d.index.hour==8].resample("1D").first().reindex(days)
  closes[p]=d.Close.resample("1D").last().reindex(days)
 opens=pd.DataFrame(opens,index=days);closes=pd.DataFrame(closes,index=days)
 # Filter days with all quotes at decision and next session.
 usable=(opens.notna().all(axis=1)&closes.notna().all(axis=1))
 opens=opens[usable];closes=closes[usable]
 return opens,closes
def metrics(a):
 a=np.asarray(a,dtype=float)
 if not len(a):return {}
 equity=np.cumprod(1+a); peak=np.maximum.accumulate(np.r_[1,equity])[1:]
 return {"days":int(len(a)),"active_days":int(np.count_nonzero(a)),
 "mean_daily_pct":round(float(a.mean()*100),5),
 "compounded_pct":round(float((equity[-1]-1)*100),4),
 "max_drawdown_pct":round(float(np.min(equity/peak-1)*100),4),
 "positive_days":int(np.count_nonzero(a>0)), "negative_days":int(np.count_nonzero(a<0)),
 "target_met":bool(float(a.mean())>=.002)}
def main():
 raw=load();opens,closes=panel(raw)
 # Use yesterday's fully observed close and older closes; next 08:00 UTC open entry.
 # Next observed session open exit; any unavailable data -> zero rather than proxy fill.
 returns=opens.shift(-1)/opens-1
 all_candidates={}
 for direction in ("trend","reversal"):
  for horizon in (2,5,10,20):
   signal=(closes.shift(1)/closes.shift(horizon+1)-1)
   # Fixed cross-sectional signal strength by rolling prior 60-day *past* dispersion.
   denom=signal.shift(1).rolling(60,min_periods=45).std().replace(0,np.nan)
   z=signal/denom
   if direction=="reversal":z=-z
   for min_z in (0.5,1.0,1.5):
    daily=[];cost_stress=[]
    for day in opens.index[:-1]:
     vals=z.loc[day].replace([np.inf,-np.inf],np.nan).dropna()
     if vals.empty or vals.abs().max()<min_z:
      daily.append((day,0.,None)); cost_stress.append(0.);continue
     # A single high-conviction pair, gross exposure exactly 1x when invested.
     p=vals.abs().idxmax();side=1 if vals[p]>0 else -1
     entry=float(opens.at[day,p]);future=float(returns.at[day,p])
     if not np.isfinite(future):daily.append((day,0.,None));cost_stress.append(0.);continue
     pip=.01 if p.endswith("JPY") else .0001
     cost=PAIRS[p][1]*pip/entry+.0001
     net=side*future-cost
     daily.append((day,float(net),p));cost_stress.append(float(side*future-2*cost))
    key=f"{direction}_{horizon}d_z{min_z:.1f}"
    all_candidates[key]={"daily":daily,"stressed":cost_stress}
 days=opens.index[:-1];split1=days[int(len(days)*.6)];split2=days[int(len(days)*.8)]
 rows=[]
 for name,d in all_candidates.items():
  x=d["daily"];times=[t for t,r,p in x]
  a=np.array([r for t,r,p in x]);stress=np.asarray(d["stressed"])
  m1=times.index(next(t for t in times if t>=split1))
  m2=times.index(next(t for t in times if t>=split2))
  rows.append({"name":name,"development":metrics(a[:m1]),
               "validation":metrics(a[m1:m2]),"audit":metrics(a[m2:]),
               "audit_2x_cost":metrics(stress[m2:])})
 # Select only using development ranking; disclose independent-looking audit but not pristine
 ordered=sorted(rows,key=lambda v:v["development"]["mean_daily_pct"],reverse=True)
 candidate=ordered[0]
 result={"status":"RESEARCH_ONLY","pairs":len(raw),"hypotheses":len(rows),"days":len(days),
 "first":str(days[0]),"last":str(days[-1]),
 "development_ends":str(split1),"validation_ends":str(split2),
 "chosen_by_development":candidate,
 "top_five":[{"name":r["name"],"development":r["development"],"validation":r["validation"],"audit":r["audit"],"audit_2x_cost":r["audit_2x_cost"]} for r in ordered[:5]],
 "number_meeting_target_in_validation":sum(r["validation"]["target_met"] for r in rows),
 "number_meeting_target_in_audit":sum(r["audit"]["target_met"] for r in rows),
 "limitations":["Yahoo last/opens, not executable bid/ask; costs indicative",
 "1x EUR equity *proxy*, no per-pair conversion, margin, lots or stop losses",
 "This is not fresh untouched OOS; older prototypes used overlapping data",
 "24 hypotheses mean positive result could be data mining; no significance gate",
 "Trading live prohibited; cannot guarantee +0.20% per day"]}
 out=Path("forex_v10_selective");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
if __name__=="__main__":main()
