"""Cross-sectional currency momentum v0.7; research-only, no broker orders.
12-pair daily currency-strength selection from lagged H1 quotes.
Trades are 24-hour normalized quote returns with indicative costs.
NOT full EUR account NAV, two-year bid/ask, or a validated strategy.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),
"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),
"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def data():
 ds={};bad={}
 for name,(ticker,spread) in TICKERS.items():
  try:
   x=yf.download(ticker,period="730d",interval="1h",threads=False,progress=False,auto_adjust=False)
   if isinstance(x.columns,pd.MultiIndex):x.columns=x.columns.get_level_values(0)
   x=x[["Open","High","Low","Close"]].dropna().sort_index()
   x.index=pd.to_datetime(x.index,utc=True)
   if len(x)<5000:raise ValueError("not enough rows")
   ds[name]=x
  except Exception as e:bad[name]=str(e)
 if len(ds)!=12:raise RuntimeError("Incomplete 12 pair universe: "+str(bad))
 return ds
def stats(v):
 v=np.array(v,dtype=float)
 if not len(v):return {"trades":0,"mean_net_bps":None,"profit_factor":None}
 profit=v[v>0].sum();loss=-v[v<0].sum()
 return {"trades":len(v),"mean_net_bps":round(v.mean()*1e4,3),
         "profit_factor":round(profit/loss,3) if loss else None,
         "win_rate_pct":round(100*(v>0).mean(),2)}
def main():
 ds=data()
 # Single unified daily decision at 08:00 UTC on each available trading day;
 # uses previous day's hourly CLOSE returns, not future prices.
 daily={}
 for name,x in ds.items():
  d=x.resample("1D").agg({"Close":"last"}).dropna()
  daily[name]=d.Close.pct_change(3).shift(1)
 day_index=sorted(set.intersection(*(set(x.index.normalize()) for x in daily.values())))
 events=[]
 for day in day_index:
  if day.weekday()>4:continue
  scores={c:[] for c in "EUR USD GBP JPY CHF CAD AUD NZD".split()}
  for name in TICKERS:
   arr=daily[name];known=arr.get(day,np.nan)
   if not np.isfinite(known):continue
   a,b=name[:3],name[3:]
   scores[a].append(float(known));scores[b].append(-float(known))
  strength={k:sum(v)/len(v) for k,v in scores.items() if v}
  if len(strength)<7:continue
  # Fixed hypothesis: rank all pair's base/quote relative strength.
  ranked=sorted([(strength[p[:3]]-strength[p[3:]],p) for p in TICKERS],reverse=True)
  chosen=[];used=set()
  for score,pair in sorted(ranked,key=lambda e:abs(e[0]),reverse=True):
   a,b=pair[:3],pair[3:]
   if a in used or b in used:continue
   chosen.append((pair,1 if score>0 else -1))
   used.update((a,b))
   if len(chosen)==2:break
  for pair,side in chosen:
   x=ds[pair]
   start=x.index.searchsorted(day+pd.Timedelta(hours=8))
   end=x.index.searchsorted(day+pd.Timedelta(days=1,hours=8))
   if start>=len(x) or end>=len(x):continue
   entry=float(x.Open.iloc[start]);exit=float(x.Open.iloc[end])
   # Count only near-exact daily entry and exit timestamps
   if abs((x.index[start]-(day+pd.Timedelta(hours=8))).total_seconds())>7200:continue
   if abs((x.index[end]-(day+pd.Timedelta(days=1,hours=8))).total_seconds())>7200:continue
   pip=.01 if pair.endswith("JPY") else .0001
   costs=TICKERS[pair][1]*pip/entry+.0001
   net=side*(exit/entry-1)-costs
   events.append({"day":day,"pair":pair,"net":net})
 if len(events)<150:raise RuntimeError("Too few daily trades")
 dates=sorted(set(e["day"] for e in events));split=dates[int(len(dates)*.7)]
 report={"strategy":"Daily cross-currency relative strength (fixed rules)","split_utc":str(split),
 "pairs":len(ds),"data_start":str(min(x.index.min() for x in ds.values())),
 "data_end":str(max(x.index.max() for x in ds.values())),
 "development":stats([e["net"] for e in events if e["day"]<split]),
 "verification":stats([e["net"] for e in events if e["day"]>=split]),
 "verification_by_pair":{p:stats([e["net"] for e in events if e["day"]>=split and e["pair"]==p]) for p in TICKERS},
 "warnings":["FX Yahoo indicative OHLC, no executable bid/ask","This is not EUR account portfolio return or daily NAV",
 "Potential currency graph correlation and selected pair overlap","No broker minimum lots, margin, stop, funding, or EUR10 viability",
 "Prior strategy development touched overlapping dates, so not untouched out-of-sample"]}
 path=Path("forex_v07_strength");path.mkdir(exist_ok=True)
 (path/"report.json").write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
