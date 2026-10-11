#!/usr/bin/env python3
"""확인 대기(1·2차 판정 불일치) 대목을 사람이 기준을 정하기 쉬운 유형으로 묶는다 → intel/queue_types.json"""
import json, os, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
LABEL = {"긍정": "좋음", "중립": "보통", "부정": "나쁨"}

TYPES = [
    ("accepts", "단점을 말했지만 괜찮다고 한 것",
     "«빳빳하지만 길들 것 같다», «작은 편이지만 내 체구엔 맞다»처럼 아쉬운 점을 말하면서 스스로 받아들인 대목입니다.",
     lambda s: s["intent"] == "없음" and s["aspect"] == "상품" and s["sentiment"] == "중립" and s["verify"] == "긍정", "보통"),
    ("delay", "배송이 오래 걸렸다는 이야기",
     "«해외 주문보다 오래 기다렸다», «늦게 와서 계절이 지났다»처럼 배송 기간을 말한 대목입니다. 처음 판정은 보통, 다시 본 판정은 나쁨이었습니다.",
     lambda s: s["aspect"] == "배송·포장" and s["sentiment"] == "중립" and s["verify"] == "부정", "나쁨"),
    ("facts", "칭찬 없이 사실만 적은 것",
     "«공장장 사인이 들어 있었다», «선물용으로 색깔별로 샀다»처럼 평가 없이 있었던 일만 적은 대목입니다. 처음 판정은 좋음이었습니다.",
     lambda s: s["intent"] == "없음" and s["aspect"] == "상품" and s["sentiment"] == "긍정" and s["verify"] == "중립", "보통"),
    ("minor", "칭찬 속에 섞인 작은 아쉬움",
     "«디자인 좋은데 맨살엔 좀 거칠다», «편한데 살짝 헐렁해서 패드를 댔다»처럼 칭찬 옆에 붙은 작은 불편입니다. 처음 판정은 나쁨, 다시 본 판정은 좋음이었습니다.",
     lambda s: s["intent"] == "없음" and s["aspect"] == "상품" and s["sentiment"] == "부정" and s["verify"] == "긍정", "나쁨"),
    ("adapting", "적응 중이거나 가볍게 짚은 불편",
     "«그립감이 애매해서 적응 중», «잉크가 금방 떨어진다», «모자가 살짝 무겁다»처럼 가볍게 짚은 불편입니다. 다시 본 판정은 나쁨이었습니다.",
     lambda s: s["intent"] == "없음" and s["aspect"] == "상품" and s["verify"] == "부정" and s["sentiment"] in ("중립", "긍정"), "나쁨"),
    ("thanks", "잘 받았다는 짧은 인사",
     "«어제 받았어요», «케이스까지 잘 받았습니다»처럼 받았다는 사실만 짧게 적은 배송 대목입니다. 처음 판정은 좋음이었습니다.",
     lambda s: s["aspect"] == "배송·포장" and s["sentiment"] == "긍정" and s["verify"] == "중립", "보통"),
    ("other", "그 밖의 것",
     "위 유형에 들지 않는 몇 건입니다(응대 이야기, 재구매 관련 등). 하나씩 보시는 걸 권합니다.",
     lambda s: True, "each"),
]


def main():
    reviews = json.load(open(f"{PROJ}/data.json"))["reviews"]
    groups = collections.OrderedDict((t[0], []) for t in TYPES)
    for r in reviews.values():
        clf = r.get("classification") or {}
        if not clf.get("needs_review"):
            continue
        for i, s in enumerate(clf.get("segments") or [], 1):
            if not s.get("verify") or s["verify"] == s.get("sentiment") or s.get("_gold") or s.get("_auto_ok"):
                continue
            s2 = {"intent": s.get("intent") or "없음", "aspect": s.get("aspect"), "sentiment": s.get("sentiment"), "verify": s["verify"]}
            tid = next(t[0] for t in TYPES if t[3](s2))
            groups[tid].append({
                "key": f"{r['id']}#{i}", "id": r["id"], "product": r.get("product_name") or "",
                "summary": s.get("summary") or "", "first": LABEL.get(s.get("sentiment")), "second": LABEL.get(s["verify"]),
                "intent": s2["intent"], "aspect": s2["aspect"],
                "text": re.sub(r"\s+", " ", (r.get("title") or "") + " — " + (r.get("content") or ""))[:240],
                "date": (r.get("written_at") or "")[:10], "link": r.get("review_link") or "",
            })
    out = []
    for tid, name, desc, _, rec in TYPES:
        items = sorted(groups[tid], key=lambda x: x["date"], reverse=True)
        if items:
            out.append({"id": tid, "name": name, "desc": desc, "rec": rec, "items": items})
    json.dump(out, open(f"{HERE}/queue_types.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for t in out:
        print(t["id"], t["name"], len(t["items"]))
    print("대목 합계", sum(len(t["items"]) for t in out), "· 후기", len({x["id"] for t in out for x in t["items"]}))


if __name__ == "__main__":
    main()
