"""Side-correct M1 Forex bot comparison using actual Dukascopy BID/ASK M1 OHLC.
Three models: bounded grid, one-minute prior-candle momentum scalper, hybrid.
No lookahead: signal before bar open. Conservative one-minute mark-to-market and
margin closeout. Fractional-size RESEARCH and executable 1000-unit size comparison.
No commission/swap/latency; OHLC candle-level liquidation is approximate.
"""
import argparse,glob,json
from pathlib import Path
import numpy as np,pandas as pd
START=50.;MAX_LEV=10.;MIN_LOT=1000
MODES=("grid","scalper","hybrid")

def read_files(path):
 files=glob.glob(str(Path(path)/"**"/"*.csv"),recursive=True)
 if not files:raise RuntimeError(f"No CSV under {path}")
 frames=[]
 for f in files:
  if Path(f).stat().st_size==0:continue
  try:d=pd.read_csv(f)
  except pd.errors.EmptyDataError:continue
  if not set(["timestamp","open","high","low","close"]).issubset(d.columns):continue
  d["time"]=pd.to_datetime(d.timestamp,unit="ms",utc=True)
  frames.append(d.set_index("time")[["open","high","low","close"]])
 if not frames:raise RuntimeError("Missing Dukascopy CSV columns")
 out=pd.concat(frames).sort_index()
 if out.index.duplicated().any():raise RuntimeError("Duplicate timestamps in "+path)
 return out.astype(float)

def load(bids,asks):
 b=read_files(bids);a=read_files(asks)
 common=b.index.intersection(a.index)
 if len(common)<1500:raise RuntimeError("Too few matched bid/ask M1 quotes")
 if len(common)<.95*min(len(b),len(a)):raise RuntimeError("Excessive bid/ask mismatches")
 b=b.loc[common];a=a.loc[common]
 if (a.open<=b.open).mean()>.01:raise RuntimeError("Invalid or inverted spread detected")
 if (a.close<=b.close).mean()>.01:raise RuntimeError("Invalid close spread detected")
 return b,a

def simulate(b,a,mode,initial=START,lot_step=0,leverage=MAX_LEV):
 cash=initial;positions=[];peak=initial;dd=0.;realized=0.;open_count=0;close_count=0
 wins=0;stopout=False;skipped=0;curve=[];daily={}
 # pos: signed BASE currency units, true opening ask for buy, bid for sell
 def equity(i):
  return cash+sum(u*((float(b.close.iat[i]) if u>0 else float(a.close.iat[i]))-ep)
                  for u,ep in positions)
 def margin(i):
  mid=(float(b.close.iat[i])+float(a.close.iat[i]))/2
  return sum(abs(u)*mid/leverage for u,_ in positions)
 def close(pos,i):
  nonlocal cash,realized,close_count,wins
  u,entry=pos;price=float(b.open.iat[i]) if u>0 else float(a.open.iat[i])
  p=u*(price-entry);cash+=p;realized+=p;close_count+=1;wins+=p>0
 def enter(side,notional,i):
  nonlocal open_count,skipped
  px=float(a.open.iat[i]) if side>0 else float(b.open.iat[i])
  qty=notional/px
  if lot_step:
   qty=int(qty//lot_step)*lot_step
  if qty<max(1e-9,lot_step):
   skipped+=1;return
  positions.append((side*qty,px));open_count+=1
 for i in range(35,len(b)-1):
  mid=(float(a.open.iat[i])+float(b.open.iat[i]))/2
  # Preliminary closeout using true quote at bar open.
  pre=cash+sum(u*((float(b.open.iat[i]) if u>0 else float(a.open.iat[i]))-ep) for u,ep in positions)
  mar=sum(abs(u)*mid/leverage for u,_ in positions)
  if pre<=.5*mar or pre<=initial*.2:
   cash=pre;positions=[];stopout=True;break
  prev=((b.close.iloc[i-1]+a.close.iloc[i-1])/2)
  older=((b.close.iloc[i-2]+a.close.iloc[i-2])/2)
  sig=np.sign(prev-older)
  last20=((b.close.iloc[i-20:i]+a.close.iloc[i-20:i])/2)
  center=float(last20.mean())
  vol=float(last20.pct_change().std())
  quiet=vol<.00012
  use_grid=mode=="grid" or (mode=="hybrid" and quiet)
  if not use_grid:
   for pos in positions:close(pos,i)
   positions=[]
  else:
   keep=[]
   for pos in positions:
    u,ep=pos
    out=float(b.open.iat[i]) if u>0 else float(a.open.iat[i])
    if u*(out-ep)>=abs(u)*max(.0006*mid,.00032):
     close(pos,i)
    else:keep.append(pos)
   positions=keep
  # no overlapping scalp orders; grid at most 4 individual positions
  if use_grid:
   spacing=max(mid*.00035,.00048)
   side=(1 if mid<center-spacing else (-1 if mid>center+spacing else 0))
   if side and len(positions)<4:
    free=max(0.,pre*leverage-sum(abs(u)*mid for u,_ in positions))
    enter(side,min(max(pre,0.)*2.,free),i)
  elif sig:
   free=max(0.,max(cash,0.)*leverage)
   enter(sig,min(max(cash,0.)*5.,free),i)
  eq=equity(i)
  margin_used=margin(i)
  if eq<=.5*margin_used or eq<=initial*.2:
   cash=eq;positions=[];stopout=True;break
  peak=max(peak,eq);dd=min(dd,eq/peak-1)
  date=b.index[i].strftime("%Y-%m-%d")
  daily[date]={"equity_usd":round(eq,4),"open_positions":len(positions)}
  if i%60==0:curve.append({"timestamp":b.index[i].isoformat(),"equity":round(eq,4)})
 # final open positions marked using actual closing bid/ask
 ending=cash if stopout else equity(len(b)-1)
 return {"roi_pct":round((ending/initial-1)*100,3),"ending_usd":round(ending,3),
 "realized_usd":round(realized,3),"unrealized_usd":round(ending-cash,3) if not stopout else 0.,
 "max_drawdown_pct":round(dd*100,3),"opened":open_count,"closed":close_count,
 "wins_closed":wins,"open_positions":len(positions),"skipped_min_lot":skipped,
 "closeout":stopout,"daily":daily,"curve":curve}

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--bid-dir",required=True);ap.add_argument("--ask-dir",required=True)
 ap.add_argument("--output",default="forex_dukascopy_compare_report.json")
 args=ap.parse_args();b,a=load(args.bid_dir,args.ask_dir)
 configurations={"fractional_50usd_10x":(50.,0,10.),
                 "micro_lot_50usd_10x":(50.,MIN_LOT,10.),
                 "micro_lot_250usd_10x":(250.,MIN_LOT,10.)}
 report={"status":"REAL_DUKASCOPY_BID_ASK_M1_WITH_SIMULATED_FILLS",
 "minutes":len(b),"start":str(b.index[0]),"end":str(b.index[-1]),
 "median_spread_pips":round(float(np.median((a.open-b.open)/.0001)),3),
 "spread_p95_pips":round(float(np.quantile((a.open-b.open)/.0001,.95)),3),
 "scenarios":{},"warnings":["No broker commissions/slippage/overnight financing",
 "Candle-level rather than tick intrabar liquidations",
 "Limited timeframe does not establish repeatable profits or 10,000% ROI",
 "Not valid if provider files were misidentified / instrument not EURUSD",
 "Exposures and fills are hypothetical; broker rules may differ"]}
 for key,(initial,lot,lev) in configurations.items():
  report["scenarios"][key]={}
  for mode in MODES:
   r=simulate(b,a,mode,initial,lot,lev)
   report["scenarios"][key][mode]={k:v for k,v in r.items() if k not in ("curve","daily")}
   if key=="fractional_50usd_10x":report["scenarios"][key][mode]["daily"]=r["daily"]
 out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(report,indent=2))
 print("SUMMARY",json.dumps({**report,"scenarios":{k:{m:{p:v for p,v in x.items() if p!="daily"} for m,x in v.items()} for k,v in report["scenarios"].items()}},indent=2))
if __name__=="__main__":main()
