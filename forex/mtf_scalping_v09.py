"""ALEX FOREX v0.9: research-only multi-pair M5 scalping with completed M15/H1 filters.
Yahoo mid-like bars; no real bid/ask, lot steps, broker margin or executable fills.
No claim of profit. Emits strict walk-forward diagnostics; prior overlapping research
means verification is NOT a pristine unseen holdout.
"""
from pathlib import Path
import json
import math
import pandas as pd
import yfinance as yf

PAIRS = {
 "EURUSD":("EURUSD=X",0.0001,1.2),
 "GBPUSD":("GBPUSD=X",0.0001,1.8),
 "USDJPY":("JPY=X",0.01,1.5),
 "AUDUSD":("AUDUSD=X",0.0001,1.8),
 "USDCAD":("CAD=X",0.0001,1.8),
 "USDCHF":("CHF=X",0.0001,1.7),
 "EURJPY":("EURJPY=X",0.01,2.5),
 "GBPJPY":("GBPJPY=X",0.01,3.2),
 "EURGBP":("EURGBP=X",0.0001,1.8),
}
STRATEGIES=("pullback","breakout")
MODES=("m5_only","m15_h1_aligned")
def get_data():
 out={};issues={}
 for pair,(ticker,_,_) in PAIRS.items():
  try:
   d=yf.download(ticker,period="30d",interval="5m",auto_adjust=False,progress=False,threads=False)
   if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
   d=d[["Open","High","Low","Close"]].dropna().sort_index()
   d.index=pd.to_datetime(d.index,utc=True)
   if len(d)<500 or not d.index.is_unique or not (d.High>=d[["Open","Close","Low"]].max(axis=1)).all() or not (d.Low<=d[["Open","Close","High"]].min(axis=1)).all():
    raise ValueError("empty/invalid candles")
   out[pair]=d
  except Exception as exc:issues[pair]=str(exc)
 if len(out)<3:raise RuntimeError(f"Too few usable FX series: {issues}")
 return out,issues

def indicators(data):
 result={}
 for pair,d in data.items():
  c=d.Close
  hi=d.High.shift().rolling(12,min_periods=12).max()
  lo=d.Low.shift().rolling(12,min_periods=12).min()
  ema=c.ewm(span=18,adjust=False).mean()
  prev=c.shift()
  tr=pd.concat([d.High-d.Low,(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
  atr=tr.rolling(14,min_periods=14).mean().shift(1)
  base={}
  breakout=pd.Series(0,index=d.index)
  breakout[(c>hi)&(prev<=hi.shift())]=1
  breakout[(c<lo)&(prev>=lo.shift())]=-1
  pullback=pd.Series(0,index=d.index)
  pullback[(prev<=ema.shift())&(c>ema)&(c>prev)]=1
  pullback[(prev>=ema.shift())&(c<ema)&(c<prev)]=-1
  base["breakout"]=breakout;base["pullback"]=pullback
  # RIGHT label means H1 value at 10:00 includes ONLY bars prior to 10:00.
  # Use last completed H1 / M15 state for signals evaluated at M5 close.
  def trend(freq,fast,slow):
   h=d.resample(freq,label="right",closed="left").agg({"Close":"last"}).dropna()
   f=h.Close.ewm(span=fast,adjust=False).mean()
   s=h.Close.ewm(span=slow,adjust=False).mean()
   t=pd.Series(0,index=h.index)
   t[(f>s)&(s>s.shift(2))]=1
   t[(f<s)&(s<s.shift(2))]=-1
   return t.reindex(d.index,method="ffill").fillna(0).astype(int)
  result[pair]={"d":d,"atr":atr,"base":base,"m15":trend("15min",8,21),"h1":trend("1h",8,24)}
 return result

def simulate(indicators,mode,cost_scale=1.0,initial=50.0):
 # This is a hypothetical fractional-USD-notional market experiment, NOT real broker execution.
 ts=sorted(set(t for item in indicators.values() for t in item["d"].index))
 events={}
 for pair,item in indicators.items():
  d=item["d"];a=item["atr"]
  for strategy,signal in item["base"].items():
   for i in range(140,len(d)-1):
    side=int(signal.iat[i])
    if side==0:continue
    enter=d.index[i+1]
    if enter.weekday()>4 or not (7<=enter.hour<18):continue
    if mode=="m15_h1_aligned" and not (side==int(item["m15"].iat[i])==int(item["h1"].iat[i])):continue
    unit=PAIRS[pair][1];spread=PAIRS[pair][2]*unit
    vol=float(a.iat[i])
    if not math.isfinite(vol) or vol<spread*4:continue
    events.setdefault(enter,[]).append((pair,strategy,side,vol,i+1))
 cash=initial;positions=[];done=[];max_open=0;rejected=0;peak=initial;max_dd=0
 all_last=min(x["d"].index.max() for x in indicators.values())
 split=all_last-pd.Timedelta(days=10)
 for t in ts:
  keep=[]
  for p in positions:
   d=indicators[p["pair"]]["d"]
   if t not in d.index:keep.append(p);continue
   b=d.loc[t]
   sl=(b.Low<=p["sl"] if p["side"]>0 else b.High>=p["sl"])
   tp=(b.High>=p["tp"] if p["side"]>0 else b.Low<=p["tp"])
   timeout=t>=p["expiry"]
   if not (sl or tp or timeout):keep.append(p);continue
   # If both stop and target touch inside same bar, choose stop (conservative).
   px=p["sl"] if sl else p["tp"] if tp else float(b.Close)
   gross=p["notional"]*p["side"]*(px/p["entry"]-1)
   spread=PAIRS[p["pair"]][1]*PAIRS[p["pair"]][2]
   # one round-trip indicative spread + slippage (not exchange observed)
   costs=p["notional"]*(spread/p["entry"]+0.0001)*cost_scale
   pnl=gross-costs
   cash+=pnl
   done.append({"pair":p["pair"],"strategy":p["strategy"],"split":"verification" if p["opened"]>=split else "development","pnl":pnl})
  positions=keep
  for pair,strategy,side,atr,i in events.get(t,[]):
   if cash<1:rejected+=1;continue
   # Multiple positions per instrument permitted across strategies.
   # No arbitrary portfolio count cap; notional & stop-risk constrain entries.
   if any(p["pair"]==pair and p["strategy"]==strategy and p["side"]==side for p in positions):continue
   notional=min(initial*0.15,cash*0.15)
   if notional<0.5:rejected+=1;continue
   aggregate=sum(p["notional"] for p in positions)
   if aggregate+notional>cash*2:rejected+=1;continue
   entry=float(indicators[pair]["d"].Open.iat[i])
   stop=1.3*atr;target=2.2*atr
   portfolio_stop=sum(p["notional"]*abs(p["entry"]-p["sl"])/p["entry"] for p in positions)
   if portfolio_stop+notional*stop/entry>cash*0.03:rejected+=1;continue
   d=indicators[pair]["d"]
   positions.append({"pair":pair,"strategy":strategy,"side":side,"entry":entry,"sl":entry-side*stop,"tp":entry+side*target,"expiry":d.index[min(i+18,len(d)-1)],"notional":notional,"opened":t})
  max_open=max(max_open,len(positions))
  peak=max(peak,cash);max_dd=max(max_dd,(peak-cash)/peak if peak else 0)
 def stat(rows):
  wins=sum(x["pnl"] for x in rows if x["pnl"]>0)
  losses=-sum(x["pnl"] for x in rows if x["pnl"]<0)
  return {"trades":len(rows),"net_usd":round(sum(x["pnl"] for x in rows),5),"profit_factor":round(wins/losses,3) if losses else None,"win_rate_pct":round(100*sum(x["pnl"]>0 for x in rows)/len(rows),2) if rows else None}
 return {"mode":mode,"cost_scale":cost_scale,"starting_usd":initial,"ending_cash_usd":round(cash,4),"return_pct":round((cash/initial-1)*100,2),"max_simultaneous":max_open,"max_cash_balance_dd_pct":round(max_dd*100,2),"unclosed":len(positions),"rejections":rejected,"split_utc":str(split),"development":stat([x for x in done if x["split"]=="development"]),"verification":stat([x for x in done if x["split"]=="verification"]),"by_strategy":{s:stat([x for x in done if x["strategy"]==s]) for s in STRATEGIES},"by_pair":{p:stat([x for x in done if x["pair"]==p]) for p in indicators}}
if __name__=="__main__":
 data,issues=get_data()
 prepared=indicators(data)
 results={"data":{p:{"bars":len(d),"start":str(d.index.min()),"end":str(d.index.max())} for p,d in data.items()},"missing_symbols":issues,"runs":[simulate(prepared,mode,scale) for mode,scale in [("m5_only",1.0),("m15_h1_aligned",1.0),("m15_h1_aligned",2.0)]],"limitations":["30d Yahoo M5 is exploratory and overlapping prior research, not untouched holdout","No historical bid/ask; costs hypothetical","Notional in fractional USD exposure, incompatible with real FX minimum trade sizes for tiny balances","No broker margin call, hedging rules, swap or overnight execution","Position risk approximate; realized balance drawdown omits open equity","No statistical claim of profitability"]}
 out=Path("forex_v09_report");out.mkdir(exist_ok=True)
 (out/"results.json").write_text(json.dumps(results,indent=2))
 print(json.dumps(results,indent=2))
