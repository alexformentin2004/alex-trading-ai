"""ALEX FOREX — intraday margin/stop-out stress laboratory.

Research only. Yahoo H1 midpoint proxy, NOT true executable bid/ask.
Signal: prior 8 completed H1 mid closes; order at NEXT H1 open, exit
after at most 4 H1 candles, or protective ATR stop/take; conservative
same-bar stop-first OHLC assumption. Costs use synthetic dynamic spread
with hour-based multipliers and slippage. Full-margin liquidation at
equity <= 50% of used margin. No live execution.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FX={"EURUSD":("EURUSD=X",1.3),"GBPUSD":("GBPUSD=X",1.8),
"USDJPY":("JPY=X",1.6),"USDCHF":("CHF=X",1.8),
"USDCAD":("CAD=X",1.9),"AUDUSD":("AUDUSD=X",1.9),
"NZDUSD":("NZDUSD=X",2.3),"EURJPY":("EURJPY=X",2.6),
"GBPJPY":("GBPJPY=X",3.5),"EURGBP":("EURGBP=X",2.0),
"EURCHF":("EURCHF=X",2.3),"AUDJPY":("AUDJPY=X",3.0)}
INITIAL=50.0
LEV=(3,10,20,30)
MAX_HOLD=4
COST_STRESSES=(1.0,2.0,3.0)
TRAIN_HOURS=1200
TEST_HOURS=400

def spread_fraction(pair,px,hour,stress):
    pip=.01 if pair.endswith("JPY") else .0001
    mult=2.5 if hour in (21,22,23,0) else (1.5 if hour in (1,2,3) else 1.0)
    return (FX[pair][1]*pip/px*mult+0.00008)*stress

def prices():
    output={}
    for p,(ticker,_) in FX.items():
        df=yf.download(ticker,period="730d",interval="1h",auto_adjust=False,progress=False,threads=False)
        if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
        df=df[["Open","High","Low","Close"]].dropna().astype(float)
        df.index=pd.to_datetime(df.index,utc=True)
        output[p]=df[~df.index.duplicated(keep="first")]
    common=sorted(set.intersection(*(set(x.index) for x in output.values())))
    if len(common)<2000:raise RuntimeError("Insufficient H1 data")
    return {p:df.reindex(common) for p,df in output.items()},pd.DatetimeIndex(common)

def signals(data,idx):
    # Trade exactly one pair per four-hour block. Non-overlapping.
    # Historical momentum from PREVIOUS eight closed candles, never current.
    choices=[]
    for p,d in data.items():
        prev=d.Close.iloc[idx-8:idx]
        if len(prev)<8 or prev.isna().any():continue
        ret=prev.iloc[-1]/prev.iloc[0]-1
        choices.append((abs(ret),p,np.sign(ret)))
    if not choices:return None
    choices.sort(key=lambda x:(-x[0],x[1]))
    return choices[0][1],float(choices[0][2])

def simulation(data,times,start,end,leverage,stress=1.0,style="trend"):
    equity=INITIAL;peak=INITIAL;min_dd=0.;trades=0;winners=0
    stopped=0;liquidated=False;first_ruin=None;fees=0.;ignored=0
    for i in range(start,end-MAX_HOLD,MAX_HOLD):
        if equity<=0:break
        s=signals(data,i)
        if s is None:continue
        p,side=s
        if style=="fade":side=-side
        if side==0:continue
        d=data[p];entry=float(d.Open.iat[i])
        if entry<=0 or not np.isfinite(entry):continue
        # Synthetic entry cost: half spread + slippage, exit half spread + slippage.
        cost=spread_fraction(p,entry,times[i].hour,stress)
        notional=equity*leverage
        used_margin=notional/leverage
        effective_equity=equity
        atr=(d.High.iloc[i-15:i]-d.Low.iloc[i-15:i]).mean()
        if not np.isfinite(atr):continue
        stopdist=max(0.003*entry,1.6*atr)
        targetdist=2*stopdist
        stop=entry-side*stopdist
        take=entry+side*targetdist
        closed=False
        for j in range(i,i+MAX_HOLD):
            hi=float(d.High.iat[j]);lo=float(d.Low.iat[j])
            exitpx=float(d.Close.iat[j])
            if side>0:
                stophit=lo<=stop
                takehit=hi>=take
                if stophit:exitpx=stop
                elif takehit:exitpx=take
            else:
                stophit=hi>=stop
                takehit=lo<=take
                if stophit:exitpx=stop
                elif takehit:exitpx=take
            # Unrealized conservative worst-point stress, before bracket exit.
            worst=lo if side>0 else hi
            adverse=side*(worst/entry-1)
            eq_worst=effective_equity+notional*(adverse-cost/2)
            if eq_worst<=0.5*used_margin:
                # stop-out preempts the theoretical stop when equity insufficient.
                exitpx=entry+(0.5*used_margin-effective_equity+notional*cost)/notional*entry/side
                liquidated=True;closed=True
                break
            if stophit or takehit:
                closed=True;break
        change=notional*side*(exitpx/entry-1)
        fees+=notional*cost
        equity=max(0.,equity+change-notional*cost)
        trades+=1
        winners+=int(change-notional*cost>0)
        peak=max(peak,equity);min_dd=min(min_dd,equity/peak-1)
        if equity<=INITIAL*0.2:
            first_ruin=str(times[i])
            break
        if liquidated:
            first_ruin=str(times[i])
            break
    return {"roi_pct":round((equity/INITIAL-1)*100,2),"max_dd_pct":round(min_dd*100,2),
            "trades":trades,"winning_trades":winners,"stopped_out":liquidated,
            "ruined":first_ruin is not None,"ruin_at":first_ruin,
            "costs_eur":round(fees,3),"ending_eur":round(equity,2),
            "hit_1000pct":bool(equity>=INITIAL*11)}

def main():
    data,times=prices()
    # 2 fixed styles, four leverages, sequential historical folds.
    configs=[(style,lev) for style in ("trend","fade") for lev in LEV]
    folds=[]
    for start in range(TRAIN_HOURS,len(times)-TEST_HOURS,TEST_HOURS):
        results=[]
        for style,lev in configs:
            dev=simulation(data,times,16,start-1,lev,style=style)
            score=dev["roi_pct"]-abs(dev["max_dd_pct"])*2-1000*dev["ruined"]
            results.append((score,style,lev))
        results.sort(reverse=True)
        _,style,lev=results[0]
        test=simulation(data,times,start,start+TEST_HOURS,lev,style=style)
        cost2=simulation(data,times,start,start+TEST_HOURS,lev,stress=2.,style=style)
        folds.append({"start":str(times[start]),"end":str(times[start+TEST_HOURS-1]),
                      "selected":style,"leverage":lev,"test":test,"double_costs":cost2})
    recent=[]
    start=len(times)-TEST_HOURS
    for style,lev in configs:
        for stress in COST_STRESSES:
            x=simulation(data,times,start,len(times),lev,stress=stress,style=style)
            recent.append({"style":style,"leverage":lev,"stress":stress,**x})
    recent.sort(key=lambda r:r["roi_pct"],reverse=True)
    report={"status":"RESEARCH_ONLY","data_type":"Yahoo mid H1 + SYNTHETIC bid ask assumptions",
            "start":str(times[0]),"end":str(times[-1]),"common_H1_bars":len(times),
            "pairs":list(FX),"initial_capital_eur":INITIAL,"target_roi_pct":1000,
            "folds":folds,"folds_hit_1000pct":sum(x["test"]["hit_1000pct"] for x in folds),
            "folds_ruined":sum(x["test"]["ruined"] for x in folds),
            "last_window_exploratory_top10":recent[:10],
            "last_window_any_hit_1000pct":sum(x["hit_1000pct"] for x in recent),
            "limitations":["NOT real bid/ask: spreads, slippage and liquidation approximated",
            "FX notional assumes identical account/quote currencies; approximate",
            "Intrabar liquidation uses OHLC worst-first, can overstate ruin",
            "No swaps/overnight financing, retail lot minimum, broker netting or news-gaps",
            "Training windows overlap development history previously inspected",
            "Daily margin stop-out threshold is synthetic, broker-specific rules vary",
            "No live orders or verified 1000% strategy"]}
    out=Path("forex_margin_intraday_v1");out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(report,indent=2))
    print("SUMMARY",json.dumps({k:v for k,v in report.items() if k in
       ("status","data_type","common_H1_bars","folds_hit_1000pct","folds_ruined",
        "last_window_exploratory_top10","last_window_any_hit_1000pct")},indent=2))
    print("FOLDS",json.dumps(folds,indent=2))
if __name__=="__main__":main()
