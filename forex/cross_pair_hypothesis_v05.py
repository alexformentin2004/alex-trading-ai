"""ALEX FX 2.0 - precommitted cross-pair momentum research, NOT executable trading.
Daily return is a normalized strategy signal, not a EUR 10 broker portfolio.
Uses no leverage. All outputs honest, including losses and flat market.
"""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def load():
 out={};failed={}
 for sym,(ticker,sp) in PAIRS.items():
  try:
   d=yf.download(ticker,period="30d",interval="5m",progress=False,auto_adjust=False,threads=False)
   if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
   d=d[["Open","High","Low","Close"]].dropna()
   d.index=pd.to_datetime(d.index,utc=True)
   if len(d)<3000 or not d.index.is_unique:raise ValueError("Missing/duplicated bars")
   out[sym]=d.sort_index()
  except Exception as e:failed[sym]=str(e)
 if len(out)<10:raise RuntimeError("Need >=10 pairs, got "+str(failed))
 return out,failed
def derive(sym,d):
 # Use only COMPLETED hourly candles: hour right-labeled; close at t uses 5m prior to t
 h=d.resample("1h",label="right",closed="left").agg({"Open":"first","High":"max","Low":"min","Close":"last"}).dropna()
 fast=h.Close.ewm(span=12,adjust=False).mean()
 slow=h.Close.ewm(span=48,adjust=False).mean()
 slope=slow-slow.shift(4)
 bias=pd.Series(0,index=h.index,dtype=int)
 bias[(fast>slow)&(slope>0)]=1
 bias[(fast<slow)&(slope<0)]=-1
 bias=bias.reindex(d.index,method="ffill").fillna(0).astype(int)
 c=d.Close;prev=c.shift()
 atr=pd.concat([d.High-d.Low,(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1).rolling(24).mean()
 local=c.ewm(span=12,adjust=False).mean()
 move=c.pct_change(6)
 side=pd.Series(0,index=d.index,dtype=int)
 # Pullback resumes within H1 continuation regime. Single hypothesis, no optimization.
 side[(prev<=local.shift())&(c>local)&(move>0)&(bias==1)]=1
 side[(prev>=local.shift())&(c<local)&(move<0)&(bias==-1)]=-1
 pip=.01 if sym.endswith("JPY") else .0001
 spread=PAIRS[sym][1]*pip
 frame=pd.DataFrame({"side":side,"entry":d.Open.shift(-1),"exit":d.Close.shift(-7),
                     "vol":atr,"bias":bias},index=d.index)
 frame["cost"]=spread/frame.entry+.0001
 frame["pnl"]=frame.side*(frame.exit/frame.entry-1)-frame.cost
 frame["sym"]=sym
 return frame[(frame.side!=0)&(frame.vol>spread*4)&(frame.index.hour>=7)&(frame.index.hour<18)&(frame.index.weekday<5)].replace([np.inf,-np.inf],np.nan).dropna()
def metrics(a):
 a=np.asarray(a,dtype=float)
 if len(a)==0:return {"trades":0,"net_mean_bps":None,"pf":None}
 win=a[a>0].sum();lose=-a[a<0].sum()
 return {"trades":len(a),"net_mean_bps":round(a.mean()*10000,3),
         "pf":round(float(win/lose),3) if lose>0 else None,
         "winning_pct":round(100*float(np.mean(a>0)),2)}
def main():
 raw,failed=load()
 signals=pd.concat([derive(s,d) for s,d in raw.items()]).sort_index()
 dates=np.sort(pd.unique(signals.index))
 split=dates[int(len(dates)*.70)]
 # Count max one new position per pair per 35 min, no retrospective filtering
 accepted=[];next_allowed={}
 for t,r in signals.iterrows():
  sym=r.sym
  if t<next_allowed.get(sym,pd.Timestamp("1900-01-01",tz="UTC")):continue
  accepted.append((t,sym,float(r.pnl)))
  next_allowed[sym]=t+pd.Timedelta(minutes=35)
 by_pair={sym:{"development":metrics([x[2] for x in accepted if x[1]==sym and x[0]<split]),
              "verification":metrics([x[2] for x in accepted if x[1]==sym and x[0]>=split])} for sym in PAIRS}
 test=[x for x in accepted if x[0]>=split]
 # Static 10% equity per trade, no leverage. Underlying orders have overlapping exposure;
 # returns below are independent idea summaries, NOT a portfolio NAV series.
 result={"system":"v0.5 H1 momentum M5 pullback","data_pairs":list(raw),"missing_pairs":failed,
        "data_period":{s:[str(d.index.min()),str(d.index.max())] for s,d in raw.items()},
        "split_utc":str(split),"total_events":len(accepted),"verification":metrics([x[2] for x in test]),
        "by_pair":by_pair,"unlevered_target_mean_daily_pct":0.2,
        "limitations":["Not 2 years or broker bid/ask; only 30d Yahoo 5m","Holdout overlaps research previously viewed: NOT independent",
        "No complete EUR portfolio, margin, minimum lots or dynamic currency P&L",
        "Fixed holding interval is approximate; no stop/target simulation","No evidence of guaranteed high daily profit; no real orders"]}
 folder=Path("forex_cross_pair_v05");folder.mkdir(exist_ok=True)
 (folder/"report.json").write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
if __name__=="__main__":main()
