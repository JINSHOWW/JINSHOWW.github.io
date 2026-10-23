"""자막 생성: 실측 timeline.json 기준. subs.srt(일본어+한글) 와 합성용 .work/main.ass

장면 안에서 일본어·한국어 문장 수가 같으면 문장 단위로 나누고, 시간은 일본어 글자 수에 비례해 배분한다.
문장 수가 다르면 장면 전체를 한 자막으로 둔다 (validate 가 경고한다).

사용: python3 pipeline/subs.py <이야기ID>
"""
import json
import re
import sys

from common import channel_cfg, load_script, story_dir

JA_SPLIT = re.compile(r"(?<=[。！？])")
KO_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_pair(ja, ko):
    js = [x.strip() for x in JA_SPLIT.split(ja) if x.strip()]
    ks = [x.strip() for x in KO_SPLIT.split(ko) if x.strip()]
    if len(js) == len(ks):
        return list(zip(js, ks))
    return [(ja.strip(), ko.strip())]


def cues(story_id):
    s = load_script(story_id)
    tl = json.loads((story_dir(story_id) / "audio" / "timeline.json").read_text(encoding="utf-8"))
    by_n = {x["n"]: x for x in tl["scenes"]}
    out = []
    for sc in s["scenes"]:
        t = by_n[sc["n"]]
        pairs = split_pair(sc["ja"], sc["ko"])
        total = sum(len(j) for j, _ in pairs)
        a, span = t["voice_start"], t["voice_end"] - t["voice_start"]
        for j, k in pairs:
            b = a + span * len(j) / total
            out.append({"n": sc["n"], "start": a, "end": b, "ja": j, "ko": k})
            a = b
    # 문장 사이 짧은 공백은 앞 자막을 늘려 깜빡임을 막는다 (0.6초 미만일 때만)
    for x, y in zip(out, out[1:]):
        if 0 < y["start"] - x["end"] < 0.6:
            x["end"] = y["start"]
    return s, out


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def ass_time(t):
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    sec, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def ass_escape(text):
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", " ")


def build_ass(cfg, cue_list, size, offset=0.0, vertical=False):
    """일본어(위, 크게) + 한글(아래, 작게)을 한 이벤트에 넣어 겹침 없이 쌓는다."""
    w, h = size
    if vertical:
        ja_fs, ko_fs, margin_v, margin_lr = 64, 40, 360, 70
    else:
        ja_fs, ko_fs, margin_v, margin_lr = 56, 34, 48, 160
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{cfg['sub_font_ja']},{ja_fs},&H00F2F2F2,&H00FFFFFF,&H00101010,&H96000000,0,0,0,0,100,100,1,0,1,3,1.5,2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for c in cue_list:
        text = (f"{ass_escape(c['ja'])}\\N{{\\fn{cfg['sub_font_ko']}\\fs{ko_fs}"
                f"\\c&H00C8D2DC&\\bord2}}{ass_escape(c['ko'])}")
        lines.append(f"Dialogue: 0,{ass_time(c['start'] - offset)},{ass_time(c['end'] - offset)},"
                     f"Sub,,0,0,0,,{{\\fad(150,150)}}{text}")
    return head + "\n".join(lines) + "\n"


def main(story_id):
    s, cl = cues(story_id)
    cfg = channel_cfg(s)
    d = story_dir(story_id)
    srt = []
    for i, c in enumerate(cl, 1):
        srt += [str(i), f"{srt_time(c['start'])} --> {srt_time(c['end'])}", c["ja"], c["ko"], ""]
    (d / "subs.srt").write_text("\n".join(srt), encoding="utf-8")
    work = d / ".work"
    work.mkdir(exist_ok=True)
    (work / "main.ass").write_text(build_ass(cfg, cl, (1920, 1080)), encoding="utf-8")
    (work / "cues.json").write_text(json.dumps(cl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"자막 {len(cl)}개: {d / 'subs.srt'}")


if __name__ == "__main__":
    main(sys.argv[1])
