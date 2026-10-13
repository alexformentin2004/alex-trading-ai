"""Session-transition edge discovery, strictly causal fixed hypotheses.
Research only, NOT a trading bot. H1 Yahoo OHLC indicative mids.
Signal from COMPLETED 00-07 UTC segment, ENTER 08 UTC, EXIT 16 UTC.
6 predeclared variants, 12 pairs, max 1x combined notional.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def data():
 out={}
 for p,(ticker,_) in PAIRS.items():
  d=yf.download(ticker,period="730d",interval="1h",auto_adjust=False,threads=False,progress=False)
  if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
  d=d[["Open","High","Low","Close"]].dropna().sort_index()
  d.index=pd.to_datetime(d.index,utc=True)
  if len(d)<9000:raise RuntimeError("Insufficient "+p)
  out[p]=d
 return out
def observations(d):
 rows=[]
 for day,group in d.groupby(d.index.normalize()):
  h=group.index.hour
  asia=group[(h>=0)&(h<=6)]
  if len(asia)!=7:continue
  at8=group[h==8];at16=group[h==16]
  if len(at8)!=1 or len(at16)!=1:continue
  a_open=float(asia.Open.iloc[0]);a_close=float(asia.Close.iloc[-1])
  entry=float(at8.Open.iloc[0]);exit_=float(at16.Open.iloc[0])
  if min(a_open,a_close,entry,exit_)<=0:continue
  asia_r=a_close/a_open-1;session_r=exit_/entry-1
  rows.append((day,asia_r,session_r,entry))
 return pd.DataFrame(rows,columns=["day","asia_ret","session_ret","entry"]).set_index("day")
def summary(a):
 a=np.asarray(a,dtype=float);e=np.cumprod(1+a);peak=np.maximum.accumulate(np.r_[1.,e])[1:]
 return {"days":len(a),"mean_daily_pct":round(float(a.mean()*100),5),"total_pct":round(float((e[-1]-1)*100),3),"max_dd_pct":round(float((e/peak-1).min()*100),3),"profitable_days":int(sum(a>0)),"meets_target":bool(a.mean()>=.002)}
def main():
 raw=data();obs={p:observations(d) for p,d in raw.items()}
 days=sorted(set.intersection(*(set(o.index) for o in obs.values())))
 days=pd.DatetimeIndex([x for x in days if x.weekday()<5],tz="UTC")
 if len(days)<500:raise RuntimeError("Too few common 08/16 trading days")
 panel={p:o.reindex(days) for p,o in obs.items()}
 # Six variations decided before results; 1 single pair maximum daily.
 # Top strength uses absolute move *relative to preceding 30-day dispersion*.
 candidates={}
 for direction in ("continue","fade"):
  for threshold in (0.5,1.0,1.5):
   series=np.zeros(len(days));traded=0;cost_sum=0.
   for i,day in enumerate(days):
    opportunities=[]
    for p,o in panel.items():
     hist=o.asia_ret.iloc[max(0,i-30):i].std()
     if i<30 or not np.isfinite(hist) or hist<=0:continue
     z=float(o.asia_ret.iat[i]/hist)
     if np.isfinite(z) and abs(z)>=threshold:
      opportunities.append((abs(z),p,np.sign(z)))
    if not opportunities:continue
    opportunities.sort(key=lambda x:(-x[0],x[1]))
    _,p,side=opportunities[0]
    if direction=="fade":side=-side
    pip=.01 if p.endswith("JPY") else .0001
    entry=panel[p].entry.iat[i]
    spread=PAIRS[p][1]*pip/entry
    cost=float(spread+.0001)
    net=float(side*panel[p].session_ret.iat[i]-cost)
    series[i]=net;traded+=1;cost_sum+=cost
   candidates[f"{direction}_z{threshold}"]={"daily":series,"trades":traded,"avg_cost_bps":round(cost_sum/max(1,traded)*10000,3)}
 split=int(len(days)*.70)
 cutoff=pd.Timestamp("2026-07-01",tz="UTC")
 # Historical validation cutoff is already seen; no claims of untouched holdout.
 precut=int(np.searchsorted(days.values,cutoff.to_datetime64()))
 trainEnd=min(split,precut)
 if trainEnd<250:raise RuntimeError("Insufficient development")
 table={}
 for name,c in candidates.items():
  a=c["daily"]
  table[name]={"train":summary(a[:trainEnd]),"seen_validation":summary(a[trainEnd:]),"trades":c["trades"],"avg_cost_bps":c["avg_cost_bps"]}
 ranked=sorted(table,key=lambda k:table[k]["train"]["mean_daily_pct"],reverse=True)
 chosen=ranked[0]
 report={"type":"predeclared session transition falsification", "status":"RESEARCH_ONLY",
  "date_start":str(days[0]),"date_end":str(days[-1]),"pairs":len(PAIRS),
  "hypotheses":len(candidates),"train_end":str(days[trainEnd-1]),
  "selected_on_train_only":chosen,"selected_metrics":table[chosen],
  "all_results":table,"target_mean_daily_pct":0.2,
  "deployable":False,
  "limitations":["Yahoo hour bars not executable broker quotes; approximate costs",
  "Seen validation period was referenced in prior experiments, not untouched",
  "No tradable EUR10 lot sizing, true currency conversion, market impact or swaps",
  "Session UTC fixed; daylight saving and weekend missing hours not modeled",
  "No confidence significance or real-time fills; never activate live automatically"]}
 folder=Path("forex_session_transition_v1");folder.mkdir(exist_ok=True)
 (folder/"report.json").write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
