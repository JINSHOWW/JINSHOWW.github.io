"""미국 주식 백테스트: 큰 종목 5개에 2만원씩, 코인에서 배운 공식을 그대로 시험한다.
처음부터 현실 체결(다음 봉 시가 + 수수료 + 미끄러짐)로만 계산. 금액은 달러 기준 수익률을 원화 10만원에 적용
(환율 변동·환전 수수료는 제외)."""
import json, urllib.request
import backtest as bt

STOCKS = "NVDA,MSFT,AAPL,GOOGL,AMZN".split(",")
BENCH = "SPY,QQQ".split(",")
PER = 20_000
SLIP = 0.0002
FEES = {"우대 0.07%": 0.0007, "기본 0.25%": 0.0025}
FRAMES = [("1d", "3y", "일봉 (3년)"), ("60m", "730d", "1시간봉 (2년)"), ("5m", "60d", "5분봉 (60일)")]
RULES = {
    "돌파+5봉필터": lambda d: bt.breakout(d, 0.5, True),
    "이동평균 5/20": lambda d: bt.run(d, bt.ma_cross(5, 20), lag=True),
    "MACD": lambda d: bt.run(d, bt.macd_rule(), lag=True),
    "골든크로스50/200": lambda d: bt.run(d, bt.ma_cross(50, 200), lag=True),
    "터틀 20/10": lambda d: bt.run(d, bt.turtle, lag=True),
    "RSI 30/70": lambda d: bt.run(d, bt.rsi_rule, lag=True),
    "볼린저밴드": lambda d: bt.run(d, bt.bollinger, lag=True),
}


def yahoo(symbol, interval, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={rng}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    r = json.load(urllib.request.urlopen(req, timeout=20))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    rows = zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])
    return [{"t": t, "o": o, "h": h, "l": l, "c": c} for t, o, h, l, c in rows if None not in (o, h, l, c)]


def won(results):
    return sum(v / bt.CASH * PER for v in results)


if __name__ == "__main__":
    start = PER * len(STOCKS)
    for interval, rng, name in FRAMES:
        data = {s: yahoo(s, interval, rng) for s in STOCKS + BENCH}
        stocks = {s: data[s] for s in STOCKS}
        hold = won(d[-1]["c"] / d[0]["c"] * bt.CASH for d in stocks.values())
        bench = "  ".join(f"{b} {data[b][-1]['c'] / data[b][0]['c'] - 1:+.0%}" for b in BENCH)
        print(f"\n[{name}] 봉 {len(stocks['NVDA']):,}개, 시작 {start:,}원")
        print(f"  5종목 그냥 보유: {hold:,.0f}원 ({hold / start - 1:+.1%})   지수 보유: {bench}")
        print(f"  {'공식':<14}" + "".join(f"{f:>18}" for f in FEES) + f"{'거래':>7}   종목별(기본 수수료)")
        for rule_name, rule in RULES.items():
            cols, trades = [], 0
            for fee in FEES.values():
                bt.FEE = fee + SLIP
                res = {s: rule(d) for s, d in stocks.items()}
                cols.append(won(v for v, *_ in res.values()))
                trades = sum(t for _, t, _ in res.values())
            per = " ".join(f"{s} {v / bt.CASH - 1:+.0%}" for s, (v, *_) in res.items())
            print(f"  {rule_name:<14}" + "".join(f"{v:>10,.0f}({v / start - 1:+5.0%})" for v in cols)
                  + f"{trades:>7,}   {per}")
