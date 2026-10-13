"""Exploratory FX multi-asset historical simulation. Research only; NOT broker-executable.
Yahoo mid-like 5m OHLC; fills approximate with explicit synthetic spreads and slippage.
No FX contract-size, margin-call or broker liquidation validation.
"""
import argparse, json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

TICKERS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X"}
PIP={"EURUSD":0.0001,"GBPUSD":0.0001,"USDJPY":0.01}
SPREAD_PIPS={"EURUSD":1.2,"GBPUSD":1.8,"USDJPY":1.5}
def get_data(out,period="30d"):
    result={}
    for sym,ticker in TICKERS.items():
        data=yf.download(ticker,interval="5m",period=period,progress=False,auto_adjust=False,threads=False)
        if data.empty or len(data)<500: raise ValueError(f"No reliable rows for {sym}")
        if isinstance(data.columns,pd.MultiIndex): data.columns=data.columns.get_level_values(0)
        data=data[["Open","High","Low","Close"]].dropna().copy()
        if not data.index.is_unique: raise ValueError("Duplicate timestamps "+sym)
        if not (data["Low"]<=data[["Open","Close","High"]].min(axis=1)).all(): raise ValueError("Invalid OHLC")
        if not (data["High"]>=data[["Open","Close","Low"]].max(axis=1)).all(): raise ValueError("Invalid OHLC")
        data.index=pd.to_datetime(data.index,utc=True)
        data=data.sort_index()
        result[sym]=data
        data.to_csv(out/(sym+"_5m.csv"))
    return result

def signals(close):
    fast=close.rolling(12,min_periods=12).mean()
    slow=close.rolling(48,min_periods=48).mean()
    std=close.rolling(24,min_periods=24).std()
    mid=close.rolling(24,min_periods=24).mean()
    prior_high=close.shift(1).rolling(24,min_periods=24).max()
    prior_low=close.shift(1).rolling(24,min_periods=24).min()
    momentum=(fast>slow)&(close>fast)&(fast.shift(1)<=slow.shift(1))
    brk=(close>prior_high)
    rev=(close<mid-1.8*std)&(fast>=slow*0.998)
    return {"trend":momentum,"breakout":brk,"reversion":rev}

def run(datasets,starting=50,leverage=500):
    # Explicit USD quote conversion for USDJPY; EURUSD/GBPUSD already USD quoted.
    events=[]
    for sym,data in datasets.items():
        sig=signals(data["Close"])
        for strategy,series in sig.items():
            chosen=series.fillna(False)
            indices=[i for i in range(60,len(data)-4) if bool(chosen.iloc[i])]
            # Breakout can persist across bars: only allow first edge.
            if strategy=="breakout": indices=[i for i in indices if i==0 or not bool(chosen.iloc[i-1])]
            for i in indices:
                start=i+1; end=i+4
                events.append((data.index[start],0,sym,strategy,start,end))
    events.sort()
    cash=float(starting);positions=[]; closed=[];max_open=0;peak=starting;max_dd=0;rejected=0
    times=sorted(set(t for d in datasets.values() for t in d.index))
    candidates={}
    for e in events:candidates.setdefault(e[0],[]).append(e)
    for t in times:
        remaining=[]
        for p in positions:
            d=datasets[p["symbol"]]
            if p["end_time"]<=t and t in d.index:
                price=float(d.loc[t,"Open"]); pip=PIP[p["symbol"]]
                # direction long, fills penalized by spread+slippage on both sides
                gross=(price-p["entry"])/p["entry"]*p["notional"]
                if p["symbol"]=="USDJPY": gross=(price-p["entry"])/price*p["notional"]
                # no extra spread on exit? apply half spread + slippage separately
                cost=p["notional"]*((SPREAD_PIPS[p["symbol"]]*pip/price)+0.00010)
                pnl=gross-cost
                cash+=pnl
                closed.append({"symbol":p["symbol"],"strategy":p["strategy"],"open":str(p["opened"]),"close":str(t),"pnl_usd":round(pnl,6)})
            else:remaining.append(p)
        positions=remaining
        for e in candidates.get(t,[]):
            _,_,sym,strategy,start,end=e
            if cash<=0:rejected+=1;continue
            d=datasets[sym];price=float(d.iloc[start]["Open"])
            # Do not use maximal leverage as position leverage: fixed 0.5x initial equity per entry
            notional=max(0,min(starting*.5,cash*.5))
            used_margin=sum(p["notional"]/leverage for p in positions)
            if notional<1 or used_margin+notional/leverage>cash*.4:
                rejected+=1;continue
            # Entry half spread + slippage; charge at entry.
            entry_cost=notional*((SPREAD_PIPS[sym]*PIP[sym]/(2*price))+0.00005)
            cash-=entry_cost
            positions.append({"symbol":sym,"strategy":strategy,"opened":t,"end_time":d.index[end],"entry":price,"notional":notional})
        max_open=max(max_open,len(positions))
        peak=max(peak,cash);max_dd=max(max_dd,(peak-cash)/peak if peak else 0)
    # Existing entries may not be closed at dataset end; report them separately.
    pnl=sum(x["pnl_usd"] for x in closed)
    wins=[x for x in closed if x["pnl_usd"]>0]
    losses=[x for x in closed if x["pnl_usd"]<0]
    return {"source":"Yahoo Finance 5m FX historical bars; synthetic costs", "initial_usd":starting,"cash_usd":round(cash,4),"closed_trades":len(closed),"open_at_end":len(positions),"max_concurrent":max_open,"max_closed_cash_drawdown_pct":round(max_dd*100,3),"win_rate_pct":round(len(wins)/len(closed)*100,3) if closed else 0,"profit_factor":round(sum(x["pnl_usd"] for x in wins)/abs(sum(x["pnl_usd"] for x in losses)),3) if losses else None,"rejected_entries":rejected,"assumed_leverage_ceiling":leverage,"limitations":["No broker-grade bid/ask","No real lot minimum","No true intrabar liquidation","No borrowing/swap","No walk-forward validation","Not the prior v0.4 portfolio engine"],"trades":closed}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",default="forex_report");a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    sets=get_data(out)
    report={"assets":{k:{"rows":len(d),"start":str(d.index.min()),"end":str(d.index.max())} for k,d in sets.items()},"runs":[run(sets,s) for s in [10,25,50]]}
    for r in report["runs"]: r.pop("trades")
    (out/"summary.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
