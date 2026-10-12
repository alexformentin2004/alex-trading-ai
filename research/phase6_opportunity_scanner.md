# Phase 6 — Opportunity Scanner v0.1 (2026-10-12)

A research-only ML opportunity selector tested on the private Bybit BTCUSDT 5-minute CSV (182,016 bars). It forecasts next-hour gross returns using 12 causal features, then chooses long, short, or **ABSTAIN**, with next-bar-open entry and 12-bar-later open exit. No execution/API access.

Models: Ridge regression and histogram gradient boosting regression. Dates: fit through 2025-09-28; tune 2025-10-02 to 2025-12-27; validation 2026-01-03 to 2026-07-27; gaps/purges protect train/tune/validation boundaries. Account: 50 nominal USDT; 50% allocation; fixed roundtrip cost 13bps of traded notional, with 26bps sensitivity option. No leverage/funding/real spread/market impact/liquidation.

**Result: ABSTAIN.** A candidate needed positive net tuning performance and at least 30 nonoverlapping trades. Ridge generated only 1–6 tuning trades across tested thresholds; gradient boosting generated 0–1. Thus no candidate passed minimum sample threshold and none was selected for live/paper deployment. At a fixed 0.30% forecast threshold, both models generated zero validation trades. This is not evidence of profitability or a 99% success probability.

Local runner + full JSON report + four passing unit tests are available in the conversation artifact `alex_opportunity_scanner_v01.zip`. The complete code has not yet been uploaded to GitHub. Existing 2026 data were already explored repeatedly in prior phases, so results must not be called pristine unseen out-of-sample evidence.