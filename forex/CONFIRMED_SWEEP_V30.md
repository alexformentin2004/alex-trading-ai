# ALEX FOREX — Confirmed Sweep v3.0
Pine v6 source: universal_confirmed_sweep_v30.pine

## Why this is materially different
1. Same failed-range-break sweep hypothesis as v2. It must be followed by a *later completed candle* that closes beyond the sweep candle extreme within 2 bars.
2. Entry queued for the subsequent bar, rather than on the initial rejection.
3. Structural stop from the sweep extreme with ATR buffer; on entry, the target is measured from actual average filled price and real distance to that structural stop.
4. A gross reward-to-indicative-cost pretrade gate avoids trades whose target is small relative to friction. Cost gate is a proxy and does NOT replace broker commission or spread.
5. Planned stop risk <=0.5% equity and gross exposure <=1x; drawdown shutdown and time stop.
6. Test window fixed July 1 to Oct 13, 2026. Default symbols M15 EURUSD, GBPUSD, USDJPY.

## Native TradingView validation
Paste Pine file in TradingView Pine Editor. Compare ROI%, max DD%, winning/total, PF in Strategy Tester against v2 same price provider and period. Both use research-only placeholder commission and slippage settings.
Results from v2: EURUSD ROI -0.47%, DD -0.80%, win 24/68, PF .837; GBPUSD -2.8%, -3%, 23/71, .487; USDJPY -0.83%, -1.5%, 22/67, .788.

v3 is not compiled or backtested by TradingView here. **Do not consider it profitable** without successful validation.
Caution: prior historic data are already examined. If v3 improves retrospectively, it must still be tested out of sample. No broker connection, micro-lot feasibility, precise bid/ask/spread, or live funds.
