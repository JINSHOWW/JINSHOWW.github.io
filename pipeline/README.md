# 영상 파이프라인

```bash
python3 pipeline/check_tools.py            # 도구 점검 (ffmpeg, 글꼴, VOICEVOX, .env 키 유무)
python3 pipeline/run.py <이야기ID>          # validate → images → tts → subs → compose → qc
python3 pipeline/run.py <이야기ID> tts subs # 일부 단계만
```

원고 작성(1~4단계), `review.md` 의 원고 검토, `metadata.md`(10단계)는 스크립트가 아니라 사람/Claude 가 쓴다.

| 스크립트 | 하는 일 | 결과 |
|---|---|---|
| validate.py | script_ja.json 형식·태그·문장 길이·추정 길이 검사 | 콘솔 |
| images.py | OPENAI_API_KEY 있으면 생성, 없으면 단색+번호 임시 이미지 | images/scene_NN.png, images/prompts.md |
| tts.py | 채널 A: VOICEVOX / B: ElevenLabs(없으면 VOICEVOX 대체). 길이 실측 | audio/scene_NN.wav, audio/timeline.json |
| subs.py | 실측 타이밍으로 일본어+한글 자막 | subs.srt, .work/main.ass |
| sfx.py | 바람·비·장작 등 효과음을 직접 합성 (외부 음원 없음) | pipeline/.cache/sfx/ |
| compose.py | 느린 확대·이동 + 디졸브, 배경음 믹스, -14 LUFS, 자막 굽기 | output/main.mp4, short.mp4, thumbnail.png, chapters.txt, audio_credits.json |
| qc.py | ffprobe·음량·싱크 자동 검사, 프레임 추출 → review.md 에 추가 | output/qc/ |

## 연출 태그 (`direction`)

| 태그 | 뜻 |
|---|---|
| `pause:2` | 장면 낭독 뒤 2초 정적 |
| `pre:1` | 장면 낭독 앞 1초 정적 |
| `speed:0.9` | 이 장면만 낭독 속도 ×0.9 (채널 기본 속도에 곱함) |
| `pitch:-0.03` | 음높이 조정 (VOICEVOX) |
| `sfx:footsteps` | 장면 시작에 효과음. wind/rain 같은 배경류 이름이면 그 장면 동안만 반복 |
| `bed:rain` | 이 장면부터 배경음 교체 (`bed:none` 은 끔). 기본값은 채널 설정 |
| `cam:zoom_in` | 카메라: zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down, still. 없으면 이야기마다 다른 순서로 자동 |
| `short` | 쇼츠에 넣을 장면 (연속 구간, 59초 이내). 없으면 정적·효과음이 몰린 구간을 자동 선택 |

효과음 이름: wind, night, rain, fire, stream, drone (배경류) / footsteps, heartbeat, bell, thud (단발).
외부 무료 음원을 쓰려면 `assets/sfx/<이름>.wav` 와 `assets/sfx/SOURCES.md` 에 출처 줄을 함께 둔다.

선택 항목: `scenes[].chapter` (챕터 이름), 최상위 `thumbnail: {"scene": 3, "text": "..."}`, `short_title_ja`.

## 목소리 고정

`config.json` 에 채널별 목소리를 두고, 처음 합성한 목소리를 `voice_lock.json` 에 기록한다.
다른 목소리가 선택되면(예: ElevenLabs 키가 생기거나 사라짐) 멈춘다. 의도한 변경이면 `--relock`.
채널 B 에 ElevenLabs 를 쓰려면 `config.json` 의 `channels.B.voice.voice_id` 를 정해야 한다.

## 시험

`tts.py <ID> --engine dummy` 는 글자 수만큼의 가짜 소리로 파이프라인만 시험한다. qc 가 실패로 표시하며 공개용 결과물에 쓰면 안 된다.
