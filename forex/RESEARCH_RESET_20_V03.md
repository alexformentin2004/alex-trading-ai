# ALEX Forex 2.0 — research reset / profitability gates

**No strategy in the repo has established a persistent profitable edge. Trading live remains disabled.**

## Target and decomposition

- Research goal: **+0.20% arithmetic mean daily return on equity at maximum 1.00x gross FX notional exposure**, net of spread, commission, slippage, conversion and financing. Include flat days. Days and equity denominated in EUR.
- Separately report gross *before trading fees*, net *after fees*, exposures and any **leveraged 2x, 5x, 10x scenarios** on identical orders, prices and fills. Never remove leverage by simply dividing a broker's realized return unless position sizing and costs are recomputed consistently.
- 'Unlevered' means gross trade notional <= equity, not 'pip gain', price return, margin allocated or portfolio win rate.
- Model broker minimum lot and quote/base to EUR P&L conversion; reject any order that a €10 account cannot fund while respecting max-loss constraints.
- Risk: 5% per ticket, 20% aggregate planned stop-loss budget, 30% drawdown entry shutdown. Gap losses may exceed limits; independent risk engine controls.
- Concentration across 12 crosses measured as signed currency exposure, not just 'position count'. No fixed 3-ticket cap.
- For 252 constant +0.2% sessions, annual compounding ~65.5%; this is ambitious and not an entitlement.

## Radical strategy research: freeze hypotheses before testing

1. Session-conditioned *liquidity sweep*: overnight high/low, prior-day high/low, London/NY open; fade only after causal M5 rejection; compare against randomized entry baseline with same exposure.
2. Cross-sectional *currency relative-value/momentum*: compute each currency's strength in full 12-pair graph and compare strongest versus weakest after spreads; avoid redundant net currency exposures.
3. *Volatility-adaptive trend continuation*: detect H1/H4 market regime; M5 pullback confirmation; volatility-dependent hold/stop.
4. *Range conditional mean reversion*: trade only when diagnostics support stationarity, avoiding macro shocks.
5. *Event-free expansion breakout*: only when liquidity/volatility can pay costs; blackout if unreliable scheduled-news data.

No automatic selection by best training ROI. ML is challenger to fixed-rule baseline; train on strictly past data, purged/embargoed folds, and protect final chronological holdout. Measure uncertainty and multiple-testing bias. If no edge found, report no edge.

## Reproducibility prerequisites before next profitability claims

- At least 2 years of independently sourced broker-quality bid/ask history, with licensing and timestamp checks.
- Fill simulation from executable bid/ask, conservative stop/target sequencing, rejection, dynamic spread and slippage and accurate cross-currency conversion.
- Full equity path at every bar including open positions, financing and margin; liquidation simulation.
- Walk-forward, regime stress tests, and sensitivity to 2x costs, minimum-lot effects and a never-seen test segment.
- No trade until strategy, broker and ten-euro execution constraints are independently validated.
