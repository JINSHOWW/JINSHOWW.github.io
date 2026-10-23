"""김프 자동매매 봇 (업비트). 하루 한 번 실행 (cron 09:05 KST).
규칙: 김치프리미엄 ≤ 0% 이면 코인마다 2만원 시장가 매수, ≥ 3% 이면 그 코인 전량 시장가 매도.
기본은 연습 모드(주문 안 냄). LIVE=1 일 때만 실제 주문.
필요한 환경변수: UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY  (출금 권한 없는 키, 서버 IP 등록)"""
import base64, hashlib, hmac, json, os, sys, time, uuid
import urllib.parse, urllib.request

COINS = "BTC,ETH,XRP,SOL,DOGE".split(",")
PER_COIN = 20_000          # 코인당 매수 금액(원)
BUDGET = 100_000           # 이 봉이 쓸 수 있는 최대 금액(원)
BUY_AT, SELL_AT = 0.0, 0.03
MIN_ORDER = 5_000          # 업비트 최소 주문 금액
LIVE = os.environ.get("LIVE") == "1"
API = "https://api.upbit.com/v1"


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    return json.load(urllib.request.urlopen(req, timeout=15))


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def token(params=None):
    """업비트 인증용 JWT (HS256). 파라미터가 있으면 SHA512 query_hash 포함."""
    payload = {"access_key": os.environ["UPBIT_ACCESS_KEY"], "nonce": str(uuid.uuid4())}
    if params:
        q = urllib.parse.urlencode(params).encode()
        payload.update(query_hash=hashlib.sha512(q).hexdigest(), query_hash_alg="SHA512")
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = hmac.new(os.environ["UPBIT_SECRET_KEY"].encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"Bearer {head}.{body}.{b64(sig)}"


def accounts():
    return {a["currency"]: float(a["balance"]) for a in get(f"{API}/accounts", {"Authorization": token()})}


def order(params):
    if not LIVE:
        return {"dry_run": params}
    req = urllib.request.Request(f"{API}/orders", data=json.dumps(params).encode(), method="POST",
                                 headers={"Authorization": token(params), "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=15))


def usd_krw():
    try:
        return get("https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?interval=1d&range=5d")[
            "chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return get("https://open.er-api.com/v6/latest/USD")["rates"]["KRW"]


def kimchi_premium():
    upbit = get(f"{API}/ticker?markets=KRW-BTC")[0]["trade_price"]
    usd = float(get("https://api.exchange.coinbase.com/products/BTC-USD/ticker")["price"])
    fx = usd_krw()
    return upbit / (usd * fx) - 1, upbit, usd, fx


def main():
    kimp, upbit, usd, fx = kimchi_premium()
    prices = {t["market"][4:]: t["trade_price"]
              for t in get(f"{API}/ticker?markets=" + ",".join(f"KRW-{c}" for c in COINS))}
    bal = accounts()
    held = {c: bal.get(c, 0) * prices[c] >= MIN_ORDER for c in COINS}
    invested = sum(bal.get(c, 0) * prices[c] for c in COINS)
    print(f"{time.strftime('%Y-%m-%d %H:%M')} {'실전' if LIVE else '연습'} | 김프 {kimp:+.2%} "
          f"(업비트 {upbit:,.0f}원, 해외 ${usd:,.0f}, 환율 {fx:,.1f}) | 원화 {bal.get('KRW', 0):,.0f}원, "
          f"코인 평가 {invested:,.0f}원 | 보유 {[c for c in COINS if held[c]]}")

    for c in COINS:
        if kimp <= BUY_AT and not held[c]:
            if invested + PER_COIN > BUDGET or bal.get("KRW", 0) < PER_COIN * 1.0005:  # 수수료 0.05% 포함
                print(f"  {c} 매수 건너뜀: 예산 또는 원화 부족")
                continue
            print(f"  {c} 매수 {PER_COIN:,}원 →", order({"market": f"KRW-{c}", "side": "bid",
                                                        "ord_type": "price", "price": str(PER_COIN)}))
            invested += PER_COIN
            bal["KRW"] = bal.get("KRW", 0) - PER_COIN * 1.0005
        elif kimp >= SELL_AT and held[c]:
            vol = bal[c]
            print(f"  {c} 전량 매도 {vol} →", order({"market": f"KRW-{c}", "side": "ask",
                                                   "ord_type": "market", "volume": str(vol)}))
    if BUY_AT < kimp < SELL_AT:
        print("  신호 없음: 그대로 유지")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # cron 로그에 남기고 다음 날 다시 시도
        print(f"{time.strftime('%Y-%m-%d %H:%M')} 오류: {e!r}", file=sys.stderr)
        sys.exit(1)
