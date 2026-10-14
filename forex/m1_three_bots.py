"""Three-strategy same-minute FX comparison. RESEARCH, NO LIVE EXECUTION.
Yahoo M1 mids (limited days), synthetic bid/ask; EURUSD USD account approximation.
A: bounded mean-reversion grid, mark-to-market all open trades.
B: at each new minute close prior position, open next on past candle direction.
C: grid in quiet periods, one-minute momentum elsewhere.
All start with 50 USD, 10x max total notional, 0.01-lot *not* assumed.
Fractional units allowed in RESEARCH: real broker with min 1000 units
would reject many €50-sized orders. No claims of executable results.
"""
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
START=50.;LEV=10.;SPREAD_PIPS=1.3;SLIPPAGE_PIPS=.3;PIP=.0001
MODELS=("grid","m1_scalper","hybrid")
def get():
 d=yf.download("EURUSD=X",period="7d",interval="1m",auto_adjust=False,progress=False,threads=False)
 if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
 d=d[["Open","High","Low","Close"]].dropna().astype(float)
 d.index=pd.to_datetime(d.index,utc=True)
 if len(d)<1200:raise RuntimeError("Need >=1200 M1 bars, received "+str(len(d)))
 return d
def evaluate(d,kind):
 capital=START;positions=[];realized=0.;peak=START;maxdd=0.;margin_peak=0.
 liquidated=False;min_equity=START;opened=0;closed=0;win=0;fees=0.;curves=[]
 # Each position: signed units and filled price, marked at executable opposing quote.
 half=(SPREAD_PIPS/2+SLIPPAGE_PIPS)*PIP
 def mark(px):
  return capital+sum(units*((px-half if units>0 else px+half)-entry) for units,entry in positions)
 for i in range(35,len(d)):
  px=float(d.Open.iat[i]);prev=float(d.Close.iat[i-1])
  if not np.isfinite(px):continue
  eq=mark(px);margin=sum(abs(units)*px/LEV for units,_ in positions)
  if eq<=0.5*margin or eq<=START*.20:
   liquidated=True
   capital=max(0.,eq);positions=[]
   break
  # Close when price crosses fixed grid micro profit objective; if strong trend,
  # all positions are still marked and exposed to stopout.
  if kind in ("grid","hybrid"):
   remaining=[]
   for units,entry in positions:
    closepx=px-half if units>0 else px+half
    pnl=units*(closepx-entry)
    if pnl>=abs(units)*max(.0006*px,2*(SPREAD_PIPS+SLIPPAGE_PIPS)*PIP):
     capital+=pnl;realized+=pnl;closed+=1;win+=pnl>0
    else:remaining.append((units,entry))
   positions=remaining
  if kind=="m1_scalper" or (kind=="hybrid" and not positions):
   if positions:
    for units,entry in positions:
     pnl=units*((px-half if units>0 else px+half)-entry)
     capital+=pnl;realized+=pnl;closed+=1;win+=pnl>0
    positions=[]
  rolling=d.Close.iloc[i-31:i].to_numpy()
  if len(rolling)<31:continue
  sig=np.sign(rolling[-1]-rolling[-2])
  vol=np.std(np.diff(rolling)/rolling[:-1])
  quiet=vol<.00012
  can_grid=(kind=="grid" or (kind=="hybrid" and quiet))
  spacing=max(.00035*px,3*(SPREAD_PIPS+SLIPPAGE_PIPS)*PIP)
  if can_grid:
   # Alternate buy and sell around rolling center, cap 4 outstanding trades.
   center=float(rolling[-20:].mean())
   buy=px<center-spacing
   sell=px>center+spacing
   if len(positions)<4 and (buy or sell):
    sign=1 if buy else -1
    open_notional=max(0.,mark(px)*LEV-sum(abs(u)*px for u,_ in positions))
    notional=min(mark(px)*2.0,open_notional)
    units=sign*max(0.,notional/px)
    if units:positions.append((units,px+half if units>0 else px-half));opened+=1
  else:
   if sig:
    free=max(0.,mark(px)*LEV-sum(abs(u)*px for u,_ in positions))
    notional=min(max(0.,mark(px)*LEV*.5),free)
    units=float(sig)*notional/px
    if abs(units)>0:positions.append((units,px+half if units>0 else px-half));opened+=1
  eq=mark(px)
  gross=sum(abs(u)*px for u,_ in positions)
  margin_peak=max(margin_peak,gross/LEV)
  min_equity=min(min_equity,eq)
  peak=max(peak,eq);maxdd=min(maxdd,eq/peak-1)
  if i%20==0:curves.append({"t":str(d.index[i]),"equity":round(eq,4),
                             "realized_equity":round(capital,4),"open":len(positions)})
 # Final mark-to-market, NOT hiding negative floats
 last=float(d.Close.iloc[-1]);equity=capital+sum(u*((last-half if u>0 else last+half)-entry) for u,entry in positions)
 if liquidated:equity=capital
 return {"roi_equity_pct":round((equity/START-1)*100,3),
 "equity_usd":round(equity,3),"realized_only_usd":round(capital,3),
 "unrealized_usd":round(equity-capital,3),"max_drawdown_pct":round(maxdd*100,3),
 "orders_opened":opened,"orders_closed":closed,"closed_wins":int(win),
 "remaining_positions":len(positions),"peak_used_margin_usd":round(margin_peak,3),
 "liquidated_or_ruined":liquidated,"curve":curves}
def main():
 d=get()
 results={k:evaluate(d,k) for k in MODELS}
 report={"status":"SYNTHETIC_SPREAD_RESEARCH","pair":"EURUSD",
         "start":str(d.index[0]),"end":str(d.index[-1]),"minute_bars":len(d),
         "capital_usd":START,"max_gross_leverage":LEV,
         "spread_pips":SPREAD_PIPS,"additional_slippage_each_side_pips":SLIPPAGE_PIPS,
         "strategies":results,
         "limitations":["Yahoo M1 MIDPOINT ONLY, spread/slippage modeled, not authentic bid/ask",
                        "Fractional base units permitted; with broker 1000-unit minimum, many/all entries infeasible",
                        "Margin closeout 50% used margin approximation, no swaps or financing",
                        "Backtest signal logic pre-specified, but already-researched period not untouched",
                        "Margin checked at next M1 open, not every tick, so gap liquidation understated",
                        "7 calendar days data, NOT a 3-4 month ROI test",
                        "No live orders or verified high-ROI strategy"]}
 out=Path("forex_m1_three_bots");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(report,indent=2))
 print("SUMMARY",json.dumps({**{k:v for k,v in report.items() if k!="strategies"},
 "strategies":{k:{a:b for a,b in v.items() if a!="curve"} for k,v in results.items()}},indent=2))
if __name__=="__main__":main()
