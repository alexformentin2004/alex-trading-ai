"""Long-window comparison on user-supplied HistData ASCII M1 CSV or ZIP.
Real M1 *BID* OHLC input, ASK is NOT supplied by M1 file: synthetic spread.
No automatic downloads. No claims of real bid/ask or broker execution.
Examples:
 python forex/m1_extended_compare_v1.py --input data/DAT_ASCII_EURUSD_M1_202609.csv
 python forex/m1_extended_compare_v1.py --input data/aug.zip data/sep.zip
"""
import argparse,json,zipfile
from pathlib import Path
from datetime import timezone,timedelta
import pandas as pd
from forex.m1_three_bots import evaluate,START,LEV,MODELS,SPREAD_PIPS,SLIPPAGE_PIPS
TZ=timezone(timedelta(hours=-5))
def read_one(path):
 path=Path(path)
 if path.suffix.lower()==".zip":
  with zipfile.ZipFile(path) as z:
   names=[n for n in z.namelist() if n.lower().endswith(".csv")]
   if not names:raise ValueError("Zip missing CSV: "+str(path))
   with z.open(names[0]) as stream:
    df=pd.read_csv(stream,sep=";",header=None,usecols=[0,1,2,3,4],
                   names=["DateTime","Open","High","Low","Close"])
 else:
  df=pd.read_csv(path,sep=";",header=None,usecols=[0,1,2,3,4],
                 names=["DateTime","Open","High","Low","Close"])
 df["DateTime"]=pd.to_datetime(df.DateTime.astype(str),format="%Y%m%d %H%M%S")
 df=df.set_index("DateTime")
 df.index=df.index.tz_localize(TZ).tz_convert("UTC")
 df=df.apply(pd.to_numeric,errors="coerce").dropna()
 bad=(df.High<df.Low)|(df.High<df.Open)|(df.High<df.Close)|(df.Low>df.Open)|(df.Low>df.Close)
 if bad.any():raise ValueError(f"Invalid OHLC bars: {bad.sum()}")
 return df
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--input",nargs="+",required=True)
 p.add_argument("--output",default="forex_m1_extended_report.json")
 args=p.parse_args()
 df=pd.concat([read_one(x) for x in args.input]).sort_index()
 if df.index.duplicated().any():raise ValueError("Duplicate minutes")
 if len(df)<1000:raise ValueError("Insufficient M1 history")
 strategies={name:evaluate(df,name) for name in MODELS}
 report={"status":"HISTDATA_BID_OHLC_WITH_SYNTHETIC_SPREAD",
 "minutes":len(df),"start":df.index[0].isoformat(),"end":df.index[-1].isoformat(),
 "initial_capital_usd":START,"leverage_limit":LEV,
 "roundtrip_spread_assumption_pips":SPREAD_PIPS,
 "slippage_each_side_pips":SLIPPAGE_PIPS,
 "sources":list(args.input),
 "strategies":{k:{x:y for x,y in v.items() if x!="curve"} for k,v in strategies.items()},
 "limits":["HistData M1 contains BID OHLC, not ASK: synthetic spread still used",
 "Fractional lot sizes permitted; 50 USD capital may not meet broker min order",
 "Simplified margin simulation and stopout checked at M1 open only",
 "This script cannot prove durable alpha or a 10,000% ROI"]}
 Path(args.output).write_text(json.dumps(report,indent=2))
 print("SUMMARY",json.dumps(report,indent=2))
if __name__=="__main__":main()
