"""Upbit 모의투자 백테스트: 가상 10만원으로 유명 매매 공식을 비교하고,
앞 기간으로 설정을 고른 뒤 처음 보는 뒤 기간에 시험한다(학습/검증)."""
import json, sys, time, urllib.request

FEE = 0.0005          # 업비트 KRW 마켓 수수료 0.05%
CASH = 100_000


def candles(market, days, unit="days"):
    """업비트 공개 API에서 봉을 오래된 순으로 가져온다 (200개씩). unit: days 또는 minutes/240 등.
    days 는 가져올 봉 개수."""
    out, to = [], ""
    while len(out) < days:
        url = f"https://api.upbit.com/v1/candles/{unit}?market={market}&count=200" + (f"&to={to}" if to else "")
        batch = json.load(urllib.request.urlopen(url, timeout=15))
        if not batch:
            break
        out += batch
        to = batch[-1]["candle_date_time_utc"]
        time.sleep(0.15)  # 초당 요청 제한
    return [{"t": c["candle_date_time_kst"][:10 if unit == "days" else 16], "o": c["opening_price"], "h": c["high_price"],
             "l": c["low_price"], "c": c["trade_price"]} for c in reversed(out[:days])]


# ---------- 지표 ----------
def sma(xs, n, i):
    return sum(xs[i - n + 1:i + 1]) / n if i >= n - 1 else None


def ema(xs, n):
    out, a = [xs[0]], 2 / (n + 1)
    for x in xs[1:]:
        out.append(out[-1] + a * (x - out[-1]))
    return out


def rsi(cl, n, i):
    if i < n: return None
    g = sum(max(cl[j] - cl[j - 1], 0) for j in range(i - n + 1, i + 1))
    l = sum(max(cl[j - 1] - cl[j], 0) for j in range(i - n + 1, i + 1))
    return 100 if l == 0 else 100 - 100 / (1 + g / l)


def std(xs, n, i):
    m = sma(xs, n, i)
    return (sum((x - m) ** 2 for x in xs[i - n + 1:i + 1]) / n) ** 0.5


# ---------- 공식들: (d, cl, i, held) -> 이날 종가 기준으로 들고 있을지(True/False) ----------
def ma_cross(fast, slow):
    def rule(d, cl, i, held):
        f, s = sma(cl, fast, i), sma(cl, slow, i)
        return held if s is None else f > s
    return rule


def rsi_rule(d, cl, i, held):
    r = rsi(cl, 14, i)
    return held if r is None else True if r < 30 else False if r > 70 else held


def bollinger(d, cl, i, held):
    """종가가 아래 밴드(20일 평균 - 2표준편차)를 뚫으면 매수, 평균선 회복하면 매도."""
    m = sma(cl, 20, i)
    if m is None: return held
    return True if cl[i] < m - 2 * std(cl, 20, i) else False if cl[i] > m else held


def macd_rule():
    cache = {}
    def rule(d, cl, i, held):
        if id(cl) not in cache:
            macd = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]
            cache[id(cl)] = (macd, ema(macd, 9))
        macd, sig = cache[id(cl)]
        return held if i < 35 else macd[i] > sig[i]
    return rule


def turtle(d, cl, i, held):
    """터틀: 20일 최고가 돌파 시 매수, 10일 최저가 이탈 시 매도."""
    if i < 20: return held
    if cl[i] > max(x["h"] for x in d[i - 20:i]): return True
    if cl[i] < min(x["l"] for x in d[i - 10:i]): return False
    return held


def run(d, rule, stop=None, start=0):
    """held 상태를 종가에 체결. stop=0.1 이면 산 값에서 10% 빠질 때 손절.
    start: 이 날부터 매매 (그 전 데이터는 지표 계산에만 쓰임)."""
    cl = [x["c"] for x in d]
    cash, coin, entry, trades, peak, mdd = CASH, 0.0, 0.0, 0, CASH, 0.0
    for i in range(start, len(d)):
        want = rule(d, cl, i, coin > 0)
        if stop and coin > 0 and cl[i] < entry * (1 - stop):
            want = False
        if want and coin == 0:
            coin, cash, entry, trades = cash * (1 - FEE) / cl[i], 0, cl[i], trades + 1
        elif not want and coin > 0:
            cash, coin, trades = coin * cl[i] * (1 - FEE), 0, trades + 1
        value = cash + coin * cl[i]
        peak = max(peak, value)
        mdd = max(mdd, 1 - value / peak)
    return cash + coin * cl[-1], trades, mdd


def breakout(d, k=0.5, ma_filter=False, start=0, allow=None, curve=None):
    """변동성 돌파: 시가 + 전날 변동폭*k 돌파 시 매수, 다음날 시가 매도.
    ma_filter: 시가가 5일 이동평균 위일 때만 (상승장에서만) 진입.
    allow: 진입을 허용할 날짜 집합 (없으면 전부). curve: 날짜별 평가금액을 담을 dict."""
    cl = [x["c"] for x in d]
    cash, trades, peak, mdd = CASH, 0, CASH, 0.0
    for i in range(max(5, start), len(d) - 1):
        target = d[i]["o"] + (d[i - 1]["h"] - d[i - 1]["l"]) * k
        if (d[i]["h"] >= target and (not ma_filter or d[i]["o"] > sma(cl, 5, i - 1))
                and (allow is None or d[i]["t"] in allow)):
            cash = cash * (1 - FEE) / target * d[i + 1]["o"] * (1 - FEE)
            trades += 2
        if curve is not None:
            curve[d[i + 1]["t"]] = cash
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


def dca(d):
    """적립식: 10만원을 매주 같은 금액으로 나눠 사고 끝까지 보유."""
    weeks = list(range(0, len(d), 7))
    coin, peak, mdd, spent = 0.0, 0.0, 0.0, 0.0
    for i, x in enumerate(d):
        if i in weeks:
            coin += CASH / len(weeks) * (1 - FEE) / x["c"]
            spent += CASH / len(weeks)
        value = coin * x["c"] + (CASH - spent)
        peak = max(peak, value)
        mdd = max(mdd, 1 - value / peak)
    return coin * d[-1]["c"] * (1 - FEE), len(weeks), mdd


STRATEGIES = {
    "그냥 보유": hold,
    "적립식(매주)": dca,
    "이동평균 5/20": lambda d: run(d, ma_cross(5, 20)),
    "5/20+손절10%": lambda d: run(d, ma_cross(5, 20), stop=0.1),
    "골든크로스50/200": lambda d: run(d, ma_cross(50, 200)),
    "RSI 30/70": lambda d: run(d, rsi_rule),
    "볼린저밴드": lambda d: run(d, bollinger),
    "MACD": lambda d: run(d, macd_rule()),
    "터틀 20/10": lambda d: run(d, turtle),
    "변동성돌파": breakout,
    "돌파+5일선필터": lambda d: breakout(d, ma_filter=True),
}


def row(name, v, t, m):
    print(f"{name:<16}{v:>10,.0f}{v / CASH - 1:>9.1%}{t:>6}{m:>9.1%}")


def learn(d, split):
    """앞 기간(학습)에서 이동평균 조합과 돌파 k값을 고르고, 처음 보는 뒤 기간(검증)에 그대로 적용."""
    train = d[:split]
    grid = [(f, s) for f in (3, 5, 10, 20) for s in (20, 30, 50, 100) if f < s]
    f, s = max(grid, key=lambda p: run(train, ma_cross(*p))[0])
    k = max((0.3, 0.4, 0.5, 0.6, 0.7), key=lambda k: breakout(train, k, True)[0])
    base = hold(d[split:])[0]
    for name, fn in ((f"학습한 이동평균 {f}/{s}", lambda x, st=0: run(x, ma_cross(f, s), start=st)),
                     (f"학습한 돌파+필터 k={k}", lambda x, st=0: breakout(x, k, True, start=st))):
        print(f"  {name}: 학습기간 {fn(train)[0] / CASH - 1:+.1%} → 검증기간 "
              f"{fn(d, split)[0] / CASH - 1:+.1%}  (검증기간 그냥 보유 {base / CASH - 1:+.1%})")


if __name__ == "__main__":
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 1095
    for market in (sys.argv[1] if len(sys.argv) > 1 else "KRW-BTC,KRW-ETH,KRW-XRP").split(","):
        d = candles(market, days)
        print(f"\n[{market}] {d[0]['t']} ~ {d[-1]['t']} ({len(d)}일), 시작 10만원")
        for y in range(0, len(d), 365):
            seg = d[y:y + 365]
            print(f"  {seg[0]['t'][:7]}~{seg[-1]['t'][:7]} 가격 변화 {seg[-1]['c'] / seg[0]['c'] - 1:+.1%}")
        print(f"{'공식':<16}{'최종금액':>10}{'수익률':>9}{'거래':>6}{'최대낙폭':>9}")
        for name, fn in STRATEGIES.items():
            row(name, *fn(d))
        split = len(d) * 2 // 3
        print(f"[학습/검증] 학습 {d[0]['t']}~{d[split - 1]['t']}, 검증 {d[split]['t']}~{d[-1]['t']}")
        learn(d, split)
