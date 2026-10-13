# ALEX FOREX Universal Adaptive v1.0
A portable TradingView Pine v6 strategy for educational research on FX symbols.

Paste `forex/universal_adaptive_v10.pine` into TradingView's Pine Editor,
add to chart on M15 or M30, then use Strategy Tester across symbols.
Do NOT mistake a working backtest script for a profitable strategy.
No claim of +0.20% mean unlevered daily ROI. No live broker integration.

Built-in: EMA/ADX trend regime, prior-completed H4 trend confirmation,
breakout/pullback trigger, London session, ATR stop & RR target,
risk-budget quantity, gross exposure cap <=1x, drawdown halt, cooldown.
Execution realism: trading system fills at next available bar; brackets are
derived from the signal close, and gaps/slippage can exceed the nominal
stop. TradingView broker emulator and syminfo mincontract may not match
your broker's minimum lots, FX currency conversion and order quantities.
Edit strategy() commissions and slippage to match the broker. Add realistic
bid/ask spread and financing externally if TradingView costs don't cover it.

This has NOT been compiled on TradingView or backtested; no profitability
or cross-pair robustness established. Please don't connect real capital.
