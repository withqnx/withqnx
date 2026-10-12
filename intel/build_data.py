#!/usr/bin/env python3
"""겸손몰 후기 대시보드(intel) 데이터 묶음을 만든다.

  python3 intel/build_data.py --meta   브레인 제품명부(NAS, 읽기만) → intel/product_meta.json  (이 맥에서만)
  python3 intel/build_data.py          data.json + intel/product_meta.json → intel/intel_data.json (어디서나, CI 포함)
조인: 겸손몰 product_id → 10MH_BRAIN/_tools/mall_products.tsv(제품_노트) → products/**/<노트>.md 프론트매터.
⛔ 브레인 '번호'로 조인하지 않는다(묶음 번호라 서로 다른 제품이 섞인다).
partner 는 N:N 이라 파트너별로 후기 수를 합산하지 않는다(나열만).
"""
import collections, glob, json, os, re, sys, unicodedata
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
BRAIN = "/Volumes/Mall(new)/DATA/10MH_BRAIN"
TSV = f"{BRAIN}/_tools/mall_products.tsv"
META = f"{HERE}/product_meta.json"
PILOT_TSV = f"{BRAIN}/_tools/pilot_partners.tsv"   # 파일럿은 노트가 없어 협력사를 여기서 읽는다(척척이 관리)
CATS = ["의류", "패션잡화", "신발", "문구", "생활", "식품", "장인"]   # 품목 7종(2026-10-12 이석원 확정, 브레인 노트 tags)
SENT = ["긍정", "중립", "부정"]
INTENTS = ["교환·반품", "문의", "제품제안", "재구매희망", "양도·거래"]
EXCLUDE_NAME = re.compile(r"추가 ?구매|추가구매|준비중")   # 심지 추가는 소속 파인라이너로 센다(2026-10-11 이석원)
QUOTE = 150


def frontmatter(path):
    txt = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---", txt, re.S)
    fm = {}
    if not m:
        return fm
    for line in unicodedata.normalize('NFC', m.group(1)).splitlines():
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        fm[k.strip()] = v
    return fm


def note_index():
    idx = {}
    for p in glob.glob(f"{BRAIN}/products/**/*.md", recursive=True):
        if "/_진행/" in unicodedata.normalize("NFC", p):
            continue
        idx.setdefault(unicodedata.normalize('NFC', os.path.basename(p)[:-3]), p)
    return idx


def pilot_partners():
    out = {}
    if os.path.exists(PILOT_TSV):
        for line in open(PILOT_TSV, encoding="utf-8"):
            if line.startswith("#") or not line.strip():
                continue
            c = [unicodedata.normalize("NFC", x).strip() for x in line.rstrip("\n").split("\t")]
            if len(c) >= 3:
                out[c[0]] = {"partners": [x.strip() for x in c[2].split("·") if x.strip()],
                             "cats": [x.strip() for x in (c[3] if len(c) >= 4 else "").split("·") if x.strip()]}
    return out


def load_roster():
    notes = note_index()
    pilots = pilot_partners()
    roster = {}
    for line in open(TSV, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 4:
            continue
        pid, name, num, note = [unicodedata.normalize('NFC', c) for c in cols[:4]]
        if "테스트" in num or EXCLUDE_NAME.search(name) or re.search(r"\[\d차 예약구매\]", name) and num != "파일럿":
            roster[pid] = None
            continue
        if num == "파일럿":
            base = re.sub(r"\[\d차 예약구매\]\s*", "", name).strip()
            if EXCLUDE_NAME.search(base):
                roster[pid] = None
                continue
            base = re.sub(r"\s*-\s*\S+$", "", base)          # 색상 꼬리 제거
            roster[pid] = {"key": f"PRE {base}", "name": base, "num": "PRE", "pilot": True,
                           "mall": name, "fm": {"partner": pilots.get(pid, {}).get("partners", []), "tags": pilots.get(pid, {}).get("cats", [])}, "group": f"PRE {base}"}
            continue
        if note in ("—", "-", ""):
            roster[pid] = None
            continue
        path = notes.get(note)
        if not path:  # 노트 파일명이 제품_노트 열보다 짧은 경우(예: '103 겸손트렌치코트')
            # 같은 번호의 노트 중 이름 글자가 가장 많이 겹치는 것(예: '203 겸손 여자 지갑' → '203 겸손지갑')
            num0 = note.split(" ")[0]
            cand = [k for k in notes if k.split(" ")[0] == num0]
            score = lambda k: len(set(k.replace(" ", "")) & set(note.replace(" ", "")))
            path = notes.get(max(cand, key=score)) if cand else None
        fm = frontmatter(path) if path else {}
        title = re.sub(r"^\d+\s+", "", note)
        # 한 줄 = 겸손몰 상세페이지(상품 id) 하나(2026-10-12 이석원). 같은 제품 노트끼리는 group으로 묶어 상세에서 서로 잇는다.
        roster[pid] = {"key": f"P{pid}", "name": re.sub(r"\s+", " ", name).strip(), "num": note.split(" ")[0], "pilot": False,
                       "mall": name, "fm": fm, "group": note}
    return roster


# 파트너 표기는 브레인 노트가 정본(척척이가 2026-10-11 «회사 + 대표 한 명»으로 통일, frontmatter_sync.py PARTNER_CANON).
# 다시 어긋나는 표기가 생겼을 때만 여기에 임시로 넣는다.
PARTNER_ALIAS = {}


def roster_to_meta(roster):
    """명부를 레포에 둘 수 있는 평평한 형태로: 상품id → 제품 정보(또는 집계 제외 None)."""
    out = {}
    for pid, info in roster.items():
        if info is None:
            out[pid] = None
            continue
        fm = info["fm"]
        partner = fm.get("partner")
        out[pid] = {"key": info["key"], "group": info["group"], "name": info["name"], "num": info["num"], "pilot": info["pilot"],
                    "mall": info["mall"], "status": fm.get("status", "판매종료" if info["pilot"] else ""),
                    "season": fm.get("season", ""),
                    "partners": list(dict.fromkeys(PARTNER_ALIAS.get(x, x) for x in
                                                   (partner if isinstance(partner, list) else ([partner] if partner else [])))),
                    "cats": [c for c in (fm.get("tags") or []) if c in CATS]}
    return out


def month(s):
    return (s or "")[:7]


def main():
    if "--meta" in sys.argv:
        meta = roster_to_meta(load_roster())
        json.dump(meta, open(META, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
        print(f"제품 명부 {sum(1 for v in meta.values() if v)}개 상품id(제외 {sum(1 for v in meta.values() if v is None)}) → {META}")
        return
    data = json.load(open(f"{PROJ}/data.json"))
    reviews = data["reviews"]
    roster = json.load(open(META, encoding="utf-8"))

    prods = {}
    unmatched = collections.Counter()
    monthly = collections.defaultdict(lambda: [0, 0, 0, 0])   # 후기수, 좋음, 보통, 나쁨(언급)
    tag_all, tag_neg = collections.Counter(), collections.Counter()
    todo, queue = [], []
    n_seg = 0

    for r in reviews.values():
        pid = str(r.get("product_id") or "")
        if pid in roster and roster[pid] is None:
            continue                      # 테스트·추가구매·예약 차수
        info = roster.get(pid)
        if info is None:                  # 명부에 아직 없는 새 상품 — 등록명으로 따로 보여 준다
            unmatched[r.get("product_name")] += 1
            nm = r.get("product_name") or f"상품 {pid}"
            info = {"key": f"NEW {pid}", "name": nm, "num": "신규", "pilot": False, "mall": nm,
                    "status": "", "season": "", "partners": [], "cats": []}
        clf = r.get("classification") or {}
        segs = clf.get("segments") or []
        key = info["key"]
        p = prods.get(key)
        if not p:
            p = prods[key] = {
                "key": key, "group": info.get("group", key), "name": info["name"], "num": info["num"], "pilot": info["pilot"],
                "mall": set(), "status": info["status"], "season": info["season"],
                "partners": info["partners"], "cats": info["cats"],
                "n": 0, "sent": [0, 0, 0], "tags": collections.Counter(), "neg": collections.Counter(),
                "intent": collections.Counter(), "series": collections.defaultdict(lambda: [0, 0, 0, 0]),
                "first": "9999", "last": "0000", "pos_q": [], "neg_q": [], "pid": pid,
                "pos": collections.Counter(), "imgs": collections.Counter(), "tq": collections.defaultdict(list),
            }
        p["mall"].add(info["mall"])
        if r.get("product_img"):
            p["imgs"][r["product_img"]] += 1
        p["n"] += 1
        d = r.get("written_at") or ""
        p["first"], p["last"] = min(p["first"], d), max(p["last"], d)
        mo = month(d)
        p["series"][mo][0] += 1
        monthly[mo][0] += 1
        for s in segs:
            n_seg += 1
            si = SENT.index(s.get("sentiment", "중립")) if s.get("sentiment") in SENT else 1
            p["sent"][si] += 1
            p["series"][mo][si + 1] += 1
            monthly[mo][si + 1] += 1
            for t in s.get("tags") or []:
                p["tags"][t] += 1; tag_all[t] += 1
                if si == 2:
                    p["neg"][t] += 1; tag_neg[t] += 1
                if si == 0:
                    p["pos"][t] += 1
                if si in (0, 2) and s.get("summary"):   # 세분류별 대표 요약(좋음/나쁨)
                    p["tq"][(t, si)].append((len(r.get("content") or "") > 60, d[:10], s["summary"], r.get("review_link", "")))
            it = s.get("intent")
            if it in INTENTS:
                p["intent"][it] += 1
                todo.append({"id": r["id"], "p": key, "i": it, "s": s.get("summary", ""),
                             "v": si, "d": d[:10], "link": r.get("review_link", "")})
            quote = {"id": r["id"], "s": s.get("summary", ""), "t": r.get("title", "")[:60],
                     "c": re.sub(r"\s+", " ", r.get("content") or "")[:QUOTE],
                     "d": d[:10], "link": r.get("review_link", ""), "len": len(r.get("content") or "")}
            if si == 0 and it in (None, "없음", "재구매희망"):
                p["pos_q"].append(quote)
            elif si == 2 and it in (None, "없음", "교환·반품"):
                p["neg_q"].append(quote)
        if clf.get("needs_review"):
            bad = [s for s in segs if s.get("verify") and s["verify"] != s.get("sentiment")
                   and not s.get("_gold") and not s.get("_auto_ok")]
            if bad:
                queue.append({"id": r["id"], "p": key, "d": d[:10], "link": r.get("review_link", ""),
                              "c": re.sub(r"\s+", " ", r.get("content") or "")[:220],
                              "segs": [{"s": s.get("summary", ""), "a": s.get("sentiment"), "b": s.get("verify"),
                                        "i": s.get("intent")} for s in bad]})

    out = []
    for p in prods.values():
        # 대표 인용: 본문이 충분히 긴 것 우선, 최신순
        for k in ("pos_q", "neg_q"):
            q = sorted(p[k], key=lambda x: (x["len"] > 60, x["d"]), reverse=True)
            seen, pick = set(), []
            for x in q:
                if x["id"] in seen:
                    continue
                seen.add(x["id"]); pick.append({kk: vv for kk, vv in x.items() if kk != "len"})
                if len(pick) == 3:
                    break
            p[k] = pick
        p["mall"] = sorted(p["mall"])
        p["tags"] = dict(p["tags"].most_common())
        p["neg"] = dict(p["neg"].most_common())
        p["pos"] = dict(p["pos"].most_common())
        p["img"] = p["imgs"].most_common(1)[0][0] if p["imgs"] else ""
        ex = {}
        for (t, si), lst in p["tq"].items():
            lst.sort(reverse=True)
            ex.setdefault(t, {})["g" if si == 0 else "b"] = [{"s": x[2], "link": x[3]} for x in lst[:2]]
        p["tex"] = ex
        del p["imgs"], p["tq"]
        p["intent"] = dict(p["intent"])
        p["series"] = [[m] + v for m, v in sorted(p["series"].items()) if m]
        p["first"], p["last"] = p["first"][:10], p["last"][:10]
        out.append(p)
    out.sort(key=lambda p: -p["n"])

    todo.sort(key=lambda x: x["d"], reverse=True)
    queue.sort(key=lambda x: x["d"], reverse=True)
    months = sorted(m for m in monthly if m)
    meta = {
        "updated": data.get("last_updated"), "built": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reviews": sum(p["n"] for p in out), "all_reviews": len(reviews), "segments": n_seg,
        "products": len(out), "queue": len(queue),
        "excluded": len(reviews) - sum(p["n"] for p in out),
        "tags": [t for t, _ in tag_all.most_common()],
        "tag_all": dict(tag_all), "tag_neg": dict(tag_neg),
        "monthly": [[m] + monthly[m] for m in months],
    }
    bundle = {"meta": meta, "products": out, "todo": todo, "queue": queue}
    path = f"{HERE}/intel_data.json"
    json.dump(bundle, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"제품 {len(out)} · 집계 후기 {meta['reviews']}/{len(reviews)} · 언급 {n_seg} · "
          f"요청 {len(todo)} · 확인대기 {len(queue)} · {os.path.getsize(path)//1024}KB")
    if unmatched:
        print("명부에 없는 상품:", unmatched.most_common(10))
    miss = [p["key"] for p in out if not p["pilot"] and not p["partners"]]
    print("파트너 없는 제품(노트 확인):", miss)


if __name__ == "__main__":
    main()
