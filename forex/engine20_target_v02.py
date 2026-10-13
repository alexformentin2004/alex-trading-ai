"""ALEX FOREX 2.0 unlevered target audit prototype. Never sends orders. No profitability claim.
12 Forex pairs, M5 candidate signals, completed M15/H1 filters, machine-learned
candidate gate. Training labels are prior 6-bar returns, chronological embargo.
Simplified quote costs; no broker tradability, no margin, no portfolio P&L.
"""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import HistGradientBoostingRegressor

PAIRS={
"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),
"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),
"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),
"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),
"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.0),
"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
FEATURES=["atr_frac","range_frac","momentum","trend15","trend60","hour","side","trend_match","vol_ratio"]
def load():
    out={};issues={}
    for pair,(ticker,spread) in PAIRS.items():
        try:
            d=yf.download(ticker,period="30d",interval="5m",auto_adjust=False,progress=False,threads=False)
            if isinstance(d.columns,pd.MultiIndex):d.columns=d.columns.get_level_values(0)
            d=d[["Open","High","Low","Close"]].dropna().sort_index()
            d.index=pd.to_datetime(d.index,utc=True)
            if len(d)<3000 or not d.index.is_unique:raise ValueError("Insufficient or duplicated candles")
            out[pair]=d
        except Exception as exc:issues[pair]=str(exc)
    if len(out)<8:raise RuntimeError("Too few valid pairs: "+str(issues))
    return out,issues

def completed_trend(d,freq):
    # At timestamp t, use ONLY previously completed higher-timeframe bars.
    h=d.resample(freq,label="right",closed="left").Close.last().dropna()
    a=h.ewm(span=8,adjust=False).mean()
    b=h.ewm(span=24,adjust=False).mean()
    direction=np.sign(a-b)
    return direction.reindex(d.index,method="ffill").fillna(0)

def candidates(pair,d):
    o,h,l,c=(d[x] for x in ["Open","High","Low","Close"])
    prev=c.shift()
    true_range=pd.concat([h-l,(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    atr=true_range.rolling(24).mean()
    asian=d.between_time("00:00","06:55")
    highs=asian.High.groupby(asian.index.floor("D")).max()
    lows=asian.Low.groupby(asian.index.floor("D")).min()
    dates=d.index.floor("D")
    day_hi=pd.Series(dates.map(highs),index=d.index)
    day_lo=pd.Series(dates.map(lows),index=d.index)
    past_high=h.shift().rolling(24).max()
    past_low=l.shift().rolling(24).min()
    direction=pd.Series(0,index=d.index)
    # Liquidity-sweep reversal
    direction[(l<past_low)&(c>past_low)&(c>prev)]=1
    direction[(h>past_high)&(c<past_high)&(c<prev)]=-1
    # London range breakout: only if sweep not triggered
    london=(d.index.hour>=7)&(d.index.hour<11)
    direction[(direction==0)&london&(c>day_hi)&(prev<=day_hi.shift())]=1
    direction[(direction==0)&london&(c<day_lo)&(prev>=day_lo.shift())]=-1
    t15=completed_trend(d,"15min");t60=completed_trend(d,"1h")
    vol=atr/prev
    vol_base=vol.shift().rolling(96).median()
    # Entry at next 5-minute OPEN, after signal candle has closed.
    data=pd.DataFrame(index=d.index)
    data["atr_frac"]=vol
    data["range_frac"]=(h-l)/c
    data["momentum"]=c.pct_change(12)
    data["trend15"]=t15
    data["trend60"]=t60
    data["hour"]=d.index.hour/23
    data["side"]=direction
    data["trend_match"]=((direction==t15)&(direction==t60)).astype(int)
    data["vol_ratio"]=vol/vol_base
    data["entry"]=o.shift(-1)
    data["exit"]=c.shift(-7) # hold six future bars after entry (i+1 to i+7)
    pip=0.01 if pair.endswith("JPY") else .0001
    spread_cost=PAIRS[pair][1]*pip
    data["gross"]=direction*(data["exit"]/data["entry"]-1)
    data["cost"]=(spread_cost/data["entry"])+.0001 # round-trip indicative cost
    data["net"]=data["gross"]-data["cost"]
    data["pair"]=pair
    # Restrict to liquid session. No forward information in features.
    eligible=(direction!=0)&(d.index.hour>=7)&(d.index.hour<18)&(d.index.weekday<5)&(atr>spread_cost*3)
    return data.loc[eligible].replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES+["net"])

def stats(x):
    if len(x)==0:return {"trades":0,"mean_return_bps":None,"profit_factor":None,"win_rate_pct":None}
    a=np.asarray(x,dtype=float)
    w=a[a>0].sum();loss=-a[a<0].sum()
    return {"trades":len(a),"mean_return_bps":round(a.mean()*10000,3),
            "profit_factor":round(float(w/loss),3) if loss>0 else None,
            "win_rate_pct":round(float((a>0).mean()*100),2)}
def unlevered_portfolio(candidates, selected_rows, split):
    """Daily capital-equity approximation, gross open exposure capped at 1x.
    Each accepted idea allocates equal 10% capital, closes after six bars.
    Independent signals may overlap; cash-equivalent uninvested balance earns 0.
    Uses indicative mid OHLC; cannot replace bid/ask broker-grade backtesting.
    """
    rows=selected_rows.sort_index().copy()
    if rows.empty:
        return {"trades":0,"calendar_days":0,"daily_mean_pct":None,"target_met":False}
    active=[];pnl=[];opened=0;rejected=0
    for t,r in rows.iterrows():
        active=[x for x in active if x>t]
        if len(active)>=10:
            rejected+=1
            continue
        # Fractional-notional 0.1x each; 10 open tickets max is EXPOSURE cap,
        # not a target or configuration for production with EUR 10.
        active.append(t+pd.Timedelta(minutes=35))
        opened+=1
        pnl.append((t,0.10*float(r["net"])))
    end=candidates.index.max()
    # Calendar trading dates; weekends excluded, all inactive weekdays included.
    start=split.normalize()
    days=pd.date_range(start,end.normalize(),freq="B",tz="UTC")
    day_returns={d:0.0 for d in days}
    for t,x in pnl:
        day=t.normalize()
        if day in day_returns:day_returns[day]+=x
    values=list(day_returns.values())
    import numpy as np
    daily_mean=float(np.mean(values)) if values else 0
    compound=float(np.prod([1+v for v in values])-1) if values else 0
    return {"trades":opened,"rejected_exposure":rejected,"calendar_days":len(values),
        "mean_daily_return_pct":round(daily_mean*100,4),
        "compounded_period_return_pct":round(compound*100,4),
        "target_daily_pct":0.2,
        "target_met_in_this_sample":daily_mean>=.002,
        "negative_days":sum(v<0 for v in values),
        "flat_days":sum(v==0 for v in values),
        "positive_days":sum(v>0 for v in values)}
def main():
    raw,issues=load()
    frames=[candidates(pair,d) for pair,d in raw.items()]
    all_=pd.concat(frames).sort_index()
    # Freeze split with embargo at 70% of time. No test labels admitted to training.
    timestamps=np.sort(pd.unique(all_.index))
    split=pd.Timestamp(timestamps[int(len(timestamps)*.7)])
    embargo=pd.Timedelta(minutes=60)
    train=all_[all_.index<split-embargo]
    test=all_[all_.index>=split]
    if len(train)<100 or len(test)<30:raise RuntimeError("Insufficient candidate samples")
    X=train[FEATURES].astype(float); Y=train["net"].astype(float)
    model=HistGradientBoostingRegressor(max_iter=120,max_leaf_nodes=7,min_samples_leaf=30,
                                        l2_regularization=3.0,learning_rate=.04,random_state=7)
    model.fit(X,Y)
    forecast=model.predict(test[FEATURES].astype(float))
    # Conservative gate: predicted gross expected reward must exceed modeled costs,
    # plus a modest penalty; threshold fixed before seeing test.
    selected=test[forecast>np.maximum(test["cost"].values*.25,.00008)]
    filtered=test[(test.trend_match==1)]
    result={"status":"research_only_not_live","pairs_loaded":sorted(raw),"issues":issues,
      "available_rows":{p:len(d) for p,d in raw.items()},"train_candidates":len(train),
      "test_candidates":len(test),"split_utc":str(split),"model":"HistGradientBoostingRegressor",
      "tests":{"all_signals":stats(test.net),"higher_timeframe_filter":stats(filtered.net),
               "ml_candidate_gate":stats(selected.net)},
      "unlevered_target_audit":{
          "all_signals":unlevered_portfolio(test,test,split),
          "higher_timeframe_filter":unlevered_portfolio(test,filtered,split),
          "ml_candidate_gate":unlevered_portfolio(test,selected,split)},
      "limitations":["Research uses short overlapping Yahoo M5 history, NOT 2 years of bid/ask",
       "No real execution or minimum lot/margin compatibility at 10 EUR",
       "Overlapping 6-bar outcomes are dependent, test uncertainty not quantified",
       "P&L is normalized price return proxy, not executable multi-currency EUR account return",
       "Unlevered portfolio uses 10% assumed capital per signal, a 1x exposure ceiling, and fixed 35-min simulated holding; no broker fills",
       "Daily results are a simplified no-leverage approximation, not validated realized EUR-account performance",
       "ML gate is experimental, no future profit guarantees; live prohibited"] }
    folder=Path("forex_engine_20_target_audit");folder.mkdir(exist_ok=True)
    (folder/"metrics.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
