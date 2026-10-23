"""단타 연구: 가장 큰 코인 5개에 2만원씩, 봉 단위를 1분까지 줄여가며 비교한다.
같은 공식을 수수료 0% / 0.05% 로 각각 돌려서, 단타가 수수료 때문에 지는지 본다."""
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
RULES = {
    "돌파+5봉필터": lambda d: bt.breakout(d, 0.5, True),
    "이동평균 5/20": lambda d: bt.run(d, bt.ma_cross(5, 20)),
    "RSI 30/70": lambda d: bt.run(d, bt.rsi_rule),
    "볼린저밴드": lambda d: bt.run(d, bt.bollinger),
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
        print(f"  {'공식':<14}{'수수료 0%':>14}{'수수료 0.05%':>16}{'거래':>8}{'거래당 수수료로 잃은 몫':>14}")
        for rule_name, rule in RULES.items():
            bt.FEE = 0.0
            free, trades = total([rule(d)[:2] for d in data.values()])
            bt.FEE = 0.0005
            paid, _ = total([rule(d)[:2] for d in data.values()])
            per_trade = (free - paid) / trades if trades else 0
            print(f"  {rule_name:<14}{free:>10,.0f}({free / start - 1:+5.0%}){paid:>10,.0f}({paid / start - 1:+5.0%})"
                  f"{trades:>8,}{per_trade:>12,.0f}원")
