#!/usr/bin/env python3
"""
data.json의 이미지 URL을 정리하는 유틸리티
사용법: python3 fix_image_urls.py

기존 data.json을 그대로 두고, 이미지 URL만 다음 패턴들을 모두 정상화:
  https://nonohumble.com//nonohumble.com/file_data/... → https://nonohumble.com/file_data/...
  //nonohumble.com/file_data/... → https://nonohumble.com/file_data/...
  nonohumble.com/file_data/... → https://nonohumble.com/file_data/...
"""

import json, re, os, shutil
from datetime import datetime

DATA_FILE = "data.json"

def fix_url(src: str) -> str:
    """이미지 URL을 정상 형식으로 변환"""
    if not src:
        return src

    # 1) // 로 시작 → https:
    if src.startswith("//"):
        src = "https:" + src

    # 2) /file_data/... → 도메인 붙이기
    elif src.startswith("/"):
        src = "https://nonohumble.com" + src

    # 3) nonohumble.com/... → https:// 붙이기
    elif src.startswith("nonohumble.com"):
        src = "https://" + src

    # 4) http 로 시작 안 하면 → 보수적으로 도메인 붙이기
    elif not src.startswith("http"):
        src = "https://nonohumble.com/" + src.lstrip("/")

    # 도메인 중복 정리 (https://nonohumble.com//nonohumble.com/...)
    src = re.sub(r"^https?://nonohumble\.com/+nonohumble\.com/+", "https://nonohumble.com/", src)
    # 슬래시 중복 정리 (단, https://는 제외)
    src = re.sub(r"(?<!:)//+", "/", src)

    return src


def main():
    if not os.path.exists(DATA_FILE):
        print(f"❌ {DATA_FILE} 파일이 없습니다.")
        return

    # 백업 생성
    backup = f"{DATA_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(DATA_FILE, backup)
    print(f"💾 백업 생성: {backup}")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    fixed_count = 0
    fixed_urls = 0
    total_with_images = 0
    examples = []

    for pid, review in data.get("reviews", {}).items():
        if not review.get("images"):
            continue
        total_with_images += 1
        new_images = []
        review_changed = False
        for src in review["images"]:
            new_src = fix_url(src)
            if new_src != src:
                fixed_urls += 1
                if len(examples) < 3:
                    examples.append((src, new_src))
                review_changed = True
            new_images.append(new_src)
        # 중복 제거
        review["images"] = list(dict.fromkeys(new_images))
        if review_changed:
            fixed_count += 1

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    print(f"📊 결과")
    print(f"  사진 있는 후기: {total_with_images}건")
    print(f"  URL 수정된 후기: {fixed_count}건")
    print(f"  수정된 URL 개수: {fixed_urls}개")

    if examples:
        print()
        print("📝 변경 예시:")
        for old, new in examples:
            print(f"  Before: {old[:80]}")
            print(f"  After:  {new[:80]}")
            print()

    print("✅ 완료! 브라우저에서 새로고침(Cmd+R)하면 반영됩니다.")


if __name__ == "__main__":
    main()
