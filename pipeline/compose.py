"""영상 합성: 장면 클립(느린 확대·이동) → 디졸브 연결 → 음성+배경음 믹스 → -14 LUFS → 자막 굽기.
출력: output/main.mp4 (1920x1080), output/short.mp4 (1080x1920, ≤59초), output/thumbnail.png (1280x720),
      output/chapters.txt, output/audio_credits.json

script_ja.json 선택 항목:
  scenes[].chapter      : 이 장면에서 시작하는 챕터 이름 (일본어)
  thumbnail             : {"scene": 3, "text": "サムネ文字"}

사용: python3 pipeline/compose.py <이야기ID> [--only main|short|thumb]
"""
import hashlib
import json
import re
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import sfx
from common import channel_cfg, load_config, load_script, parse_direction, run, story_dir
from subs import build_ass

CFG = load_config()
SR = CFG["audio"]["sample_rate"]
FPS = CFG["video"]["fps"]
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
CAM_ORDER = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up", "zoom_in", "pan_down", "still"]


# ---------- 오디오 ----------

def read_wav(path):
    with wave.open(str(path)) as w:
        ch, sr = w.getnchannels(), w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32767
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        raise ValueError(f"{path}: {sr}Hz (48000Hz 필요)")
    return x


def write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def active_rms(x):
    frames = x[: len(x) // 2400 * 2400].reshape(-1, 2400)
    r = np.sqrt((frames ** 2).mean(axis=1))
    r = r[r > 0.01]
    return float(np.sqrt((r ** 2).mean())) if len(r) else 0.05


def loop_to(x, n):
    return np.tile(x, n // len(x) + 1)[:n]


def build_mix(story_id, s, cfg, tl, work):
    voice = np.concatenate([read_wav(story_dir(story_id) / "audio" / f"scene_{sc['n']:02d}.wav")
                            for sc in s["scenes"]])
    n = len(voice)
    ref = active_rms(voice)
    bed_gain = ref * 10 ** (cfg["bed_gain_db"] / 20)
    sfx_gain = ref * 10 ** (cfg["sfx_gain_db"] / 20)
    credits = {}

    # 배경음: bed 태그가 나온 장면부터 바뀐다. 바뀔 때 2초 교차 페이드
    bed = np.zeros(n)
    current = cfg["bed_default"]
    segs = []
    for sc, t in zip(s["scenes"], tl["scenes"]):
        d = parse_direction(sc.get("direction"))
        if d["bed"]:
            current = d["bed"]
        if segs and segs[-1][0] == current:
            segs[-1][2] = t["end"]
        else:
            segs.append([current, t["start"], t["end"]])
    xf = int(2 * SR)
    for name, a, b in segs:
        if name == "none":
            continue
        path, credit = sfx.get(name)
        credits[name] = credit
        src = read_wav(path)
        i0, i1 = int(a * SR), min(n, int(b * SR) + xf)
        seg = loop_to(src, i1 - i0) / (active_rms(src) + 1e-9) * bed_gain
        ramp = np.ones(i1 - i0)
        k = min(xf, len(ramp) // 2)
        ramp[:k] = np.linspace(0, 1, k)
        ramp[-k:] = np.linspace(1, 0, k)
        bed[i0:i1] += seg * ramp

    # 효과음: 장면 시작에 한 번 (bed 류 이름이면 그 장면 동안 반복)
    fx = np.zeros(n)
    for sc, t in zip(s["scenes"], tl["scenes"]):
        for name in parse_direction(sc.get("direction"))["sfx"]:
            path, credit = sfx.get(name)
            credits[name] = credit
            src = read_wav(path)
            i0 = int(t["start"] * SR)
            if name in sfx.BEDS:
                i1 = int(t["end"] * SR)
                seg = loop_to(src, i1 - i0)
                k = min(int(0.8 * SR), (i1 - i0) // 2)
                seg[:k] *= np.linspace(0, 1, k)
                seg[-k:] *= np.linspace(1, 0, k)
            else:
                seg = src[: n - i0]
            fx[i0:i0 + len(seg)] += seg / (active_rms(src) + 1e-9) * sfx_gain

    mix = voice + bed + fx
    mix /= max(1.0, np.abs(mix).max() / 0.95)
    write_wav(work / "mix.wav", mix)
    return work / "mix.wav", credits


def loudnorm(src, dst, extra_in=(), af_pre=""):
    a = CFG["audio"]
    base = f"loudnorm=I={a['target_lufs']}:TP={a['true_peak']}:LRA={a['lra']}"
    pre = f"{af_pre}," if af_pre else ""
    p = run(["ffmpeg", "-hide_banner", "-nostats", *extra_in, "-i", str(src),
             "-af", f"{pre}{base}:print_format=json", "-f", "null", "-"])
    m = json.loads(re.findall(r"\{[^{}]+\}", p.stderr)[-1])
    af = (f"{pre}{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:linear=true,aresample={SR}")
    run(["ffmpeg", "-y", "-v", "error", *extra_in, "-i", str(src), "-af", af,
         "-ac", "2", "-c:a", "pcm_s16le", str(dst)])


# ---------- 비디오 ----------

def cam_expr(cam, frames, w, h):
    D = max(frames - 1, 1)
    c_x, c_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {
        "zoom_in": (f"1+0.10*on/{D}", c_x, c_y),
        "zoom_out": (f"1.10-0.10*on/{D}", c_x, c_y),
        "pan_left": ("1.12", f"(iw-iw/zoom)*(1-on/{D})", c_y),
        "pan_right": ("1.12", f"(iw-iw/zoom)*on/{D}", c_y),
        "pan_up": ("1.12", c_x, f"(ih-ih/zoom)*(1-on/{D})"),
        "pan_down": ("1.12", c_x, f"(ih-ih/zoom)*on/{D}"),
        "still": ("1.04", c_x, c_y),
    }[cam]


def render_clip(img, out, sec, cam):
    frames = int(round(sec * FPS))
    z, x, y = cam_expr(cam, frames, 1920, 1080)
    # 4K 로 키운 뒤 zoompan 해야 떨림이 적다
    vf = (f"scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1920x1080:fps={FPS},"
          f"format=yuv420p")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(img), "-vf", vf,
         "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])


def build_video(story_id, s, cfg, tl, work):
    d = story_dir(story_id)
    clips_dir = work / "clips"
    clips_dir.mkdir(exist_ok=True)
    X = cfg["xfade"]
    # 이야기마다 카메라 순서를 다르게 시작한다 (같은 틀 반복 방지)
    shift = int(hashlib.md5(story_id.encode()).hexdigest(), 16) % len(CAM_ORDER)
    clips = []
    scenes = list(zip(s["scenes"], tl["scenes"]))
    for i, (sc, t) in enumerate(scenes):
        dr = parse_direction(sc.get("direction"))
        cam = dr["cam"] or CAM_ORDER[(i + shift) % len(CAM_ORDER)]
        sec = t["end"] - t["start"] + (X if i < len(scenes) - 1 else 0)
        out = clips_dir / f"scene_{sc['n']:02d}.mp4"
        render_clip(d / "images" / f"scene_{sc['n']:02d}.png", out, sec, cam)
        clips.append(out)
        print(f"  클립 {sc['n']:02d} {cam} {sec:.1f}s")

    # 디졸브 연결. 장면 k 는 정확히 timeline start_k 에 나타나기 시작해 음성과 맞는다.
    raw = work / "video_raw.mp4"
    if len(clips) == 1:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(clips[0]), "-c", "copy", str(raw)])
        return raw
    # 입력이 너무 많으면 ffmpeg 가 무거워지므로 40개씩 묶어 단계적으로 잇는다
    chunk = 40
    level = [(c, tl["scenes"][i]["start"]) for i, c in enumerate(clips)]
    stage = 0
    while len(level) > 1:
        nxt = []
        for g in range(0, len(level), chunk):
            group = level[g:g + chunk]
            if len(group) == 1:
                nxt.append(group[0])
                continue
            out = work / f"join_{stage}_{g}.mp4"
            t0 = group[0][1]
            inputs, fl, prev = [], [], "[0:v]"
            for k, (c, _) in enumerate(group):
                inputs += ["-i", str(c)]
            for k in range(1, len(group)):
                off = group[k][1] - t0
                lab = f"[v{k}]"
                fl.append(f"{prev}[{k}:v]xfade=transition=fade:duration={X}:offset={off:.3f}{lab}")
                prev = lab
            run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fl),
                 "-map", prev, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])
            nxt.append((out, t0))
        level, stage = nxt, stage + 1
    level[0][0].replace(raw)
    return raw


def mux(video, audio, ass, out, t0=None, t1=None, vf_extra=None):
    cut = ["-ss", f"{t0:.3f}", "-to", f"{t1:.3f}"] if t0 is not None else []
    vf = f"{vf_extra + ',' if vf_extra else ''}ass={ass}"
    run(["ffmpeg", "-y", "-v", "error", *cut, "-i", str(video), "-i", str(audio),
         "-map", "0:v", "-map", "1:a", "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR),
         "-movflags", "+faststart", "-shortest", str(out)])


# ---------- 쇼츠 ----------

def pick_short_window(s, tl, max_sec):
    scenes = list(zip(s["scenes"], tl["scenes"]))
    tagged = [i for i, (sc, _) in enumerate(scenes) if parse_direction(sc.get("direction"))["short"]]
    if tagged:
        a, b = tagged[0], tagged[-1]
    else:
        # 정적·효과음이 몰린 연속 구간 = 긴장 구간으로 본다
        def score(sc):
            d = parse_direction(sc.get("direction"))
            return d["pause"] + d["pre"] + 1.5 * len(d["sfx"]) + (1 if d["speed"] < 1 else 0)
        best, a, b = -1, 0, 0
        for i in range(len(scenes)):
            tot, sc_sum = 0, 0
            for j in range(i, len(scenes)):
                tot = scenes[j][1]["end"] - scenes[i][1]["start"]
                if tot > max_sec:
                    break
                sc_sum += score(scenes[j][0])
                if sc_sum > best:
                    best, a, b = sc_sum, i, j
    while b > a and scenes[b][1]["end"] - scenes[a][1]["start"] > max_sec:
        b -= 1
    t0 = scenes[a][1]["start"]
    t1 = min(scenes[b][1]["end"], t0 + max_sec)
    return t0, t1, [scenes[k][0]["n"] for k in range(a, b + 1)]


def build_short(story_id, s, cfg, raw, mix_norm, cues, work, out_dir):
    tl = json.loads((story_dir(story_id) / "audio" / "timeline.json").read_text(encoding="utf-8"))
    t0, t1, ns = pick_short_window(s, tl, CFG["video"]["short_max_sec"])
    w, h = CFG["video"]["short"]
    cl = [c for c in cues if c["end"] > t0 and c["start"] < t1]
    cl = [dict(c, start=max(c["start"], t0), end=min(c["end"], t1)) for c in cl]
    ass = work / "short.ass"
    ass.write_text(build_ass(cfg, cl, (w, h), offset=t0, vertical=True), encoding="utf-8")
    title = work / "short_title.txt"
    title.write_text(s.get("short_title_ja") or s["title_ja"], encoding="utf-8")
    dur = t1 - t0
    audio = work / "short_audio.wav"
    loudnorm(mix_norm, audio, extra_in=["-ss", f"{t0:.3f}", "-to", f"{t1:.3f}"],
             af_pre=f"afade=t=in:d=0.4,afade=t=out:st={dur - 1.5:.3f}:d=1.5")
    vf = (f"split[a][b];[a]scale=-2:{h},crop={w}:{h},boxblur=24:2,eq=brightness=-0.18[bg];"
          f"[b]scale={w}:-2[fg];[bg][fg]overlay=0:(H-h)/2-140,"
          f"drawtext=fontfile={FONT_BOLD}:textfile={title}:fontsize=72:fontcolor=0xEEEEEE:"
          f"borderw=4:bordercolor=0x000000:x=(w-text_w)/2:y=260,"
          f"fade=t=in:d=0.4,fade=t=out:st={dur - 1.2:.3f}:d=1.2")
    mux(raw, audio, ass, out_dir / "short.mp4", t0, t1, vf_extra=vf)
    print(f"쇼츠: {t0:.1f}~{t1:.1f}s ({dur:.1f}s), 장면 {ns}")
    return {"start": t0, "end": t1, "scenes": ns}


# ---------- 썸네일 ----------

def build_thumb(story_id, s, out_dir):
    d = story_dir(story_id)
    th = s.get("thumbnail") or {}
    n = th.get("scene") or s["scenes"][len(s["scenes"]) // 2]["n"]
    text = th.get("text") or s["title_ja"]
    W, H = CFG["video"]["thumb"]
    img = Image.open(d / "images" / f"scene_{n:02d}.png").convert("RGB").resize((W, H), Image.LANCZOS)
    shade = Image.new("L", (W, H))
    ImageDraw.Draw(shade).rectangle([0, int(H * 0.55), W, H], fill=170)
    img = Image.composite(Image.new("RGB", (W, H)), img, shade.filter(ImageFilter.GaussianBlur(60)))
    draw = ImageDraw.Draw(img)
    size = 110
    while size > 40:
        font = ImageFont.truetype(FONT_BOLD, size)
        box = draw.multiline_textbbox((0, 0), text, font=font, stroke_width=6)
        if box[2] - box[0] <= W - 100:
            break
        size -= 6
    draw.multiline_text((W // 2, H - 60), text, font=font, fill=(245, 240, 230), anchor="md",
                        stroke_width=6, stroke_fill=(0, 0, 0), align="center")
    img.save(out_dir / "thumbnail.png", optimize=True)
    print(f"썸네일: 장면 {n}, 「{text}」")


# ---------- 실행 ----------

def chapters(s, tl, out_dir):
    lines = []
    for sc, t in zip(s["scenes"], tl["scenes"]):
        if sc.get("chapter"):
            sec = 0 if not lines else int(t["start"])
            lines.append(f"{sec // 60}:{sec % 60:02d} {sc['chapter']}")
    (out_dir / "chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(story_id, only=None):
    s = load_script(story_id)
    cfg = channel_cfg(s)
    d = story_dir(story_id)
    tl = json.loads((d / "audio" / "timeline.json").read_text(encoding="utf-8"))
    if tl["engine"] == "dummy":
        print("경고: 시험용 가짜 음성(dummy)으로 합성한다. 이 결과물은 공개하면 안 된다.")
    work = d / ".work"
    work.mkdir(exist_ok=True)
    out_dir = d / "output"
    out_dir.mkdir(exist_ok=True)
    cues = json.loads((work / "cues.json").read_text(encoding="utf-8"))

    if only in (None, "thumb"):
        build_thumb(story_id, s, out_dir)
    if only == "thumb":
        return
    raw = work / "video_raw.mp4"
    mix_norm = work / "mix_norm.wav"
    if only in (None, "main") or not raw.exists():
        print("장면 클립 렌더링 ...")
        raw = build_video(story_id, s, cfg, tl, work)
        mix, credits = build_mix(story_id, s, cfg, tl, work)
        loudnorm(mix, mix_norm)
        mux(raw, mix_norm, work / "main.ass", out_dir / "main.mp4")
        chapters(s, tl, out_dir)
        (out_dir / "audio_credits.json").write_text(
            json.dumps({"voice": tl["credit"], "sounds": credits}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"본편: {out_dir / 'main.mp4'}")
    if only in (None, "short"):
        info = build_short(story_id, s, cfg, raw, mix_norm, cues, work, out_dir)
        (work / "short.json").write_text(json.dumps(info), encoding="utf-8")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[a.index("--only") + 1] if "--only" in a else None)
