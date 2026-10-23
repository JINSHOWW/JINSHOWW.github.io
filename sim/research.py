"""2차 연구: 10개 코인 돌파+5일선필터 포트폴리오를 더 다듬는다.
  1) 비중 다시 맞추기(리밸런싱) 주기   2) 변동 큰 코인 적게 사기(변동성 역가중)   3) 4시간봉
돌파 공식은 다음 봉 시가에 팔아 현금이 되므로 리밸런싱에 추가 수수료가 없다."""
import sys
from backtest import CASH, breakout, candles, sma
from portfolio import COINS, mdd

YEAR_DAYS = 365


def load(n, unit="days"):
    data = {c: candles(f"KRW-{c}", n, unit) for c in COINS}
    data = {c: d for c, d in data.items() if len(d) >= n}
    common = set.intersection(*({x["t"] for x in d} for d in data.values()))
    data = {c: [x for x in d if x["t"] in common] for c, d in data.items()}
    return data, [x["t"] for x in data["BTC"]]


def multipliers(data, dates, allow=None):
    """코인별로 봉마다 돌파 공식 자산이 몇 배가 됐는지, 그리고 총 거래 횟수."""
    out, trades = {}, 0
    for c, d in data.items():
        curve = {}
        trades += breakout(d, 0.5, True, allow=allow, curve=curve)[1]
        vals, last = [], CASH
        for t in dates:
            last = curve.get(t, last)
            vals.append(last)
        out[c] = [1.0] + [vals[j] / vals[j - 1] for j in range(1, len(vals))]
    return out, trades


def equal(data, j):
    return {c: 1 / len(data) for c in data}


def inverse_vol(lookback):
    """최근 lookback봉 종가 변동(표준편차)이 클수록 적게. 어제까지 데이터만 씀."""
    def weigh(data, j):
        if j <= lookback:
            return equal(data, j)
        inv = {}
        for c, d in data.items():
            r = [d[i]["c"] / d[i - 1]["c"] - 1 for i in range(j - lookback, j)]
            m = sum(r) / len(r)
            inv[c] = 1 / ((sum((x - m) ** 2 for x in r) / len(r)) ** 0.5 or 1e-9)
        s = sum(inv.values())
        return {c: v / s for c, v in inv.items()}
    return weigh


def simulate(data, mult, weigh, every):
    value, values, hold = CASH, [], {}
    for j in range(len(mult["BTC"])):
        if j == 0 or (every and j % every == 0):
            hold = {c: value * w for c, w in weigh(data, j).items()}
        for c in hold:
            hold[c] *= mult[c][j]
        value = sum(hold.values())
        values.append(value)
    return values


def report(name, values, per_year, trades=None):
    yearly = "  ".join(f"{values[min(y + per_year - 1, len(values) - 1)] / values[y] - 1:+6.1%}"
                       for y in range(0, len(values) - 1, per_year))
    t = f"{trades:>6}" if trades is not None else " " * 6
    print(f"{name:<26}{values[-1]:>10,.0f}{values[-1] / CASH - 1:>9.1%}{mdd(values):>9.1%}{t}   {yearly}")


def header():
    print(f"{'방법':<26}{'최종금액':>10}{'수익률':>9}{'최대낙폭':>9}{'거래':>6}   1년차  2년차  3년차")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1095

    data, dates = load(days)
    btc = [x["c"] for x in data["BTC"]]
    bull = {dates[i] for i in range(20, len(dates)) if btc[i - 1] > sma(btc, 20, i - 1)}
    mult, trades = multipliers(data, dates)
    mult_bull, trades_bull = multipliers(data, dates, bull)
    print(f"[일봉] 코인 {len(data)}개, {dates[0]} ~ {dates[-1]}, 시작 10만원")
    header()
    report("똑같이, 처음 한 번만", simulate(data, mult, equal, None), YEAR_DAYS, trades)
    report("똑같이, 1년마다 재조정", simulate(data, mult, equal, 365), YEAR_DAYS, trades)
    report("똑같이, 30일마다 재조정", simulate(data, mult, equal, 30), YEAR_DAYS, trades)
    for lb in (30, 90):
        report(f"변동성역가중({lb}일), 30일", simulate(data, mult, inverse_vol(lb), 30), YEAR_DAYS, trades)
    report("변동성역가중(90일)+BTC필터", simulate(data, mult_bull, inverse_vol(90), 30), YEAR_DAYS, trades_bull)

    print("\n90일 변동성역가중 비중 예시 (마지막 재조정 시점):")
    w = inverse_vol(90)(data, (len(dates) - 1) // 30 * 30)
    print("  " + "  ".join(f"{c} {v:.0%}" for c, v in sorted(w.items(), key=lambda x: -x[1])))

    per_year = YEAR_DAYS * 6
    data4, dates4 = load(days * 6, "minutes/240")
    mult4, trades4 = multipliers(data4, dates4)
    print(f"\n[4시간봉] 코인 {len(data4)}개, {dates4[0]} ~ {dates4[-1]}, 시작 10만원")
    header()
    report("똑같이, 처음 한 번만", simulate(data4, mult4, equal, None), per_year, trades4)
    report("변동성역가중(90일), 30일", simulate(data4, mult4, inverse_vol(540), 180), per_year, trades4)
