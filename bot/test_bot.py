"""김프 봇 오프라인 테스트: 가짜 키·가짜 시세·가짜 잔고, 연습 모드. 실제 주문이나 네트워크 요청 없음.
실행: python3 bot/test_bot.py   (pyjwt 가 있으면 인증 토큰도 검증)"""
import hashlib, os, sys, urllib.parse

os.environ.update(UPBIT_ACCESS_KEY="test-access", UPBIT_SECRET_KEY="test-secret-key-for-offline-checks")
os.environ.pop("LIVE", None)
sys.path.insert(0, os.path.dirname(__file__))
import kimp_bot as k

assert not k.LIVE

try:
    import jwt
    p = {"market": "KRW-BTC", "side": "bid", "ord_type": "price", "price": "20000"}
    d = jwt.decode(k.token(p)[7:], os.environ["UPBIT_SECRET_KEY"], algorithms=["HS256"])
    assert d["query_hash"] == hashlib.sha512(urllib.parse.urlencode(p).encode()).hexdigest()
    print("인증 토큰 OK")
except ImportError:
    print("pyjwt 없음: 토큰 검증 건너뜀 (pip install pyjwt)")

PRICES = {"BTC": 150_000_000, "ETH": 5_000_000, "XRP": 3_000, "SOL": 250_000, "DOGE": 300}
k.get = lambda url, h=None: [{"market": f"KRW-{c}", "trade_price": p} for c, p in PRICES.items()]
orders = []
real_order = k.order
k.order = lambda params: orders.append(params) or real_order(params)

CASES = [  # (이름, 김프, 잔고, 기대: 매수 코인 수, 매도 코인 수)
    ("역프 -0.5%, 빈 계좌 10만1천원 (수수료 포함)", -0.005, {"KRW": 101_000}, 5, 0),
    ("역프, 원화 딱 10만원 → 수수료 때문에 4개만", -0.005, {"KRW": 100_000}, 4, 0),
    ("김프 +3.5%, BTC·XRP 보유", 0.035, {"KRW": 60_000, "BTC": 0.000133, "XRP": 6.6}, 0, 2),
    ("김프 +1%, 신호 없음", 0.01, {"KRW": 100_000}, 0, 0),
    ("역프인데 원화 3만원뿐", -0.01, {"KRW": 30_000}, 1, 0),
    ("역프, 이미 5개 다 보유", -0.01, {"KRW": 0, **{c: 20_000 / p for c, p in PRICES.items()}}, 0, 0),
]
for name, kimp, bal, want_buy, want_sell in CASES:
    orders.clear()
    k.kimchi_premium = lambda kimp=kimp: (kimp, 1, 1, 1)
    k.accounts = lambda bal=bal: dict(bal)
    print(f"\n## {name}")
    k.main()
    buys = sum(o["side"] == "bid" for o in orders)
    sells = sum(o["side"] == "ask" for o in orders)
    assert (buys, sells) == (want_buy, want_sell), f"{name}: 매수 {buys}/매도 {sells}, 기대 {want_buy}/{want_sell}"
print("\n모든 테스트 통과")
