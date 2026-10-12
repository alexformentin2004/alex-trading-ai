# Historical BTCUSDT data inventory

Google Drive holds Bybit BTCUSDT USDT perpetual historical candles and a quality report.

- Period reported: 2025-01-01 to 2026-09-24 UTC
- 1-minute candles reported: 910,080
- 5-minute candles reported: 182,016
- Reported missing and duplicate 1-minute timestamps: zero
- Existing CSV and Parquet versions; do **not** commit raw market data.

These values are taken from a stored quality report, not independently verified by this code. Verify file schema, OHLCV integrity, timezone and candle continuity before treating the dataset as valid.

The provided engine currently reads CSV files with `timestamp` and `close` columns. It is a simple baseline and does not account for funding, liquidation, variable fee tiers, realistic orderbook execution, or walk-forward optimization.

Readme of previous 20 strategy study: research window 2025-01-01 to 2026-07-31, sealed holdout 2026-08-01 to 2026-09-24; described taker fee 0.055% each side and slippage 0.01% each side; funding excluded. Do not tune on the sealed holdout.
