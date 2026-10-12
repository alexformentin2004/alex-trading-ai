# Phase 3: Real BTCUSDT 5-minute benchmark — 20 fixed variants

**Experiment date:** 2026-10-12. Research only. No live orders.

Data: Bybit BTCUSDT perpetual 5m CSV held in private Google Drive. 182,016 bars, from 2025-01-01 to 2026-09-24 UTC. The dataset passed basic continuity and OHLC checks.

These are 20 **new illustrative** variants across SMA crossover, EMA crossover, price momentum, and breakout families, five parameter sets per family. They are not yet verified as identical to the previous dashboard's 20 strategies.

Research window: before 2026-08-01 UTC. Holdout: 2026-08-01 through 2026-09-24 UTC. Fixed position sizing uses 50% of available cash on each buy. Independent account starts at 50 nominal units in each evaluation interval. Prior-bar close signals, fill at next open. Assumptions: taker fee 5.5bps per side; slippage 1bp per side; **funding and measured spread not included**; no liquidation modeling or leverage. Accounting is nominal quote units, NOT a verified EUR conversion.

## Results
- Research-positive strategies: **0 / 20**.
- Holdout-positive strategies: **6 / 20**.
- Highest research result: **EMA 96/384: -26.119%** across the research period; holdout **+9.555%**.
- Highest holdout result: **SMA 96/384: +12.355%** across about 55 days; research **-29.365%**. Its holdout position was still open at endpoint.
- Baseline SMA 12/48: research **-79.355%**, holdout **-4.227%**.

**Conclusion:** No evidence for sustainable profitability, much less 20% per month with 99% success probability. Using the 55-day holdout to choose a winner would contaminate any future assessment on that same window. Model real funding, spread, fills, exchange filters, and use new unseen forward data for subsequent validation.

The executable reproducibility package is available in the project conversation attachment, but is **not yet committed to GitHub**. Do not claim these GitHub docs alone reproduce the calculations.
