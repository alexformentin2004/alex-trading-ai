"""Download public Bybit V5 linear perpetual 5m candles; NO API keys or orders.
Reference: https://bybit-exchange.github.io/docs/v5/market/kline
Outputs OHLCV. The Bybit kline endpoint does NOT contain a trade count.
"""
import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT="https://api.bybit.com/v5/market/kline"
BAR_MS=300000

def utc_ms(text):
    dt=datetime.fromisoformat(text.replace('Z','+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Specify timezone (e.g. Z for UTC)')
    return int(dt.astimezone(timezone.utc).timestamp()*1000)

def normalize_response(payload):
    if payload.get('retCode')!=0:
        raise RuntimeError(str(payload.get('retMsg','Bybit API error')))
    out=[]
    for bar in payload.get('result',{}).get('list',[]):
        if len(bar)<7:
            raise ValueError('Malformed kline record')
        timestamp=datetime.fromtimestamp(int(bar[0])/1000,tz=timezone.utc).isoformat()
        out.append(dict(timestamp_utc=timestamp,open=bar[1],high=bar[2],
                        low=bar[3],close=bar[4],volume=bar[5],
                        turnover=bar[6],trades=''))
    return out

def fetch_symbol(symbol,start,end,path):
    if start>=end or start%BAR_MS or end%BAR_MS:
        raise ValueError('Aligned ascending five-minute UTC boundaries required')
    records={}
    cursor=start
    while cursor<end:
        upper=min(end,cursor+1000*BAR_MS)
        q=urlencode({'category':'linear','symbol':symbol,'interval':'5',
                     'start':cursor,'end':upper-1,'limit':1000})
        req=Request(ENDPOINT+'?'+q,headers={'User-Agent':'ALEX-Trading-Research/0.7'})
        with urlopen(req,timeout=30) as handle:
            chunk=normalize_response(json.load(handle))
        for row in chunk:
            t=utc_ms(row['timestamp_utc'])
            if cursor<=t<upper:
                records[t]=row
        cursor=upper
        time.sleep(.15)
    expected=range(start,end,BAR_MS)
    missing=sum(t not in records for t in expected)
    if missing:
        raise ValueError(f'Missing {missing} requested candles; nothing written')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as handle:
        fields=('timestamp_utc','open','high','low','close','volume','turnover','trades')
        writer=csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        writer.writerows([records[t] for t in expected])
    return len(records)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--symbol',action='append',required=True)
    ap.add_argument('--start',required=True)
    ap.add_argument('--end',required=True)
    ap.add_argument('--outdir',type=Path,default=Path('data'))
    a=ap.parse_args()
    for sym in a.symbol:
        if not sym.endswith('USDT') or not sym.isalnum() or sym!=sym.upper():
            ap.error('Use uppercase USDT contract symbols')
        dest=a.outdir/f'{sym}_BYBIT_LINEAR_5m.csv'
        n=fetch_symbol(sym,utc_ms(a.start),utc_ms(a.end),dest)
        print(sym,n,dest)

if __name__=='__main__':
    main()
