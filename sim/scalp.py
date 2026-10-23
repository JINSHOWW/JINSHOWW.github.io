"""단타 연구: 가장 큰 코인 5개에 2만원씩, 봉 단위를 1분까지 줄여가며 비교한다.
같은 공식을 수수료 0% / 0.05% / 현실 체결(다음 봉 시가 + 수수료 + 미끄러짐)로 돌려서,
단타가 무엇 때문에 지는지(혹은 착시인지) 본다."""
from concurrent.futures import ThreadPoolExecutor
import backtest as bt

COINS = "BTC,ETH,XRP,SOL,DOGE".split(",")
PER_COIN = 20_000
# (봉 단위, 이름, 가져올 봉 개수)  봉 개수는 업비트 요청 수를 맞추려고 단위마다 다르게
FRAMES = [
    ("minutes/1", "1분봉 (최근 7일)", 7 * 1440),
    ("minutes/5", "5분봉 (최근 30일)", 30 * 288),
    ("minutes/15", "15분봉 (최근 90일)", 90 * 96),
    ("minutes/60", "1시간봉 (최근 180일)", 180 * 24),
    ("days", "일봉 (최근 365일)", 365),
]
SLIP = 0.0002  # 호가 차이·미끄러짐 한 번에 0.02% 가정
RULES = {  # lag=True: 신호 본 다음 봉 시가에 체결 (돌파는 원래 목표가 주문이라 그대로)
    "돌파+5봉필터": lambda d, lag: bt.breakout(d, 0.5, True),
    "이동평균 5/20": lambda d, lag: bt.run(d, bt.ma_cross(5, 20), lag=lag),
    "RSI 30/70": lambda d, lag: bt.run(d, bt.rsi_rule, lag=lag),
    "볼린저밴드": lambda d, lag: bt.run(d, bt.bollinger, lag=lag),
}


def total(results):
    """코인별 (10만원 기준 최종금액, 거래수) -> 2만원씩 넣었을 때 합계."""
    return sum(v / bt.CASH * PER_COIN for v, _ in results), sum(t for _, t in results)


if __name__ == "__main__":
    start = PER_COIN * len(COINS)
    for unit, name, n in FRAMES:
        with ThreadPoolExecutor(len(COINS)) as ex:
            data = dict(zip(COINS, ex.map(lambda c: bt.candles(f"KRW-{c}", n, unit), COINS)))
        first = min(d[0]["t"] for d in data.values())
        last = max(d[-1]["t"] for d in data.values())
        hold = sum(d[-1]["c"] / d[0]["c"] * PER_COIN for d in data.values())
        print(f"\n[{name}] {first} ~ {last}, 봉 {n:,}개씩, 시작 {start:,}원")
        print(f"  그냥 보유: {hold:,.0f}원 ({hold / start - 1:+.1%})")
        print(f"  {'공식':<12}{'수수료 0%':>14}{'수수료 0.05%':>15}{'현실 체결':>15}{'거래':>8}")
        for rule_name, rule in RULES.items():
            cols = []
            for fee, lag in ((0.0, False), (0.0005, False), (0.0005 + SLIP, True)):
                bt.FEE = fee
                cols.append(total([rule(d, lag)[:2] for d in data.values()]))
            print(f"  {rule_name:<12}" + "".join(f"{v:>9,.0f}({v / start - 1:+5.0%})" for v, _ in cols)
                  + f"{cols[0][1]:>8,}")
        bt.FEE = 0.0005 + SLIP
        print("  볼린저 현실 체결 코인별: " + "  ".join(
            f"{c} {bt.run(d, bt.bollinger, lag=True)[0] / bt.CASH - 1:+.0%}" for c, d in data.items()))
