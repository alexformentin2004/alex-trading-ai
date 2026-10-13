"""Aggressive 90-day Forex research with broker-feasibility and ruin gates.
Not investment advice. Synthetic close-to-next-close execution using daily FX
Yahoo indicative prices. Results are NOT executable broker performance.
Strategy selection uses only preceding data; historical folds are not pristine.
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
LOOKBACKS=(3,10,20)
DIRECTIONS=("trend","fade")
LEVERAGES=(1.,3.,5.,10.,20.,30.)
WINDOW=63 # approximately three months of FX trading days
TRAIN=252
TEST=63
INITIAL_CAPITAL=50.0 # risk-capital model, no deposited money
TARGET=11.0 # 11x terminal wealth => +1000% ROI
RUIN=0.20 # 80% loss from initial capital or complete liquidation

def load():
 d={}
 for pair,(ticker,_) in PAIRS.items():
  raw=yf.download(ticker,period="730d",interval="1d",auto_adjust=False,progress=False,threads=False)
  if isinstance(raw.columns,pd.MultiIndex):raw.columns=raw.columns.get_level_values(0)
  s=raw["Close"].dropna().astype(float)
  s.index=pd.to_datetime(s.index,utc=True).normalize()
  d[pair]=s[~s.index.duplicated(keep="last")]
 common=sorted(set.intersection(*(set(x.index) for x in d.values())))
 days=pd.DatetimeIndex(common)
 if len(days)<500:raise RuntimeError("Not enough shared daily observations")
 closes=pd.DataFrame({p:s.reindex(days) for p,s in d.items()},index=days)
 if closes.isna().any().any():raise RuntimeError("Missing price")
 return closes

def build(closes):
 rets=closes.pct_change().shift(-1)
 result={}
 for direction in DIRECTIONS:
  for lookback in LOOKBACKS:
   momentum=closes.pct_change(lookback)
   score=momentum.abs().shift(0)
   best=score.idxmax(axis=1)
   side=momentum.lookup if False else None
   gross=np.zeros(len(closes)-1)
   costs=np.zeros(len(closes)-1)
   selection=[]
   for i in range(len(gross)):
    p=best.iat[i]
    signal=np.sign(momentum[p].iat[i])
    if direction=="fade":signal=-signal
    if not np.isfinite(signal) or signal==0:continue
    gross[i]=float(signal*rets[p].iat[i])
    pip=.01 if p.endswith("JPY") else .0001
    # Round-trip spread plus 1 bp slippage/commissions reserve.
    costs[i]=float(PAIRS[p][1]*pip/closes[p].iat[i]+.0001)
    selection.append(p)
   result[f"{direction}_{lookback}"]=(gross,costs)
 return result

def simulate(gross,costs,leverage,start,end,stress=1.0):
 equity=INITIAL_CAPITAL
 peak=equity
 dd=0.
 ruin=False
 values=[]
 for i in range(start,end):
  if ruin:
   values.append(0.)
   continue
  # Margin at constant leverage; net return includes return * cost.
  r=leverage*(gross[i]-stress*costs[i])
  # Insolvency/liquidation approximation, no debt/no margin call model.
  if r<=-1.0:
   equity=0.
   ruin=True
  else:
   equity*=1+r
  peak=max(peak,equity)
  dd=min(dd,equity/peak-1.)
  if equity<=INITIAL_CAPITAL*RUIN:
   ruin=True
  values.append(equity)
 return {"roi_pct":round((equity/INITIAL_CAPITAL-1)*100,3),
         "max_dd_pct":round(dd*100,3),"ruined":ruin,
         "hit_1000pct":equity>=INITIAL_CAPITAL*TARGET,
         "end_eur":round(equity,2)}

def main():
 closes=load()
 arrays=build(closes)
 dates=closes.index[:-1]
 # Rolling expanding train window and 63-day evaluations. Purge one entry day.
 folds=[]
 for start in range(TRAIN,len(dates)-TEST+1,TEST):
  # select strategy and leverage jointly on past only, with strong penalties.
  ranking=[]
  for name,(gross,costs) in arrays.items():
   for leverage in LEVERAGES:
    train=simulate(gross,costs,leverage,20,start-1)
    score=train["roi_pct"]-0.75*abs(train["max_dd_pct"])-1000*int(train["ruined"])
    ranking.append((score,name,leverage))
  ranking.sort(reverse=True)
  _,selected,lev=ranking[0]
  g,c=arrays[selected]
  test=simulate(g,c,lev,start,start+TEST)
  stress=simulate(g,c,lev,start,start+TEST,stress=2.)
  folds.append({"start":str(dates[start].date()),"end":str(dates[start+TEST-1].date()),
    "selected":selected,"leverage":lev,"test":test,"double_costs":stress})
 # Report all strategies/leverage for the most recent 63-day period, explicitly
 # as an exploratory already-examined window, never selecting on it.
 latest=[]
 start=len(dates)-TEST
 for name,(gross,costs) in arrays.items():
  for lev in LEVERAGES:
   x=simulate(gross,costs,lev,start,len(dates))
   latest.append({"strategy":name,"leverage":lev,**x})
 latest.sort(key=lambda x:x["roi_pct"],reverse=True)
 # Monte Carlo: bootstrap daily NET RETURNS, not a claim of independence.
 # Fixed seed, 2000 simulations, display ruin and huge ROI frequency.
 mc={}
 for name in arrays:
  g,c=arrays[name]
  net=(g-c)[20:]
  for lev in LEVERAGES:
   rng=np.random.default_rng(20261013)
   draws=rng.choice(net,size=(2000,WINDOW),replace=True)
   factor=1+lev*draws
   eq=np.cumprod(np.maximum(0.,factor),axis=1)
   min_eq=np.minimum.accumulate(eq,axis=1)
   ruined=(min_eq<=RUIN).any(axis=1) | (factor<=0).any(axis=1)
   hits=(eq[:,-1]>=TARGET)&(~ruined)
   mc[f"{name}_{int(lev)}x"]={"bootstrap_ruin_probability_pct":round(float(ruined.mean()*100),2),
       "bootstrap_1000pct_survival_probability_pct":round(float(hits.mean()*100),2),
       "bootstrap_median_roi_pct":round(float((np.median(eq[:,-1])-1)*100),2)}
 report={"status":"RESEARCH_ONLY_NO_LIVE","goal_roi_pct":1000,"horizon_trading_days":WINDOW,
 "target_wealth_multiple":11,"capital_eur":INITIAL_CAPITAL,"leverages":LEVERAGES,
 "pairs":list(PAIRS),"date_range":[str(dates[0].date()),str(dates[-1].date())],
 "folds":folds,"fold_count":len(folds),
 "folds_hit_target":sum(f["test"]["hit_1000pct"] for f in folds),
 "folds_ruined":sum(f["test"]["ruined"] for f in folds),
 "latest_exploratory_top10":latest[:10],
 "latest_exploratory_any_hit_target":sum(x["hit_1000pct"] for x in latest),
 "bootstrap":mc,
 "calibration":{"costs":"Indicative spread per pair + 1 bp one-turn friction, multiplied by exposure.",
 "compounding":"Constant notional leverage relative to current equity, rebalance daily.",
 "ruin":"Equity <= 20% of start, or one-day loss >=100%; stops future trades.",
 "note":"At risk capital 50 EUR, broker 0.01 standard lot may exceed allowable notional. This test does not certify broker feasibility."},
 "limitations":["Yahoo daily indicative closes, not broker bid/ask or executions.",
 "Historical periods already seen in prior work: walk-forward is not a clean future holdout.",
 "No funding, swap/rollover, changing spread, overnight margin calls or stop-out dynamics.",
 "Bootstrap iid day assumption breaks regime clustering and underestimates tail risks.",
 "30x may exceed allowed retail FX leverage depending on pair and jurisdiction.",
 "No strategy is promoted based on spectacular in-sample compounded returns."]}
 target=Path("forex_aggressive_v1");target.mkdir(exist_ok=True)
 (target/"report.json").write_text(json.dumps(report,indent=2))
 print("SUMMARY",json.dumps({k:v for k,v in report.items() if k in
 ["status","goal_roi_pct","fold_count","folds_hit_target","folds_ruined",
 "latest_exploratory_top10","latest_exploratory_any_hit_target"]},indent=2))
 print("FOLDS",json.dumps(folds,indent=2))
if __name__=="__main__": main()
