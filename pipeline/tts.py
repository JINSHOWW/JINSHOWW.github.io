"""장면별 음성 합성 + 길이 실측 → audio/scene_NN.wav, audio/timeline.json

- 채널 A: VOICEVOX 고정
- 채널 B: ELEVENLABS_API_KEY 가 있으면 ElevenLabs, 없으면 VOICEVOX 대체 목소리
- 처음 쓴 목소리를 pipeline/voice_lock.json 에 고정하고, 다른 목소리가 선택되면 멈춘다
- direction 의 pre/pause 는 무음으로, speed/pitch 는 합성 파라미터로 반영

사용: python3 pipeline/tts.py <이야기ID> [--force] [--relock]
      python3 pipeline/tts.py <이야기ID> --engine dummy   # 파이프라인 시험용 가짜 음성 (본편 금지)
"""
import hashlib
import json
import sys
import wave

import numpy as np
import requests

from common import (CACHE, PIPELINE, channel_cfg, env, load_config, load_script,
                    parse_direction, run, story_dir)

SR = load_config()["audio"]["sample_rate"]
LOCK = PIPELINE / "voice_lock.json"

VOICEVOX_HELP = """VOICEVOX 엔진에 연결할 수 없다 ({url}).
다음 중 하나로 실행한 뒤 다시 시도한다:
  1) Docker:  docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-latest
  2) 앱:      https://voicevox.hiroshiba.jp/ 에서 VOICEVOX 설치 후 실행 (엔진이 50021 포트로 뜬다)
  3) 다른 주소면 .env 에 VOICEVOX_URL=http://호스트:포트
확인: curl {url}/version"""


def voicevox_url():
    return env("VOICEVOX_URL") or "http://localhost:50021"


def voicevox_speaker_id(url, name, style):
    for sp in requests.get(f"{url}/speakers", timeout=10).json():
        if sp["name"] == name:
            for st in sp["styles"]:
                if st["name"] == style:
                    return st["id"]
    sys.exit(f"VOICEVOX 에 {name}（{style}）가 없다. /speakers 목록을 확인할 것")


def tts_voicevox(text, voice, d, url, spk):
    q = requests.post(f"{url}/audio_query", params={"text": text, "speaker": spk}, timeout=60)
    q.raise_for_status()
    q = q.json()
    q["speedScale"] = voice["speed"] * d["speed"]
    q["pitchScale"] = voice.get("pitch", 0.0) + d["pitch"]
    q["intonationScale"] = voice.get("intonation", 1.0)
    q["prePhonemeLength"] = 0.05
    q["postPhonemeLength"] = 0.1
    q["outputSamplingRate"] = SR
    q["outputStereo"] = False
    r = requests.post(f"{url}/synthesis", params={"speaker": spk}, json=q, timeout=300)
    r.raise_for_status()
    return r.content, "wav"


def tts_elevenlabs(text, voice, d, key):
    if not voice.get("voice_id"):
        sys.exit("pipeline/config.json 의 channels.B.voice.voice_id 를 정해야 한다 (목소리 고정)")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}",
        params={"output_format": "mp3_44100_192"},
        headers={"xi-api-key": key},
        json={"text": text, "model_id": voice["model_id"], "language_code": "ja",
              "voice_settings": {"stability": voice["stability"],
                                 "similarity_boost": voice["similarity_boost"],
                                 # ElevenLabs speed 허용 범위 0.7~1.2
                                 "speed": max(0.7, min(1.2, voice["speed"] * d["speed"]))}},
        timeout=300,
    )
    if r.status_code != 200:
        sys.exit(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    return r.content, "mp3"


def tts_dummy(text, voice, d):
    """시험용: 글자 수에 비례한 길이의 웅얼거리는 소리. 실제 영상에 쓰면 안 된다."""
    sec = max(1.0, len(text) / 7.0 / d["speed"])
    t = np.arange(int(sec * SR)) / SR
    env_ = 0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t) ** 2
    sig = 0.2 * env_ * np.sin(2 * np.pi * (140 + 20 * np.sin(2 * np.pi * 0.7 * t)) * t)
    return to_wav_bytes(sig), "wav"


def to_wav_bytes(sig):
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(sig, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def read_wav(path):
    with wave.open(str(path)) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32767


def trim_silence(sig, thresh=0.01):
    """앞뒤 무음 제거 (엔진마다 앞뒤 여백이 달라 타이밍이 흔들리는 것을 막는다)."""
    idx = np.where(np.abs(sig) > thresh)[0]
    if len(idx) == 0:
        return sig
    pad = int(0.03 * SR)
    return sig[max(0, idx[0] - pad): idx[-1] + pad]


def pick_voice(script, engine_override):
    cfg = channel_cfg(script)
    voice = cfg["voice"]
    if engine_override == "dummy":
        return "dummy", voice
    if voice["engine"] == "elevenlabs":
        if env("ELEVENLABS_API_KEY"):
            return "elevenlabs", voice
        voice = voice["fallback"]
    return voice["engine"], voice


def check_lock(channel, engine, voice, relock):
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
    ident = {"engine": engine, "voice": voice.get("voice_id") or f"{voice.get('speaker')}/{voice.get('style')}"}
    if engine == "dummy":
        return
    if channel in lock and lock[channel] != ident and not relock:
        sys.exit(f"채널 {channel} 목소리는 {lock[channel]} 로 고정돼 있다. 지금 선택: {ident}.\n"
                 f"의도한 변경이면 --relock (채널 전체 목소리가 바뀐다)")
    lock[channel] = ident
    LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(story_id, force=False, relock=False, engine_override=None):
    s = load_script(story_id)
    cfg = channel_cfg(s)
    engine, voice = pick_voice(s, engine_override)
    out = story_dir(story_id) / "audio"
    out.mkdir(exist_ok=True)
    tmp = CACHE / "tts"
    tmp.mkdir(parents=True, exist_ok=True)

    url = spk = None
    if engine == "voicevox":
        url = voicevox_url()
        try:
            requests.get(f"{url}/version", timeout=3)
        except requests.RequestException:
            print(VOICEVOX_HELP.format(url=url))
            sys.exit(2)
        spk = voicevox_speaker_id(url, voice["speaker"], voice["style"])
    check_lock(s["channel"], engine, voice, relock)

    t = 0.0
    timeline = {"engine": engine, "credit": voice.get("credit", "TEST VOICE") if engine != "dummy" else "DUMMY",
                "scenes": []}
    for sc in s["scenes"]:
        n = sc["n"]
        d = parse_direction(sc.get("direction"))
        # 원고·목소리·속도가 바뀌면 파일 이름이 바뀌어 다시 합성된다
        key = hashlib.sha1(json.dumps([engine, voice, sc["ja"], d["speed"], d["pitch"]],
                                      ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]
        raw_path = out / f"voice_{n:02d}_{engine}_{key}.wav"
        for old in out.glob(f"voice_{n:02d}_*.wav"):
            if old != raw_path:
                old.unlink()
        if force or not raw_path.exists():
            if engine == "voicevox":
                data, fmt = tts_voicevox(sc["ja"], voice, d, url, spk)
            elif engine == "elevenlabs":
                data, fmt = tts_elevenlabs(sc["ja"], voice, d, env("ELEVENLABS_API_KEY"))
            else:
                data, fmt = tts_dummy(sc["ja"], voice, d)
            src = tmp / f"{story_id}_{n:02d}.{fmt}"
            src.write_bytes(data)
            run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(SR),
                 "-sample_fmt", "s16", str(raw_path)])
            src.unlink()
        voice_sig = trim_silence(read_wav(raw_path))
        pre = d["pre"]
        post = d["pause"] + cfg["scene_gap"]
        sig = np.concatenate([np.zeros(int(pre * SR)), voice_sig, np.zeros(int(post * SR))])
        (out / f"scene_{n:02d}.wav").write_bytes(to_wav_bytes(sig))
        dur = len(sig) / SR
        vs = t + pre
        ve = vs + len(voice_sig) / SR
        timeline["scenes"].append({"n": n, "start": round(t, 3), "voice_start": round(vs, 3),
                                   "voice_end": round(ve, 3), "end": round(t + dur, 3)})
        t += dur
    timeline["total"] = round(t, 3)
    (out / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"음성 {len(s['scenes'])}장면, 실측 총 {t / 60:.2f}분 ({engine})")


if __name__ == "__main__":
    a = sys.argv[1:]
    eng = a[a.index("--engine") + 1] if "--engine" in a else None
    main(a[0], "--force" in a, "--relock" in a, eng)
