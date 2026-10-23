# PC에서 이어하기

모바일 세션(2026-10-23)에서 하던 일을 PC에서 이어가기 위한 문서. 새 Claude 세션은 이 파일부터 읽는다.

## 지금까지 한 것

1. **graphify · ponytail · caveman 연동**: `.claude/settings.json`, `.claude/skills/graphify/`, `CLAUDE.md` (main에 병합됨)
2. **모의투자 연구**: `sim/` 폴더. 결과와 배운 점은 `sim/LEARNINGS.md` (28개 항목)
   - 결론: 단타는 수수료에 다 졌다. 가장 쓸 만한 건 **김치프리미엄 규칙** (3년 +235% vs 보유 +107%, 검증 통과)
3. **김프 자동매매 봇**: `bot/kimp_bot.py` (작성 완료, 기본 연습 모드)
   - 규칙: BTC ETH XRP SOL DOGE, 김프 ≤ 0% 이면 코인마다 2만원 매수, ≥ 3% 이면 전량 매도. 총 10만원 한도
   - 인증 토큰(JWT)은 PyJWT로 검증 완료
   - **남은 것**: `bot/test_bot.py` 실행(모바일 환경에선 권한 검사에 막힘), 실제 업비트 연결 확인, 서버 설정

## PC에서 할 일 (순서대로)

### 1. Claude Code + 저장소 준비

```bash
git clone https://github.com/JINSHOWW/JINSHOWW.github.io
cd JINSHOWW.github.io
claude
```

### 2. 도구 연동 (처음에 했던 것)

```bash
uv tool install graphifyy        # 또는 pipx install graphifyy  (패키지 이름 y 두 개!)
graphify update .                # 지식 그래프 만들기
```

- ponytail, caveman: Claude Code를 저장소에서 열면 `.claude/settings.json` 때문에 플러그인 설치를 물어봄 → 허용
  - 안 물어보면 직접: `/plugin marketplace add DietrichGebert/ponytail` → `/plugin install ponytail@ponytail`,
    `/plugin marketplace add juliusbrussee/caveman` → `/plugin install caveman@caveman`
- caveman 말투가 불편하면 `/caveman off`

### 3. 봇 테스트 권한 열기

Claude Code에서 `/permissions` → Allow 에 아래 추가 (봇 테스트·연습 실행만 허용):

```
Bash(python3 bot/test_bot.py)
Bash(python3 bot/kimp_bot.py)
```

그다음 Claude에게: **"HANDOFF.md 보고 김프 봇 테스트부터 이어서 해줘"**

### 4. 서버 (고정 IP 필요)

업비트 API 키는 등록한 IP에서만 동작한다. 추천: 오라클 클라우드 Always Free (서울 리전) VM + 예약 공인 IP.
집 PC를 24시간 켜두고 써도 된다 (공유기 공인 IP가 고정인지 확인).

```bash
# 서버에서
git clone https://github.com/JINSHOWW/JINSHOWW.github.io && cd JINSHOWW.github.io
python3 bot/test_bot.py                  # 오프라인 테스트
```

### 5. 업비트 API 키

업비트 → 마이페이지 → Open API 관리:
- 권한: **자산조회, 주문조회, 주문하기만**. **출금하기는 절대 체크하지 않기**
- 허용 IP: 서버 공인 IP
- 키는 서버에만 저장. 저장소·채팅에 올리지 않기

```bash
# 서버에서, 저장소 밖에 키 파일 만들기
cat > ~/.kimp_env <<'EOF'
export UPBIT_ACCESS_KEY=여기에_액세스키
export UPBIT_SECRET_KEY=여기에_시크릿키
EOF
chmod 600 ~/.kimp_env
```

### 6. 연습 모드로 며칠

```bash
crontab -e
# 매일 09:05 KST (서버 시간이 UTC면 00:05)
5 0 * * * . ~/.kimp_env && cd ~/JINSHOWW.github.io && python3 bot/kimp_bot.py >> ~/kimp.log 2>&1
```

`~/kimp.log` 에 "연습 | 김프 +x.xx% ..." 가 매일 찍히는지 확인. 주문 대신 `{'dry_run': ...}` 만 나와야 정상.

### 7. 실전 전환

며칠 로그가 정상이면 cron 줄에서 `python3` 앞에 `LIVE=1 ` 추가. 업비트 원화 계좌에 10만원 이상 넣어두기
(수수료 때문에 5개 다 사려면 100,050원 필요).

## 주의

- 규칙은 3년 데이터로만 확인됐다. 10만원이 줄어들 수 있다.
- 이 저장소는 공개(GitHub Pages). 매매 기록·키·잔고를 커밋하지 않는다.
- 실제 주문 관련 작업은 Claude가 한 건씩 확인받고 진행한다.
