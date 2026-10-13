import unittest
from decimal import Decimal as D
from portfolio_core_v04 import (PairSpec,Order,entry_decision,gross_pnl_eur,full_cost_eur,
    notional_eur,reserved_margin_eur,planned_loss_eur,portfolio_snapshot,leverage_comparison)
EURUSD=PairSpec("EURUSD","EUR","USD")
USDJPY=PairSpec("USDJPY","USD","JPY")
def euro(lots="0.01",entry="1.10",stop="1.095",spread=".00012",leverage="30"):
    return Order(EURUSD,1,D(lots),D(entry),D(stop),D("0.91"),D("0.91"),D(spread),D(0),D(leverage))
class LedgerTests(unittest.TestCase):
    def test_quote_currency_conversion(self):
        o=euro()
        self.assertEqual(gross_pnl_eur(o,D("1.11"),D(".90")),D("9.000000"))
    def test_short_usdjpy_conversion(self):
        o=Order(USDJPY,-1,D(".01"),D("150"),D("151"),D(".006"),D(".9"))
        self.assertEqual(gross_pnl_eur(o,D("149"),D(".006")),D("6.00000"))
    def test_minimum_lot(self):
        with self.assertRaises(ValueError):notional_eur(euro(lots=".001"))
    def test_ten_euro_account_rejects_min_lot(self):
        ok,why=entry_decision(euro(),D("10"),[])
        self.assertFalse(ok);self.assertEqual(why,"per_trade_risk")
    def test_margin_reject_even_with_tiny_stop(self):
        o=euro(stop="1.09999")
        ok,why=entry_decision(o,D("10"),[])
        self.assertFalse(ok);self.assertEqual(why,"margin")
    def test_concurrent_multiple_tickets(self):
        o=euro(stop="1.09999",leverage="500")
        ok,why=entry_decision(o,D("100"),[o,o])
        self.assertTrue(ok)
        self.assertEqual(portfolio_snapshot([o,o,o],D("100"))["open_positions"],3)
    def test_leverage_scaling(self):
        r=leverage_comparison(D(".002"),D(".001"))
        self.assertEqual(r[0]["net_return_pct"],"0.100")
        self.assertEqual(r[3]["net_return_pct"],"1.000")
    def test_stop_loss_includes_spread(self):
        self.assertGreater(planned_loss_eur(euro()),D("4.55"))
    def test_costs_affect_net_not_gross(self):
        self.assertGreater(full_cost_eur(euro()),0)
if __name__=="__main__":unittest.main()
