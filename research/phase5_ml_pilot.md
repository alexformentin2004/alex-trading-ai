# Phase 5 — Machine learning pilot (2026-10-12)

First reproducible ML experiment on private Bybit BTCUSDT perpetual 5-minute dataset. Full code, tests and JSON report distributed as `alex_ml_v01.zip` in the project conversation; this GitHub document is not the implementation.

Model: standardized logistic regression with lagged price returns, volatility, ranges, volume anomalies, EMA separation, RSI, and time-of-day. Target: positive net price change for entry at next open, exit 12 bars later (1 hour), using 13 basis points modeled round-trip costs. Fixed account starts at 50 **nominal USDT**, position size 50% available capital, no leverage. Training Jan-Sep 2025, threshold tuning Oct-Dec 2025 (selected 0.56), validation Jan-Jul 2026 with 1-day embargoes. Later Aug-Sep 2026 was previously seen in research and is NOT pristine holdout.

Validation: 60,768 examples; ROC AUC **0.59191**, positive class prevalence **32.316%**, Brier **0.21470**. Trading: **93 trades, -10.11513% cumulative simulated return**, max drawdown **10.46112%**, win rate **43.011%**. Previously inspected Aug-Sep: 6 trades, +0.55527%, not independently confirmatory.

Conclusion: predictive ranking does not imply tradable advantage. Not profitable, not live-ready. Fees/slippage are illustrative; no actual funding, measured spread, liquidity, liquidation, market impact, exchange filters, or tax. All older windows are contaminated by repeated strategy investigation; require NEW forward paper-trading evidence before any profitability claims. Three local unit tests passed.
