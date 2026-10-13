"""FX v0.5 exploratory strategies: causal signals, ATR exits, session filters.
Research-only. Yahoo candles are NOT broker bid/ask. No broker contract minima or liquidation.
"""
from pathlib import Path
import json
import pandas as pd
import yfinance as yf

TICKERS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X"}
PIPS={"EURUSD":0.0001,"GBPUSD":0.0001,"USDJPY":0.01}
SPREAD={"EURUSD":1.2,"GBPUSD":1.8,"USDJPY":1.5}

def download():
    result={}
    for symbol,ticker in TICKERS.items():
        d=yf.download(ticker,period="30d",interval="5m",auto_adjust=False,threads=False,progress=False)
        if d.empty or len(d)<500: raise RuntimeError("Insufficient data: "+symbol)
        if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
        d=d[["Open","High","Low","Close"]].dropna().sort_index()
        d.index=pd.to_datetime(d.index,utc=True)
        assert d.index.is_unique and (d.High>=d[["Open","Close","Low"]].max(axis=1)).all() and (d.Low<=d[["Open","Close","High"]].min(axis=1)).all()
        result[symbol]=d
    return result

def candidate_data(d, strategy):
    close=d.Close
    prev=close.shift(1)
    ema_fast=close.ewm(span=18,adjust=False).mean()
    ema_slow=close.ewm(span=72,adjust=False).mean()
    tr=pd.concat([(d.High-d.Low),(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False).mean().shift(1)
    high=d.High.shift(1).rolling(36,min_periods=36).max()
    low=d.Low.shift(1).rolling(36,min_periods=36).min()
    # Signals from completed candle, fills no earlier than next candle open
    if strategy=="breakout":
        direction=pd.Series(0,index=d.index)
        direction[(close>high)&(ema_fast>ema_slow)&(prev<=high.shift(1))]=1
        direction[(close<low)&(ema_fast<ema_slow)&(prev>=low.shift(1))]=-1
    elif strategy=="pullback":
        direction=pd.Series(0,index=d.index)
        direction[(ema_fast>ema_slow)&(prev<=ema_fast.shift(1))&(close>ema_fast)&(close>prev)]=1
        direction[(ema_fast<ema_slow)&(prev>=ema_fast.shift(1))&(close<ema_fast)&(close<prev)]=-1
    else: raise ValueError(strategy)
    # ATR too small relative to assumed full spread means no practical scalp edge
    return direction,atr

def backtest(datasets, mode="filtered", initial=50, cost_multiplier=1.0):
    strategies=["breakout","pullback"]
    prepared={(sym,st):candidate_data(d,st) for sym,d in datasets.items() for st in strategies}
    candidates={}
    holdout_start=min(d.index.max() for d in datasets.values())-pd.Timedelta(days=10)
    for (sym,st),(signal,atr) in prepared.items():
        d=datasets[sym]
        for i in range(80,len(d)-1):
            t=d.index[i+1]
            if signal.iat[i]==0: continue
            if mode=="filtered":
                if not (7<=t.hour<18 and t.weekday()<5):continue
                if atr.iat[i] < PIPS[sym]*SPREAD[sym]*3:continue
            a=float(atr.iat[i])
            if pd.isna(a) or a<=0:continue
            candidates.setdefault(t,[]).append((sym,st,int(signal.iat[i]),float(d.Open.iat[i+1]),a))
    cash=float(initial); pos=[]; trades=[]; peak=cash; maxdd=0; maxopen=0
    alltimes=sorted(set(t for d in datasets.values() for t in d.index))
    last_entry={}; rejected=0
    for t in alltimes:
        keep=[]
        for p in pos:
            d=datasets[p["symbol"]]
            if t not in d.index:keep.append(p);continue
            bar=d.loc[t]; direction=p["side"];exit_price=None;why=None
            if direction==1:
                if bar.Low<=p["stop"]:exit_price=p["stop"];why="stop"
                elif bar.High>=p["target"]:exit_price=p["target"];why="take"
            else:
                if bar.High>=p["stop"]:exit_price=p["stop"];why="stop"
                elif bar.Low<=p["target"]:exit_price=p["target"];why="take"
            if exit_price is None and t>=p["timeout"]:exit_price=float(bar.Close);why="timeout"
            if exit_price is None:keep.append(p);continue
            # notional in USD; price-based relative movement approximates USD PnL across these 3 pairs
            gross=p["notional"]*direction*(exit_price/p["entry"]-1)
            # costs: round-trip spread plus 1 pip-equivalent slippage estimate
            cost=p["notional"]*((SPREAD[p["symbol"]]*PIPS[p["symbol"]]/p["entry"])+0.00010)*cost_multiplier
            pnl=gross-cost
            cash+=pnl
            trades.append({"symbol":p["symbol"],"strategy":p["strategy"],"split":"holdout" if p["opened"]>=holdout_start else "development","pnl":pnl,"reason":why})
        pos=keep
        for sym,st,side,entry,atr in candidates.get(t,[]):
            if cash<1:rejected+=1;continue
            if mode=="filtered" and (sym,st) in last_entry and (t-last_entry[(sym,st)])<pd.Timedelta(minutes=60):continue
            # Limit repeated directional overlap but not total number of positions.
            if mode=="filtered" and any(p["symbol"]==sym and p["strategy"]==st for p in pos):continue
            # Fixed small exposure: configured leverage ceiling is NOT position leverage.
            notional=min(initial*0.35,cash*0.35)
            if notional<1:rejected+=1;continue
            stop_dist=atr*1.4;target_dist=atr*2.2
            cash_risk=notional*stop_dist/entry
            if cash_risk>cash*.02:rejected+=1;continue
            d=datasets[sym];at=d.index.get_indexer([t])[0]
            timeout=d.index[min(at+12,len(d)-1)]
            pos.append({"symbol":sym,"strategy":st,"opened":t,"side":side,"entry":entry,"stop":entry-side*stop_dist,"target":entry+side*target_dist,"timeout":timeout,"notional":notional})
            last_entry[(sym,st)]=t
        peak=max(peak,cash)
        maxdd=max(maxdd,(peak-cash)/peak if peak else 0)
        maxopen=max(maxopen,len(pos))
    def metrics(xs):
        net=sum(t["pnl"] for t in xs);wins=sum(1 for t in xs if t["pnl"]>0)
        gp=sum(t["pnl"] for t in xs if t["pnl"]>0);gl=-sum(t["pnl"] for t in xs if t["pnl"]<0)
        return {"trades":len(xs),"net_usd":round(net,4),"win_rate_pct":round(100*wins/len(xs),2) if xs else None,"profit_factor":round(gp/gl,3) if gl else None}
    by={}
    for st in strategies:
        by[st]={sp:metrics([x for x in trades if x["strategy"]==st and x["split"]==sp]) for sp in ["development","holdout"]}
    return {"mode":mode,"cost_multiplier":cost_multiplier,"initial_usd":initial,"ending_cash_usd":round(cash,4),"trades":len(trades),"max_open_positions":maxopen,"max_realized_cash_drawdown_pct":round(maxdd*100,2),"rejections":rejected,"holdout_begins_utc":str(holdout_start),"by_strategy":by,"by_split":{sp:metrics([x for x in trades if x["split"]==sp]) for sp in ["development","holdout"]},"limitations":["Exploratory; strategy rules designed before running but based on awareness of previous losing sample","No tick/bid-ask and stops are conservative if SL/TP both hit within same bar","Unrealistic micro-lot execution at $10-$50","No real liquidation or spread dynamics","USDJPY PnL and broker funding approximated","Holdout is chronological but not independent of prior strategy research"]}
if __name__=="__main__":
    out=Path("forex_v05_report");out.mkdir(exist_ok=True)
    data=download()
    results={"datasets":{sym:{"rows":len(d),"start":str(d.index.min()),"end":str(d.index.max())} for sym,d in data.items()},"runs":[backtest(data,mode=m,cost_multiplier=c) for m,c in [("baseline",1.0),("filtered",1.0),("filtered",2.0)]]}
    (out/"comparison.json").write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
