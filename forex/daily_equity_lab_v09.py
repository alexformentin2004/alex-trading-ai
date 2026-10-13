"""ALEX FOREX ENGINE 2.0 v0.9 — honest unlevered daily equity search.
12 FX pairs, 1x max exposure, 12 frozen strategy hypotheses, 2y+ indicative H1.
Signals from previous day's *complete* closes; open-to-open returns, proxy costs.
NOT broker-executable. No leverage. No live trading.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
UNIVERSE={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),
"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),
"AUDUSD":("AUDUSD=X",1.9),"NZDUSD":("NZDUSD=X",2.3),
"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),
"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def download():
 raw={}
 for pair,(ticker,spread) in UNIVERSE.items():
  d=yf.download(ticker,period="730d",interval="1h",auto_adjust=False,progress=False,threads=False)
  if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
  d=d[["Open","Close"]].dropna().sort_index()
  d.index=pd.to_datetime(d.index,utc=True)
  if len(d)<9000:raise RuntimeError(pair+" lacks H1 history")
  # Signal close is the final completed H1 close before 08:00 UTC the NEXT day.
  # Daily entry at 08:00; signals use PREVIOUS DAY <=23:59, hence no lookahead.
  last=d.Close.resample("1D").last()
  opens=d.Open[d.index.hour==8].resample("1D").first()
  raw[pair]=pd.DataFrame({"close":last,"open":opens})
 common=sorted(set.intersection(*(set(x.dropna().index) for x in raw.values())))
 common=pd.DatetimeIndex(common,tz="UTC")
 return common,{p:d.reindex(common) for p,d in raw.items()}
def daily_returns(days,quotes):
 # Entries at today's 08 UTC. Decisions based on yesterday complete close.
 rets=pd.DataFrame({p:x["open"].shift(-1)/x["open"]-1 for p,x in quotes.items()},index=days)
 lookbacks=(5,10,20)
 candidates={}
 for style in ("momentum","reversion","breakout","currency_strength"):
  for lookback in lookbacks:
   scores=pd.DataFrame(index=days)
   for p,q in quotes.items():
    c=q["close"]
    hist=c.shift(1)
    mom=hist/hist.shift(lookback)-1
    if style=="momentum":score=mom
    elif style=="reversion":score=-mom
    elif style=="breakout":
     top=hist.shift(1).rolling(lookback).max()
     bot=hist.shift(1).rolling(lookback).min()
     score=pd.Series(np.where(hist>top,1,np.where(hist<bot,-1,0)),index=days,dtype=float)
    else:score=mom
    scores[p]=score
   if style=="currency_strength":
    # Equal-weight network strengths from the 12 pair graph, computed daily causally.
    strengths={}
    for currency in ("EUR","USD","GBP","JPY","CHF","CAD","AUD","NZD"):
     components=[]
     for pair in UNIVERSE:
      if pair[:3]==currency:components.append(scores[pair])
      if pair[3:]==currency:components.append(-scores[pair])
     strengths[currency]=sum(components)/len(components)
    scores=pd.DataFrame({pair:strengths[pair[:3]]-strengths[pair[3:]] for pair in UNIVERSE},index=days)
   # Fixed deterministic opportunity: strongest ABS signal, one gross 1x FX position.
   strongest=scores.abs().idxmax(axis=1)
   daily=[]
   for i,day in enumerate(days[:-1]):
    p=strongest.iat[i]
    signal=scores.at[day,p]
    r=rets.at[day,p]
    if not np.isfinite(signal) or abs(signal)<1e-8 or not np.isfinite(r):
     daily.append((day,0.,None))
     continue
    entry=float(quotes[p].at[day,"open"])
    pip=.01 if p.endswith("JPY") else .0001
    # spread + synthetic slippage/commission, both in quote-return proxy
    cost=UNIVERSE[p][1]*pip/entry+.0001
    daily.append((day,float(np.sign(signal)*r-cost),p))
   candidates[style+"_"+str(lookback)]=daily
 return candidates
def metrics(records):
 a=np.asarray([e[1] for e in records],dtype=float)
 if len(a)==0:return {"days":0}
 equity=np.cumprod(1+a)
 peak=np.maximum.accumulate(np.r_[1.,equity])[1:]
 dd=float(np.min(equity/peak-1))
 return {"days":len(a),"active_days":sum(x[2] is not None for x in records),
  "arithmetic_mean_daily_pct":round(float(np.mean(a)*100),5),
  "compounded_pct":round(float((equity[-1]-1)*100),4),
  "max_drawdown_pct":round(dd*100,4),
  "positive_days":int(sum(a>0)),"negative_days":int(sum(a<0)),
  "meets_target":bool(np.mean(a)>=.002)}
def main():
 days,q=download()
 if len(days)<500:raise RuntimeError("not enough aligned daily observations")
 series=daily_returns(days,q)
 # Fixed dates, chronological partitions; skip last day lacking next open
 tradable=days[:-1]
 p1=tradable[int(.6*len(tradable))]
 p2=tradable[int(.8*len(tradable))]
 summaries={}
 for name,rows in series.items():
  dev=[r for r in rows if r[0]<p1]
  val=[r for r in rows if p1<=r[0]<p2]
  audit=[r for r in rows if r[0]>=p2]
  summaries[name]={"development":metrics(dev),"validation":metrics(val),"audit":metrics(audit)}
 # Select on DEVELOPMENT ONLY. Audit is disclosed, NEVER optimized here.
 ranked=sorted(summaries,key=lambda n:summaries[n]["development"]["arithmetic_mean_daily_pct"],reverse=True)
 best=ranked[0]
 result={"status":"RESEARCH_ONLY","candidate_count":len(series),
  "pairs":len(UNIVERSE),"aligned_trading_days":len(tradable),
  "development_ends":str(p1),"validation_ends":str(p2),
  "best_development_strategy":best,"best_strategy_metrics":summaries[best],
  "top5":[{"name":n,**summaries[n]} for n in ranked[:5]],
  "validation_target_crossers":[n for n in ranked if summaries[n]["validation"]["meets_target"]],
  "audit_target_crossers":[n for n in ranked if summaries[n]["audit"]["meets_target"]],
  "promoted_to_live":False,
  "limitations":["Indicative Yahoo last/opens, not bid/ask executions or broker fees",
   "1x exposure is a synthetic EUR account exposure proxy, not actual cross-FX EUR settlement",
   "Daily rebalancing, no stop orders/margin/minimum lots; EUR10 viability NOT established",
   "Historical periods have been examined in prior research; audit is NOT pristine",
   "Results vary by provider and assumptions; no confidence correction for 12 hypotheses",
   "No automatic selection based on audit, no live trading"]}
 out=Path("forex_v09_daily_equity");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
if __name__=="__main__":main()
