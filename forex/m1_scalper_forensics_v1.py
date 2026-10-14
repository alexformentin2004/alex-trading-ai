"""ALEX FOREX M1 scalp forensic audit: 1/2/3/5-min holds, same quote history.
No live trading. Yahoo midpoint and explicitly synthetic friction (not bid/ask).
All positions opened at next bar's open on PRIOR completed candle's direction.
P&L per unit is exact for XXXUSD with USD account; fractional units are
hypothetical. No in-sample optimisation; variants are diagnostics only.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIR="EURUSD"; CAPITAL=50.;LEV=10.;PIP=.0001
SPREAD=1.3; SLIP_EACH_SIDE=.3
HOLDS=(1,2,3,5)
def fetch():
 df=yf.download("EURUSD=X",period="7d",interval="1m",auto_adjust=False,progress=False,threads=False)
 if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
 df=df[["Open","High","Low","Close"]].dropna().astype(float)
 df.index=pd.to_datetime(df.index,utc=True)
 if len(df)<1000:raise RuntimeError("Too few candles")
 return df

def audit(df,hold=1,mode="momentum",spread=SPREAD,slip=SLIP_EACH_SIDE,
          min_base_units=0):
 """No overlapping positions, next-open execution. Spread on one roundtrip
 plus slippage each side. Equity compounding, cap leverage 10, no margin call
 possible within this OHLC duration model; separate caveat in report.
 """
 equity=CAPITAL;peak=CAPITAL;dd=0.;rows=[];skipped=0
 i=2
 while i+hold<len(df):
  prev=float(df.Close.iat[i-1]);older=float(df.Close.iat[i-2])
  direction=np.sign(prev-older)
  if mode=="contrarian":direction=-direction
  if direction==0:i+=hold;continue
  entry=float(df.Open.iat[i]);exitpx=float(df.Open.iat[i+hold])
  # EURUSD account in USD, exposure in USD, exact base units at price.
  base_units=equity*LEV/entry
  if min_base_units and base_units<min_base_units:
   skipped+=1;i+=hold;continue
  gross_pips=float(direction*(exitpx-entry)/PIP)
  roundtrip_cost_pips=spread+2*slip
  net_pips=gross_pips-roundtrip_cost_pips
  gross=base_units*direction*(exitpx-entry)
  friction=base_units*roundtrip_cost_pips*PIP
  equity=max(0.,equity+gross-friction)
  peak=max(peak,equity);dd=min(dd,equity/peak-1)
  highs=df.High.iloc[i:i+hold].to_numpy();lows=df.Low.iloc[i:i+hold].to_numpy()
  favorable=(max(highs)-entry if direction>0 else entry-min(lows))/PIP
  adverse=(min(lows)-entry if direction>0 else entry-max(highs))/PIP
  rows.append({"time":df.index[i].isoformat(),"side":"long" if direction>0 else "short",
  "gross_pips":gross_pips,"net_pips":net_pips,
  "mfe_pips":float(favorable),"mae_pips":float(adverse),
  "fee_usd":float(friction),"gross_usd":float(gross),"equity_usd":float(equity)})
  i+=hold
  if equity<=CAPITAL*.2:break
 return rows,{"end_usd":round(equity,3),"roi_pct":round((equity/CAPITAL-1)*100,3),
  "max_dd_pct":round(dd*100,3),"orders":len(rows),
  "skipped_min_units":skipped,
  "gross_total_usd":round(sum(x["gross_usd"] for x in rows),3),
  "costs_total_usd":round(sum(x["fee_usd"] for x in rows),3),
  "avg_gross_pips":round(float(np.mean([x["gross_pips"] for x in rows])),4) if rows else None,
  "avg_net_pips":round(float(np.mean([x["net_pips"] for x in rows])),4) if rows else None,
  "positive_gross_pct":round(100*sum(x["gross_pips"]>0 for x in rows)/len(rows),2) if rows else None,
  "positive_net_pct":round(100*sum(x["net_pips"]>0 for x in rows)/len(rows),2) if rows else None,
  "avg_mfe_pips":round(float(np.mean([x["mfe_pips"] for x in rows])),4) if rows else None,
  "avg_mae_pips":round(float(np.mean([x["mae_pips"] for x in rows])),4) if rows else None}

def main():
 df=fetch();variants={};primary=None
 for hold in HOLDS:
  for mode in ("momentum","contrarian"):
   rows,summary=audit(df,hold,mode)
   variants[f"{mode}_{hold}m"]=summary
   if hold==1 and mode=="momentum":primary=rows
 # Emulate 1000-unit micro-lot broker minimum for EURUSD.
 _,feasibility=audit(df,1,"momentum",min_base_units=1000)
 byday={}
 for r in primary:
  day=r["time"][:10]
  x=byday.setdefault(day,{"trades":0,"gross_pips":0.,"net_pips":0.,
                            "fees_usd":0.,"final_equity":None})
  x["trades"]+=1;x["gross_pips"]+=r["gross_pips"]
  x["net_pips"]+=r["net_pips"];x["fees_usd"]+=r["fee_usd"]
  x["final_equity"]=r["equity_usd"]
 for x in byday.values():
  for key in ("gross_pips","net_pips","fees_usd","final_equity"):
   x[key]=round(x[key],3)
 sides={}
 for side in ("long","short"):
  a=[r for r in primary if r["side"]==side]
  sides[side]={"n":len(a),"avg_gross_pips":round(float(np.mean([r["gross_pips"] for r in a])),4) if a else None,
    "avg_net_pips":round(float(np.mean([r["net_pips"] for r in a])),4) if a else None}
 report={"status":"RESEARCH_NOT_LIVE","pair":PAIR,"start":str(df.index[0]),
 "end":str(df.index[-1]),"bars":len(df),"initial_usd":CAPITAL,"leverage":LEV,
 "roundtrip_spread_pips":SPREAD,"slippage_each_side_pips":SLIP_EACH_SIDE,
 "variants":variants,"primary_daily":byday,"primary_sides":sides,
 "micro_lot_1000_units_feasibility":feasibility,
 "limitations":["Yahoo M1 mid-only, not executable bid/ask","No broker stopouts intrabar",
 "Does not incorporate overnight financing or separate broker commission",
 "All variants same known historical period; not a held-out proof",
 "No market order latency, quote age or variable spreads",
 "Fractional units unless micro-lot feasibility check is applied"]}
 out=Path("forex_m1_scalper_audit");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(report,indent=2))
 (out/"primary_trades.csv").write_text(pd.DataFrame(primary).to_csv(index=False))
 print("SUMMARY",json.dumps({k:v for k,v in report.items() if k not in ("primary_daily",)},indent=2))
 print("DAYS",json.dumps(byday,indent=2))
if __name__=="__main__":main()
