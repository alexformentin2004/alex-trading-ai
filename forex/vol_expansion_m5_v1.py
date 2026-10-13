"""Volatility Expansion Momentum M5 research — speculative, no live trading.
Yahoo M5 indicative midpoint. Fixed configs, causal signals, fee/slippage proxy.
Maximum 10x assumed; 3-4 month target cannot be verified with Yahoo's short
M5 retention. Fail closed if missing full history; use shorter exploratory folds.
"""
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
PAIRS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X"}
SPREAD={"EURUSD":1.3,"GBPUSD":1.8,"USDJPY":1.6}
CONFIGS=[(length,mult,confirm) for length in (12,24,48) for mult in (1.3,1.8) for confirm in (0,1)]
LEVERAGES=(1,3,5,10)
CAP=50.;TARGET=101*CAP
def fetch():
 out={}
 for pair,ticker in PAIRS.items():
  df=yf.download(ticker,period="60d",interval="5m",auto_adjust=False,progress=False,threads=False)
  if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
  df=df[["Open","High","Low","Close"]].dropna().astype(float)
  df.index=pd.to_datetime(df.index,utc=True)
  out[pair]=df
 return out
def signals(df,length,mult,confirm):
 prev=df.Close.shift(1)
 ret=(prev/prev.shift(length)-1).to_numpy()
 tr=pd.concat([df.High-df.Low,(df.High-prev).abs(),(df.Low-prev).abs()],axis=1).max(axis=1)
 atr=tr.rolling(14).mean().shift(1).to_numpy()
 med=pd.Series(atr,index=df.index).rolling(length).median().shift(1).to_numpy()
 expansion=(atr>mult*med)
 direction=np.sign(ret)
 if confirm:
  direction=np.where(np.sign((df.Close.shift(1)/df.Open.shift(1)-1).to_numpy())==direction,direction,0)
 return expansion,direction,atr
def evaluate(df,pair,config,leverage,start,end,stress=1.0):
 length,mult,confirm=config
 expand,side,atr=signals(df,length,mult,confirm)
 equity=CAP;peak=CAP;maxdd=0.;wins=0;trades=0;ruined=False
 # enter at bar open, hold max 3 bars, allow only nonoverlapping positions
 i=max(start,length+25)
 while i<end-3:
  if not expand[i] or not np.isfinite(side[i]) or side[i]==0 or not np.isfinite(atr[i]):
   i+=1;continue
  px=float(df.Open.iat[i]);s=float(side[i])
  pip=.01 if pair.endswith("JPY") else .0001
  cost=(SPREAD[pair]*pip/px+.00012)*stress
  distance=max(float(atr[i])*1.1,px*.00015)
  stop=px-s*distance;target=px+s*distance*2
  fill=None
  for j in range(i,i+3):
   hi=float(df.High.iat[j]);lo=float(df.Low.iat[j])
   if s==1:
    if lo<=stop:fill=stop;break
    if hi>=target:fill=target;break
   else:
    if hi>=stop:fill=stop;break
    if lo<=target:fill=target;break
  if fill is None:fill=float(df.Close.iat[i+2])
  r=leverage*(s*(fill/px-1)-cost)
  if r<=-1:
   equity=0.;ruined=True
  else:equity*=1+r
  trades+=1;wins+=r>0;peak=max(peak,equity);maxdd=min(maxdd,equity/peak-1)
  if equity<=.2*CAP:ruined=True
  if ruined:break
  i+=3
 return {"roi_pct":round((equity/CAP-1)*100,3),"max_dd_pct":round(maxdd*100,3),
 "trades":trades,"win_rate_pct":round(wins/max(1,trades)*100,2),
 "ruined":ruined,"hit_10000pct":bool(equity>=TARGET),"end_eur":round(equity,2)}
def main():
 data=fetch();results={}
 for pair,df in data.items():
  if len(df)<2500:raise RuntimeError(f"Insufficient M5 data for {pair}: {len(df)}")
  # 3 chronological contiguous folds; no parameter selection on each test fold.
  train=int(len(df)*.5);block=(len(df)-train)//3
  chosen=None;best=-1e18
  for c in CONFIGS:
   for lev in LEVERAGES:
    m=evaluate(df,pair,c,lev,200,train)
    score=m["roi_pct"]-1.0*abs(m["max_dd_pct"])-1e6*m["ruined"]
    if score>best:best=score;chosen=(c,lev)
  c,lev=chosen;folds=[]
  for k in range(3):
   st=train+k*block;end=train+(k+1)*block if k<2 else len(df)
   test=evaluate(df,pair,c,lev,st,end)
   double=evaluate(df,pair,c,lev,st,end,2)
   folds.append({"from":str(df.index[st]),"to":str(df.index[end-1]),
                 "standard_cost":test,"double_cost":double})
  results[pair]={"rows":len(df),"start":str(df.index[0]),"end":str(df.index[-1]),
                 "training_selected":{"config":c,"leverage":lev},
                 "forward_folds":folds}
 report={"status":"RESEARCH_ONLY","objective_roi_pct":10000,"goal_horizon":"3-4 months",
 "horizon_tested":"AVAILABLE Yahoo M5 slice; NOT 3-4 months",
 "configs_per_pair":len(CONFIGS)*len(LEVERAGES),"pairs":results,
 "notes":["Only EURUSD GBPUSD USDJPY; not all 12 due runtime and M5 source",
 "M5 midpoint proxy, synthetic spread plus slippage, no true broker bid/ask",
 "H1/M5 researched historical period is contaminated, not untouched future OOS",
 "No broker margin call, fees, min lot, USD/EUR conversion or finance",
 "Even a huge ROI on training data cannot count as a proven discovery",
 "Trading uses leverage in simulation, no real execution"]}
 out=Path("forex_vol_expansion_m5_v1");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(report,indent=2))
 print("SUMMARY",json.dumps(report,indent=2))
if __name__=="__main__":main()
