import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from multi_market import CostModel, TradeRule, barrier_outcomes, make_features, resample_bars, load_bybit_csv, run_trades, confidence_lower_bound

def synthetic(n=252):
    ix=pd.date_range('2025-01-01',periods=n,freq='5min',tz='UTC',name='timestamp_utc')
    return pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,
                         'volume':10.,'turnover':1000.,'trades':10.},index=ix)

class MultimarketTests(unittest.TestCase):
    def test_aggregation(self):
        d=resample_bars(synthetic(),15)
        self.assertEqual(len(d),84)
        self.assertEqual(float(d.iloc[0].volume),30.)
    def test_intrabar_stop_first_long_and_short(self):
        d=synthetic()
        for side in (-1,1):
            returns,_=barrier_outcomes(d,np.full(len(d),1.),
                TradeRule(bars=3,atr_stop=1,reward_risk=1),CostModel(),side)
            self.assertLess(returns[0],0)
    def test_no_same_bar_lookahead(self):
        d=synthetic()
        f,_=make_features(d)
        d.iloc[-1,d.columns.get_loc('close')]=10000
        g,_=make_features(d)
        pd.testing.assert_series_equal(f.iloc[-1],g.iloc[-1])
    def test_no_trade_without_edge(self):
        d=synthetic()
        n=len(d)
        ret=np.full(n,-.01)
        ex=np.arange(n)
        score=np.zeros(n)
        t=run_trades(d.index,ret,ret,ex,ex,score,score,.001,
                     TradeRule(bars=3),d.index[0],d.index[-1])
        self.assertEqual(t['trades'],0)
    def test_small_sample_not_certified(self):
        self.assertEqual(confidence_lower_bound(np.array([.01]*5)),float('-inf'))

if __name__ == '__main__':
    unittest.main()
