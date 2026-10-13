"""Independent M15 replication of ALEX Sweep Reclaim v2 for 3 pairs.
No TradingView execution: next-bar OHLC simulation, conservative same-bar stop first.
Yahoo M15 has short retention: report EXACT actual available dates.
Never use audit as evidence of deployable edge. No broker execution.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS={"EURUSD":("EURUSD=X",0.0001,1.3),"GBPUSD":("GBPUSD=X",0.0001,1.8),"USDJPY":("JPY=X",0.01,1.6)}
def download(ticker):
 d=yf.download(ticker,period="60d",interval="15m",progress=False,threads=False,auto_adjust=False)
 if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
 d=d[["Open","High","Low","Close"]].dropna().sort_index()
 d.index=pd.to_datetime(d.index,utc=True)
 if len(d)<1000:raise RuntimeError("Insufficient M15 data")
 return d
def signal_frame(d):
 c=d.Close
 tr=pd.concat([(d.High-d.Low),(d.High-c.shift()).abs(),(d.Low-c.shift()).abs()],axis=1).max(axis=1)
 atr=tr.ewm(alpha=1/14,adjust=False).mean()
 high=d.High.shift(1).rolling(24).max()
 low=d.Low.shift(1).rolling(24).min()
 candle=(d.High-d.Low).clip(lower=1e-10)
 lower=(d[["Open","Close"]].min(axis=1)-d.Low)/candle
 upper=(d.High-d[["Open","Close"]].max(axis=1))/candle
 # H1 confirmation uses the PRIOR completed H1 candle (right-labelled H1).
 h=d.resample("1h",closed="left",label="right").agg({"Close":"last"}).dropna()
 hprev=h.Close.shift(1)
 hema=h.Close.ewm(span=20,adjust=False).mean().shift(1)
 hc=hprev.reindex(d.index,method="ffill")
 hm=hema.reindex(d.index,method="ffill")
 # Previous completed H1 for a bar ending 15m after the hour:
 # h resample right labels H1 bar completion. At 09:15, 09:00 is previous H1.
 # To mirror Pine offset[1] we use a further lag (conservative).
 hp=h.Close.shift(1).reindex(d.index,method="ffill")
 he=h.Close.ewm(span=20,adjust=False).mean().shift(1).reindex(d.index,method="ffill")
 lon=pd.Series(d.index.tz_convert("Europe/London").hour,index=d.index)
 active=(lon>=7)&(lon<17)
 atrpct=atr/c*100
 long=active&(atrpct>=.035)&(atrpct<=.35)&(d.Low<low)&(c>low)&(c>d.Open)&(lower>=.3)&(hp<he)
 short=active&(atrpct>=.035)&(atrpct<=.35)&(d.High>high)&(c<high)&(c<d.Open)&(upper>=.3)&(hp>he)
 return atr,long.fillna(False),short.fillna(False)
def run(pair,d):
 pip,spread=PAIRS[pair][1:]
 atr,buy,sell=signal_frame(d)
 equity=10000.;peak=equity;dd=0.;records=[];last_entry=-10000;i=40
 while i<len(d)-2:
  if i-last_entry<=5 or not (buy.iat[i] or sell.iat[i]):
   i+=1;continue
  side=1 if buy.iat[i] else -1
  stop=float(d.Low.iat[i]-.3*atr.iat[i]) if side==1 else float(d.High.iat[i]+.3*atr.iat[i])
  entry=float(d.Open.iat[i+1]);distance=side*(entry-stop)
  if not np.isfinite(distance) or distance<=0 or distance<2*1e-6:
   i+=1;continue
  # 0.5% initial-stop risk, hard max 1x gross notional.
  notional_fraction=min(1.0,.005/(distance/entry))
  if notional_fraction<=0:i+=1;continue
  target=entry+side*2*distance
  exit_=float(d.Close.iat[min(i+18,len(d)-1)])
  why="time";last=min(i+18,len(d)-1)
  for j in range(i+1,min(i+19,len(d))):
   b=d.iloc[j]
   stophit=(b.Low<=stop if side==1 else b.High>=stop)
   targethit=(b.High>=target if side==1 else b.Low<=target)
   if stophit:
    exit_=min(float(b.Open),stop) if side==1 else max(float(b.Open),stop)
    why="stop";last=j;break
   if targethit:exit_=target;why="target";last=j;break
  cost=(spread*pip/entry+0.00012)*notional_fraction
  net=side*(exit_/entry-1)*notional_fraction-cost
  previous=equity;equity*=1+net;peak=max(peak,equity);dd=min(dd,equity/peak-1)
  records.append({"entry":str(d.index[i+1]),"exit":str(d.index[last]),"side":"LONG" if side==1 else "SHORT",
                   "exit_type":why,"net_return_pct":round(net*100,6),"equity":round(equity,3)})
  last_entry=i+1;i=last+1
 dates=pd.DatetimeIndex([pd.Timestamp(x["entry"]) for x in records],tz="UTC") if records else []
 wins=sum(r["net_return_pct"]>0 for r in records)
 grosspos=sum(max(0,r["net_return_pct"]) for r in records)
 grossneg=-sum(min(0,r["net_return_pct"]) for r in records)
 return {"pair":pair,"data_start_utc":str(d.index.min()),"data_end_utc":str(d.index.max()),
  "bars":len(d),"trades":len(records),"wins":wins,"win_rate_pct":round(100*wins/len(records),2) if records else None,
  "profit_factor":round(grosspos/grossneg,3) if grossneg else None,
  "roi_pct":round((equity/10000-1)*100,4),"max_dd_pct":round(dd*100,4),
  "stop_exits":sum(r["exit_type"]=="stop" for r in records),
  "target_exits":sum(r["exit_type"]=="target" for r in records),
  "time_exits":sum(r["exit_type"]=="time" for r in records),
  "records":records}
def main():
 outputs=[]
 for pair,(ticker,pip,spread) in PAIRS.items():
  print("Downloading",pair,flush=True)
  outputs.append(run(pair,download(ticker)))
 report={"system":"Sweep Reclaim v2 M15 independent replication","status":"RESEARCH ONLY",
 "requested_period":"2026-07-01 through 2026-10-13","executed_period":"actual downloaded M15 coverage in each pair below",
 "method":"next-open entry, 2R target, ATR structural stop, conservative same-bar stop-first, max 1x notional, flat 0.5% risk",
 "costs":"spread estimate per pair +1.2 bps friction per trade, applied once",
 "results":[{k:v for k,v in x.items() if k!="records"} for x in outputs],
 "important_limitations":["Not a TradingView-native backtest; Pine broker emulator may differ",
 "Yahoo M15 retention cannot cover full requested 1 July to 13 October period",
 "Indicative mid quotes not executable bid/ask and forex conversion approximated",
 "No minimum broker lots, swaps, fill latency or live feasibility, no claims of profitability"]}
 folder=Path("forex_sweep_v20_m15");folder.mkdir(exist_ok=True)
 (folder/"report.json").write_text(json.dumps(report,indent=2))
 for x in outputs:
  pd.DataFrame(x["records"]).to_csv(folder/(x["pair"]+"_trades.csv"),index=False)
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
