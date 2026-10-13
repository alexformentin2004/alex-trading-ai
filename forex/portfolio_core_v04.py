"""ALEX FX 2.0 — deterministic EUR-denominated execution/risk research core.
No market-data fetching, no broker orders. Intended for testable ledger mechanics.
All money Decimal; side +1/-1; 1 lot = 100_000 base units.
"""
from dataclasses import dataclass
from decimal import Decimal as D
from typing import Dict, List

LOT=D("100000")
def dec(x): return x if isinstance(x,D) else D(str(x))
@dataclass(frozen=True)
class PairSpec:
    symbol:str
    base:str
    quote:str
    min_lot:D=D("0.01")
    step_lot:D=D("0.01")
@dataclass(frozen=True)
class Order:
    spec:PairSpec
    side:int
    lots:D
    entry:D
    stop:D
    quote_to_eur:D
    usd_to_eur:D
    spread_quote:D=D("0")
    commission_eur:D=D("0")
    leverage:D=D("30")

def validate(order:Order):
    p=order
    if p.side not in (-1,1):raise ValueError("side")
    if min(p.lots,p.entry,p.stop,p.quote_to_eur,p.usd_to_eur,p.leverage)<=0:raise ValueError("positive inputs")
    if p.lots < p.spec.min_lot or (p.lots/p.spec.step_lot)%1:raise ValueError("min lot / step")
    if p.side*(p.entry-p.stop)<=0:raise ValueError("stop must be adverse")
    if p.spread_quote<0 or p.commission_eur<0:raise ValueError("negative fees")
def gross_pnl_eur(o:Order,exit_price:D,quote_to_eur_at_exit:D)->D:
    validate(o)
    return LOT*o.lots*o.side*(dec(exit_price)-o.entry)*dec(quote_to_eur_at_exit)
def full_cost_eur(o:Order)->D:
    validate(o)
    return LOT*o.lots*o.spread_quote*o.quote_to_eur+o.commission_eur
def notional_eur(o:Order)->D:
    validate(o)
    return LOT*o.lots*o.entry*o.quote_to_eur
def reserved_margin_eur(o:Order)->D:
    return notional_eur(o)/o.leverage
def planned_loss_eur(o:Order)->D:
    # conservative order-entry conversion held constant as planning estimate
    return max(D("0"),-gross_pnl_eur(o,o.stop,o.quote_to_eur))+full_cost_eur(o)
def entry_decision(o:Order,equity:D,existing:List[Order],risk_trade=D("0.05"),risk_total=D("0.20"),margin_cap=D("0.70")):
    validate(o);equity=dec(equity)
    if equity<=0:return False,"no_equity"
    if planned_loss_eur(o)>equity*risk_trade:return False,"per_trade_risk"
    if sum((planned_loss_eur(x) for x in existing),D(0))+planned_loss_eur(o)>equity*risk_total:return False,"aggregate_risk"
    if sum((reserved_margin_eur(x) for x in existing),D(0))+reserved_margin_eur(o)>equity*margin_cap:return False,"margin"
    return True,"accepted"
def portfolio_snapshot(positions:List[Order],equity:D)->Dict[str,str]:
    equity=dec(equity)
    exposure=sum((notional_eur(x) for x in positions),D(0))
    stop=sum((planned_loss_eur(x) for x in positions),D(0))
    marg=sum((reserved_margin_eur(x) for x in positions),D(0))
    return {"equity_eur":str(equity),"open_positions":len(positions),
        "gross_exposure_eur":str(exposure),"gross_exposure_multiple":str(exposure/equity if equity>0 else 0),
        "planned_stop_loss_eur":str(stop),"reserved_margin_eur":str(marg)}
def leverage_comparison(price_return:D,roundtrip_cost:D,multiples=(1,2,5,10)):
    # same synthetic 1x gross exposure return: both gains and trading fees scale.
    return [{"multiple":k,"gross_return_pct":str(D(100)*dec(k)*dec(price_return)),
      "cost_pct":str(D(100)*dec(k)*dec(roundtrip_cost)),
      "net_return_pct":str(D(100)*dec(k)*(dec(price_return)-dec(roundtrip_cost)))}
      for k in multiples]
