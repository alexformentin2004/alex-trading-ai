# Bid/Ask Forex Phase 1
- REAL tick source: [HistData specification](https://www.histdata.com/f-a-q/data-files-detailed-specification/) supplies YYYYMMDD HHMMSSmmm,bid,ask,volume, **fixed EST**.
- Alternative manual official bid+ask export: [Dukascopy](https://www.dukascopy.com/api/data/get/historical-data-export).
- This version implements **import and audit**; it does NOT claim to have downloaded broker quotes or run multi-month real-tick historical research.
- Use: `python forex/bidask_tick_audit_v1.py --input /path/DAT_ASCII_EURUSD_T_202509.csv --pair EURUSD --capital-usd 50 --leverage 10 --units-step 1000`.
- At 50 USD, EURUSD ~1.10, leverage 10 and 1000-unit minimum, 550 USD max notional <1100 USD micro-lot, so **zero executable trades**.
- Mismatch with EUR account: engine supports USD-account pairs ending USD only until proper conversions are implemented.
- GH CI uses only synthetic fixture for data parser and accounting integrity. A successful test **does not** imply a profitable strategy.
- Future path: explicitly sourced public historical tick snapshot, bid/ask fidelity tests, broker-exact lot/margin schedules, monthly walk-forward and trading commissions.
