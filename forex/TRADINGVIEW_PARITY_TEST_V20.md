# ALEX FOREX — TradingView native parity test

This is a *test harness* of Sweep & Reclaim v2, not a new optimized strategy. No signal, risk, or exit parameters were changed. Added only:
- Date window: July 1, 2026 00:00 UTC to October 13, 2026 23:59 UTC.
- No new entries outside window and a forced close after the end date.
- Grey background outside interval.

## Steps
1. Open TradingView with M15 chart of EURUSD, same price feed used for v1 when possible (e.g. OANDA EURUSD vs OANDA GBPUSD and OANDA USDJPY).
2. Paste the entire [Pine file](./universal_sweep_reclaim_v20_tv_test.pine) into Pine Editor, save, Add to chart.
3. Repeat with GBPUSD and USDJPY. Keep input defaults identical.
4. In Strategy Tester, record Total P&L % (ROI), Max equity drawdown %, profitable trades / closed trades, and profit factor. Enable all strategy costs that match the broker (commissions, slippage, financing), and use the exact same chart provider.
5. In Strategy Tester export List of Trades for each pair as CSV where supported. Copy the values into this matrix:

| Pair | v1 ROI | v1 DD | v1 Win / trades | v1 PF | v2 ROI | v2 DD | v2 Win / trades | v2 PF |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| EURUSD | -1.80% | -2.20% | 26 / 92 | 0.655 | ? | ? | ? | ? |
| GBPUSD | -4.00% | -4.00% | 25 / 90 | 0.482 | ? | ? | ? | ? |
| USDJPY | -2.63% | -3.10% | 13 / 59 | 0.525 | ? | ? | ? | ? |

### Limitations
TradingView Pine is not executable via connected GitHub Actions or this environment. This file has not been compiled on TradingView; if Pine compiler reports an error, provide its line/message for a correction. Test results from an independent Yahoo Python reconstruction CANNOT replace these native TradingView values. The account currency is EUR, slippage and commission placeholders are configured in strategy() and do not fully represent broker spread. No guarantee of profitability, and no live orders.
