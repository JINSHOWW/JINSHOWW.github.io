"""이야기 하나를 단계별로 실행한다. 원고 작성·검토(1~4단계)와 메타데이터(10단계)는 사람/Claude 가 쓴다.

사용: python3 pipeline/run.py <이야기ID> [단계...]
  단계: validate images tts subs compose qc   (생략하면 전부 순서대로)
  예:   python3 pipeline/run.py yeou-nui tts subs
"""
import sys

import compose
import images
import qc
import subs
import tts
import validate

STEPS = ["validate", "images", "tts", "subs", "compose", "qc"]


def main(story_id, steps):
    for st in steps:
        print(f"\n=== {st} ===")
        if st == "validate":
            if validate.main(story_id):
                sys.exit("원고 형식 오류. 고친 뒤 다시 실행")
        elif st == "images":
            images.main(story_id)
        elif st == "tts":
            tts.main(story_id)
        elif st == "subs":
            subs.main(story_id)
        elif st == "compose":
            compose.main(story_id)
        elif st == "qc":
            qc.main(story_id)
        else:
            sys.exit(f"모르는 단계: {st} (가능: {STEPS})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:] or STEPS)
