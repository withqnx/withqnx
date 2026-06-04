#!/usr/bin/env python3
"""
data.json + index.html + 폰트 파일들 → dashboard.html (완전 단일 파일)

사용법: python3 build.py

생성된 dashboard.html은:
- fetch 없이 데이터 내장 (CORS 문제 없음)
- 폰트도 base64로 내장 (외부 파일 의존 없음)
- 더블클릭으로 어디서든 바로 열림
- NAS에 올려두면 다른 사용자도 그냥 더블클릭
"""

import json, os, base64
from datetime import datetime

DATA_FILE = "data.json"
TEMPLATE = "index.html"
OUTPUT = "dashboard.html"
FONTS_DIR = "fonts"


def embed_fonts(html: str) -> tuple[str, int]:
    """fonts/ 폴더의 ttf 파일들을 base64로 변환해서 @font-face url() 자리에 박아넣기"""
    if not os.path.isdir(FONTS_DIR):
        print(f"  ⚠️  {FONTS_DIR}/ 폴더 없음 - 폰트 임베드 스킵")
        return html, 0

    embedded = 0
    for fn in os.listdir(FONTS_DIR):
        if not fn.endswith(".ttf"):
            continue
        path = os.path.join(FONTS_DIR, fn)
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")

        # url('fonts/Paperlogy-XXX.ttf') → url('data:font/ttf;base64,...')
        old_url = f"url('fonts/{fn}')"
        new_url = f"url('data:font/ttf;base64,{b64}')"
        if old_url in html:
            html = html.replace(old_url, new_url)
            embedded += 1

    return html, embedded


def main():
    if not os.path.exists(DATA_FILE):
        print(f"❌ {DATA_FILE} 없음. 먼저 크롤링하세요.")
        return
    if not os.path.exists(TEMPLATE):
        print(f"❌ {TEMPLATE} 없음.")
        return

    # 데이터
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # HTML
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    # 데이터 임베드
    data_json = json.dumps(data, ensure_ascii=False)
    data_json = data_json.replace("</", "<\\/")

    inject = f"""<script>
window.__EMBEDDED_DATA__ = {data_json};
window.__BUILD_TIME__ = "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}";
</script>
"""
    html = html.replace("</head>", inject + "</head>")

    # 폰트 임베드
    print("▶ 폰트 임베드 중...")
    html, embedded = embed_fonts(html)
    print(f"  ✓ {embedded}개 폰트 임베드 완료")

    # 출력
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = os.path.getsize(OUTPUT) / 1024 / 1024
    print()
    print("=" * 50)
    print(f"✅ {OUTPUT} 생성 완료")
    print("=" * 50)
    print(f"   파일 크기: {size_mb:.2f} MB")
    print(f"   포함 후기: {len(data.get('reviews', {}))}건")
    print(f"   임베드 폰트: {embedded}개")
    print(f"   빌드 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("📂 이제 dashboard.html을:")
    print("   - 더블클릭 → 브라우저에서 바로 열림 (서버, 폰트 폴더 불필요)")
    print("   - NAS에 올리기 → 다른 사용자도 더블클릭으로 사용")
    print("   - 단축어 앱에서 URL로 지정 → 메뉴바/Dock에서 한 번 클릭")


if __name__ == "__main__":
    main()
