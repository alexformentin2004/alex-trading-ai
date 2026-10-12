"""ALEX Trading AI research-only prototype, no live trading or API access."""
import argparse
import csv
import json
import math
import random
from pathlib import Path


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not {'timestamp', 'close'}.issubset(rows[0]):
        raise ValueError('CSV requires timestamp and close columns')
    stamps = [row['timestamp'] for row in rows]
    prices = [float(row['close']) for row in rows]
    if stamps != sorted(stamps) or len(stamps) != len(set(stamps)):
        raise ValueError('Timestamp order or duplicates invalid')
    if any(not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError('Invalid close price')
    return prices


def backtest(prices, initial_cash=50., fast=12, slow=48, fee_bps=5.5,
             slippage_bps=1., spread_bps=0., risk_fraction=.5):
    if not 0 < fast < slow or not 0 < risk_fraction <= 1:
        raise ValueError('Invalid parameters')
    cash, qty = float(initial_cash), 0.
    peak, max_dd, trades = cash, 0., 0
    curve = []
    for i, price in enumerate(prices):
        # Previous candles only; trading decision cannot observe current bar.
        if i >= slow:
            recent = prices[i-slow:i]
            signal = sum(recent[-fast:])/fast > sum(recent)/slow
            if signal and qty == 0:
                stake = cash * risk_fraction
                fill = price * (1 + (slippage_bps + spread_bps/2)/10000)
                fee = stake * fee_bps/10000
                qty = (stake-fee)/fill
                cash -= stake
                trades += 1
            elif not signal and qty:
                fill = price * (1 - (slippage_bps + spread_bps/2)/10000)
                value = qty*fill
                cash += value*(1-fee_bps/10000)
                qty = 0.
                trades += 1
        equity = cash + qty*price
        peak = max(peak, equity)
        max_dd = max(max_dd, 1-equity/peak)
        curve.append(equity)
    return {'ending_equity': round(curve[-1], 5),
            'return_pct': round((curve[-1]/initial_cash-1)*100, 4),
            'max_drawdown_pct': round(max_dd*100, 4),
            'trade_events': trades, 'equity_curve': [round(p,5) for p in curve]}


def demo_prices(n=1000):
    rng = random.Random(20261012)
    price = 100.
    prices = []
    for _ in range(n):
        price *= math.exp(.00005+.012*rng.gauss(0,1))
        prices.append(price)
    return prices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--out', type=Path, default=Path('report.json'))
    args = parser.parse_args()
    if args.demo == bool(args.csv):
        parser.error('Choose exactly one of --csv or --demo')
    prices = demo_prices() if args.demo else load_csv(args.csv)
    split = int(len(prices)*.7)
    if split < 60 or len(prices)-split < 60:
        raise ValueError('Need at least 200 bars')
    # Holdout indicator warmup uses history but no holdout positions carry over.
    train = backtest(prices[:split])
    test = backtest(prices[split-48:])
    test['equity_curve'] = test['equity_curve'][48:]
    report = {'moduleId': 'alex.trading', 'schemaVersion': 1,
              'source': 'synthetic' if args.demo else 'csv',
              'research_only': True, 'train': train, 'test': test}
    args.out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in test.items() if k != 'equity_curve'}, indent=2))


if __name__ == '__main__':
    main()
