"""ALEX Forex 2.0: deterministic leverage/risk accounting tests.
These are unit tests, NOT evidence of trading profitability.
Run: python -m unittest forex/test_portfolio_accounting_v03.py -v
"""
from dataclasses import dataclass
import unittest

@dataclass(frozen=True)
class Fill:
    pair: str
    side: int
    entry: float
    exit: float
    notional_eur: float
    fees_eur: float = 0.0
    financing_eur: float = 0.0

def realized_eur(fill: Fill, eur_per_quote: float) -> float:
    """Notional is EUR account exposure; convert return in quote/base terms
    assuming EUR-valued notional and close-valued conversion supplied by caller.
    This is a synthetic test helper, NOT general-purpose FX P&L conversion.
    """
    if fill.entry <= 0 or fill.exit <= 0 or fill.notional_eur < 0:
        raise ValueError("Invalid price or notional")
    if fill.side not in (-1, 1) or eur_per_quote <= 0:
        raise ValueError("Invalid side/conversion")
    # This helper intentionally expresses EUR-equivalent notional return,
    # not broker units. Quote conversion belongs to live execution adapter.
    simple_return=fill.side*(fill.exit/fill.entry-1.0)
    return fill.notional_eur*simple_return-fill.fees_eur-fill.financing_eur

def portfolio_return_pct(opening_equity_eur: float, positions: list[Fill]) -> float:
    """Net return as % actual equity; not raw pip or instrument return."""
    if opening_equity_eur <= 0: raise ValueError("positive equity required")
    return 100 * sum(realized_eur(p,1.0) for p in positions) / opening_equity_eur

def leverage_scenarios(equity, price_return, roundtrip_cost_fraction, multiples=(1,2,5,10)):
    """Fixed *exposure leverage*, with costs scaling by trade notional.
    This intentionally uses a one-currency synthetic price model.
    """
    if equity <= 0 or roundtrip_cost_fraction<0:raise ValueError()
    out=[]
    for mult in multiples:
        gross=mult*price_return
        cost=mult*roundtrip_cost_fraction
        net=gross-cost
        out.append({"exposure_multiplier":mult,"gross_equity_return_pct":round(gross*100,6),
                    "trading_cost_pct":round(cost*100,6),
                    "net_equity_return_pct":round(net*100,6),
                    "ending_equity":round(equity*(1+net),6)})
    return out

class FinancialAccountingTests(unittest.TestCase):
    def test_one_percent_move_one_x(self):
        results=leverage_scenarios(10,.01,.001)
        self.assertEqual(results[0]["gross_equity_return_pct"],1)
        self.assertEqual(results[0]["net_equity_return_pct"],.9)
    def test_leverage_scales_losses_as_well(self):
        r=leverage_scenarios(10,-.01,.001)
        self.assertEqual(r[0]["net_equity_return_pct"],-1.1)
        self.assertEqual(r[-1]["net_equity_return_pct"],-11)
    def test_costs_scale_with_notional(self):
        r=leverage_scenarios(10,.002,.001)
        self.assertAlmostEqual(r[0]["trading_cost_pct"],.1)
        self.assertAlmostEqual(r[2]["trading_cost_pct"],.5)
    def test_no_leverage_target_is_equity_return(self):
        trade=Fill("EURUSD",1,1,1.003,10,.01)
        self.assertAlmostEqual(portfolio_return_pct(10,[trade]),.2)
    def test_multiple_positions_aggregate(self):
        a=Fill("EURUSD",1,1,1.01,5,.0)
        b=Fill("GBPUSD",-1,1,.98,5,.0)
        self.assertAlmostEqual(portfolio_return_pct(10,[a,b]),1.5)
    def test_negative_equity_rejected(self):
        with self.assertRaises(ValueError):portfolio_return_pct(0,[])
if __name__=="__main__":unittest.main()
