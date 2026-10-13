"""ALEX FOREX 2.0 / SESSION EDGE v1.1 — complete, falsifiable strategy.

Asia compression -> London range expansion, with executable timing,
stop, take profit and time stop. All twelve pairs monitored.
Research-only: Yahoo H1 mid OHLC + estimated spread/slippage; not broker fills.
Trade equity: 1x max gross notional, one candidate per day, no margin leverage.
Events selected using only information available at 11:00 UTC.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),
"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),
"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),
"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
def fetch():
 data={}
 for p,(ticker,_) in PAIRS.items():
  d=yf.download(ticker,period="730d",interval="1h",auto_adjust=False,progress=False,threads=False)
  if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
  d=d[["Open","High","Low","Close"]].dropna().sort_index()
  d.index=pd.to_datetime(d.index,utc=True)
  if len(d)<10000:raise RuntimeError("Insufficient "+p)
  data[p]=d
 return data
def proposals(sym,df):
 # Entry: 11:00 UTC after confirmation at 10:00 hour CLOSE.
 # Asian range from 00:00-06:00 completed bars; confirmation from 07:00-10:00.
 # Avoid DST session-exact claim; UTC static approximation.
 pips=PAIRS[sym][1];pip=.01 if sym.endswith("JPY") else .0001
 past_abs=df.Close.pct_change().abs().rolling(100,min_periods=100).median()
 days=pd.DatetimeIndex(sorted(set(df.index.normalize())))
 proposals={}
 for day in days:
  if day.weekday()>4:continue
  asias=df.loc[(df.index>=day)&(df.index<day+pd.Timedelta(hours=7))]
  london=df.loc[(df.index>=day+pd.Timedelta(hours=7))&(df.index<day+pd.Timedelta(hours=11))]
  target=day+pd.Timedelta(hours=11)
  if len(asias)!=7 or len(london)!=4 or target not in df.index:continue
  # Low-range Asia filter relative to *previous* 100-bar hourly typical range.
  prev=df.index.get_indexer([day],method="pad")[0]
  if prev<101:continue
  typical=float((df.High-df.Low).iloc[prev-100:prev].median())
  asia_hi=float(asias.High.max());asia_lo=float(asias.Low.min())
  arange=asia_hi-asia_lo
  if not (typical>0 and arange<=4.5*typical):continue
  close=float(london.Close.iloc[-1]);early=float(london.Close.iloc[0])
  # London expansion: sustained close outside Asian range (not merely a wick).
  side=1 if close>asia_hi and close>early else (-1 if close<asia_lo and close<early else 0)
  if not side:continue
  entry=float(df.at[target,"Open"])
  if side==1 and entry<asia_hi or side==-1 and entry>asia_lo:continue
  # Hard stop behind Asian midpoint or 1.2x typical hourly range, whichever tighter
  stop_dist=max(1.2*typical,2.5*pips*pip)
  # Stop distance capped to make target meaningful; reject runaway gap.
  if abs(entry-close)>stop_dist*.3:continue
  stop=entry-side*stop_dist
  target_price=entry+side*1.8*stop_dist
  cost=pips*pip/entry+.00012  # spread + indicative friction
  if (1.8*stop_dist/entry)<4*cost:continue # reward sufficient relative to costs
  # Record score BEFORE any future prices; choose strongest normalized break.
  strength=abs(close-(asia_hi if side>0 else asia_lo))/max(arange,typical)
  proposals[day]=(sym,side,entry,stop,target_price,stop_dist,cost,strength,target)
 return proposals
def outcome(df,proposal,fees_multiplier=1):
 sym,side,entry,stop,tp,dist,cost,strength,t=proposal
 # Entry at 11. Process only FUTURE bars 11:00-17:00, worst-case stop first.
 bars=df.loc[(df.index>=t)&(df.index<t+pd.Timedelta(hours=7))]
 if len(bars)<5:return None
 exit_=float(bars.Close.iloc[-1]);kind="time"
 for _,bar in bars.iterrows():
  if side>0:
   stop_hit=bar.Low<=stop;target_hit=bar.High>=tp
  else:
   stop_hit=bar.High>=stop;target_hit=bar.Low<=tp
  if stop_hit:
   exit_=float(min(stop,float(bar.Open)) if side==1 else max(stop,float(bar.Open)))
   kind="stop";break
  if target_hit:
   exit_=float(tp);kind="take_profit";break
 # One unit of EUR-denominated gross exposure. No additional leverage.
 pnl=side*(exit_/entry-1)-cost*fees_multiplier
 return float(pnl),kind
def calc(a):
 a=np.asarray(a,dtype=float)
 if len(a)==0:return {"days":0}
 eq=np.cumprod(1+a);peak=np.maximum.accumulate(np.r_[1.,eq])[1:]
 return {"days":len(a),"active_days":int(np.count_nonzero(a)),"mean_daily_pct":round(float(a.mean()*100),5),
 "cumulative_pct":round(float((eq[-1]-1)*100),4),
 "max_drawdown_pct":round(float(min(eq/peak-1)*100),4),
 "positive_days":int(sum(a>0)),"negative_days":int(sum(a<0)),
 "meets_0_2_pct_target":bool(a.mean()>=.002)}
def main():
 data=fetch();prs={p:proposals(p,d) for p,d in data.items()}
 days=sorted(set.intersection(*(set(d.index.normalize()) for d in data.values())))
 # Generate fixed day-level ledger, including all non-trading days.
 records=[]
 for day in days:
  if day.weekday()>4:continue
  c=[x[day] for x in prs.values() if day in x]
  if not c:records.append((day,0.,0.,None,None));continue
  # Highest normalized, causal breakout strength among 12 pairs, 1x max exposure.
  c.sort(key=lambda x:(-x[7],x[0]))
  p=c[0];v=outcome(data[p[0]],p,1);v2=outcome(data[p[0]],p,2)
  if v is None:records.append((day,0.,0.,None,None));continue
  records.append((day,v[0],v2[0],p[0],v[1]))
 n=len(records);one=int(.6*n);two=int(.8*n)
 def metrics(slice_):
  s=records[slice_]
  return {"normal":calc([x[1] for x in s]),"double_cost":calc([x[2] for x in s]),
   "selected_pairs":{p:sum(x[3]==p for x in s) for p in PAIRS},
   "stop_count":sum(x[4]=="stop" for x in s),
   "target_count":sum(x[4]=="take_profit" for x in s)}
 report={"name":"Session Edge Asia Compression + London Expansion","mode":"RESEARCH_ONLY",
 "data_window":[str(min(d.index.min() for d in data.values())),str(max(d.index.max() for d in data.values()))],
 "total_days":n,"development":metrics(slice(0,one)),"validation":metrics(slice(one,two)),
 "audit":metrics(slice(two,None)),
 "all_pairs_monitored":list(PAIRS),
 "hard_limits":{"gross_exposure":"1x","max_one_trade_per_day":True,
                "stop_and_take_profit":"tested, adverse same-bar priority"},
 "limitations":["Yahoo H1 indicative mids; cannot infer executable broker bid/ask and gap fills",
 "Static UTC sessions ignore DST and exchange-specific settlement and news releases",
 "1x synthetic quote return approximates EUR notional, no currency translation ledger",
 "Historical audit dates explored by prior experiments, not pristine holdout",
 "30% drawdown stop not simulated because offline research and no live promotion",
 "Minimum lot, real leverage and EUR10 broker compatibility not verified",
 "No statistical guarantee, no AI or real-time execution"]}
 out=Path("forex_session_edge_v11");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
