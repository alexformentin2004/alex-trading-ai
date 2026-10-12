import csv
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from research_v2 import load_bars, backtest, experiment

def bars(n=200):
    start=datetime(2026,7,31,tzinfo=timezone.utc)
    return [{"timestamp":start+timedelta(minutes=5*i),
             "open":100+i*.1,"high":101+i*.1,"low":99+i*.1,
             "close":100+i*.1,"volume":10.0,"turnover":1000.0,"trades":20.0}
            for i in range(n)]

class RealDataHarnessTests(unittest.TestCase):
    def test_boundary_uses_prior_close_only(self):
        base=bars()
        first=backtest(base,48,120)
        modified=bars()
        for i in range(120,len(modified)):
            modified[i]["close"]=20000.0
        self.assertEqual(first,backtest(modified,48,120))

    def test_flat_market_does_not_trade(self):
        base=bars()
        for b in base:
            b["open"]=b["high"]=b["low"]=b["close"]=100.0
        r=backtest(base,48,200)
        self.assertEqual(r["entries"],0)
        self.assertEqual(r["final_equity"],50.0)

    def test_holdout_no_warmup_returns(self):
        base=bars(450)
        r=experiment(base,"2026-08-01T00:00:00+00:00")
        self.assertEqual(r["holdout"]["first_trade"],"2026-08-01T00:00:00+00:00")
        self.assertEqual(r["holdout"]["initial_cash"],50.0)

    def test_csv_gap_rejected(self):
        base=bars(3)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bars.csv"
            with p.open("w",newline="") as f:
                writer=csv.writer(f)
                writer.writerow(("timestamp_utc","open","high","low","close","volume","turnover","trades"))
                for b in (base[0],base[2]):
                    writer.writerow((b["timestamp"].isoformat(),*[b[x] for x in ("open","high","low","close","volume","turnover","trades")]))
            with self.assertRaises(ValueError):
                load_bars(p)

if __name__=="__main__":
    unittest.main()
