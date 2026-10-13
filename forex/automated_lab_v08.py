"""ALEX FOREX 2.0 automated research lab v0.8.

Research-only: indicative H1 midpoint data; NOT broker executable.
Precommitted development split: first 60% discovery, next 20% validation,
last 20% locked audit. The holdout was previously exposed to other strategies:
this is NOT a pristine independent test. No 'profitable' certification.
"""
import json, itertools
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),
"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),
"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),
"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
# 4 families * 3 horizons * 2 holding windows * 2 volatility states = 48 fixed candidates.
GRID=list(itertools.product(("trend","reversal","breakout","compression"),(12,24,48),(6,12),("high","low")))
def prices():
 result={};fail={}
 for pair,(ticker,_) in PAIRS.items():
  try:
   x=yf.download(ticker,period="730d",interval="1h",auto_adjust=False,progress=False,threads=False)
   if isinstance(x.columns,pd.MultiIndex):x.columns=x.columns.get_level_values(0)
   x=x[["Open","High","Low","Close"]].dropna().sort_index()
   x.index=pd.to_datetime(x.index,utc=True)
   if len(x)<8000 or not x.index.is_unique:raise ValueError("inadequate hourly data")
   result[pair]=x
  except Exception as e:fail[pair]=str(e)
 if len(result)!=12:raise RuntimeError("Must load all 12 pairs "+str(fail))
 return result
def make_events(pair,df,parameters):
 family,lookback,hold,regime=parameters
 c=df.Close
 ret=c.pct_change()
 sigma=ret.rolling(96,min_periods=96).std()
 prior_sigma=sigma.shift(1).rolling(240,min_periods=240).median()
 state=sigma>prior_sigma if regime=="high" else sigma<prior_sigma
 prior_hi=df.High.shift().rolling(lookback).max()
 prior_lo=df.Low.shift().rolling(lookback).min()
 mean=c.rolling(lookback).mean()
 dev=c.rolling(lookback).std()
 z=(c-mean)/dev.replace(0,np.nan)
 mom=c-c.shift(lookback)
 if family=="trend":
  side=np.sign(mom)
 elif family=="reversal":
  side=pd.Series(np.where(z>1.5,-1,np.where(z< -1.5,1,0)),index=df.index)
 elif family=="breakout":
  side=pd.Series(np.where(c>prior_hi,1,np.where(c<prior_lo,-1,0)),index=df.index)
 else:
  ratio=(df.High-df.Low).rolling(lookback).mean() / (df.High-df.Low).rolling(96).mean()
  side=pd.Series(np.where((ratio<.75)&(c>mean),1,np.where((ratio<.75)&(c<mean),-1,0)),index=df.index)
 side=pd.Series(side,index=df.index).fillna(0).astype(int)
 eligible=state&(side!=0)&(df.index.hour>=7)&(df.index.hour<18)&(df.index.weekday<5)
 # Signal is recognized after completed bar at t, executed at next hourly OPEN.
 # Exit is the future next-open at t+hold+1 (not used in features).
 ent=df.Open.shift(-1);out=df.Open.shift(-(hold+1))
 spread_pips=PAIRS[pair][1]
 spread=spread_pips*(.01 if pair.endswith("JPY") else .0001)
 cost=(spread/ent+.0001)
 net=side*(out/ent-1)-cost
 pos=np.flatnonzero(eligible.to_numpy() & net.notna().to_numpy())
 if not len(pos):return []
 events=[];next_allowed=-1
 for i in pos:
  if i<next_allowed:continue
  events.append((df.index[i+1],pair,float(net.iloc[i]),float(cost.iloc[i])))
  next_allowed=i+hold+1
 return events
def metrics(x):
 a=np.asarray(x,dtype=float)
 if not len(a):return {"trades":0,"net_bps":None,"pf":None}
 pos=a[a>0].sum();neg=-a[a<0].sum()
 return {"trades":len(a),"net_bps":round(float(a.mean()*1e4),3),
         "pf":round(float(pos/neg),3) if neg else None,"win_pct":round(float((a>0).mean()*100),2)}
def score(events,first,last):
 a=[e[2] for e in events if first<=e[0]<last]
 # Penalize noisy discovery and too-few signals, no test-period tuning
 if len(a)<100:return -999
 x=np.asarray(a)
 return float(x.mean()-1.5*x.std(ddof=1)/np.sqrt(len(x)))
def main():
 data=prices()
 start=max(d.index.min() for d in data.values());end=min(d.index.max() for d in data.values())
 t1=start+.6*(end-start);t2=start+.8*(end-start)
 candidates=[]
 for par in GRID:
  e=sorted((ev for p,d in data.items() for ev in make_events(p,d,par)),key=lambda a:a[0])
  development=metrics([v[2] for v in e if start<=v[0]<t1])
  validation=metrics([v[2] for v in e if t1<=v[0]<t2])
  candidates.append({"parameters":par,"score":score(e,start,t1),"development":development,
                     "validation":validation,"events":e})
 # Choose by discovery; validation must be positive AND have >=100 trades.
 ranked=sorted(candidates,key=lambda x:x["score"],reverse=True)
 qualified=[x for x in ranked if x["validation"]["trades"]>=100 and x["validation"]["net_bps"] is not None
            and x["validation"]["net_bps"]>0 and x["validation"]["pf"] is not None and x["validation"]["pf"]>1]
 # Selection for audit uses only development+validation; never test result.
 chosen=qualified[0] if qualified else None
 def describe(x):return {"parameters":list(x["parameters"]),"development":x["development"],"validation":x["validation"],
 "audit":metrics([v[2] for v in x["events"] if t2<=v[0]<=end])}
 result={"version":"v0.8.0","status":"RESEARCH_ONLY","target":"0.20% mean daily unlevered account return NET",
   "pairs":list(data),"data_start":str(start),"data_end":str(end),
   "discovery_until":str(t1),"validation_until":str(t2),"candidate_count":len(GRID),
   "top_discovery":[describe(v) for v in ranked[:5]],
   "qualifying_in_validation":len(qualified),
   "selected_candidate":describe(chosen) if chosen else None,
   "promotion":"DENIED: audit not sufficient for live" ,
   "limitations":["Yahoo midpoint indicative hourly candles, NO bid/ask broker fills",
      "Selection metric is individual trade return, NOT a EUR-equity portfolio or target daily NAV",
      "No multiple-hypothesis-adjusted significance and no pristine unseen future data",
      "Cost assumptions fixed and approximate, no actual margin/minimum lots",
      "Never send real orders or claim profitable deployment"]}
 out=Path("forex_v08_lab");out.mkdir(exist_ok=True)
 (out/"lab_report.json").write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
if __name__=="__main__":main()
