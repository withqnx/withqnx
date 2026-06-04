#!/usr/bin/env python3
"""
대시보드 빌드 스크립트.

스크립트가 NAS의 작업 폴더 안에 있을 때:
  - 같은 폴더의 data.json + index.html + tags.json + fonts/ 를 합쳐서
  - 같은 폴더에 "겸손몰 후기 분석.html" 생성

사용법: python3 deploy_nas.py
"""

import os, json, base64, sys
from datetime import datetime

DATA_FILE = "data.json"
TAGS_FILE = "tags.json"
GROUPS_FILE = "groups.json"
TEMPLATE = "index.html"
FONTS_DIR = "fonts"
OUTPUT_NAME = "겸손몰 후기 분석.html"

# 스크립트가 있는 폴더를 작업 디렉터리로 (NAS에서 직접 실행 대응)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)


def embed_fonts(html: str):
    if not os.path.isdir(FONTS_DIR):
        return html, 0
    embedded = 0
    for fn in sorted(os.listdir(FONTS_DIR)):
        if not fn.endswith(".ttf"):
            continue
        with open(os.path.join(FONTS_DIR, fn), "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        old_url = f"url('fonts/{fn}')"
        new_url = f"url('data:font/ttf;base64,{b64}')"
        if old_url in html:
            html = html.replace(old_url, new_url)
            embedded += 1
    return html, embedded


def main():
    print("=" * 55)
    print("📦 대시보드 빌드")
    print(f"   작업 폴더: {SCRIPT_DIR}")
    print("=" * 55)

    if not os.path.exists(DATA_FILE):
        print(f"❌ {DATA_FILE} 없음 — 먼저 크롤링을 실행하세요.")
        return 1
    if not os.path.exists(TEMPLATE):
        print(f"❌ {TEMPLATE} 없음")
        return 1

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    # tags.json 로드 (없으면 기본값)
    if os.path.exists(TAGS_FILE):
        with open(TAGS_FILE, "r", encoding="utf-8") as f:
            tags = json.load(f)
        print(f"▶ tags.json 로드: {len(tags)}개 태그")
    else:
        tags = ["#사이즈","#색상","#핏","#배송","#마감","#재질","#내구성","#디자인","#가격","#구성","#기획"]
        print("▶ tags.json 없음 → 기본 태그 사용")

    # groups.json 로드 (없으면 null — 브라우저 localStorage 사용)
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            groups = json.load(f)
        print(f"▶ groups.json 로드: {len(groups)}개 그룹")
    else:
        groups = None
        print("▶ groups.json 없음 → 브라우저 기본값 사용")

    # api_exhausted 상태 확인
    api_exhausted = data.get("api_exhausted", False)
    api_exhausted_at = data.get("api_exhausted_at") or ""
    if api_exhausted:
        # 미분류 후기 수 계산
        reviews = data.get("reviews", {})
        unclassified_count = sum(
            1 for r in reviews.values()
            if not r.get("classification") or not r["classification"].get("segments")
        )
        print(f"⚠️  API 잔액 부족 상태 감지 — 미분류 후기 {unclassified_count}건")
    else:
        unclassified_count = 0

    # 데이터 임베드
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    tags_json = json.dumps(tags, ensure_ascii=False).replace("</", "<\\/")
    groups_json = json.dumps(groups, ensure_ascii=False).replace("</", "<\\/") if groups is not None else "null"
    inject = f"""<script>
window.__EMBEDDED_TAGS__ = {tags_json};
window.__EMBEDDED_GROUPS__ = {groups_json};
window.__EMBEDDED_DATA__ = {data_json};
window.__BUILD_TIME__ = "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}";
window.__API_EXHAUSTED__ = {str(api_exhausted).lower()};
window.__API_EXHAUSTED_AT__ = "{api_exhausted_at}";
window.__UNCLASSIFIED_COUNT__ = {unclassified_count};
</script>
"""
    html = html.replace("</head>", inject + "</head>")

    # 폰트 임베드
    print("▶ 폰트 임베드...")
    html, embedded = embed_fonts(html)
    print(f"  ✓ {embedded}개 폰트 임베드")

    # 출력
    try:
        with open(OUTPUT_NAME, "w", encoding="utf-8") as f:
            f.write(html)
    except PermissionError:
        print(f"❌ 쓰기 권한 없음: {OUTPUT_NAME}")
        return 1

    size_mb = os.path.getsize(OUTPUT_NAME) / 1024 / 1024
    print()
    print("=" * 55)
    print("✅ 완료")
    print("=" * 55)
    print(f"   파일: {OUTPUT_NAME}")
    print(f"   크기: {size_mb:.2f} MB")
    print(f"   후기: {len(data.get('reviews',{}))}건")
    print(f"   태그: {len(tags)}개")
    print()
    print("📂 같은 네트워크의 동료들은:")
    print(f"   파인더 → NAS → 이 폴더 → '{OUTPUT_NAME}' 더블클릭")
    return 0


if __name__ == "__main__":
    sys.exit(main())
