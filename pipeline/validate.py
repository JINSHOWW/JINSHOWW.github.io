"""script_ja.json 형식 검사 + 낭독 길이 추정.

사용: python3 pipeline/validate.py <이야기ID>
"""
import re
import sys

from common import load_script, parse_direction

# 일본어 낭독 속도 대략값 (글자/초). 실제 길이는 tts 단계에서 실측한다.
CPS = {"A": 7.0, "B": 5.5}
MAX_SENT = {"A": 45, "B": 70}  # 한 문장 권장 최대 글자 수


def main(story_id):
    s = load_script(story_id)
    errors, warns = [], []
    for k in ("id", "channel", "title_ja", "scenes"):
        if k not in s:
            errors.append(f"최상위 키 누락: {k}")
    if s.get("id") != story_id:
        errors.append(f"id({s.get('id')})가 폴더 이름({story_id})과 다르다")
    ch = s.get("channel")
    if ch not in ("A", "B"):
        errors.append(f"channel 은 A 또는 B: {ch}")
        ch = "A"

    total, short_total = 0.0, 0.0
    for i, sc in enumerate(s.get("scenes", []), 1):
        tag = f"장면 {sc.get('n', '?')}"
        if sc.get("n") != i:
            errors.append(f"{tag}: n 은 1부터 연속이어야 한다 (기대값 {i})")
        for k in ("ja", "ko", "image_prompt"):
            if not str(sc.get(k, "")).strip():
                errors.append(f"{tag}: {k} 비어 있음")
        if re.search(r"[぀-ヿ가-힣]", sc.get("image_prompt", "")):
            warns.append(f"{tag}: image_prompt 는 영어로")
        try:
            d = parse_direction(sc.get("direction"))
        except ValueError as e:
            errors.append(f"{tag}: {e}")
            continue
        ja = sc.get("ja", "")
        for sent in re.split(r"[。！？!?]", ja):
            if len(sent) > MAX_SENT[ch]:
                warns.append(f"{tag}: 긴 문장 {len(sent)}자 「{sent[:20]}…」")
        est = len(ja) / CPS[ch] / d["speed"] + d["pause"] + d["pre"]
        total += est
        if d["short"]:
            short_total += est

    print(f"장면 {len(s.get('scenes', []))}개, 추정 길이 {total / 60:.1f}분, 쇼츠 지정 {short_total:.0f}초")
    target = {"A": (5, 12), "B": (30, 60)}[ch]
    if not target[0] <= total / 60 <= target[1]:
        warns.append(f"채널 {ch} 목표 길이 {target[0]}~{target[1]}분을 벗어남 (추정)")
    if short_total == 0:
        warns.append("short 태그가 없다: 쇼츠 구간을 자동 선택한다")
    elif short_total > 59:
        warns.append(f"쇼츠 지정 구간 추정 {short_total:.0f}초 > 59초")
    for w in warns:
        print("주의:", w)
    for e in errors:
        print("오류:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
