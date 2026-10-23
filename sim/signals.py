"""정보(심리·이벤트) 신호 시험. 모든 신호는 그 시점에 이미 공개된 값만 쓰고, 다음 봉 시가에 체결한다.
  코인: 공포·탐욕 지수, 김치프리미엄  (BTC ETH XRP SOL DOGE 2만원씩, 3년)
  미국 주식(SPY): VIX 공포 지수, FOMC 직전, 월말·월초  (20년)"""
import json, time, urllib.request
import backtest as bt
from us_stocks import yahoo

COINS = "BTC,ETH,XRP,SOL,DOGE".split(",")
PER = 20_000
CRYPTO_FEE, STOCK_FEE, SLIP = 0.0005, 0.0007, 0.0002
# FOMC 결정 발표일 (연준 공개 일정을 손으로 옮김)
FOMC = """2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16""".split()


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))


def day(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def when(series, test):
    """그날 값이 조건을 만족하면 True, 아니면 지금 상태 유지(None 은 상태 유지)."""
    def rule(d, cl, i, held):
        v = series.get(d[i]["t"])
        return held if v is None else test(v, held)
    return rule


def ffill(series, dates):
    out, last = {}, None
    for t in dates:
        last = series.get(t, last)
        out[t] = last
    return out


def stats(d, rule, lag=True):
    """(최종금액 10만원 기준, 거래수, 최대낙폭, 들고 있던 날 비율).
    lag=False 는 미리 정해진 달력 일정용: 그날 종가에 체결(장 마감 주문)."""
    held_days = 0
    def counting(dd, cl, i, held):
        nonlocal held_days
        held_days += held
        return rule(dd, cl, i, held)
    v, t, m = bt.run(d, counting, lag=lag)
    return v, t, m, held_days / len(d)


def line(name, rows, start):
    v = sum(r[0] / bt.CASH * (start / len(rows)) for r in rows)
    t = sum(r[1] for r in rows)
    m = max(r[2] for r in rows)
    inv = f"{sum(r[3] for r in rows) / len(rows):>8.0%}" if len(rows[0]) > 3 else f"{'-':>8}"
    print(f"  {name:<34}{v:>10,.0f}{v / start - 1:>9.1%}{t:>6}{m:>9.1%}{inv}")


def head(title):
    print(f"\n{title}\n  {'방법':<34}{'최종금액':>10}{'수익률':>9}{'거래':>6}{'최대낙폭':>9}{'보유비율':>8}")


def crypto():
    bt.FEE = CRYPTO_FEE + SLIP
    data = {c: bt.candles(f"KRW-{c}", 1095) for c in COINS}
    dates = [x["t"] for x in data["BTC"]]
    fng = {day(int(x["timestamp"])): int(x["value"]) for x in get("https://api.alternative.me/fng/?limit=0")["data"]}
    usd = {day(t): c for t, c in ((x["t"], x["c"]) for x in yahoo("BTC-USD", "1d", "5y"))}
    fx = ffill({day(x["t"]): x["c"] for x in yahoo("KRW=X", "1d", "5y")}, dates)
    kimp = {t: x["c"] / (usd[t] * fx[t]) - 1 for t, x in zip(dates, data["BTC"]) if t in usd and fx.get(t)}
    k = sorted(kimp.values())
    print(f"[코인 5개] {dates[0]} ~ {dates[-1]}, 시작 10만원 (현실 체결, 수수료 0.05% + 미끄러짐 0.02%)")
    print(f"  김치프리미엄 범위: 최저 {k[0]:+.1%}, 중간 {k[len(k) // 2]:+.1%}, 최고 {k[-1]:+.1%}  "
          f"/ 공포탐욕 데이터 {sum(t in fng for t in dates)}일")

    head("[코인] 공포·탐욕 지수 / 김치프리미엄  (최대낙폭은 가장 나빴던 코인)")
    always = lambda d, cl, i, held: True
    line("그냥 보유", [stats(d, always) for d in data.values()], 100_000)
    line("공포(≤25) 매수, 탐욕(≥75) 매도", [stats(d, when(fng, lambda v, h: True if v <= 25 else False if v >= 75 else h)) for d in data.values()], 100_000)
    line("보유하되 극탐욕(≥80) 매도, ≤50 재매수", [stats(d, when(fng, lambda v, h: False if v >= 80 else True if v <= 50 else h)) for d in data.values()], 100_000)
    line("보유하되 김프 ≥5% 매도, ≤2% 재매수", [stats(d, when(kimp, lambda v, h: False if v >= 0.05 else True if v <= 0.02 else h)) for d in data.values()], 100_000)
    line("역프(≤0%) 매수, 김프 ≥3% 매도", [stats(d, when(kimp, lambda v, h: True if v <= 0 else False if v >= 0.03 else h)) for d in data.values()], 100_000)

    kimp_check(data, dates, kimp)

    head("[코인] 돌파+5일선필터에 정보 필터 더하기 (돌파는 목표가 주문)")
    calm = {t for t in dates if fng.get(t, 50) < 75}
    fear_ok = {t for t in dates if fng.get(t, 50) <= 50}
    low_kimp = {dates[i] for i in range(1, len(dates)) if kimp.get(dates[i - 1], 0) < 0.03}
    for name, allow in (("돌파+필터 (기존)", None), ("+ 탐욕(≥75)일 땐 쉬기", calm),
                        ("+ 지수 50 이하일 때만", fear_ok), ("+ 어제 김프 3% 미만일 때만", low_kimp)):
        line(name, [bt.breakout(d, 0.5, True, allow=allow) for d in data.values()], 100_000)
    fomc_off = set(dates) - set(FOMC)
    line("+ FOMC 발표일엔 쉬기", [bt.breakout(d, 0.5, True, allow=fomc_off) for d in data.values()], 100_000)


def kimp_check(data, dates, kimp):
    """김프 규칙이 우연인지: 기준값을 바꿔도, 기간을 나눠도, 코인마다도 좋은지 본다."""
    rule = lambda lo, hi: when(kimp, lambda v, h: True if v <= lo else False if v >= hi else h)
    always = lambda d, cl, i, held: True
    split = len(dates) * 2 // 3
    print(f"\n[김프 검증] 기준값 표: 칸 = 3년 수익률 (그냥 보유 "
          f"{sum(stats(d, always)[0] for d in data.values()) / len(data) / bt.CASH - 1:+.0%})")
    his = (0.02, 0.03, 0.04, 0.05)
    print("  매수\\매도" + "".join(f"{f'≥{h:.0%}':>9}" for h in his))
    for lo in (-0.01, 0.0, 0.005, 0.01):
        print(f"  ≤{lo:+.1%}  " + "".join(
            f"{sum(stats(d, rule(lo, hi))[0] for d in data.values()) / len(data) / bt.CASH - 1:>+9.0%}" for hi in his))
    for name, a, b in (("앞 2년", 0, split), ("마지막 1년", split, len(dates))):
        seg = {c: d[a:b] for c, d in data.items()}
        r = sum(stats(d, rule(0, 0.03))[0] for d in seg.values()) / len(seg) / bt.CASH - 1
        h = sum(stats(d, always)[0] for d in seg.values()) / len(seg) / bt.CASH - 1
        print(f"  {name} ({dates[a]}~{dates[b - 1]}): 역프매수/김프3%매도 {r:+.0%}  vs 그냥 보유 {h:+.0%}")
    print("  코인별: " + "  ".join(f"{c} {stats(d, rule(0, 0.03))[0] / bt.CASH - 1:+.0%}"
                                   f"(보유 {stats(d, always)[0] / bt.CASH - 1:+.0%})" for c, d in data.items()))


def stocks():
    bt.FEE = STOCK_FEE + SLIP
    spy = [dict(x, t=day(x["t"])) for x in yahoo("SPY", "1d", "20y")]
    dates = [x["t"] for x in spy]
    vix = {day(x["t"]): x["c"] for x in yahoo("%5EVIX", "1d", "20y")}
    print(f"\n[미국 SPY] {dates[0]} ~ {dates[-1]} ({len(dates)}일), 시작 10만원 (현실 체결, 수수료 0.07% + 미끄러짐 0.02%, 현금 이자 제외)")

    head("[주식] VIX 공포 지수")
    line("SPY 그냥 보유", [stats(spy, lambda d, cl, i, held: True)], 100_000)
    after = {}
    for i, t in enumerate(dates):  # VIX 30 넘은 날부터 60거래일 동안 보유
        if vix.get(t, 0) > 30:
            for j in range(i, min(i + 60, len(dates))):
                after[dates[j]] = True
    line("VIX>30 뒤 60일만 보유", [stats(spy, lambda d, cl, i, held: after.get(d[i]["t"], False))], 100_000)
    line("보유하되 VIX>30이면 현금, <20 재매수", [stats(spy, when(vix, lambda v, h: False if v > 30 else True if v < 20 else h))], 100_000)
    line("VIX>25 매수, VIX<15 매도", [stats(spy, when(vix, lambda v, h: True if v > 25 else False if v < 15 else h))], 100_000)

    head("[주식] 달력 효과")
    month_end = set()
    for i in range(1, len(dates)):
        if dates[i][5:7] != dates[i - 1][5:7]:  # 새 달 첫 거래일 i: 전달 마지막날 종가에 사서 3번째 거래일 종가에 팜
            month_end.update(dates[i - 1:i + 2])
    line("월말·월초(마지막날~3일째)만 보유", [stats(spy, lambda d, cl, i, held: d[i]["t"] in month_end, lag=False)], 100_000)
    fomc_eve = {dates[i - 1] for i, t in enumerate(dates) if t in FOMC and i}
    line("FOMC 전날 종가~발표일 종가만 (2023~)", [stats(spy[next(i for i, t in enumerate(dates) if t >= "2023"):], lambda d, cl, i, held: d[i]["t"] in fomc_eve, lag=False)], 100_000)
    line("같은 기간 SPY 그냥 보유 (2023~)", [stats(spy[next(i for i, t in enumerate(dates) if t >= "2023"):], lambda d, cl, i, held: True)], 100_000)


if __name__ == "__main__":
    crypto()
    stocks()
