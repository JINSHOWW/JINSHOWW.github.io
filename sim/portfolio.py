"""10만원을 여러 코인에 똑같이 나눠 투자할 때를 비교한다.
코인은 '지금 잘나가는 것'이 아니라 3년 전부터 상장돼 있던 주요 코인으로 미리 고정 (생존 편향 줄이기)."""
import sys
from backtest import CASH, FEE, breakout, candles, sma

COINS = "BTC,ETH,XRP,SOL,DOGE,ADA,TRX,LINK,AVAX,DOT".split(",")


def mdd(values):
    peak, worst = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        worst = max(worst, 1 - v / peak)
    return worst


def report(name, values, dates):
    yearly = "  ".join(f"{values[min(y + 364, len(values) - 1)] / values[y] - 1:+6.1%}"
                       for y in range(0, len(values) - 1, 365))
    print(f"{name:<22}{values[-1]:>10,.0f}{values[-1] / CASH - 1:>9.1%}{mdd(values):>9.1%}   {yearly}")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1095
    data = {c: candles(f"KRW-{c}", days) for c in COINS}
    data = {c: d for c, d in data.items() if len(d) >= days}  # 3년 안 된 코인은 제외
    common = set.intersection(*({x["t"] for x in d} for d in data.values()))
    data = {c: [x for x in d if x["t"] in common] for c, d in data.items()}
    dates = [x["t"] for x in data["BTC"]]
    n = len(data)

    # 시장 필터: 어제 비트코인 종가가 20일 평균 위일 때만 진입 (하락장엔 전부 현금)
    btc = [x["c"] for x in data["BTC"]]
    bull = {dates[i] for i in range(20, len(dates)) if btc[i - 1] > sma(btc, 20, i - 1)}

    def split_breakout(allow=None):
        total = [0.0] * len(dates)
        for d in data.values():
            curve = {}
            breakout(d, 0.5, True, allow=allow, curve=curve)
            last = CASH
            for j, t in enumerate(dates):
                last = curve.get(t, last)
                total[j] += last / n
        return total

    hold = [sum(d[j]["c"] / d[0]["c"] * (1 - FEE) ** 2 for d in data.values()) * CASH / n
            for j in range(len(dates))]
    btc_only = {}
    breakout(data["BTC"], 0.5, True, curve=btc_only)
    btc_curve, last = [], CASH
    for t in dates:
        last = btc_only.get(t, last)
        btc_curve.append(last)

    print(f"코인 {n}개: {', '.join(data)}  /  {dates[0]} ~ {dates[-1]}, 시작 10만원 (코인당 {CASH // n:,}원)")
    print(f"{'방법':<22}{'최종금액':>10}{'수익률':>9}{'최대낙폭':>9}   연도별 수익률(1년차 2년차 3년차)")
    report("10개 그냥 보유", hold, dates)
    report("BTC 하나 돌파+필터", btc_curve, dates)
    report("10개 나눠 돌파+필터", split_breakout(), dates)
    report("10개 나눠 돌파+필터+BTC필터", split_breakout(bull), dates)
    print("\n코인별 돌파+필터 (각 10만원 기준):")
    for c, d in data.items():
        v = breakout(d, 0.5, True)
        print(f"  {c:<5}{v[0] / CASH - 1:>+8.1%}  최대낙폭 {v[2]:.1%}  (그냥 보유 {d[-1]['c'] / d[0]['c'] - 1:+.1%})")
