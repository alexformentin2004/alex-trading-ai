# ALEX Trading AI

Early-stage BTCUSDT quantitative research prototype. **No exchange access, real-money execution or verified trading edge.**

## Quick start
Python 3.10+; no third-party dependencies for the baseline:

```bash
python -m unittest discover -s tests -v
python engine.py --demo --out report.json
python engine.py --csv data/btc_5m.csv --out report.json
```

CSV input currently needs sorted unique `timestamp` and positive `close` columns. Actual Bybit source schema has not yet been checked against this simple importer. The synthetic demo is solely for testing engine behavior, not strategy performance.

## What is included
- Long/flat moving-average baseline, prior-bar signal and simplified next-close execution.
- Fixed transaction-fee, slippage and spread parameters.
- A simple chronological 70/30 research split and JSON reports.
- Four automated tests.
- A record of historical Drive datasets in [DATA_SOURCES.md](DATA_SOURCES.md).

## Important limitations
This baseline is **not a validated perpetual-futures simulator**. It lacks funding, maker/taker decisions, mark-price liquidation, exchange minimum order constraints, realistic intrabar fills and correct production-grade risk management. Neither the research split nor test metrics should be used to claim profitability. The test split uses a warmup prefix and resets positions; its reported return includes warmup activity, so it needs correction before scientific use.

## Next engineering stage
Verify BTCUSDT CSV/Parquet schema and integrity; build a reliable bar adapter; integrate perpetual funding and real fee assumptions; reproduce 20 strategy baselines using a sealed out-of-sample period and walk-forward validation; then paper-trade before considering real capital.

Never commit API keys, financial records or large raw historical datasets. Repository visibility is currently public.

## Phase 2 — verified data adapter (2026-10-12)

`research_v2.py` accepts the **actual** Bybit 5-minute CSV schema (`timestamp_utc,open,high,low,close,volume,turnover,trades`). Run locally:

```bash
python research_v2.py --csv data/BTCUSDT_BYBIT_PERPETUAL_5m.csv --out report_v2.json
python -m unittest discover -s tests -v
```

The local source file was inspected independently: 182,016 bars from 2025-01-01 00:00 UTC to 2026-09-24 23:55 UTC; zero 5-minute interval gaps and zero basic OHLC inconsistencies. The code's GitHub Actions tests do not include the private dataset. Holdout begins 2026-08-01 UTC. **Baseline only**: next-bar-open fills, fixed taker-like fees 5.5bps per side and slippage 1bp per side, no measured spread, no funding, no leverage or liquidation. 50 EUR initial research cash, with 50% available cash allocated to each entry. Never infer profitability from this incomplete cost model.
