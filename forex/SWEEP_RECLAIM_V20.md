# Sweep Reclaim v2 — TradingView research

A portable Pine v6 script for EURUSD, GBPUSD, USDJPY and other liquid forex pairs.

- Hypothesis: a failed break of the preceding 24-bar range, with wick rejection and confirmed reclaim.
- Unlike v1, it does not chase EMA trend breakouts.
- It places entries after confirmed candles, and attaches stops and targets using actual position average entry after fill.
- Structural stop beyond swept candle plus 0.3 ATR; target at 2R; time exit.
- Entry window London hours; completed higher-timeframe H1 context, ATR filter and cooldown.
- Nominal sizing capped to 1x account equity, planned per-trade risk initially 0.5%.

Open the .pine file in TradingView Pine Editor, add to 15m chart, and run Strategy Tester on the same 2026-07-01 to 2026-10-13 window on all three pairs. Do not change parameters separately for each pair just to fit historical data.

IMPORTANT: Not compiled or backtested in TradingView. Profitability NOT established, not a working live broker strategy. Slippage, spread and commissions are placeholders and instrument contract/lot minimum and true costs must be confirmed for chosen broker. TradingView backtest engine cannot perfectly reproduce gaps or executable bid/ask.
