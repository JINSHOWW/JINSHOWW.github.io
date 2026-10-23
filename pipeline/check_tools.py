"""필요한 도구가 있는지 점검한다. 키는 '있음/없음'만 표시하고 값은 출력하지 않는다.

사용: python3 pipeline/check_tools.py
"""
import shutil
import subprocess
import sys

import requests

from common import ROOT, env

ok_all = True


def report(name, ok, hint=""):
    global ok_all
    ok_all &= ok
    print(f"[{'OK' if ok else '없음'}] {name}" + (f"  → {hint}" if not ok and hint else ""))


for tool in ("ffmpeg", "ffprobe"):
    report(tool, shutil.which(tool) is not None, "sudo apt-get install -y ffmpeg")

if shutil.which("ffmpeg"):
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, text=True).stdout
    for f in ("ass", "loudnorm", "zoompan", "ebur128"):
        report(f"ffmpeg 필터 {f}", f" {f} " in filters, "libass 포함 빌드의 ffmpeg 필요")

fonts = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
for font in ("Noto Sans CJK JP", "Noto Serif CJK JP", "Noto Sans CJK KR"):
    report(f"글꼴 {font}", font in fonts, "sudo apt-get install -y fonts-noto-cjk")

for mod in ("PIL", "numpy", "requests"):
    try:
        __import__(mod)
        report(f"python {mod}", True)
    except ImportError:
        report(f"python {mod}", False, "pip install pillow numpy requests")

url = env("VOICEVOX_URL") or "http://localhost:50021"
try:
    v = requests.get(f"{url}/version", timeout=3).text.strip()
    report(f"VOICEVOX 엔진 ({url}, {v})", True)
except requests.RequestException:
    report(f"VOICEVOX 엔진 ({url})", False,
           "엔진 실행: docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-latest "
           "또는 VOICEVOX 앱 실행")

print()
print(".env 파일:", "있음" if (ROOT / ".env").exists() else "없음 (.env.example 참고)")
for key, use in (("OPENAI_API_KEY", "이미지 생성"), ("ELEVENLABS_API_KEY", "낭독 음성")):
    print(f"  {key}: {'설정됨' if env(key) else '없음'} ({use}; 없으면 대체 경로 사용)")

gi = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
report(".gitignore 에 .env", any(l.strip() == ".env" for l in gi.splitlines()))

sys.exit(0 if ok_all else 1)
