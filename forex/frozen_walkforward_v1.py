"""Frozen chronological FX research protocol v1.

This script deliberately DOES NOT select a winning configuration based on
the already-seen 2026-07..10 dates. Uses prior history only for parameter
choice and 2026-07-01+ purely as a DISCLOSED, CONTAMINATED historical check.
A future, as-yet-unobserved time period is required for a genuine final test.
All output is research only, not an actionable execution system.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),
"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),"USDCAD":("CAD=X",1.9),
"AUDUSD":("AUDUSD=X",1.9),"NZDUSD":("NZDUSD=X",2.3),
"EURJPY":("EURJPY=X",2.6),"GBPJPY":("GBPJPY=X",3.5),
"EURGBP":("EURGBP=X",2.0),"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
CONFIGS=[(style,lookback) for style in ("trend","reversion") for lookback in (5,10,20)]
TRAIN=180
TEST=45
DATE_PREVIOUSLY_EXAMINED="2026-07-01"

def fetch():
 out={}
 for pair,(ticker,spread) in PAIRS.items():
  d=yf.download(ticker,period="730d",interval="1h",auto_adjust=False,
                progress=False,threads=False)
  if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
  d=d[["Open","Close"]].dropna()
  d.index=pd.to_datetime(d.index,utc=True)
  op=d.Open[d.index.hour==8].resample("1D").first()
  prior=d.Close.resample("1D").last().shift(1)
  out[pair]=pd.DataFrame({"entry":op,"known_close":prior})
 common=sorted(set.intersection(*(set(d.dropna().index) for d in out.values())))
 common=pd.DatetimeIndex(common,tz="UTC")
 return common,{pair:d.reindex(common) for pair,d in out.items()}

def returns(days,quotes):
 # Signals from previous fully completed day, entries at today's 08 UTC.
 # A 08-to-next-08 position is held at most one day. Portfolio 1x max.
 y=pd.DataFrame({pair:q.entry.shift(-1)/q.entry-1 for pair,q in quotes.items()},index=days)
 costs=pd.DataFrame(index=days)
 for pair,q in quotes.items():
  pip=.01 if pair.endswith("JPY") else .0001
  costs[pair]=PAIRS[pair][1]*pip/q.entry+.0001
 variants={}
 for style,lookback in CONFIGS:
  signals=pd.DataFrame({p:(q.known_close/q.known_close.shift(lookback)-1) for p,q in quotes.items()},index=days)
  if style=="reversion":signals=-signals
  # One position across all 12 pairs, fixed 1x gross (when signal available).
  best=signals.abs().fillna(0).idxmax(axis=1)
  vals=np.zeros(len(days)-1)
  for i,day in enumerate(days[:-1]):
   pair=best.iat[i];s=signals.at[day,pair];gross=y.at[day,pair]
   if pd.notna(s) and abs(s)>0 and np.isfinite(gross):
    vals[i]=float(np.sign(s)*gross-costs.at[day,pair])
  variants[style+"_"+str(lookback)]=vals
 return variants

def stat(a):
 a=np.asarray(a,dtype=float)
 if not len(a):return {"days":0}
 equity=np.cumprod(1+a)
 peaks=np.maximum.accumulate(np.r_[1.,equity])[1:]
 return {"days":len(a),"mean_daily_pct":round(float(a.mean()*100),5),
 "compound_pct":round(float((equity[-1]-1)*100),3),
 "max_dd_pct":round(float((equity/peaks-1).min()*100),3),
 "meets_target":bool(a.mean()>=.002)}

def main():
 days,quotes=fetch()
 if len(days)<550:raise RuntimeError("Less than 550 common observations")
 arrays=returns(days,quotes)
 # dates == return record's ENTRY date; next-day exit remains observed.
 entries=days[:-1]
 cutoff=pd.Timestamp(DATE_PREVIOUSLY_EXAMINED,tz="UTC")
 clean_indices=np.flatnonzero(entries<cutoff)
 if len(clean_indices)<TRAIN+TEST:raise RuntimeError("Insufficient pre-examined sample")
 # DISJOINT, expanding time-ordered training with 45-day forward windows.
 # Purge one day at the boundary because next-day exit overlaps.
 folds=[]
 for start in range(TRAIN,len(clean_indices)-TEST+1,TEST):
  train_idx=np.arange(0,start-1)
  test_idx=np.arange(start,start+TEST)
  choices={name:float(a[train_idx].mean()) for name,a in arrays.items()}
  chosen=max(choices,key=choices.get)
  folds.append({"start":str(entries[test_idx[0]].date()),"end":str(entries[test_idx[-1]].date()),
   "chosen":chosen,"development_mean_daily_pct":round(choices[chosen]*100,5),
   "forward":stat(arrays[chosen][test_idx]),
   "all_strategies_forward":{n:stat(a[test_idx]) for n,a in arrays.items()}})
 selected_days=sum(f["forward"]["days"] for f in folds)
 eligible=all(f["forward"]["meets_target"] for f in folds)
 historical={name:stat(a[np.flatnonzero(entries>=cutoff)]) for name,a in arrays.items()}
 selected_means=[f["forward"]["mean_daily_pct"] for f in folds]
 report={"research_type":"pre-registered expanding walk-forward screening",
 "status":"NO_LIVE","pairs":list(PAIRS),"fixed_hypotheses":list(arrays),
 "available_range":[str(entries[0].date()),str(entries[-1].date())],
 "prior_studied_cutoff":DATE_PREVIOUSLY_EXAMINED,
 "train_days_initial":TRAIN,"forward_days_per_fold":TEST,"purge_days":1,
 "folds":folds,"forward_total_days":selected_days,
 "forward_weighted_mean_daily_pct":round(sum(x["forward"]["mean_daily_pct"]*x["forward"]["days"] for x in folds)/selected_days,5),
 "all_folds_reach_0_2_pct_daily":eligible,
 "previously_seen_jul_2026_and_later_not_used_to_select":historical,
 "promotion_allowed":False,
 "required_next":"Freeze hypotheses, get unexamined future bid/ask data from broker, then single blind evaluation",
 "limitations":["Costs are indicative, no executable tick bid/ask or EUR-account settled FX portfolio",
 "Historical source and existing periods previously inspected; pre-July is not completely pristine",
 "Yahoo daily 08 UTC entry times and weekend gaps are not broker-executable",
 "Potential data issues, financing, swaps, margin, minimum lot unresolved",
 "Forward folds are pseudo-out-of-sample inside historical data, NOT untouched final audit"]}
 out=Path("forex_walkforward_v1");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
