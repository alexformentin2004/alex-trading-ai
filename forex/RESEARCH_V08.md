# Forex research reset — v0.8

Status: research design only. NO validated profitable Forex strategy.

## Why stop tuning previous systems
- v0.5 / v0.6 / v0.7 negative on short overlapping sample
- Previous variants chosen after observing losing samples: potential selection bias
- Yahoo FX OHLC is not an executable bid/ask quote feed
- $10–$50 accounts have real minimum lot and cost constraints
- high available leverage does not itself create positive expected value
- v0.7's apparent concurrency is not a proof of sustainable trading risk control

## Prespecified candidate hypotheses
1. London-range expansion: Asian high/low established before London, first breakout, minimum volatility and execution-cost filters
2. Range reversion: regime-classified compressed trend/volatility, enter on normalized excursion, stop by volatility
3. Volatility regime transition: rolling realized volatility expands from prior low-volatility percentile, require price confirmation
4. Relative currency strength: consistent signed pair returns across currency graph, select diversified exposures

## Research design
- Collect multiple years of real tick bid/ask or at minimum independently validated M1 bid/ask; preserve source/license/time zone.
- Freeze candidate specifications, risk constraints, transaction cost scenarios, and metrics before examining holdout.
- Development / validation / untouched final test segmented chronologically, then rolling walk-forward across multiple market regimes.
- Next-bar fills, no future data leakage; for ambiguous stop/take touches choose adverse ordering unless tick data resolves it.
- Compare to a no-trade baseline; use net expectation/trade, profit factor, drawdown, tail losses and bootstrap uncertainty.
- Include realistic lot increments, minimum volume, currency P&L conversion, spread, commission, slippage, swap, margin utilization and broker liquidation.
- Portfolio ledger supports multiple independently tracked tickets on same instrument and cross-pair; aggregate currency and margin risk caps, NO arbitrary global cap of three positions.
- At $10–$50, reject non-executable trades rather than treating fractional inaccessible lots as filled.
- Kill conditions: unacceptable drawdown, absence of holdout advantage, failure with 2x cost, execution mismatch.

## Advancement criteria
Do NOT declare a winner based on a single positive backtest or tuning to the same data.
Require out-of-sample net positive expectancy, stability across periods/instruments, sensitivity tests, defensible sample size, and broker-executable minimums.
If none passes: report 'no edge found' and paper trade or continue research, do not trade real money.

## First concrete engineering tasks
1. Audit previous strategy-v07 ledger for pyramiding timing, same-bar stop/target, cash vs equity, outstanding margin and no-lookahead signals.
2. Replace Yahoo intraday short-window dependency with verifiable longer licensed historical dataset.
3. Implement candidate hypothesis registry and reproducible walk-forward runner.
4. Emit strategy-by-symbol-by-period tables, trade log and rejected-order log.
