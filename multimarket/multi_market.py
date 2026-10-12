"""ALEX Trading AI v0.7 — causal, research-only opportunity research.

Never routes orders. All returns are illustrative nominal quote-currency returns,
not a prediction or guarantee. Requires pandas, numpy, scikit-learn.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ('mom3','mom12','rv24','range12','ema_ratio','vol_z','rsi14','atr_rel','hour_sin','hour_cos')
TRAIN_END = pd.Timestamp('2025-09-30', tz='UTC')
TUNE_START = pd.Timestamp('2025-10-03', tz='UTC')
TUNE_END = pd.Timestamp('2025-12-28', tz='UTC')
VALID_START = pd.Timestamp('2026-01-04', tz='UTC')
VALID_END = pd.Timestamp('2026-08-01', tz='UTC')

@dataclass(frozen=True)
class CostModel:
    fee_bps_side: float = 5.5
    slippage_bps_side: float = 1.0
    assumed_half_spread_bps: float = 0.0
    # A funding value of None means UNAVAILABLE, not zero funding.
    funding_bps_per_8h: float | None = None

@dataclass(frozen=True)
class TradeRule:
    bars: int
    atr_stop: float = 1.5
    reward_risk: float = 2.0
    min_stop_pct: float = 0.002
    max_stop_pct: float = 0.03
    fraction: float = 0.25
    cooldown_bars: int = 3
    daily_stop_pct: float = 0.02
    max_drawdown: float = 0.10


def load_bybit_csv(path: Path, expected_minutes: int = 5) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = ['timestamp_utc', 'open', 'high', 'low', 'close', 'volume', 'turnover', 'trades']
    if any(col not in df for col in required) or df.empty:
        raise ValueError('Missing Bybit CSV columns or empty dataset')
    df = df[required].copy()
    df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc'], utc=True, errors='raise')
    if df['timestamp_utc'].duplicated().any() or not df['timestamp_utc'].is_monotonic_increasing:
        raise ValueError('Duplicate/unsorted timestamps')
    delta = df['timestamp_utc'].diff().dropna()
    if not (delta == pd.Timedelta(minutes=expected_minutes)).all():
        raise ValueError('Gap or frequency mismatch')
    # Bybit V5 kline has no trade count; missing trades are metadata, not zero trades.
    numeric = df[['open','high','low','close','volume','turnover']].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError('NaN/inf data')
    o, h, l, c = [df[x].to_numpy() for x in ('open','high','low','close')]
    if (l <= 0).any() or (l > np.minimum(o,c)).any() or (h < np.maximum(o,c)).any():
        raise ValueError('Bad OHLC')
    if (df[['volume','turnover','trades']] < 0).any().any():
        raise ValueError('Negative activity')
    return df.set_index('timestamp_utc')


def resample_bars(base: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes not in (5,15,60):
        raise ValueError('Allowed frame 5, 15 or 60 minutes')
    if minutes == 5:
        return base.copy()
    freq = f'{minutes}min'
    agg = base.resample(freq, label='left', closed='left').agg(
        {'open':'first','high':'max','low':'min','close':'last',
         'volume':'sum','turnover':'sum','trades':'sum'})
    counts = base['open'].resample(freq).count()
    if not (counts == minutes // 5).all():
        raise ValueError('Partial/incomplete resampling bucket')
    return agg


def make_features(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    # Every market-derived column is shifted one complete candle back.
    c = df.close
    ret = c.pct_change()
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema48 = c.ewm(span=48, adjust=False).mean()
    previous = c.shift(1)
    tr = pd.concat([df.high-df.low, (df.high-previous).abs(),
                    (df.low-previous).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean().shift(1)
    diff = c.diff()
    up = diff.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = 100 - 100/(1+up/down.replace(0,np.nan))
    v = np.log1p(df.volume)
    vmean = v.rolling(48,min_periods=48).mean()
    vstd = v.rolling(48,min_periods=48).std().replace(0,np.nan)
    hour = df.index.hour.to_numpy()+df.index.minute.to_numpy()/60
    feats = pd.DataFrame({
        'mom3':c.pct_change(3).shift(1),
        'mom12':c.pct_change(12).shift(1),
        'rv24':ret.rolling(24,min_periods=24).std().shift(1),
        'range12':((df.high-df.low)/c).rolling(12,min_periods=12).mean().shift(1),
        'ema_ratio':((ema12-ema48)/c).shift(1),
        'vol_z':((v-vmean)/vstd).shift(1),
        'rsi14':rsi.shift(1)/100,
        'atr_rel':atr/df.open,
        'hour_sin':np.sin(2*np.pi*hour/24),
        'hour_cos':np.cos(2*np.pi*hour/24)
    },index=df.index)
    return feats.replace([np.inf,-np.inf],np.nan), atr.to_numpy(dtype=float)


def barrier_outcomes(df: pd.DataFrame, atr: np.ndarray, rule: TradeRule,
                     costs: CostModel, direction: int) -> tuple[np.ndarray,np.ndarray]:
    """Return realized net price P&L and exit index for every potential entry.

    For each bar t, entry is at OPEN(t). A barrier can be hit during the same
    bar; if both barriers touch, assign the STOP first. Gaps fill at the worse
    of bar open and stop. Remaining positions exit at horizon-bar close.
    Funding is intentionally not assigned when historical funding is missing.
    """
    if direction not in (-1,1):
        raise ValueError('direction must be -1 or +1')
    if min(costs.fee_bps_side,costs.slippage_bps_side,costs.assumed_half_spread_bps) < 0:
        raise ValueError('Negative execution cost')
    n = len(df)
    horizon = rule.bars
    out = np.full(n,np.nan)
    exits = np.full(n,-1,dtype=np.int32)
    valid_n = max(0,n-horizon+1)
    t = np.arange(valid_n)
    entry = df.open.to_numpy(dtype=float)[:valid_n]
    risk = np.clip(atr[:valid_n]/entry*rule.atr_stop,rule.min_stop_pct,rule.max_stop_pct)
    usable = np.isfinite(atr[:valid_n]) & (atr[:valid_n]>0)
    stop = entry*(1-direction*risk)
    target = entry*(1+direction*risk*rule.reward_risk)
    high = df.high.to_numpy(dtype=float)
    low = df.low.to_numpy(dtype=float)
    opens = df.open.to_numpy(dtype=float)
    closes = df.close.to_numpy(dtype=float)
    active = usable.copy()
    exit_price = np.full(valid_n,np.nan)
    hold_steps = np.zeros(valid_n,dtype=np.int32)
    for k in range(horizon):
        indices=t+k
        if direction==1:
            hit_stop = low[indices] <= stop
            hit_target = high[indices] >= target
            adverse_gap = np.minimum(opens[indices],stop)
        else:
            hit_stop = high[indices] >= stop
            hit_target = low[indices] <= target
            adverse_gap = np.maximum(opens[indices],stop)
        take_stop = active & hit_stop
        take_target = active & ~hit_stop & hit_target
        exit_price[take_stop]=adverse_gap[take_stop]
        exit_price[take_target]=target[take_target]
        closed=take_stop|take_target
        exits[np.flatnonzero(closed)]=indices[closed]
        hold_steps[closed]=k+1
        active[closed]=False
    exit_price[active]=closes[(t+horizon-1)[active]]
    exits[np.flatnonzero(active)]=t[active]+horizon-1
    hold_steps[active]=horizon
    entry_friction=(costs.slippage_bps_side+costs.assumed_half_spread_bps)/10000
    fee=costs.fee_bps_side/10000
    if direction==1:
        exec_entry=entry*(1+entry_friction)
        exec_exit=exit_price*(1-entry_friction)
        gross=exec_exit/exec_entry
        pnl=(gross-1)-fee*(1+gross)
    else:
        exec_entry=entry*(1-entry_friction)
        exec_exit=exit_price*(1+entry_friction)
        gross=exec_exit/exec_entry
        pnl=(1-gross)-fee*(1+gross)
    if costs.funding_bps_per_8h is not None:
        # Net funding sign convention is illustrative: positive rate costs longs.
        timeframe_minutes = int((df.index[1]-df.index[0]).total_seconds()/60)
        pnl-=direction*costs.funding_bps_per_8h/10000 * hold_steps*timeframe_minutes/480
    out[:valid_n]=np.where(usable,pnl,np.nan)
    exits[:valid_n]=np.where(usable,exits[:valid_n],-1)
    return out,exits


def run_trades(index: pd.DatetimeIndex, long_pnl: np.ndarray, short_pnl: np.ndarray,
               long_exits: np.ndarray, short_exits: np.ndarray,
               score_l: np.ndarray, score_s: np.ndarray, threshold: float,
               rule: TradeRule, first: pd.Timestamp, last: pd.Timestamp) -> dict:
    eligible=np.flatnonzero((index>=first)&(index<last))
    cash=50.0
    peak=50.0
    max_dd=0.0
    pos=[]
    next_entry=-1
    last_date=None
    day_start=50.0
    paused=False
    blocked=False
    pending=None
    for i in eligible:
        date=index[i].date()
        if date!=last_date:
            last_date=date;day_start=cash;paused=False
        # Process realized outcomes at their exit bar, never at their entry.
        # Thus the strategy cannot react to an outcome before it occurred.
        if pending is not None and pending['exit_index']<=i:
            before=cash
            cash*=1+rule.fraction*pending['ret']
            peak=max(peak,cash)
            max_dd=max(max_dd,1-cash/peak)
            pos.append({'entered':index[pending['entry_index']].isoformat(),
                        'exited':index[pending['exit_index']].isoformat(),
                        'side':pending['side'],
                        'net_notional_return':round(float(pending['ret']),7),
                        'account_return':round(float(cash/before-1),7)})
            next_entry=int(pending['exit_index'])+1+rule.cooldown_bars
            pending=None
            if max_dd>=rule.max_drawdown or cash<=0:
                blocked=True
        if blocked or paused or pending is not None or i<next_entry:
            continue
        if cash<day_start*(1-rule.daily_stop_pct):
            paused=True;continue
        a,b=score_l[i],score_s[i]
        if not np.isfinite(a) or not np.isfinite(b):
            continue
        direction=1 if a>=b else -1
        predicted=max(a,b)
        if predicted<=threshold:
            continue
        ret=long_pnl[i] if direction==1 else short_pnl[i]
        ex=long_exits[i] if direction==1 else short_exits[i]
        if not np.isfinite(ret) or ex<i or ex>=len(index) or index[ex]>=last:
            continue
        pending={'entry_index':i, 'exit_index':int(ex),
                 'side':'LONG' if direction==1 else 'SHORT','ret':float(ret)}
    trade_rets=np.array([p['account_return'] for p in pos])
    return {'trades':len(pos),'ending_capital':round(cash,6),
            'return_pct':round((cash/50-1)*100,4),
            'max_drawdown_pct':round(max_dd*100,4),
            'win_rate_pct':round(100*(trade_rets>0).mean(),2) if len(pos) else None,
            'mean_account_trade_return_pct':round(100*float(trade_rets.mean()),4) if len(pos) else None,
            'trade_returns':trade_rets,'examples':pos}

def confidence_lower_bound(values: np.ndarray, seed: int = 20261012) -> float:
    if len(values)<30:
        return float('-inf')
    rng=np.random.default_rng(seed)
    # iid bootstrap is optimistic if trades share regimes; gate is screening only.
    boot=np.array([rng.choice(values,size=len(values),replace=True).mean() for _ in range(1000)])
    return float(np.quantile(boot,.01))


def fit_and_score(frame: pd.DataFrame, horizon: int, threshold_grid=(.00025,.0005,.001,.002)) -> dict:
    rule=TradeRule(bars=horizon)
    costs=CostModel()
    feat,atr=make_features(frame)
    long_pnl,long_exit=barrier_outcomes(frame,atr,rule,costs,1)
    short_pnl,short_exit=barrier_outcomes(frame,atr,rule,costs,-1)
    x=feat.to_numpy(dtype=float)
    ix=frame.index
    finite=np.isfinite(x).all(axis=1)&np.isfinite(long_pnl)&np.isfinite(short_pnl)
    # Ensure training/trade labels terminate strictly before split boundary.
    train=(ix<TRAIN_END)&finite&(ix[np.clip(long_exit,0,len(ix)-1)]<TRAIN_END)&(ix[np.clip(short_exit,0,len(ix)-1)]<TRAIN_END)
    select=np.flatnonzero(train)[::horizon]
    if len(select)<300:
        raise ValueError('Insufficient non-overlapping train samples')
    tune_mask=(ix>=TUNE_START)&(ix<TUNE_END)&finite
    eval_mask=(ix>=VALID_START)&(ix<VALID_END)&finite
    if tune_mask.sum()<100 or eval_mask.sum()<100:
        raise ValueError('Insufficient tune/validation sample')
    choices=[]
    models = {
        'ridge':lambda: make_pipeline(StandardScaler(),Ridge(alpha=100.0)),
        'hist_gradient_boosting':lambda: HistGradientBoostingRegressor(max_iter=65,max_leaf_nodes=15,
                                                                       learning_rate=.045,l2_regularization=12,
                                                                       min_samples_leaf=35, random_state=42),
    }
    for model_name,make_model in models.items():
        preds=[]
        for y in (long_pnl,short_pnl):
            model=make_model()
            model.fit(x[select],y[select])
            prediction=model.predict(np.nan_to_num(x,nan=0.0,posinf=0.0,neginf=0.0))
            prediction[~finite]=np.nan
            preds.append(prediction)
        for threshold in threshold_grid:
            t=run_trades(ix,long_pnl,short_pnl,long_exit,short_exit,*preds,threshold,rule,TUNE_START,TUNE_END)
            bound=confidence_lower_bound(t['trade_returns'])
            approved=(t['trades']>=30 and t['return_pct']>0 and bound>0 and
                      t['max_drawdown_pct']<rule.max_drawdown*100)
            choices.append({'model':model_name,'threshold':threshold,
                            'tune_trades':t['trades'],'tune_return_pct':t['return_pct'],
                            'tune_max_drawdown_pct':t['max_drawdown_pct'],
                            'screening_lcb99_trade_pct':None if not math.isfinite(bound) else round(bound*100,5),
                            'approved':approved,'scores':preds})
    survivors=[p for p in choices if p['approved']]
    # Selection uses tuning data ONLY. Pre-declared deterministic tie break.
    survivors.sort(key=lambda p:(p['screening_lcb99_trade_pct'],p['tune_return_pct']),reverse=True)
    selected=survivors[0] if survivors else None
    leaderboard=[{k:v for k,v in p.items() if k!='scores'} for p in choices]
    report={'rows':len(frame),'train_samples':len(select),'tune_samples':int(tune_mask.sum()),
            'diagnostic_validation_samples':int(eval_mask.sum()),
            'timeframe_minutes':int((ix[1]-ix[0]).total_seconds()/60),
            'data_first':ix[0].isoformat(),'data_last':ix[-1].isoformat(),
            'configs':{'costs':asdict(costs),'rules':asdict(rule)},
            'screening':leaderboard,'decision':'ABSTAIN' if selected is None else 'RESEARCH_CANDIDATE',
            'selected_model':None if selected is None else selected['model'],
            'selected_threshold':None if selected is None else selected['threshold'],
            'diagnostic_validation':None}
    if selected is not None:
        diag=run_trades(ix,long_pnl,short_pnl,long_exit,short_exit,*selected['scores'],
                        selected['threshold'],rule,VALID_START,VALID_END)
        report['diagnostic_validation']={k:v for k,v in diag.items() if k!='trade_returns'}
    return report


def main():
    parser=argparse.ArgumentParser(description='Research-only multi-symbol and multi-timeframe opportunity lab')
    parser.add_argument('--market',action='append',required=True,
                        help='SYMBOL=PATH (repeat; Bybit 5m OHLCV CSV)')
    parser.add_argument('--frames',default='5,15,60',help='Comma-separated: 5,15,60')
    parser.add_argument('--out',type=Path,default=Path('market_research_report.json'))
    args=parser.parse_args()
    frames=[int(x) for x in args.frames.split(',')]
    if not frames or any(x not in (5,15,60) for x in frames):
        parser.error('frames must be 5,15,60')
    report={'project':'ALEX Trading AI','moduleId':'trading-lab','appVersion':'0.7.0','schemaVersion':1, 'research_only':True,
            'validation_status':'reused_historical_diagnostics_not_fresh_holdout',
            'target_monthly_roi_pct':20,'target_guaranteed':False,
            'portfolio_cross_asset_backtest':False, 'markets':{}}
    for item in args.market:
        if '=' not in item:
            parser.error('market requires SYMBOL=PATH')
        symbol,path=item.split('=',1)
        if symbol in report['markets'] or not symbol or not path:
            parser.error('bad/duplicate market')
        source=load_bybit_csv(Path(path))
        with open(path,'rb') as market_stream:
            sha=hashlib.file_digest(market_stream,'sha256').hexdigest()
        report['markets'][symbol]={'provenance':{'source':str(Path(path).name),'sha256':sha,'rows_5m':len(source)}}
        for frame in frames:
            data=resample_bars(source,frame)
            horizon={5:12,15:8,60:4}[frame]
            out=fit_and_score(data,horizon)
            report['markets'][symbol][str(frame)]=out
            print(symbol, frame, 'min:',out['decision'],
                  '| train:',out['train_samples'], '| selection candidates:',
                  sum(int(z['approved']) for z in out['screening']))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    print('Saved',args.out)

if __name__=='__main__':
    main()