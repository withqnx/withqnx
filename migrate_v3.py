#!/usr/bin/env python3
"""분류 v2 → v3(3축) 소급 변환.

기계 변환이 가능한 건 그 자리에서 바꾸고, 불가능하거나 품질이 의심되는 건은
재분류 대상으로 표시만 한다(내용을 지우지 않는다).

  python3 migrate_v3.py               # dry-run (기본) — 아무것도 안 쓴다
  python3 migrate_v3.py --apply       # data.json 갱신 + reclass_targets.json 생성
"""
import json, os, re, sys, collections
import taxonomy as T

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
APPLY = "--apply" in sys.argv

# 재분류가 필요한 신호들 — 기계 변환으로는 복구할 수 없는 정보다
Q_PAT  = re.compile(r"(가능한[가까]요|있나요|되나요|인가요|어떻게\s*(하|해)|문의|알려\s*주세요|궁금)")
ADV    = re.compile(r"(그런데|근데|하지만|다만|아쉬운|아쉽|한 가지|단점|빼고는|말고는|것만 빼면)")
CS_PAT = re.compile(r"(상담|응대|고객\s*센터|답변이|연락이|문자가|안내가)")
PRETTY = re.compile(r"(예쁘|이쁘|예뻐|이뻐|예쁩|이쁩)")
SHAPE  = re.compile(r"(패턴|라인|넥|실루엣|형태|모양|각|곡선|디테일|스티치|비율|기장|굽|테|프레임)")
SATISF = re.compile(r"(만족|좋아요|좋습니다|감사합니다|잘\s*받았)")
GIFT   = re.compile(r"(선물|생신|생일|드렸|사드|아버지|어머니|남편|아내|와이프|딸|아들|언니|친구)")


def reasons_to_reclassify(rv, segs_v2):
    """왜 사람/AI가 다시 봐야 하는지. 빈 리스트면 기계 변환으로 충분."""
    why = []
    text = (rv.get("content") or "") + " " + (rv.get("title") or "")
    clf = rv.get("classification") or {}
    if not segs_v2:
        why.append("미분류")
    if any(s.get("category") not in T.V2_TO_V3 for s in segs_v2):
        why.append("규격외 카테고리")
    # #또사고싶다는 의도 축으로 승격되므로 규격 위반이 아니다
    if any(T.TAG_ALIASES.get(t, t) not in T.TAGS and t != "#또사고싶다"
           for s in segs_v2 for t in (s.get("hashtags") or [])):
        why.append("규격외 태그")
    if segs_v2 and all(not (s.get("summary") or "").strip() for s in segs_v2):
        why.append("요약 없음")
    if Q_PAT.search(text):
        why.append("문의 의도 가능")          # v2엔 담을 축이 없었다
    if CS_PAT.search(rv.get("content") or ""):
        why.append("응대·소통 대상 가능")      # v2엔 담을 축이 없었다
    if ADV.search(rv.get("content") or "") and len(segs_v2) == 1:
        why.append("혼합 누락 의심")
    body = rv.get("content") or ""
    tags_all = {t for s in segs_v2 for t in (s.get("hashtags") or [])}
    # 근거 없는 "예쁘다"가 #디자인으로 샌 것 → #첫인상 으로 가야 한다
    if "#디자인" in tags_all and PRETTY.search(body) and not SHAPE.search(body):
        why.append("#디자인 오적용(근거 없는 예쁘다)")
    # "만족합니다" 류가 #퀄리티로 샌 것 → 태그 없음이 정답
    if "#퀄리티" in tags_all and SATISF.search(body):
        why.append("#퀄리티 오적용(순수 감정 표현)")
    # 신설 태그라 기존 분류엔 존재할 수 없다
    if GIFT.search(body):
        why.append("#선물 신설 태그 대상")
    if T.HEDGE.search(clf.get("reasoning") or ""):
        why.append("reasoning이 애매함을 인정")
    return why


def main():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    reviews = data["reviews"]

    stat = collections.Counter()
    why_stat = collections.Counter()
    cat_before = collections.Counter()
    cat_after = collections.Counter()
    targets = []

    for rid, rv in reviews.items():
        clf = rv.get("classification") or {}
        segs_v2 = clf.get("segments") or []
        for s in segs_v2:
            cat_before[s.get("category")] += 1

        why = reasons_to_reclassify(rv, segs_v2)
        if why:
            targets.append({"id": rid, "why": why})
            for w in why:
                why_stat[w] += 1

        new_segs, failed = [], False
        for s in segs_v2:
            m = T.migrate_segment_v2(s)
            if m is None:
                failed = True
                break
            new_segs.append(m)

        if failed or not new_segs:
            stat["기계변환 불가(재분류 대기)"] += 1
            continue

        for s in new_segs:
            cat_after[s["category"]] += 1
        stat["기계변환 완료"] += 1

        if APPLY:
            clf["segments"] = new_segs
            clf["_v3"] = True
            clf["tags"] = [t for s in new_segs for t in s["tags"]]
            clf["tags"] = list(dict.fromkeys(clf["tags"]))
            if why:
                clf["reclassify_pending"] = why
            rv["classification"] = clf
            rv["hashtags"] = clf["tags"]

    print(f"후기 {len(reviews)}건")
    for k, v in stat.most_common():
        print(f"  {v:5d}  {k}")
    print(f"\n재분류 대상 {len(targets)}건 — 사유별(중복 포함):")
    for k, v in why_stat.most_common():
        print(f"  {v:5d}  {k}")

    print("\n파생 카테고리 변화 (기계변환분만):")
    keys = sorted(set(cat_before) | set(cat_after), key=lambda k: -cat_before.get(k, 0))
    for k in keys:
        b, a = cat_before.get(k, 0), cat_after.get(k, 0)
        mark = "" if b == a else "   <-- 이동"
        print(f"  {str(k):16s} {b:5d} -> {a:5d}{mark}")

    if not APPLY:
        print("\n[DRY-RUN] 아무것도 쓰지 않았다. 실제 적용은 --apply")
        return

    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, DATA_FILE)
    targets_path = os.path.join(os.path.dirname(os.path.abspath(DATA_FILE)), "reclass_targets.json")
    with open(targets_path, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {DATA_FILE}, {targets_path} ({len(targets)}건)")


if __name__ == "__main__":
    main()
