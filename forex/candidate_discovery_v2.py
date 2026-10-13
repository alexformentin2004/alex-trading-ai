"""Frozen cross-pair FX strategy discovery v2: carry-neutral session momentum and fade.

This is an intentionally SMALL family of hypotheses, 12 pairs, 2 directions,
3 lookbacks, 2 execution frequencies. Training-selection uses preceding dates
only, no selection on forward windows, report failure honestly.
Yahoo H1 midpoint proxy; spread/cost estimates not true bid/ask.
"""
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf

PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),"USDJPY":("JPY=X",1.6),
"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),
"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),
"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.),"EURCHF":("EURCHF=X",2.3),
"AUDJPY":("AUDJPY=X",3.)}
TRAIN=240;TEST=96;CAP=50.
def load():
 data={}
 for pair,(ticker,sp) in PAIRS.items():
  df=yf.download(ticker,period="730d",interval="1h",auto_adjust=False,progress=False,threads=False)
  if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
  df=df[["Open","Close"]].dropna().astype(float)
  df.index=pd.to_datetime(df.index,utc=True)
  data[pair]=df
 common=pd.DatetimeIndex(sorted(set.intersection(*(set(df.index) for df in data.values()))))
 return common,{p:df.reindex(common) for p,df in data.items()}
def portfolios(t,d):
 variants={}
 for step in (4,8):
  entry_idx=np.arange(25,len(t)-step,step)
  dates=t[entry_idx]
  for lookback in (4,12,24):
   for mode in ("trend","fade"):
    # Portfolios rotate notional toward strongest signal each step.
    # This does NOT mean six strategies independently share the same equity.
    net=np.zeros(len(entry_idx))
    for j,i in enumerate(entry_idx):
     items=[]
     for p,df in d.items():
      prev=float(df.Close.iat[i-1]);past=float(df.Close.iat[i-lookback])
      val=prev/past-1
      scale=1 if mode=="trend" else -1
      items.append((abs(val),p,np.sign(val)*scale))
     items.sort(key=lambda v:(-v[0],v[1]))
     _,p,side=items[0];px=float(d[p].Open.iat[i]);end=float(d[p].Open.iat[i+step])
     pip=.01 if p.endswith("JPY") else .0001
     spread=PAIRS[p][1]*pip/px
     # gross 1x, one full round-trip spread plus 1bps extra, no funding
     net[j]=side*(end/px-1)-spread-.0001
    variants[f"{mode}_{lookback}h_{step}h"]=net
 return dates,variants
def metrics(a):
 a=np.asarray(a);eq=np.cumprod(1+a);peak=np.maximum.accumulate(np.r_[1.,eq])[1:]
 return {"n":len(a),"roi_pct":round((eq[-1]-1)*100,3),
         "mean_pct_per_period":round(np.mean(a)*100,5),
         "dd_pct":round((eq/peak-1).min()*100,3),
         "win_rate_pct":round(100*np.mean(a>0),2)}
def main():
 t,d=load();dates,vars=portfolios(t,d)
 if len(dates)<TRAIN+2*TEST:raise RuntimeError("Insufficient synchronized observations")
 folds=[]
 for start in range(TRAIN,len(dates)-TEST+1,TEST):
  # selection uses only PREVIOUS period, one-period purge
  ranking=sorted([(metrics(a[:start-1])["roi_pct"],name) for name,a in vars.items()],reverse=True)
  selected=ranking[0][1]
  fold=metrics(vars[selected][start:start+TEST])
  folds.append({"start":str(dates[start]),"end":str(dates[start+TEST-1]),"strategy":selected,"forward":fold})
 # Across all rolling folds, zero target cherry picking.
 n=len(folds);positive=sum(f["forward"]["roi_pct"]>0 for f in folds)
 # Fixed candidate comparison in the most recent, already-seen 3mo period.
 cutoff=pd.Timestamp("2026-07-01",tz="UTC");end=pd.Timestamp("2026-10-13",tz="UTC")
 indices=np.flatnonzero((dates>=cutoff)&(dates<end))
 exploratory={}
 if len(indices):
  for name,a in vars.items():exploratory[name]=metrics(a[indices])
 report={"status":"RESEARCH_ONLY","pairs":len(d),"bars":len(t),"strategies":len(vars),
 "windows":n,"positive_windows":int(positive),"forward_windows":folds,
 "previously_seen_2026_jul_oct":exploratory,
 "limitations":["Yahoo mid H1, approximated spreads/fees, no broker fills",
 "Previous date ranges have been inspected, so not an untouched future evaluation",
 "Portfolio 1x notional, no borrowing charges or exchange conversion",
 "No claim of sustainable profitability until independent positive forward trials"]}
 out=Path("forex_discovery_v2");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(report,indent=2))
 print("SUMMARY",json.dumps({"bars":int(len(t)),"strategies":int(len(vars)),"windows":int(n),
 "positive_windows":int(positive),"folds":folds[-8:],
 "recent":sorted(exploratory.items(),key=lambda x:x[1]["roi_pct"],reverse=True)[:5]},indent=2))
if __name__=="__main__":main()
