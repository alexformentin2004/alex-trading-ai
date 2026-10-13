# Forex data acquisition branch
This branch is isolated from the BTC trading research in main.
The GitHub Actions workflow downloads Dukascopy **real** M1 historical candles for EURUSD, GBPUSD, USDJPY for 2025-01-06 through 2025-01-08 UTC, validates basic nonempty CSV output, then uploads a short-lived artifact. This is a data pipeline smoke test, **not a profitability backtest**.
Go to Actions > Forex real data smoke test. If it succeeds, download the artifact, then adapt the v0.4 engine to the observed schema; do not claim performance before a genuine data-backed backtest with costs and portfolio margin.
Data source: https://github.com/Leo4815162342/dukascopy-node
No broker credentials, no live trading, no deposits.
