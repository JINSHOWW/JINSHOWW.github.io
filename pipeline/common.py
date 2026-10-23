"""파이프라인 공용 함수: 경로, 설정, .env, ffmpeg 호출, 연출 태그 해석."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
STORIES = ROOT / "stories"
CACHE = PIPELINE / ".cache"


def load_config():
    return json.loads((PIPELINE / "config.json").read_text(encoding="utf-8"))


def load_env():
    """.env 를 읽어 os.environ 에 넣는다. 값은 절대 출력하지 않는다."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def env(key):
    load_env()
    return os.environ.get(key) or None


def story_dir(story_id):
    d = STORIES / story_id
    if not d.exists():
        sys.exit(f"이야기 폴더가 없다: {d}")
    return d


def load_script(story_id):
    return json.loads((story_dir(story_id) / "script_ja.json").read_text(encoding="utf-8"))


def run(cmd, quiet=True):
    """명령 실행. 실패하면 stderr 끝부분을 보여주고 종료한다."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-3000:])
        sys.exit(f"명령 실패: {' '.join(map(str, cmd[:6]))} ...")
    if not quiet:
        print(p.stdout)
    return p


def duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(p.stdout.strip())


TAG_RE = re.compile(r"^(pause|pre|speed|pitch|sfx|bed|cam|short)(?::(.+))?$")
CAMS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "still"}


def parse_direction(tags):
    """["pause:2", "sfx:wind", "speed:0.9", "short"] -> dict. 모르는 태그는 오류."""
    d = {"pause": 0.0, "pre": 0.0, "speed": 1.0, "pitch": 0.0,
         "sfx": [], "bed": None, "cam": None, "short": False}
    for t in tags or []:
        m = TAG_RE.match(t.strip())
        if not m:
            raise ValueError(f"알 수 없는 연출 태그: {t}")
        k, v = m.group(1), m.group(2)
        if k == "short":
            d["short"] = True
        elif k in ("pause", "pre", "speed", "pitch"):
            d[k] = float(v)
        elif k == "sfx":
            d["sfx"].append(v)
        elif k == "bed":
            d["bed"] = v
        elif k == "cam":
            if v not in CAMS:
                raise ValueError(f"cam 값 오류: {v} (가능: {sorted(CAMS)})")
            d["cam"] = v
    return d


def channel_cfg(script):
    return load_config()["channels"][script["channel"]]
