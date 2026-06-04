#!/usr/bin/env python3
"""
기존 data.json의 후기들을 다시 분류 (크롤링 안 함).
각 segment(긍정/부정 등) 안에 어떤 키워드가 들어가는지 매핑.

사용법: python3 reclassify.py

옵션:
  - FORCE = True 로 두면 이미 새 포맷으로 분류된 것도 다시 분류
  - 기본은 False — 한 번 분류한 건 안 건드림 (중도 재실행 안전)
"""

import os, sys, json, re, time
from datetime import datetime

DATA_FILE = "data.json"
FORCE = False  # True면 이미 분류된 것도 다시
SAVE_EVERY = 50  # N개마다 중간 저장

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    # .env 로드 시도
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY"):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["ANTHROPIC_API_KEY"] = key
                    ANTHROPIC_API_KEY = key
                    break

if not ANTHROPIC_API_KEY:
    print("❌ ANTHROPIC_API_KEY가 필요합니다. .env 파일에 추가해주세요.")
    sys.exit(1)

import requests

HASHTAG_KEYWORDS = """- #사이즈: 사이즈, 크기, 치수, 작아, 커요, 맞아요, 딱 맞
- #색상: 색상, 색깔, 컬러, 색감, 빛깔
- #핏: 핏, 루즈, 타이트, 슬림
- #배송: 배송, 포장, 택배, 도착, 기다림
- #마감: 마감, 마무리, 봉제, 스티치, 박음질
- #재질: 재질, 소재, 원단, 촉감, 감촉
- #내구성: 내구, 튼튼, 약함, 오래
- #디자인: 디자인, 예쁘다, 모양, 스타일
- #가격: 가격, 비싸다, 저렴, 가성비"""

CLASSIFY_PROMPT = """쇼핑몰 후기를 정밀 분석해서 JSON으로만 답하세요.

제목: {title}
내용: {content}

규칙:
1. 후기를 segment로 분리. 각 segment는 하나의 카테고리 + 그에 해당하는 키워드들을 가짐.
   예: "디자인은 예쁜데 사이즈는 작아요" →
   [{{"category":"긍정","summary":"디자인 예쁨","hashtags":["#디자인"]}},
    {{"category":"부정","summary":"사이즈 작음","hashtags":["#사이즈"]}}]

2. category: 긍정 | 부정 | 교환요청 | 반품요청 | 추가구매 | 양도/거래 | 중립/단순수령
3. ⚠️ 교환요청 vs 양도/거래:
   - 판매자에게 "교환해주세요" = 교환요청
   - 구매자끼리 "교환하실 분/양도합니다/팝니다" = 양도/거래

4. hashtags는 다음 중에서만 선택 (해당 segment에 명시적으로 언급된 것만):
{hashtags}

5. 본문이 없거나 단순 "잘 받았어요" 류면 segments는 [{{"category":"중립/단순수령","summary":"단순 수령","hashtags":[]}}]

6. confidence: 0.0~1.0 (0.6 미만이면 사람이 검토 필요)

출력 예:
{{"segments":[
  {{"category":"긍정","sentiment":"positive","summary":"디자인 만족","hashtags":["#디자인"],"confidence":0.9}},
  {{"category":"부정","sentiment":"negative","summary":"마감 별로","hashtags":["#마감"],"confidence":0.85}}
],"mixed":true,"overall_sentiment":"neutral","confidence":0.85}}"""


def classify_with_ai(title: str, content: str, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 600,
                    "messages": [{"role": "user", "content":
                        CLASSIFY_PROMPT.format(
                            title=title[:200],
                            content=(content or "(본문 없음)")[:600],
                            hashtags=HASHTAG_KEYWORDS
                        )
                    }]
                },
                timeout=20
            )
            data = resp.json()
            text = data["content"][0]["text"].strip()
            text = re.sub(r"```json|```", "", text).strip()
            result = json.loads(text)

            # 검증
            if "segments" not in result or not result["segments"]:
                raise ValueError("segments 없음")

            # confidence 낮으면 needs_review 플래그
            if result.get("confidence", 1.0) < 0.6:
                result["needs_review"] = True

            return result
        except Exception as e:
            if attempt == retries:
                print(f"     ✗ AI 분류 실패: {e}")
                return None
            time.sleep(1)
    return None


def is_new_format(classification: dict) -> bool:
    """이미 새 포맷(segment 안에 hashtags)인지 판별"""
    if not classification:
        return False
    segs = classification.get("segments", [])
    if not segs:
        return False
    # 첫 segment에 hashtags 키가 있으면 새 포맷
    return "hashtags" in segs[0]


def main():
    if not os.path.exists(DATA_FILE):
        print(f"❌ {DATA_FILE} 없음")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    reviews = list(data["reviews"].values())
    total = len(reviews)

    # 재분류 대상 추리기
    targets = []
    for r in reviews:
        if FORCE or not is_new_format(r.get("classification")):
            targets.append(r)

    if not targets:
        print("✅ 모든 후기가 이미 새 포맷으로 분류되어 있습니다.")
        return

    print("=" * 55)
    print("🤖 후기 재분류 시작 (segment별 키워드 매핑)")
    print(f"   전체: {total}건 / 재분류 대상: {len(targets)}건")
    print(f"   시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)
    print()

    success = 0
    failed = 0
    needs_review = 0

    for i, r in enumerate(targets, 1):
        title = r.get("title", "")
        content = r.get("content", "")
        pid = r.get("id", "?")

        result = classify_with_ai(title, content)
        if result:
            # 기존 hashtags 필드는 segment별로 분산되므로 제거하지 않고 두되,
            # 모든 segment의 hashtags 합쳐서 전체 hashtags도 갱신
            all_hashtags = []
            for seg in result.get("segments", []):
                for h in seg.get("hashtags", []):
                    if h not in all_hashtags:
                        all_hashtags.append(h)
            r["hashtags"] = all_hashtags
            r["classification"] = result
            success += 1
            if result.get("needs_review"):
                needs_review += 1

            preview = title[:30].replace("\n", " ")
            cats = " + ".join(s.get("category", "?") for s in result["segments"])
            print(f"  [{i}/{len(targets)}] #{pid} {preview}... → {cats}")
        else:
            failed += 1
            print(f"  [{i}/{len(targets)}] #{pid} ⚠️ 실패")

        # 중간 저장
        if i % SAVE_EVERY == 0:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  💾 중간 저장 ({i}/{len(targets)})")

        time.sleep(0.1)  # API rate limit 여유

    # 최종 저장
    data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 55)
    print("✅ 완료")
    print("=" * 55)
    print(f"  성공: {success}건")
    print(f"  실패: {failed}건")
    print(f"  검토 필요: {needs_review}건")


if __name__ == "__main__":
    main()
