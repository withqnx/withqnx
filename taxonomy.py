#!/usr/bin/env python3
"""분류 체계 v3 단일 출처 — 대상(aspect)·감정(sentiment)·의도(intent) 3축.

`분류 가이드 v2.md`(문서 버전 v3)와 항상 같은 내용을 유지한다.
crawl.py / classify_pending.py / migrate_v3.py 가 모두 여기를 import 한다.
"""

ASPECTS   = ("상품", "배송·포장", "응대·소통")
SENTIMENTS = ("긍정", "부정", "중립")
INTENTS   = ("없음", "교환·반품", "양도·거래", "문의", "재구매희망")

# v2의 #또사고싶다는 의도 축으로 올라가 태그에서 빠졌다 (14개 → 13개)
TAGS = ("#사이즈", "#핏", "#색상", "#마감", "#재질", "#내구성", "#디자인",
        "#퀄리티", "#가격", "#구성", "#기획", "#무게감", "#사용성",
        "#첫인상", "#선물")

# 대시보드·보고서가 계속 쓰는 파생 카테고리
DERIVED_CATEGORIES = ("긍정", "부정", "중립/단순수령", "양도/거래",
                      "교환/반품", "배송관련불편", "문의")


def derive_category(seg: dict) -> str:
    """3축에서 기존 6+1 카테고리를 계산한다. 순서가 곧 우선순위다."""
    intent = seg.get("intent") or "없음"
    aspect = seg.get("aspect") or "상품"
    sent   = seg.get("sentiment") or "중립"
    if intent == "양도·거래":               return "양도/거래"
    if intent == "교환·반품":               return "교환/반품"
    if intent == "문의":                    return "문의"
    if aspect == "배송·포장" and sent == "부정": return "배송관련불편"
    if sent == "긍정":                      return "긍정"
    if sent == "부정":                      return "부정"
    return "중립/단순수령"


# v2 카테고리 → v3 3축 (기계 변환용)
V2_TO_V3 = {
    "긍정":          {"aspect": "상품",      "sentiment": "긍정", "intent": "없음"},
    "부정":          {"aspect": "상품",      "sentiment": "부정", "intent": "없음"},
    "배송관련불편":   {"aspect": "배송·포장", "sentiment": "부정", "intent": "없음"},
    "양도/거래":      {"aspect": "상품",      "sentiment": "중립", "intent": "양도·거래"},
    "교환/반품":      {"aspect": "상품",      "sentiment": "중립", "intent": "교환·반품"},
    "중립/단순수령":  {"aspect": "상품",      "sentiment": "중립", "intent": "없음"},
    # v1 잔재 — 실데이터에 아직 남아 있다
    "제품관련불편":   {"aspect": "상품",      "sentiment": "부정", "intent": "없음"},
    "교환요청":       {"aspect": "상품",      "sentiment": "중립", "intent": "교환·반품"},
    "반품요청":       {"aspect": "상품",      "sentiment": "중립", "intent": "교환·반품"},
    "반품":          {"aspect": "상품",      "sentiment": "중립", "intent": "교환·반품"},
    "추가구매":       {"aspect": "상품",      "sentiment": "긍정", "intent": "재구매희망"},
    "추가구매희망":   {"aspect": "상품",      "sentiment": "긍정", "intent": "재구매희망"},
    "또사고싶다":     {"aspect": "상품",      "sentiment": "긍정", "intent": "재구매희망"},
    "#또사고싶다":    {"aspect": "상품",      "sentiment": "긍정", "intent": "재구매희망"},
}

# 모델이 만들어내던 창작 태그 → 가장 가까운 정식 태그 (없으면 버린다)
TAG_ALIASES = {
    "#소재 및 재질": "#재질", "#질감": "#재질", "#신축성": "#재질",
    "#필기감": "#사용성", "#필감": "#사용성", "#그립감": "#사용성",
    "#사용방법": "#사용성", "#쿠션감": "#재질", "#날카로움": "#퀄리티",
    "#품질": "#퀄리티", "무게감": "#무게감", "#인테리어": "#디자인",
    "#얼굴형": "#사이즈", "#외관": "#첫인상", "#실물": "#첫인상",
}

# reasoning이 스스로 애매하다고 말하면 confidence를 믿지 않는다
import re as _re
HEDGE = _re.compile(r"(애매|헷갈|불확실|모호|판단\s*어려|걸침|파악\s*불가|섞여\s*있어)")
HEDGED_CONFIDENCE = 0.7


def normalize_tags(tags):
    """창작 태그를 정식 태그로 보내고, 매핑 불가한 것은 버린다."""
    out = []
    for t in tags or []:
        t = TAG_ALIASES.get(t, t)
        if t in TAGS and t not in out:
            out.append(t)
    return out


def postprocess(clf: dict) -> dict:
    """모델 출력에 규격 검증을 씌운다. 규격 위반은 조용히 고치지 않고 검토 큐로 보낸다."""
    segs = clf.get("segments") or []
    problems = []

    for s in segs:
        if s.get("aspect") not in ASPECTS:
            problems.append(f"aspect={s.get('aspect')!r}"); s["aspect"] = "상품"
        if s.get("sentiment") not in SENTIMENTS:
            problems.append(f"sentiment={s.get('sentiment')!r}"); s["sentiment"] = "중립"
        if s.get("intent") not in INTENTS:
            problems.append(f"intent={s.get('intent')!r}"); s["intent"] = "없음"

        raw = s.get("tags") or s.get("hashtags") or []
        s["tags"] = normalize_tags(raw)
        s.pop("hashtags", None)
        dropped = [t for t in raw if TAG_ALIASES.get(t, t) not in TAGS]
        if dropped:
            problems.append(f"규격외 태그 {dropped}")
        # 태그는 상품 속성 어휘다. 배송·응대에는 붙지 않는다.
        if s["aspect"] != "상품" and s["tags"]:
            problems.append(f"{s['aspect']}에 태그 {s['tags']}")
            s["tags"] = []
        if not (s.get("summary") or "").strip():
            problems.append("summary 없음")
        s["category"] = derive_category(s)

    if segs:
        min_conf = min(float(s.get("confidence", 0.9)) for s in segs)
        clf["confidence"] = min_conf
        clf["needs_review"] = min_conf < 0.8

    # 스스로 애매하다고 써놓고 confidence를 높게 준 경우를 신뢰하지 않는다.
    # v2에서 이런 게 193건이었고 전부 검토 큐를 빠져나갔다.
    if HEDGE.search(clf.get("reasoning") or "") and clf.get("confidence", 0) > HEDGED_CONFIDENCE:
        clf["confidence"] = HEDGED_CONFIDENCE
        clf["needs_review"] = True
        problems.append("reasoning이 애매함을 인정 → confidence 강제 하향")

    # reasoning은 분리했다는데 세그먼트가 하나면 출력이 자기모순이다
    if ("분리" in (clf.get("reasoning") or "")) and len(segs) < 2:
        problems.append("reasoning은 분리인데 segment 1개")
        clf["needs_review"] = True

    if problems:
        clf["needs_review"] = True
        clf["spec_problems"] = problems

    tags = []
    for s in segs:
        for t in s.get("tags", []):
            if t not in tags:
                tags.append(t)
    clf["tags"] = tags
    clf["_v3"] = True
    return clf


def migrate_segment_v2(seg: dict) -> dict:
    """v2 세그먼트 하나를 v3로 기계 변환한다. 불가능하면 None."""
    axes = V2_TO_V3.get(seg.get("category"))
    if not axes:
        return None
    tags = normalize_tags(seg.get("hashtags") or seg.get("tags") or [])
    intent = axes["intent"]
    # #또사고싶다는 태그가 아니라 의도다
    if "#또사고싶다" in (seg.get("hashtags") or []) and intent == "없음":
        intent = "재구매희망"
    # 태그는 상품 속성 어휘다 — 배송·응대 세그먼트에는 남기지 않는다
    if axes["aspect"] != "상품":
        tags = []
    out = {"aspect": axes["aspect"], "sentiment": axes["sentiment"], "intent": intent,
           "tags": tags, "summary": seg.get("summary") or "",
           "confidence": seg.get("confidence", 0.9)}
    out["category"] = derive_category(out)
    return out
