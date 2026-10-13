"""FX 2.0 v0.6: prespecified 12-pair H1 regime research, 2-year Yahoo attempt.
Two structurally different models on completed hourly candles; trade at next open.
No leverage, EUR-account tradeability, tick bid/ask, or broker fills. No live orders.
"""
from pathlib import Path
import json,math
import numpy as np
import pandas as pd
import yfinance as yf
PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),
"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),
"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def fetch():
 out={};missing={}
 for sym,(tick,sp) in PAIRS.items():
  try:
   d=yf.download(tick,period="730d",interval="1h",threads=False,progress=False,auto_adjust=False)
   if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
   d=d[["Open","High","Low","Close"]].dropna().sort_index()
   d.index=pd.to_datetime(d.index,utc=True)
   if len(d)<1000 or not d.index.is_unique:raise RuntimeError("Missing/duplicate candles")
   out[sym]=d
  except Exception as e:missing[sym]=str(e)
 if len(out)<8:raise RuntimeError("Too few symbols "+str(missing))
 return out,missing
def signals(sym,d):
 c=d.Close
 # Both hypotheses are based only on completed H1 bars.
 mom=c.pct_change(48)
 slow=c.ewm(span=96,adjust=False).mean()
 fast=c.ewm(span=24,adjust=False).mean()
 m=np.sign(mom).fillna(0)
 trend=np.sign(fast-slow)
 vol=c.pct_change().rolling(72).std()
 v_med=vol.shift(1).rolling(240).median()
 mean=c.rolling(72).mean()
 sd=c.rolling(72).std().replace(0,np.nan)
 z=(c-mean)/sd
 results={}
 # momentum strategy only in elevated volatility / trend agreement
 s=pd.Series(0,index=d.index,dtype=int)
 s[(m==trend)&(m>0)&(vol>v_med)]=1
 s[(m==trend)&(m<0)&(vol>v_med)]=-1
 results["momentum_regime"]=s
 # opposite hypothesis: fading excess in a quiet sideways range
 s2=pd.Series(0,index=d.index,dtype=int)
 flat=(abs(fast/slow-1)<0.002)&(vol<v_med)
 s2[(z< -1.8)&flat]=1
 s2[(z> 1.8)&flat]=-1
 results["range_reversion"]=s2
 events=[]
 sp=PAIRS[sym][1]*(0.01 if sym.endswith("JPY") else .0001)
 for strategy,side in results.items():
  for i in range(400,len(d)-7):
   direction=int(side.iat[i])
   if direction==0 or (i and side.iat[i-1]==direction):continue
   t=d.index[i+1]
   if t.weekday()>4 or not 7<=t.hour<19:continue
   entry=float(d.Open.iat[i+1]);exit=float(d.Close.iat[i+7])
   if not entry or not exit:continue
   net=direction*(exit/entry-1)-(sp/entry+.0001)
   events.append({"time":t,"pair":sym,"strategy":strategy,"ret":net})
 return events
def metric(a):
 a=np.array(a,dtype=float)
 if len(a)==0:return {"n":0,"net_mean_bps":None,"pf":None,"win_pct":None}
 win=a[a>0].sum();loss=-a[a<0].sum()
 return {"n":len(a),"net_mean_bps":round(a.mean()*10000,3),"pf":round(float(win/loss),3) if loss else None,"win_pct":round(100*float((a>0).mean()),2)}
def main():
 data,missing=fetch()
 events=sorted((e for p,d in data.items() for e in signals(p,d)),key=lambda x:x["time"])
 # Fixed chronological 70%/30% development/verification. Per-market counts disclosed.
 dates=sorted(set(e["time"] for e in events))
 if len(dates)<100:raise RuntimeError("Too few events to assess")
 split=dates[int(.7*len(dates))]
 # Simple same-pair same-strategy no-overlap throttle: one 7h position at a time.
 last={};accepted=[]
 for e in events:
  k=(e["pair"],e["strategy"])
  if e["time"]<last.get(k,pd.Timestamp("1900-01-01",tz="UTC")):continue
  accepted.append(e);last[k]=e["time"]+pd.Timedelta(hours=7)
 def period(e):return "development" if e["time"]<split else "verification"
 report={"status":"research_only","loaded":len(data),"missing":missing,
  "date_range":{p:[str(d.index.min()),str(d.index.max()),len(d)] for p,d in data.items()},
  "split":str(split),"count":len(accepted),
  "strategies":{s:{x:metric([e["ret"] for e in accepted if e["strategy"]==s and period(e)==x]) for x in ("development","verification")} for s in ("momentum_regime","range_reversion")},
  "pairs":{p:{"verification":metric([e["ret"] for e in accepted if e["pair"]==p and period(e)=="verification"])} for p in PAIRS},
  "limitations":["Only Yahoo indicative OHLC, not real bid/ask tick fills","Not a portfolio equity curve or EUR10 executable return","The two hypotheses are frozen for this test; exploration on previous FX dates makes holdout imperfect","No Monte Carlo or formal multiple-test corrected uncertainty","No stop loss, true lot size, leverage or margin: DO NOT TRADE LIVE"]}
 out=Path("forex_v06_long_h1");out.mkdir(exist_ok=True)
 (out/"research.json").write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
