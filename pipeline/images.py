"""장면 이미지 생성. OPENAI_API_KEY 가 있으면 생성, 없으면 단색 임시 이미지.
어느 경우든 images/prompts.md 에 최종 프롬프트를 기록한다.

사용: python3 pipeline/images.py <이야기ID> [--force]
"""
import base64
import sys

import requests
from PIL import Image, ImageDraw, ImageFont

from common import channel_cfg, env, load_script, story_dir

GUARD = ("Original characters and scenery only; do not resemble any real person, "
         "celebrity, existing artwork, film, anime or game character. No text, no letters, "
         "no watermark. No gore, no nudity.")
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def full_prompt(cfg, scene):
    return f"{scene['image_prompt'].strip()} Style: {cfg['image_style']}. {GUARD}"


def placeholder(path, cfg, n):
    img = Image.new("RGB", (1920, 1080), tuple(cfg["placeholder_color"]))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 220)
    small = ImageFont.truetype(FONT, 40)
    d.text((960, 500), f"{n:02d}", font=font, fill=(110, 110, 120), anchor="mm")
    d.text((960, 700), "TEMP IMAGE", font=small, fill=(90, 90, 100), anchor="mm")
    img.save(path)


def generate(path, prompt, key):
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "gpt-image-1", "prompt": prompt, "size": "1536x1024", "n": 1},
        timeout=180,
    )
    if r.status_code != 200:
        # 응답 본문에 키가 들어가지 않으므로 앞부분만 보여준다
        raise RuntimeError(f"이미지 API {r.status_code}: {r.text[:300]}")
    raw = base64.b64decode(r.json()["data"][0]["b64_json"])
    path.write_bytes(raw)
    Image.open(path).convert("RGB").resize((1920, 1080), Image.LANCZOS).save(path)


def main(story_id, force=False):
    s = load_script(story_id)
    cfg = channel_cfg(s)
    out = story_dir(story_id) / "images"
    out.mkdir(exist_ok=True)
    key = env("OPENAI_API_KEY")
    mode = "생성(OpenAI gpt-image-1)" if key else "임시 이미지 (API 키 없음)"
    lines = [f"# 이미지 프롬프트 — {s['title_ja']}", "", f"- 모드: {mode}",
             f"- 공통 스타일: {cfg['image_style']}", f"- 공통 제약: {GUARD}", ""]
    for sc in s["scenes"]:
        n = sc["n"]
        path = out / f"scene_{n:02d}.png"
        prompt = full_prompt(cfg, sc)
        lines += [f"## {n:02d}", "", prompt, ""]
        if path.exists() and not force:
            continue
        if key:
            print(f"생성 {n:02d} ...")
            generate(path, prompt, key)
        else:
            placeholder(path, cfg, n)
    (out / "prompts.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"이미지 {len(s['scenes'])}장: {out} ({mode})")


if __name__ == "__main__":
    main(sys.argv[1], "--force" in sys.argv)
