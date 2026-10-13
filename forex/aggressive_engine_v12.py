"""ALEX FX 2.0 — AGGRESSIVE VOLATILITY ENGINE v1.2 research-only.
Aggression defined as 10x trade-capacity vs Session Edge (10 vs 1 daily).
No promise of 10x profit. H1 OHLC indicative data; no broker real fills.
Same-day signals based on completed prior hourly candles; next-open entry.
Fixed max 10 entries/day; max 4 live positions; per-ticket stop distance,
portfolio initial-stop risk <= 20% of equity, max gross notional 1x in
unlevered target audit. At 1x and realistic hourly ATR stops, risk budgets
usually nonbinding; "5% risk cap" applies to planned stop exposure only.
Positions use equal 0.25x notional when opened, 4 max; all results unlevered
equity proxy. No EUR10 micro-lot assumption.
"""
from pathlib import Path
import json
import pandas as pd
import numpy as np
import yfinance as yf

PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),
"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),
"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),
"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def load():
 dct={}
 for p,(ticker,_) in PAIRS.items():
  d=yf.download(ticker,period="730d",interval="1h",threads=False,auto_adjust=False,progress=False)
  if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
  d=d[["Open","High","Low","Close"]].dropna().sort_index()
  d.index=pd.to_datetime(d.index,utc=True)
  if len(d)<10000:raise RuntimeError("bad history: "+p)
  dct[p]=d
 return dct
def cand(p,d):
 c=d.Close
 tr=pd.concat([(d.High-d.Low),(d.High-c.shift()).abs(),(d.Low-c.shift()).abs()],axis=1).max(axis=1)
 atr=tr.rolling(24).mean()
 ma=c.ewm(span=24,adjust=False).mean()
 # Pre-specified aggressive triggers: short-horizon momentum burst + trend,
 # and reversal after a 3-sigma candle relative to recent volatility.
 return_=c.pct_change()
 sigma=return_.shift().rolling(96).std()
 trend=c/c.shift(12)-1
 m=(return_.abs()/(sigma+1e-12))
 side=pd.Series(0,index=d.index,dtype=int)
 side[(m>1.2)&(return_>0)&(trend>0)&(c>ma)]=1
 side[(m>1.2)&(return_<0)&(trend<0)&(c<ma)]=-1
 # Reversal events are intentionally lower priority than burst continuation.
 side[(side==0)&(m>2.5)&(return_>0)&(c/ma>1.002)]=-1
 side[(side==0)&(m>2.5)&(return_<0)&(c/ma<.998)]=1
 strength=(m*abs(trend)/(sigma+1e-12)).clip(upper=1000)
 events=[]
 pip=.01 if p.endswith("JPY") else .0001
 spread=PAIRS[p][1]*pip
 for i in range(110,len(d)-8):
  if not (7<=d.index[i].hour<19 and d.index[i].weekday()<5):continue
  direction=int(side.iat[i])
  if not direction or not np.isfinite(atr.iat[i]) or atr.iat[i]<=spread*3:continue
  entry=float(d.Open.iat[i+1])
  stopdist=float(atr.iat[i])*1.1
  if stopdist/entry>0.025:continue
  # Event placed at next bar; all ranking properties based on completed bar i.
  events.append({"time":d.index[i+1],"pair":p,"side":direction,"entry":entry,
    "stopdist":stopdist,"score":float(strength.iat[i]),"idx":i+1,
    "cost":spread/entry+.00012})
 return events
def run(events,data):
 # Chronological selection; a maximum of 10 entries/day and 4 simultaneous 0.25x tickets.
 events.sort(key=lambda e:(e["time"],-e["score"],e["pair"]))
 active=[];pnl_by_day={};count_by_day={};accepted=[];total_rejected=0
 for event in events:
  now=event["time"]
  # Close positions whose bar-based exit time has passed before considering a new entry.
  active=[a for a in active if a["end"]>now]
  day=now.normalize()
  if count_by_day.get(day,0)>=10 or len(active)>=4 or any(x["pair"]==event["pair"] for x in active):
   total_rejected+=1;continue
  d=data[event["pair"]];index=event["idx"]
  if index+6>=len(d):continue
  direction=event["side"];entry=event["entry"];dist=event["stopdist"]
  stop=entry-direction*dist;tp=entry+direction*1.5*dist
  exit_=float(d.Close.iat[index+5]);kind="time";last=index+5
  for k in range(index,index+6):
   bar=d.iloc[k]
   hit_stop=(bar.Low<=stop) if direction>0 else (bar.High>=stop)
   hit_tp=(bar.High>=tp) if direction>0 else (bar.Low<=tp)
   if hit_stop:
    exit_=min(float(bar.Open),stop) if direction>0 else max(float(bar.Open),stop)
    kind="stop";last=k;break
   if hit_tp:exit_=tp;kind="target";last=k;break
  risk_per_equity=.25*(dist/entry+event["cost"])
  # Independent limits: nominal risk 5% per order, combined <=20% current equity.
  # Separate from EUR 10 min lot feasibility (not available in this prototype).
  if risk_per_equity>.05 or sum(x["risk"] for x in active)+risk_per_equity>.2:
   total_rejected+=1;continue
  realized=.25*(direction*(exit_/entry-1)-event["cost"])
  pnl_by_day[day]=pnl_by_day.get(day,0)+realized
  count_by_day[day]=count_by_day.get(day,0)+1
  active.append({"pair":event["pair"],"end":d.index[last]+pd.Timedelta(hours=1),
                 "risk":risk_per_equity})
  accepted.append({"time":str(now),"pair":event["pair"],"ret":realized,"exit_kind":kind})
 return pnl_by_day,count_by_day,accepted,total_rejected
def metric(days,pnl,count):
 vals=np.asarray([pnl.get(d,0.) for d in days],dtype=float)
 if not len(vals):return {}
 equity=np.cumprod(1+vals);peak=np.maximum.accumulate(np.r_[1.,equity])[1:]
 return {"days":len(vals),"trade_count":sum(count.get(d,0) for d in days),
 "active_days":sum(count.get(d,0)>0 for d in days),
 "avg_trades_per_day":round(sum(count.get(d,0) for d in days)/len(vals),3),
 "max_trades_per_day":max([count.get(d,0) for d in days],default=0),
 "average_daily_pct":round(float(vals.mean()*100),5),
 "compounded_pct":round(float((equity[-1]-1)*100),4),
 "max_drawdown_pct":round(float(min(equity/peak-1)*100),4),
 "target_0_2_pct_met":bool(vals.mean()>=.002)}
def main():
 data=load()
 events=[e for pair,df in data.items() for e in cand(pair,df)]
 pnl,count,trades,rejected=run(events,data)
 days=sorted(set.intersection(*(set(d.index.normalize()) for d in data.values())))
 days=[d for d in days if d.weekday()<5 and d<min(df.index.max().normalize() for df in data.values())]
 s1=int(len(days)*.6);s2=int(len(days)*.8)
 result={"strategy":"Aggressive Volatility Engine v1.2","status":"RESEARCH_ONLY",
 "aggression_definition":"up to 10 new tickets daily vs Session Edge 1, not 10x leverage",
 "signals_generated":len(events),"trades_accepted":len(trades),
 "events_rejected":rejected,"pairs_monitored":list(PAIRS),
 "development":metric(days[:s1],pnl,count),"validation":metric(days[s1:s2],pnl,count),
 "audit":metric(days[s2:],pnl,count),
 "audited_pair_trade_counts":{p:sum(r["pair"]==p and pd.Timestamp(r["time"])>=days[s2] for r in trades) for p in PAIRS},
 "limitations":["Indicative Yahoo hourly OHLC, spread+slippage estimated","Portfolio unrealized PnL not marked to market while positions overlap; drawdown approximate",
 "Quotes not broker executable, no EUR conversion or micro-lot support","No minimum lot/margin, leverage or overnight swap checks",
 "Position exit simulation optimistic if bid/ask and slippage worse than assumptions",
 "Candidate search on previously studied dates, audit not pristine",
 "No trading real; no demonstrated statistical profit guarantee"]}
 folder=Path("forex_aggressive_v12");folder.mkdir(exist_ok=True)
 (folder/"report.json").write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
if __name__=="__main__":main()
