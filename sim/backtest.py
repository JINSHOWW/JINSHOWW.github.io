"""Upbit 모의투자 백테스트: 가상 10만원으로 매매 기준 4개를 비교한다."""
import json, sys, time, urllib.request

FEE = 0.0005          # 업비트 KRW 마켓 수수료 0.05%
CASH = 100_000


def candles(market, days):
    """업비트 공개 API에서 일봉을 오래된 순으로 가져온다 (200개씩)."""
    out, to = [], ""
    while len(out) < days:
        url = f"https://api.upbit.com/v1/candles/days?market={market}&count=200" + (f"&to={to}" if to else "")
        batch = json.load(urllib.request.urlopen(url, timeout=15))
        if not batch:
            break
        out += batch
        to = batch[-1]["candle_date_time_utc"]
        time.sleep(0.15)  # 초당 요청 제한
    return [{"o": c["opening_price"], "h": c["high_price"], "l": c["low_price"], "c": c["trade_price"]}
            for c in reversed(out[:days])]


def sma(xs, n, i):
    return sum(xs[i - n + 1:i + 1]) / n


def rsi(cl, n, i):
    gains = [max(cl[j] - cl[j - 1], 0) for j in range(i - n + 1, i + 1)]
    losses = [max(cl[j - 1] - cl[j], 0) for j in range(i - n + 1, i + 1)]
    return 100 if sum(losses) == 0 else 100 - 100 / (1 + sum(gains) / sum(losses))


# 각 기준은 (i일째) -> "buy" / "sell" / None 을 돌려준다. 체결은 i일 종가.
def ma_cross(d, cl, i, held):
    if i < 20: return None
    fast, slow = sma(cl, 5, i), sma(cl, 20, i)
    return "buy" if fast > slow and not held else "sell" if fast < slow and held else None


def rsi_rule(d, cl, i, held):
    if i < 15: return None
    r = rsi(cl, 14, i)
    return "buy" if r < 30 and not held else "sell" if r > 70 and held else None


def run(d, rule):
    cl = [x["c"] for x in d]
    cash, coin, trades, peak, mdd = CASH, 0.0, 0, CASH, 0.0
    for i in range(len(d)):
        sig = rule(d, cl, i, coin > 0)
        if sig == "buy":
            coin, cash, trades = cash * (1 - FEE) / cl[i], 0, trades + 1
        elif sig == "sell":
            cash, coin, trades = coin * cl[i] * (1 - FEE), 0, trades + 1
        value = cash + coin * cl[i]
        peak = max(peak, value)
        mdd = max(mdd, 1 - value / peak)
    return cash + coin * cl[-1], trades, mdd


def breakout(d, k=0.5):
    """변동성 돌파: 전날 변동폭*k 만큼 오르면 매수, 다음날 시가에 매도."""
    cash, trades, peak, mdd = CASH, 0, CASH, 0.0
    for i in range(1, len(d) - 1):
        target = d[i]["o"] + (d[i - 1]["h"] - d[i - 1]["l"]) * k
        if d[i]["h"] >= target:
            cash = cash * (1 - FEE) / target * d[i + 1]["o"] * (1 - FEE)
            trades += 2
        peak = max(peak, cash)
        mdd = max(mdd, 1 - cash / peak)
    return cash, trades, mdd


def hold(d):
    cl = [x["c"] for x in d]
    peak, mdd = cl[0], 0.0
    for c in cl:
        peak = max(peak, c)
        mdd = max(mdd, 1 - c / peak)
    return CASH * (1 - FEE) ** 2 * cl[-1] / cl[0], 2, mdd


if __name__ == "__main__":
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 365
    for market in (sys.argv[1] if len(sys.argv) > 1 else "KRW-BTC,KRW-ETH,KRW-XRP").split(","):
        d = candles(market, days)
        print(f"\n[{market}] 최근 {len(d)}일, 시작 10만원")
        print(f"{'기준':<14}{'최종금액':>12}{'수익률':>9}{'거래':>6}{'최대낙폭':>9}")
        for name, (v, t, m) in {
            "그냥 보유": hold(d),
            "이동평균 5/20": run(d, ma_cross),
            "RSI 30/70": run(d, rsi_rule),
            "변동성 돌파": breakout(d),
        }.items():
            print(f"{name:<14}{v:>12,.0f}{v / CASH - 1:>9.1%}{t:>6}{m:>9.1%}")
