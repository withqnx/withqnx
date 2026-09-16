#!/usr/bin/env python3
"""
data.json 소급 마이그레이션 — 제품 식별 키를 '제품명 문자열' → 'cafe24 상품번호'로.

하는 일 3가지
  1) 각 후기에 product_id 를 채운다  (product_link 의 /product/<슬러그>/<번호>/ 에서 추출)
  2) product_img 의 도메인 중복(https://nonohumble.com//nonohumble.com/...)을 제거해 정규화한다
  3) 같은 product_id 안에서 정식 표시명을 골라 products.json 으로 내보낸다
       {product_id: {"name": 대표명, "img": 썸네일, "aliases": [그동안 쓰인 다른 표기들]}}

기존 product_name 은 지우지 않는다(되돌릴 수 있게 남겨둔다).

사용법
  python3 migrate_product_id.py              # dry-run (기본) — 아무것도 쓰지 않는다
  python3 migrate_product_id.py --apply      # 실제로 data.json 수정 + products.json 생성
  python3 migrate_product_id.py --data /tmp/copy.json --apply   # 사본으로 테스트
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import unquote

# /product/<슬러그>/<상품번호>/ — 상품번호가 유일하게 믿을 수 있는 제품 식별자다.
PRODUCT_ID_RE = re.compile(r"/product/[^/]+/(\d+)/")

# 도메인이 두 번 박힌 깨진 썸네일 URL. 실측: 깨진 URL=404, 중복 제거하면 200.
_DUP_DOMAIN_RE = re.compile(r"^(?:https?:)?//+nonohumble\.com/+nonohumble\.com/", re.I)
_BARE_DUP_RE = re.compile(r"^/+nonohumble\.com/", re.I)

# "겸손-지우산" 처럼 URL 슬러그가 그대로 제품명이 된 경우를 알아본다.
# 공백 없이 하이픈으로 이어붙인 것만 잡는다("... 남성용 - 네이비" 같은 정식 표기는 제외).
_SLUG_LIKE_RE = re.compile(r"\S-\S")


def normalize_img(url: str) -> str:
    """깨진 썸네일 URL(도메인 중복)을 실제로 200 이 나오는 형태로 되돌린다."""
    if not url:
        return ""
    u = url.strip()
    if _DUP_DOMAIN_RE.match(u):
        u = _DUP_DOMAIN_RE.sub("https://nonohumble.com/", u)
    elif _BARE_DUP_RE.match(u):
        u = _BARE_DUP_RE.sub("https://nonohumble.com/", u)
    elif u.startswith("//"):
        u = "https:" + u
    return u


def extract_product_id(link: str) -> str:
    m = PRODUCT_ID_RE.search(link or "")
    return m.group(1) if m else ""


def is_slug_like(name: str) -> bool:
    return bool(_SLUG_LIKE_RE.search(name or ""))


def unslugify(name: str) -> str:
    """슬러그 폴백으로 들어온 이름을 최소한 읽을 수 있게: URL 디코딩 + 하이픈→공백."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", unquote(name).replace("-", " ")).strip()


def pick_canonical(name_counter: Counter) -> str:
    """같은 상품번호 안에서 대표 이름을 고른다. 정식 표시명(하이픈 없는 쪽) 우선."""
    proper = {n: c for n, c in name_counter.items() if n and not is_slug_like(n)}
    pool = proper or {n: c for n, c in name_counter.items() if n}
    if not pool:
        return ""
    # 많이 쓰인 순 → 같으면 긴 이름(정보가 더 많은 쪽)
    best = sorted(pool.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
    return best if proper else unslugify(best)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="실제로 파일에 쓴다. 주지 않으면 dry-run(기본).")
    ap.add_argument("--dry-run", action="store_true",
                    help="명시적 dry-run(기본 동작이라 없어도 같다).")
    ap.add_argument("--data", default="data.json", help="대상 data.json 경로")
    ap.add_argument("--products", default=None,
                    help="내보낼 products.json 경로 (기본: data.json 과 같은 폴더)")
    args = ap.parse_args()

    apply = args.apply and not args.dry_run
    data_path = args.data
    products_path = args.products or os.path.join(os.path.dirname(os.path.abspath(data_path)),
                                                  "products.json")

    if not os.path.exists(data_path):
        print(f"✗ {data_path} 가 없습니다.")
        return 1

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    reviews = data.get("reviews", {})

    names_by_pid = defaultdict(Counter)
    imgs_by_pid = defaultdict(Counter)
    n_total = len(reviews)
    n_pid = n_no_pid = 0
    n_img_fixed = n_img_ok = n_img_missing = 0
    no_pid_samples = []

    for rid, r in reviews.items():
        pid = extract_product_id(r.get("product_link", ""))
        if pid:
            n_pid += 1
            names_by_pid[pid][(r.get("product_name") or "").strip()] += 1
        else:
            n_no_pid += 1
            if len(no_pid_samples) < 5:
                no_pid_samples.append((rid, r.get("product_name", ""), r.get("product_link", "")))

        raw_img = r.get("product_img") or ""
        new_img = normalize_img(raw_img)
        if not raw_img:
            n_img_missing += 1
        elif new_img != raw_img:
            n_img_fixed += 1
        else:
            n_img_ok += 1
        if pid and new_img:
            imgs_by_pid[pid][new_img] += 1

        if apply:
            if pid:
                r["product_id"] = pid
            if new_img:
                r["product_img"] = new_img   # product_name 은 그대로 둔다(되돌리기용)

    # ── products.json 만들기 ──
    products = {}
    n_merged_names = 0
    merged_detail = []
    for pid, counter in names_by_pid.items():
        canonical = pick_canonical(counter)
        aliases = sorted(n for n in counter if n and n != canonical)
        if aliases:
            n_merged_names += len(aliases)
            merged_detail.append((pid, canonical, aliases, sum(counter.values())))
        img = imgs_by_pid[pid].most_common(1)[0][0] if imgs_by_pid.get(pid) else ""
        products[pid] = {"name": canonical, "img": img, "aliases": aliases}

    all_names = {(r.get("product_name") or "").strip()
                 for r in reviews.values() if (r.get("product_name") or "").strip()}

    mode = "APPLY" if apply else "DRY-RUN(기록 안 함)"
    print(f"── migrate_product_id  [{mode}]  대상: {data_path}")
    print(f"후기 {n_total}건")
    print(f"  product_id 부여: {n_pid}건 / 추출 실패: {n_no_pid}건")
    print(f"  제품명(문자열) {len(all_names)}개 → 상품번호 {len(products)}개")
    print(f"  이름 통합(대표명으로 흡수된 별칭 표기): {n_merged_names}건, "
          f"별칭을 가진 상품 {len(merged_detail)}개")
    print(f"  썸네일 정규화: {n_img_fixed}건 수정 / {n_img_ok}건 이미 정상 / {n_img_missing}건 없음")

    if no_pid_samples:
        print("\n  ⚠️ product_id 추출 실패 표본:")
        for rid, nm, lk in no_pid_samples:
            print(f"    #{rid} [{nm}] {lk[:80]}")

    print("\n  이름이 여러 표기로 갈렸던 상품 (상위 12개, 후기수 순):")
    for pid, canon, aliases, cnt in sorted(merged_detail, key=lambda x: -x[3])[:12]:
        print(f"    {pid}  {canon}  ({cnt}건)  ← {', '.join(aliases)}")

    slug_only = [(pid, p["name"]) for pid, p in products.items()
                 if p["name"] and p["name"] not in all_names]
    if slug_only:
        print(f"\n  정식 표시명이 한 번도 안 잡혀서 슬러그를 풀어 쓴 상품 {len(slug_only)}개:")
        for pid, nm in slug_only:
            print(f"    {pid}  → '{nm}'")

    if apply:
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(products_path, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 기록 완료: {data_path}, {products_path}")
    else:
        print(f"\n(dry-run) --apply 를 주면 {data_path} 수정 + {products_path} 생성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
