"""Offline deterministic unit tests; test quotes are SYNTHETIC, not research outcomes."""
import csv,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from forex.bidask_tick_audit_v1 import load_ticks,replay
class HarnessTest(unittest.TestCase):
 def test_real_quote_side_and_lot_infeasible(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"fixture.csv"
   t=datetime(2025,1,2)
   with path.open("w",newline="") as f:
    w=csv.writer(f)
    for i in range(160):
     dt=t+timedelta(seconds=i)
     b=1.1000+i*.000001
     w.writerow([dt.strftime("%Y%m%d %H%M%S")+"000",f"{b:.6f}",f"{b+.00012:.6f}",0])
   ticks,meta=load_ticks(path)
   self.assertEqual(meta["ticks"],160)
   self.assertEqual(ticks[0][0].hour,5)
   no=replay(ticks,leverage=10,initial=50,units_step=1000)
   self.assertEqual(no["trades"],0)
   self.assertGreater(no["orders_skipped_min_lot"],0)
   yes=replay(ticks,leverage=10,initial=500,units_step=1000)
   self.assertGreater(yes["trades"],0)
 def test_reject_inverted_and_unsorted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"invalid.csv"
   p.write_text("20250102 000001000,1.1010,1.1000,0\\n")
   with self.assertRaises(ValueError):load_ticks(p)
if __name__=="__main__":unittest.main()
