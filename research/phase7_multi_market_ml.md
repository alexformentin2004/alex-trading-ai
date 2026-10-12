# Phase 7 — BTCUSDT multi-timeframe ML screening (2026-10-12)

## Dataset and integrity
Private Bybit BTCUSDT USDT-perpetual OHLCV at 5 minutes, 182,016 contiguous bars, 2025-01-01 through 2026-09-24 UTC. SHA-256: `11201c59bc2900210838d12eb212a70dfa4eeb631bf93de179c02f2e7d1d37b7`. 15m and 60m were aggregated exclusively from the same BTC 5m candles. **ETH, SOL, BNB not yet backtested**: no matching historical files were found in the accessible Drive search.

## Protocol
Training ends 2025-09-30 (labels closed before boundary). Threshold-selection period 2025-10-03 to 2025-12-27 UTC. Diagnostic period Jan-Jul 2026 is historically reused from earlier phases and is **not a pristine holdout**. Model alternatives: Ridge and Histogram Gradient Boosting regression for long and short expected trade P&L. 4 thresholds each × 3 resolutions => 24 candidate configurations, selecting only if ≥30 completed trades, positive cumulative tuning result, below 10% observed closed-trade drawdown, and a positive **unadjusted iid bootstrap lower 1% quantile** for mean account return per trade.

## Actual historical research outputs
| Timeframe | Nonoverlapping train examples | HGB threshold 0.00025 tuning | HGB threshold 0.002 tuning | Approved |
|---|---:|---|---|---:|
| 5m | 6,524 | 259 trades; −10.1377% | 42 trades; −0.9857% | 0 |
| 15m | 3,258 | 225 trades; −9.5131% | 53 trades; −4.0366% | 0 |
| 60m | 1,620 | 165 trades; −1.7446% | 80 trades; +1.3475%, 99% iid bootstrap lower-bound on mean account trade return −0.04953% | 0 |

**Decision on ALL THREE timeframes: ABSTAIN.** Historical diagnostic validation was deliberately not used to approve candidates. No proven profitable strategy or guarantee of 20% monthly ROI with 99% reliability.

## Important limitations
Fee 5.5bps per side, slippage 1bp per side, zero assumed spread (not measured), no historical funding, liquidity impact, mark-price stops, stop order execution constraints or liquidation. Stop-first ties and unfavorable gaps are modeled; 25% nominal account exposure per entry, no leverage and one position per instrument. Daily loss controls depend on realized exits, not full intratrade mark-to-market. iid bootstrap screening does not address multiple testing or regime dependence, so it is **not** a statistical certification of future returns. Cross-asset portfolio constraints and correlation are not yet implemented.

Executable engine, documentation, public candle downloader and test suite are in the [multimarket](../multimarket/) directory. The local CSV is deliberately not committed.
