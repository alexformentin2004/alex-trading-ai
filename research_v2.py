"""Validated Bybit 5-minute research baseline. No order execution or leverage."""
from __future__ import annotations
import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXPECTED = ("timestamp_utc", "open", "high", "low", "close", "volume", "turnover", "trades")

def load_bars(path: Path):
    bars = []
    previous = None
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(EXPECTED).issubset(reader.fieldnames):
            raise ValueError("Bybit source must contain " + ", ".join(EXPECTED))
        for line, row in enumerate(reader, start=2):
            try:
                time = datetime.fromisoformat(row["timestamp_utc"])
                if time.tzinfo is None or time.utcoffset() != timedelta(0):
                    raise ValueError("timestamps must be UTC timezone-aware")
                values = {k: float(row[k]) for k in EXPECTED[1:]}
                o, h, l, c = (values[k] for k in ("open", "high", "low", "close"))
                if not all(math.isfinite(v) for v in values.values()) or not (0 < l <= min(o,c) <= max(o,c) <= h):
                    raise ValueError("invalid OHLC")
                if any(values[k] < 0 for k in ("volume", "turnover", "trades")):
                    raise ValueError("negative activity")
                if previous is not None and time-previous != timedelta(minutes=5):
                    raise ValueError("missing, duplicated, or unsorted 5m timestamp")
                previous = time
                bars.append({"timestamp": time, **values})
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"Invalid bar at CSV line {line}: {exc}") from exc
    if not bars:
        raise ValueError("Dataset is empty")
    return bars

def backtest(bars, first_trade, last_trade, fast=12, slow=48, initial_cash=50.0,
             fraction=0.5, fee_bps=5.5, slippage_bps=1.0, half_spread_bps=0.0):
    """Signals on last completed close; fill at following bar open. Long/flat, unlevered."""
    if not (0 < fast < slow and 0 < fraction <= 1 and first_trade >= slow and
            first_trade < last_trade <= len(bars)):
        raise ValueError("Invalid strategy or evaluation boundaries")
    closes = [b["close"] for b in bars]
    cash = initial_cash
    quantity = 0.0
    peak = initial_cash
    max_drawdown = 0.0
    entries = exits = 0
    curve = []
    orders = []
    roundtrip_bps = fee_bps + slippage_bps + half_spread_bps
    for i in range(first_trade, last_trade):
        # Exactly bars [i-slow, i), so no use of candle i prices in the signal.
        window = closes[i-slow:i]
        active = sum(window[-fast:])/fast > sum(window)/slow
        opening = bars[i]["open"]
        if active and quantity == 0:
            stake = cash*fraction
            fee = stake*fee_bps/10000
            fill = opening*(1+(slippage_bps+half_spread_bps)/10000)
            quantity = (stake-fee)/fill
            cash -= stake
            entries += 1
            orders.append({"time": bars[i]["timestamp"].isoformat(), "side":"BUY", "fill":fill})
        elif not active and quantity > 0:
            fill = opening*(1-(slippage_bps+half_spread_bps)/10000)
            proceeds = quantity*fill*(1-fee_bps/10000)
            cash += proceeds
            quantity = 0.0
            exits += 1
            orders.append({"time": bars[i]["timestamp"].isoformat(), "side":"SELL", "fill":fill})
        value = cash+quantity*bars[i]["close"]
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, 1-value/peak)
        curve.append({"timestamp":bars[i]["timestamp"].isoformat(), "equity":round(value,6)})
    # End value includes marked-to-market open positions, not forced liquidation.
    final = curve[-1]["equity"]
    return {"first_trade":bars[first_trade]["timestamp"].isoformat(),
            "last_bar":bars[last_trade-1]["timestamp"].isoformat(),
            "initial_cash":initial_cash, "final_equity":final,
            "return_pct":round(100*(final/initial_cash-1),5),
            "max_drawdown_pct":round(max_drawdown*100,5),
            "entries":entries, "exits":exits,
            "open_position":quantity>0,
            "fills":orders, "equity_curve":curve}

def experiment(bars, holdout_start="2026-08-01T00:00:00+00:00"):
    boundary = datetime.fromisoformat(holdout_start)
    index = next((i for i,b in enumerate(bars) if b["timestamp"]>=boundary),None)
    if index is None or index < 49 or len(bars)-index < 10:
        raise ValueError("Insufficient bars around the holdout boundary")
    # Research and holdout accounts are independent; warmup uses pre-boundary
    # closes only. Nothing in the holdout is used for parameter selection.
    return {"dataset":{"rows":len(bars),"first":bars[0]["timestamp"].isoformat(),
                         "last":bars[-1]["timestamp"].isoformat(),
                         "holdout_start":holdout_start},
            "assumptions":{"instrument":"BTCUSDT Bybit perpetual",
                           "exposure":"unlevered long/flat proxy",
                           "fee_bps_per_side":5.5,"slippage_bps_per_side":1.0,
                           "spread_bps_per_side":0.0,"funding":"NOT MODELED",
                           "execution":"next bar open (signal on previous close)",
                           "size":"50% of available cash per entry"},
            "research":backtest(bars,48,index),
            "holdout":backtest(bars,index,len(bars)),
            "caution":"Research-only illustrative baseline. No funding, liquidation, latency or intrabar fill risk modeled."}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--csv",type=Path,required=True)
    parser.add_argument("--out",type=Path,default=Path("report_v2.json"))
    args=parser.parse_args()
    report=experiment(load_bars(args.csv))
    args.out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    for key in ("research","holdout"):
        r=report[key]
        print(key,{k:r[k] for k in ("initial_cash","final_equity","return_pct","max_drawdown_pct","entries","exits","open_position")})

if __name__=="__main__":
    main()
