# ALEX Trading AI — Multi-Market Research v0.7.0

**Status: RESEARCH ONLY · NO LIVE TRADING · NO VERIFIED POSITIVE EDGE**

This build is a runnable ML lab that reads Bybit perpetual OHLCV datasets, validates continuity, derives causal features, resamples 5m to 15m/60m and compares Ridge and Histogram Gradient Boosting models. It scans **LONG / SHORT / ABSTAIN**, with entry at the next candle's open and conservative intrabar stop-first assumptions. It does not execute exchange orders.

## Verified run, 12 October 2026

- Data actually used: private Bybit BTCUSDT perpetual 5-minute CSV, 182,016 bars covering 2025-01-01 through 2026-09-24 UTC.
- Google Drive did not show a comparable ETHUSDT / SOLUSDT / BNBUSDT file when searched. Those markets were **not tested**.
- Real-data intervals: BTCUSDT at 5m, 15m (derived), 60m (derived).
- 2 algorithms × 4 prediction thresholds × 3 timeframes = 24 screening configurations; no passed the prespecified screening gate.
- Most positive tuning outcome: histogram gradient boosting at 60m with threshold 0.002 had **+1.3475% cumulative** over 2025-10-03 through 2025-12-27, 80 closed trades, but 99% **iid bootstrap** lower bound for mean account-return per trade was **−0.04953%**, so it is **REJECTED**.
- 5m HGB threshold .00025: **−10.1377% cumulative**, 259 closed trades in tuning; 15m same model threshold: **−9.5131%**, 225 closed trades. A large number of trades by itself is not an edge.
- The Jan–Jul 2026 partition was **not used to select thresholds or approve candidates** because it had already been inspected extensively in earlier phases. No fresh, uncontaminated holdout exists yet. The system abstains on all three frames.

## Getting started

Requires Python 3.10+, plus packages from requirements.txt.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python multi_market.py \
  --market BTCUSDT=/path/to/BTCUSDT_BYBIT_PERPETUAL_5m.csv \
  --frames 5,15,60 \
  --out reports/btc_real_5_15_60.json
```

Additional markets can be downloaded using **public, unauthenticated** Bybit V5 klines, subject to service availability, rate limits, instrument listing history and API conditions:

```sh
python fetch_bybit_public.py \
  --symbol ETHUSDT --symbol SOLUSDT --symbol BNBUSDT \
  --start 2025-01-01T00:00:00Z --end 2026-09-25T00:00:00Z \
  --outdir data
python multi_market.py \
  --market BTCUSDT=data/BTCUSDT_BYBIT_PERPETUAL_5m.csv \
  --market ETHUSDT=data/ETHUSDT_BYBIT_LINEAR_5m.csv \
  --frames 5,15,60 --out reports/multi_market.json
```

**Important:** The downloader was written and unit-tested against synthetic responses, not exercised against the live Bybit API in this run. API-origin klines do **not** include trade count (field left missing); the model does not use that field. It checks missing intervals and rejects partial exports. A market with a shorter listing history may not be downloadable back to 2025-01-01.

## Model logic and safe assumptions

- Data integrity: strictly ordered UTC timestamps every 5 minutes, valid OHLC and nonnegative volume/turnover.
- Features: 10 lagged momentum, volatility, trend, RSI, volume and UTC-hour features. **No future candle input** at entry.
- Target: realized *net fractional notional return* of a hypothetical long/short trade, started at next bar open; stop at 1.5 ATR, reward 2× initial stop, maximum hold 12×5m / 8×15m / 4×60m bars. If stop and target are both hit inside a candle, stop fills first; stop gaps are penalized.
- Model: separate Ridge and HistGradientBoostingRegressor for long/short expected returns.
- Signal: trade only when the larger estimated net return exceeds the chosen threshold, otherwise abstain.
- Position: 25% of simulated 50 USDT starting account per trade, one open position per market, 3-bar cooldown, heuristic daily realized-stop and account drawdown pause.
- Costs: fixed fee **5.5 bps/side**, slippage **1 bp/side**, **spread assumed zero**, **historical funding missing/excluded**. Without these costs a positive finding would be even less credible. No liquidation, order-book impact, margin/leverage, borrow costs or real execution latency.
- Periods: fit Jan–Sep 2025, tune 3 Oct–27 Dec 2025, historical *diagnostic only* from 4 Jan–31 Jul 2026. Training labels must end before the training boundary. A 99% iid bootstrap lower bound of average trade return is a **screening heuristic**, **not** 99% probability of future profit and not valid against multiple-testing and market-dependence without further work.
- No shared-capital portfolio optimization or cross-asset correlation simulation yet. Market returns must **not** be added together as if independent.
- Risk accounting uses closed-trade equity; intratrade mark-to-market risk and losses during the open trade are not fully captured.

## Required next gates before paper trading

1. Obtain genuine recent and cross-asset data, funding history, mark price data, executable spread/order book samples and contract trading rules.
2. Re-run with purged event based walk-forward splits, block bootstrap and multiple-comparison adjustment.
3. Freeze model and thresholds before collecting unseen forward data, then compare against passive and randomized baselines.
4. Run paper trading with continuous reconciliation and explicit no-trade controls. No live funding or API keys in this codebase.

A monthly **+20% ROI with 99% certainty cannot be guaranteed or established** by this study.

## Data policy

Never commit proprietary/personal trading information, large raw market data, financial API tokens, secrets, account history or private source URLs. The repository is currently public.