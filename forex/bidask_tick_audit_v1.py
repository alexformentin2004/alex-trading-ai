"""Bid/ask historical Forex audit harness. Requires REAL externally provided tick CSV.

Supports HistData ticks: 'YYYYMMDD HHMMSSmmm,bid,ask,volume' where timestamps
are FIXED UTC-05:00 (EST without DST); converts to UTC. All orders use
actual opposing quote side: buy ASK, sell BID, mark open long at BID/short
at ASK. No invented spread. This is research simulation, not broker fills.
"""
import argparse,csv,json,math
from pathlib import Path
from datetime import datetime,timezone,timedelta
import numpy as np

EST=timezone(timedelta(hours=-5))
MAX_GAP=300
def load_ticks(path,limit=5_000_000):
 ticks=[];bad=0;out_of_order=0;prev=None
 with open(path,newline="") as f:
  for i,row in enumerate(csv.reader(f)):
   if i>=limit:raise ValueError("CSV too long; split months before running")
   if not row or len(row)<3:continue
   raw=row[0].strip()
   try:
    t=datetime.strptime(raw,"%Y%m%d %H%M%S%f").replace(tzinfo=EST).astimezone(timezone.utc)
    bid=float(row[1]);ask=float(row[2])
    if not (math.isfinite(bid) and math.isfinite(ask) and 0<bid<ask):raise ValueError("bid/ask invalid")
   except (ValueError,OverflowError):
    bad+=1;continue
   if prev is not None and t<prev:out_of_order+=1
   ticks.append((t,bid,ask))
   prev=t
 if not ticks:raise ValueError("No valid quote ticks")
 if out_of_order:raise ValueError("Out-of-order quotes: "+str(out_of_order))
 if bad/max(1,i+1)>0.01:raise ValueError("Too many invalid quotes")
 return ticks,{"ticks":len(ticks),"bad_rows":bad,
                "start_utc":ticks[0][0].isoformat(),"end_utc":ticks[-1][0].isoformat(),
                "median_spread_pips":None}
def replay(ticks,pair="EURUSD",leverage=10.,initial=50.,units_step=1000,margin_closeout=.5):
 """Fixed causal schedule, signal from preceding tick prices before entry.
 Hold ~5 min. This is plumbing verification, not a strategy discovery.
 Retail micro-lot 1000 base units is enforced: can have ZERO trades.
 Currency conversion is only exact when account USD and pair XXXUSD.
 """
 if not pair.endswith("USD"):raise ValueError("Only XXXUSD pairs supported for exact USD account PnL.")
 pip=.0001
 equity=initial;peak=initial;dd=0.;trades=0;wins=0;liq=0;skip=0
 # 30 ticks lookback, disjoint 30-tick forward holds (not 30-minute bars).
 for i in range(30,len(ticks)-30,30):
  old=ticks[i-30];now=ticks[i]
  if (now[0]-old[0]).total_seconds()>MAX_GAP:continue
  direction=1 if (old[1]+old[2])<(now[1]+now[2]) else -1
  max_units=equity*leverage/now[2]
  units=int(max_units//units_step)*units_step
  if units<=0:
   skip+=1;continue
  entry=now[2] if direction==1 else now[1]
  margin=units*entry/leverage
  mark=equity
  exitpx=None;reason="window"
  for j in range(i+1,min(i+31,len(ticks))):
   t,bid,ask=ticks[j]
   px=bid if direction==1 else ask
   if (t-now[0]).total_seconds()>MAX_GAP:break
   live=mark+units*direction*(px-entry)
   # liquidation at or below 50% used initial margin
   if live<=margin*margin_closeout:
    exitpx=px;reason="closeout";liq+=1;break
   exitpx=px
  if exitpx is None:continue
  pl=units*direction*(exitpx-entry)
  equity=max(0.,equity+pl)
  peak=max(peak,equity);dd=min(dd,equity/peak-1)
  wins+=pl>0;trades+=1
  if equity<=initial*.2:break
 return {"initial_account_usd":initial,"end_usd":round(equity,4),
         "roi_pct":round((equity/initial-1)*100,3),"max_dd_pct":round(dd*100,3),
         "trades":trades,"winning_trades":wins,"closeouts":liq,
         "orders_skipped_min_lot":skip,"leverage":leverage,"units_step":units_step,
         "hit_1000pct":bool(equity>=11*initial)}
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--input",required=True)
 parser.add_argument("--pair",default="EURUSD")
 parser.add_argument("--leverage",type=float,default=10.)
 parser.add_argument("--capital-usd",type=float,default=50.)
 parser.add_argument("--units-step",type=int,default=1000)
 parser.add_argument("--output",default="forex_bidask_report.json")
 args=parser.parse_args()
 if not(1<=args.leverage<=30):raise ValueError("Leverage 1..30 only; actual permissions vary")
 ticks,meta=load_ticks(args.input)
 pip=.01 if args.pair.endswith("JPY") else .0001
 spreads=np.array([(a-b)/pip for _,b,a in ticks])
 meta["median_spread_pips"]=round(float(np.median(spreads)),3)
 meta["spread_95p_pips"]=round(float(np.percentile(spreads,95)),3)
 r=replay(ticks,pair=args.pair,leverage=args.leverage,initial=args.capital_usd,units_step=args.units_step)
 report={"source":"USER_SUPPLIED_HISTDATA_TICK_CSV","execution_model":"Bid/ask quotes, no market impact or external fees",
         "pair":args.pair,"quotes":meta,"results":r,"promotion_allowed":False,
         "limitations":["Fixed EST timestamps per HistData file spec, no DST","Live spread still provider-specific",
          "Tick-to-tick trading is an engineering smoke test NOT validated alpha",
          "Zero broker commissions, no slippage, swaps or actual margin-call rules",
          "Cannot estimate probability of ruin from one short tick file",
          "Only USD-quoted pairs supported for exact account USD arithmetic"]}
 Path(args.output).write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
