"""완성 영상 자동 검수 → review.md 에 결과 추가. 추출한 프레임은 사람이(또는 Claude 가) 직접 본다.

- ffprobe: 해상도, 길이, 오디오 트랙
- 일정 간격 프레임 추출 + 접촉 시트 (output/qc/)
- loudnorm 분석: -14 LUFS ±1, True Peak ≤ -1 dBTP
- 싱크: 장면 3곳 이상에서 자막 시작과 실제 음성 시작(최종 오디오의 에너지 상승 지점) 차이

사용: python3 pipeline/qc.py <이야기ID>
"""
import datetime
import json
import re
import subprocess
import sys

import numpy as np

from common import load_config, run, story_dir

CFG = load_config()


def probe(path):
    p = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,sample_rate,channels:format=duration",
             "-of", "json", str(path)])
    j = json.loads(p.stdout)
    v = next((x for x in j["streams"] if x["codec_type"] == "video"), {})
    a = [x for x in j["streams"] if x["codec_type"] == "audio"]
    return {"w": v.get("width"), "h": v.get("height"), "dur": float(j["format"].get("duration", 0)),
            "audio": [f"{x['codec_name']} {x['sample_rate']}Hz {x['channels']}ch" for x in a]}


def loudness(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = json.loads(re.findall(r"\{[^{}]+\}", p.stderr)[-1])
    return float(m["input_i"]), float(m["input_tp"]), float(m["input_lra"])


def frames(path, dur, qc, prefix, count=12):
    out = []
    step = max(dur / count, 3)
    t = min(1.0, dur / 2)
    while t < dur - 0.2:
        f = qc / f"{prefix}_{int(t):05d}s.jpg"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
             "-q:v", "3", str(f)])
        out.append(f)
        t += step
    return out


def contact_sheet(files, out, cols=4):
    from PIL import Image
    ims = [Image.open(f) for f in files]
    w = 480
    h = int(ims[0].height * w / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h))
    for i, im in enumerate(ims):
        sheet.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    sheet.save(out, quality=85)


def envelope(path, t0, t1, sr=16000):
    raw = run_bytes(["ffmpeg", "-v", "error", "-ss", f"{max(t0, 0):.3f}", "-to", f"{t1:.3f}", "-i", str(path),
                     "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"])
    x = np.frombuffer(raw, "<i2").astype(np.float32) / 32767
    win = sr // 100  # 10ms
    x = x[: len(x) // win * win].reshape(-1, win)
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-6)


def run_bytes(cmd):
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode:
        sys.exit(p.stderr.decode()[-2000:])
    return p.stdout


def voice_lag(final, ref, t, sr=16000):
    """최종 오디오와 원래 낭독 트랙의 포락선을 맞대어, t 부근에서 낭독이 몇 초 밀렸는지 잰다.
    배경음·효과음이 겹쳐도 낭독의 억양 모양으로 맞추므로 안정적이다."""
    a, b = max(t - 0.5, 0), t + 4.0
    ef = envelope(final, a - 0.5 if a >= 0.5 else 0, b + 0.5, sr)
    er = envelope(ref, a, b, sr)
    pad = int(round((a - (a - 0.5 if a >= 0.5 else 0)) * 100))
    best, lag = -2, None
    for k in range(-pad, len(ef) - len(er) - pad + 1):
        seg = ef[pad + k: pad + k + len(er)]
        if len(seg) < len(er):
            break
        c = np.corrcoef(seg, er)[0, 1]
        if c > best:
            best, lag = c, k / 100
    return lag, best


def main(story_id):
    d = story_dir(story_id)
    out = d / "output"
    qc = out / "qc"
    qc.mkdir(exist_ok=True)
    tl = json.loads((d / "audio" / "timeline.json").read_text(encoding="utf-8"))
    cues = json.loads((d / ".work" / "cues.json").read_text(encoding="utf-8"))
    a = CFG["audio"]
    lines, fails = [], []

    def check(ok, msg):
        lines.append(f"- [{'통과' if ok else '실패'}] {msg}")
        if not ok:
            fails.append(msg)

    if tl["engine"] == "dummy":
        check(False, "음성이 시험용 dummy 다. 실제 TTS 로 다시 만들어야 한다")

    for name, size, maxdur in (("main.mp4", CFG["video"]["main"], None),
                               ("short.mp4", CFG["video"]["short"], 60)):
        f = out / name
        if not f.exists():
            check(False, f"{name} 없음")
            continue
        p = probe(f)
        check([p["w"], p["h"]] == size, f"{name} 해상도 {p['w']}x{p['h']} (기준 {size[0]}x{size[1]})")
        check(bool(p["audio"]), f"{name} 오디오 {p['audio'] or '없음'}")
        if maxdur:
            check(p["dur"] <= maxdur, f"{name} 길이 {p['dur']:.1f}s (≤{maxdur}s)")
        else:
            check(abs(p["dur"] - tl["total"]) < 1.0, f"{name} 길이 {p['dur'] / 60:.2f}분 (음성 실측 {tl['total'] / 60:.2f}분)")
        i, tp, lra = loudness(f)
        check(abs(i - a["target_lufs"]) <= 1.0 and tp <= -1.0,
              f"{name} 음량 {i:.1f} LUFS, TP {tp:.1f} dBTP, LRA {lra:.1f}")
        fs = frames(f, p["dur"], qc, name.split(".")[0], 12 if maxdur is None else 6)
        contact_sheet(fs, qc / f"{name.split('.')[0]}_sheet.jpg", cols=4 if maxdur is None else 6)

    th = out / "thumbnail.png"
    if th.exists():
        from PIL import Image
        w, h = Image.open(th).size
        check([w, h] == CFG["video"]["thumb"] and th.stat().st_size < 2_000_000,
              f"thumbnail.png {w}x{h}, {th.stat().st_size // 1024}KB (2MB 미만)")
    else:
        check(False, "thumbnail.png 없음")

    # 싱크 기준: 장면 음성을 이어 붙인 원래 낭독 트랙
    import wave
    ref = d / ".work" / "narration_ref.wav"
    with wave.open(str(ref), "wb") as w:
        for i, x in enumerate(tl["scenes"]):
            with wave.open(str(d / "audio" / f"scene_{x['n']:02d}.wav")) as r:
                if i == 0:
                    w.setparams(r.getparams())
                w.writeframes(r.readframes(r.getnframes()))

    # 싱크: 첫 장면, 1/3, 2/3, 마지막 장면
    sc = tl["scenes"]
    picks = sorted({0, len(sc) // 3, 2 * len(sc) // 3, len(sc) - 1})
    for k in picks:
        s = sc[k]
        cue = next(c for c in cues if c["n"] == s["n"])
        lag, corr = voice_lag(out / "main.mp4", ref, s["voice_start"])
        got = s["voice_start"] + (lag or 0)
        diff = cue["start"] - got
        check(lag is not None and corr > 0.5 and abs(diff) <= 0.1,
              f"싱크 장면 {s['n']}: 자막 시작 {cue['start']:.2f}s / 최종 오디오의 낭독 시작 {got:.2f}s "
              f"(차 {diff:+.2f}s, 상관 {corr:.2f})")
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{(cue['start'] + cue['end']) / 2:.2f}",
             "-i", str(out / "main.mp4"), "-frames:v", "1", "-q:v", "3", str(qc / f"sync_scene{s['n']:02d}.jpg")])

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = [f"\n## 영상 자동 검수 ({stamp})", "", *lines, "",
            f"- 프레임: `output/qc/` (main_sheet.jpg, short_sheet.jpg, sync_scene*.jpg) — 눈으로 확인한 결과는 아래에 적는다", ""]
    rv = d / "review.md"
    with rv.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(body))
    print("\n".join(lines))
    print(f"\n{'실패 ' + str(len(fails)) + '건' if fails else '자동 검수 전부 통과'} → {rv}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
