"""FX v0.7: cost-aware H1 trend-breakout on historical 5-minute FX candles.
Research only; simulated spreads, no retail lot-size or real broker margin support.
"""
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

SYMBOLS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X"}
PIP={"EURUSD":.0001,"GBPUSD":.0001,"USDJPY":.01}
SPREAD={"EURUSD":1.2,"GBPUSD":1.8,"USDJPY":1.5}
def get_prices():
    out={}
    for s,ticker in SYMBOLS.items():
        d=yf.download(ticker,interval="5m",period="30d",threads=False,progress=False,auto_adjust=False)
        if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
        d=d[["Open","High","Low","Close"]].dropna()
        d.index=pd.to_datetime(d.index,utc=True)
        if len(d)<500:raise RuntimeError("Insufficient genuine bars "+s)
        assert d.index.is_monotonic_increasing and d.index.is_unique
        out[s]=d
    return out

def signals(d):
    # H1 aggregation; every signal uses completed H1 bar, enter at next 5m bar
    h=d.resample("1h",label="left",closed="left").agg({"Open":"first","High":"max","Low":"min","Close":"last"}).dropna()
    prev=h.Close.shift()
    tr=pd.concat([h.High-h.Low,(h.High-prev).abs(),(h.Low-prev).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14,min_periods=14).mean()
    fast=h.Close.ewm(span=12,adjust=False).mean()
    slow=h.Close.ewm(span=36,adjust=False).mean()
    hi=h.High.shift(1).rolling(12,min_periods=12).max()
    lo=h.Low.shift(1).rolling(12,min_periods=12).min()
    direction=pd.Series(0,index=h.index)
    direction[(h.Close>hi)&(fast>slow)&(slow>slow.shift(3))]=1
    direction[(h.Close<lo)&(fast<slow)&(slow<slow.shift(3))]=-1
    direction[(direction==1)&(h.Close.shift(1)>hi.shift(1))]=0
    direction[(direction==-1)&(h.Close.shift(1)<lo.shift(1))]=0
    rows=[]
    for j in range(48,len(h)-1):
        if not direction.iat[j]:continue
        # H1 closing at h.index[j]+1h, then take first candle on/after close
        ts=h.index[j]+pd.Timedelta(hours=1)
        if not (7<=ts.hour<18 and ts.weekday()<5):continue
        bar_index=d.index.searchsorted(ts)
        if bar_index>=len(d)-1:continue
        rows.append((d.index[bar_index],j,int(direction.iat[j]),float(atr.iat[j]),bar_index))
    return rows

def sim(all_data,spread_scale=1.0,initial=50.0):
    cash=initial;pos=[];trades=[];maxpos=0;peak=initial;dd=0;events={};next_id=1;peak_reserved=0;opened_total=0
    for sym,d in all_data.items():
        for ts,j,side,atr,bar_index in signals(d):
            if not (atr>0):continue
            events.setdefault(ts,[]).append((sym,side,atr,bar_index))
    clock=sorted(set(t for d in all_data.values() for t in d.index))
    for t in clock:
        alive=[]
        for p in pos:
            d=all_data[p["sym"]]
            if t not in d.index:alive.append(p);continue
            b=d.loc[t]
            stop_hit=b.Low<=p["stop"] if p["side"]==1 else b.High>=p["stop"]
            take_hit=b.High>=p["target"] if p["side"]==1 else b.Low<=p["target"]
            timeout=t>=p["expiry"]
            if not (stop_hit or take_hit or timeout):alive.append(p);continue
            # Conservative: if stop and target in same candle, stop wins.
            exit_px=p["stop"] if stop_hit else p["target"] if take_hit else float(b.Close)
            # Returns on USD notional: exact-ish for USD quote pairs, approximated for JPY.
            gross=p["notional"]*p["side"]*(exit_px/p["entry"]-1)
            cost=p["notional"]*(SPREAD[p["sym"]]*PIP[p["sym"]]/p["entry"]+0.00010)*spread_scale
            pnl=gross-cost;cash+=pnl
            trades.append({"symbol":p["sym"],"pnl":pnl,"opened":str(p["opened"]),"exit":str(t)})
        pos=alive
        # Pyramid winners on later 5m bars: additional independently tracked tickets.
        # No global count cap. Each setup admits at most 4 tickets, under a shared
        # margin budget and portfolio notional ceiling.
        staged=[]
        for base in list(pos):
            if base.get("level",0)>=3 or base.get("last_add")==t: continue
            d=all_data[base["sym"]]
            if t not in d.index:continue
            mark=float(d.loc[t,"Close"])
            progress=(mark-base["entry"])*base["side"]
            if progress>=base["atr"]*0.5*(base["level"]+1):
                staged.append((base["sym"],base["side"],base["atr"],d.index.get_indexer([t])[0],base["group"],base["level"]+1))
                base["level"]+=1;base["last_add"]=t
        incoming=[(sym,side,atr,index,None,0) for sym,side,atr,index in events.get(t,[])]+staged
        for sym,side,atr,index,group,level in incoming:
            d=all_data[sym]
            if group is None and any(p["sym"]==sym and p["side"]==side and p.get("level",0)==0 for p in pos):continue
            entry=float(d.Open.iat[index])
            # Avoid signals that cannot clear round-trip spread within typical ATR
            if atr <= SPREAD[sym]*PIP[sym]*spread_scale*6:continue
            notional=min(initial*0.25,cash*0.25)/(1+level)
            # Aggregate exposure limits, independent of ticket count.
            used=sum(p["notional"] for p in pos)
            if notional<0.25 or used+notional>max(1.0,cash*3.0):continue
            margin=(used+notional)/500.0
            if margin>cash*0.35:continue
            stopdist=1.5*atr
            if notional*stopdist/entry>cash*0.01:continue
            expiry=d.index[min(index+48,len(d)-1)]
            gid=group if group is not None else next_id
            pos.append(dict(ticket_id=next_id,group=gid,level=level,last_add=t,
                sym=sym,side=side,entry=entry,atr=atr,stop=entry-side*stopdist,
                target=entry+side*3.0*atr,expiry=expiry,notional=notional,opened=t))
            next_id+=1;opened_total+=1
            peak_reserved=max(peak_reserved,margin)
        maxpos=max(maxpos,len(pos))
        peak=max(peak,cash);dd=max(dd,(peak-cash)/peak)
    # Report open exposure; no fabricated unrealized profits.
    wins=[x["pnl"] for x in trades if x["pnl"]>0];loss=[x["pnl"] for x in trades if x["pnl"]<0]
    return {"tickets_opened":opened_total,"peak_margin_estimate_usd":round(peak_reserved,5),"initial_usd":initial,"cash_usd":round(cash,4),"return_pct":round(100*(cash/initial-1),2),"closed_trades":len(trades),"win_rate_pct":round(100*len(wins)/len(trades),2) if trades else None,"profit_factor":round(sum(wins)/-sum(loss),3) if loss else None,"max_simultaneous":maxpos,"realized_balance_dd_pct":round(100*dd,2),"open_at_end":len(pos),"by_symbol":{s:{"count":sum(x["symbol"]==s for x in trades),"net_usd":round(sum(x["pnl"] for x in trades if x["symbol"]==s),5)} for s in all_data}}
if __name__=="__main__":
    data=get_prices()
    report={"description":"H1 trend breakout; single hypothesis, no parameter optimization; research only","markets":{s:{"bars":len(d),"start":str(d.index.min()),"end":str(d.index.max())} for s,d in data.items()},"scenarios":{"base":sim(data,1),"double_cost":sim(data,2)},"warnings":["This is NOT prior v0.4 strategy engine","Short overlapping research window; no clean holdout","No historic bid/ask data; cost assumptions only","No broker lot steps, stop-level rules, funding or liquidation","Pyramiding increases correlated risk and has not been validated against broker fills","Profit depends on assumptions; no evidence of persistent edge"]}
    out=Path("forex_v06_report");out.mkdir(exist_ok=True)
    (out/"summary.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
