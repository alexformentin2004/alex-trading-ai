"""ALEX Forex v0.8 research comparison; no real-money execution. Prices from Yahoo M5.
One bar delayed signals. USD quote P&L approximation only, flat estimated cost.
No bid/ask, broker min lots, margin call or genuine 2020-25 holdout. No validated edge.
"""
import json
from pathlib import Path
import pandas as pd
import yfinance as yf
T={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X"}
PIP={"EURUSD":.0001,"GBPUSD":.0001,"USDJPY":.01}
SPREAD={"EURUSD":1.2,"GBPUSD":1.8,"USDJPY":1.5}
STRATEGIES=("london_breakout","range_reversion","volatility_expansion","relative_strength")
def prices():
    out={}
    for s,t in T.items():
        d=yf.download(t,period="30d",interval="5m",auto_adjust=False,progress=False,threads=False)
        if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
        d=d[["Open","High","Low","Close"]].dropna()
        d.index=pd.to_datetime(d.index,utc=True)
        d=d.sort_index()
        assert len(d)>500 and d.index.is_unique
        out[s]=d
    return out
def make_signals(data):
    out={}
    # Currency strength: compare directional 12-bar returns across currencies, using past closes only.
    strength={}
    for sym,d in data.items(): strength[sym]=d.Close.pct_change(12)
    for sym,d in data.items():
        close=d.Close;prev=close.shift(1)
        tr=pd.concat([d.High-d.Low,(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
        atr=tr.rolling(24,min_periods=24).mean()
        roll_mean=close.rolling(48,min_periods=48).mean()
        roll_std=close.rolling(48,min_periods=48).std()
        hour=d.index.hour
        is_london=(hour>=7)&(hour<=11)
        # Asian range calculated only from PRIOR 00:00-06:59 UTC observations on same date.
        asia=d.between_time("00:00","06:59")
        day=asia.index.floor("D")
        hi=asia.groupby(day).High.max()
        lo=asia.groupby(day).Low.min()
        days=d.index.floor("D")
        asian_high=pd.Series(days.map(hi),index=d.index)
        asian_low=pd.Series(days.map(lo),index=d.index)
        london=pd.Series(0,index=d.index)
        london[(is_london)&(close>asian_high)&(prev<=asian_high.shift(1))]=1
        london[(is_london)&(close<asian_low)&(prev>=asian_low.shift(1))]=-1
        out[(sym,"london_breakout")]=london
        z=(close-roll_mean)/roll_std.replace(0,float("nan"))
        trend=(close/close.shift(48)-1).abs()
        reversion=pd.Series(0,index=d.index)
        reversion[(z < -2)&(trend<.004)]=1
        reversion[(z > 2)&(trend<.004)]=-1
        out[(sym,"range_reversion")]=reversion
        expansion=pd.Series(0,index=d.index)
        vol=close.pct_change().rolling(12).std()
        vol_base=vol.shift(1).rolling(96).median()
        expansion[(vol>vol_base*1.7)&(close>close.shift(12).rolling(12).max())]=1
        expansion[(vol>vol_base*1.7)&(close<close.shift(12).rolling(12).min())]=-1
        out[(sym,"volatility_expansion")]=expansion
        # Relative cross-sectional strength: currency graph normalized against other 2 available pairs
        other=[strength[x].reindex(d.index).ffill() for x in data if x!=sym]
        cross=sum(x for x in other)/len(other)
        relative=strength[sym]-cross
        rs=pd.Series(0,index=d.index)
        rs[(relative>.0015)&(close>close.shift(24))]=1
        rs[(relative<-.0015)&(close<close.shift(24))]=-1
        out[(sym,"relative_strength")]=rs
        out[(sym,"atr")]=atr
    return out
def simulate(data,fee_scale=1.0):
    sig=make_signals(data);events={}
    last=min(x.index.max() for x in data.values())
    split=last-pd.Timedelta(days=10)
    for sym,d in data.items():
        for strat in STRATEGIES:
            signal=sig[(sym,strat)]
            for i in range(120,len(d)-1):
                side=int(signal.iat[i]) if pd.notna(signal.iat[i]) else 0
                if side==0:continue
                t=d.index[i+1]
                if not (7<=t.hour<19 and t.weekday()<5):continue
                a=float(sig[(sym,"atr")].iat[i])
                if not (a>SPREAD[sym]*PIP[sym]*2.5):continue
                # only edge of same-side signal to limit repeated signals
                if i and signal.iat[i-1]==side:continue
                events.setdefault(t,[]).append((sym,strat,side,a,i+1))
    capital=50.;cash=50.;positions=[];done=[];max_open=0;rejected=0
    clock=sorted(set(t for d in data.values() for t in d.index))
    for t in clock:
        keep=[]
        for p in positions:
            d=data[p["sym"]]
            if t not in d.index:keep.append(p);continue
            bar=d.loc[t]
            sl=(bar.Low<=p["stop"] if p["side"]==1 else bar.High>=p["stop"])
            tp=(bar.High>=p["target"] if p["side"]==1 else bar.Low<=p["target"])
            end=t>=p["expires"]
            if not (sl or tp or end):keep.append(p);continue
            price=p["stop"] if sl else p["target"] if tp else float(bar.Close)
            gross=p["notional"]*p["side"]*(price/p["entry"]-1)
            cost=p["notional"]*(SPREAD[p["sym"]]*PIP[p["sym"]]/p["entry"]+.0001)*fee_scale
            pnl=gross-cost;cash+=pnl
            done.append({"symbol":p["sym"],"strategy":p["strategy"],"opened":str(p["opened"]),"split":"verification" if p["opened"]>=split else "development","pnl_usd":round(pnl,7)})
        positions=keep
        for sym,strat,side,atr,i in events.get(t,[]):
            if cash<1:rejected+=1;continue
            # No arbitrary total ticket cap; concurrent strategies can share same pair.
            if any(p["sym"]==sym and p["strategy"]==strat and p["side"]==side for p in positions):continue
            notional=min(cash*.15,capital*.15)
            if notional<.5:rejected+=1;continue
            # These are fractional hypothetical notional positions, NOT broker-tradable micro lots.
            if sum(p["notional"] for p in positions)+notional>max(1,cash*2):
                rejected+=1;continue
            entry=float(data[sym].Open.iat[i])
            dist=1.4*atr
            expires=data[sym].index[min(i+24,len(data[sym])-1)]
            positions.append({"sym":sym,"strategy":strat,"side":side,"entry":entry,"stop":entry-side*dist,"target":entry+side*2.4*atr,"expires":expires,"notional":notional,"opened":t})
        max_open=max(max_open,len(positions))
    def metric(rows):
        wins=[x["pnl_usd"] for x in rows if x["pnl_usd"]>0];los=[x["pnl_usd"] for x in rows if x["pnl_usd"]<0]
        return {"trades":len(rows),"pnl_usd":round(sum(x["pnl_usd"] for x in rows),4),"profit_factor":round(sum(wins)/-sum(los),3) if los else None}
    report={"starting_capital_usd":capital,"ending_cash_usd":round(cash,4),"max_simultaneous_positions":max_open,"total_closed":len(done),"rejected_entries":rejected,"verification_start_utc":str(split),"total":metric(done),"by_strategy":{s:{sp:metric([x for x in done if x["strategy"]==s and x["split"]==sp]) for sp in ("development","verification")} for s in STRATEGIES},"warnings":["No independently sealed holdout: previous team has inspected overlapping historical period","Simulated stop and target assume adverse same-bar priority","Notional fractions are not executable with $10-$50 at standard Forex minimum lots","USDJPY USD accounting approximated","No bid/ask spread history, funding, equity mark-to-market, real margin calls or hedging constraints","No claim of statistical profitability"]}
    return report
if __name__=="__main__":
    out=Path("forex_v08_report");out.mkdir(exist_ok=True)
    data=prices()
    reports={"data":{s:{"rows":len(d),"first":str(d.index.min()),"last":str(d.index.max())} for s,d in data.items()},"base":simulate(data,1.),"costs_2x":simulate(data,2.)}
    (out/"report.json").write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2))
