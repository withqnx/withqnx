#!/usr/bin/env python3
"""
debug_html/ 폴더의 HTML 파일들을 다시 파싱해서 data.json에 통합.

사용법: python3 merge_debug.py

각 debug_html/{post_id}.html 파일을 읽고:
  1. 본문 재추출 시도 (개선된 파서 사용)
  2. 본문이 비어있어도 일단 후기로 등록 (제목만 적은 케이스)
  3. 분류/해시태그도 함께 적용
  4. data.json에 추가 (이미 있는 ID는 본문 있는 쪽으로 갱신)
"""

import json, os, re, time
from datetime import date

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ beautifulsoup4가 필요합니다.")
    print("   source venv/bin/activate && pip install beautifulsoup4")
    exit(1)

# crawl.py에서 필요한 부분만 가져오기 (같은 폴더에서 실행)
import sys
sys.path.insert(0, ".")

try:
    from crawl import (
        parse_detail, classify, extract_hashtags,
        BASE_URL, _ARTICLE_ID_RE
    )
except ImportError as e:
    print(f"❌ crawl.py를 import할 수 없습니다: {e}")
    print("   crawl.py와 같은 폴더에서 실행하세요.")
    exit(1)

DATA_FILE = "data.json"
DEBUG_DIR = "debug_html"


def parse_html_string(html: str, post_id: str) -> dict:
    """HTML 문자열에서 본문/이미지/상품명 추출 (parse_detail과 동일 로직)"""
    soup = BeautifulSoup(html, "html.parser")

    # 상품명/링크
    detail_product_name = ""
    detail_product_link = ""
    for h3 in soup.find_all("h3"):
        a = h3.find("a", href=True)
        if a and ("product" in a["href"] or "/product/" in a["href"]):
            txt = a.get_text(strip=True)
            if txt and txt not in ["상품 사용후기", "댓글달기", "관련 글 보기"]:
                detail_product_name = txt
                href = a["href"]
                detail_product_link = (BASE_URL + href) if href.startswith("/") else href
                break

    if not detail_product_name:
        for a in soup.find_all("a", href=True):
            m = re.search(r"/product/([^/?]+)/\d+/?", a["href"])
            if m:
                from urllib.parse import unquote
                cand = unquote(m.group(1))
                if cand and "detail" not in cand:
                    detail_product_name = cand
                    detail_product_link = (BASE_URL + a["href"]) if a["href"].startswith("/") else a["href"]
                    break

    # 제목 (h3 안에 게시글 제목 있음 — 상품명 h3 다음에 보통 또 다른 h3가 제목)
    title = ""
    for h3 in soup.find_all("h3"):
        txt = h3.get_text(strip=True)
        if txt and txt not in ["상품 사용후기", "댓글달기", "관련 글 보기",
                                "WORLD SHIPPING", "SEARCH", "현재 결제가 진행중입니다.",
                                detail_product_name]:
            # h3 안에 a 태그(상품 링크)가 있는지 확인 - 있으면 그건 상품, 아니면 게시글 제목
            if not h3.find("a", href=lambda h: h and "/product/" in h):
                title = txt
                break

    # 작성일 / 조회수 - 메타정보에서 추출
    written_at = ""
    views = "0"
    # "2026-05-15 14:36:40" 같은 패턴 찾기
    for s in soup.stripped_strings:
        m = re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$", s)
        if m and not written_at:
            written_at = s
        m = re.match(r"^조회\s*(\d+)$", s)
        if m and views == "0":
            views = m.group(1)

    # 본문 추출 (parse_detail 로직과 동일)
    content = ""
    selectors = [
        ".xans-board-readbody", ".readContents", ".board-view-content",
        ".content-area", "#contents .board-view", "td.read-content",
        ".xans-board-read .content",
    ]
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            txt = node.get_text(separator="\n", strip=True)
            if len(txt) > 10:
                content = txt
                break

    if not content:
        ps = soup.find_all("p")
        body_parts = []
        for p in ps:
            txt = p.get_text(separator="\n", strip=True)
            if (len(txt) > 8 and not any(skip in txt for skip in [
                "Copyright", "SHIPPING TO", "고객센터", "결제정보",
                "쇼핑몰 기본정보", "이용약관", "회사소개",
                "현재 결제가 진행중", "오늘 하루 보지 않기",
                "회원에게만", "본 결제 창"
            ])):
                body_parts.append(txt)
        if body_parts:
            content = "\n".join(body_parts).strip()

    if not content:
        for h3 in soup.find_all("h3"):
            txt = h3.get_text(strip=True)
            if txt in ["상품 사용후기", "댓글달기", "관련 글 보기",
                       "WORLD SHIPPING", "SEARCH", "현재 결제가 진행중입니다.",
                       detail_product_name, title]:
                continue
            body_parts = []
            for sib in h3.find_next_siblings():
                stxt = sib.get_text(separator="\n", strip=True)
                if any(x in stxt for x in ["스팸신고", "수정", "삭제", "목록",
                                            "댓글달기", "비밀번호", "이전"]):
                    break
                if stxt and len(stxt) > 5:
                    if re.match(r"^[가-힣]\*+\s*\(ip:.*?\)$", stxt):
                        continue
                    body_parts.append(stxt)
            if body_parts:
                content = "\n".join(body_parts).strip()
                break

    # 잡음 제거 (crawl.py와 같은 패턴)
    if content:
        noise_patterns = [
            r"전체상품목록 바로가기.*?(?=\n|$)",
            r"본문 바로가기.*?(?=\n|$)",
            r"첫 쇼핑을 지원하는.*?쿠폰.*?(?=\n|$)",
            r"오늘 하루 보지 않기",
            r"상세보기\s*상품정보선택\s*주문상품선택",
            r"상품정보선택", r"주문상품선택",
            r"PLEASE SELECT THE DESTINATION.*",
            r"SHIPPING TO\s*:.*", r"LANGUAGE\s*:.*",
            r"WORLD SHIPPING", r"현재 결제가 진행중입니다\.",
            r"본 결제 창은.*?마시기 바랍니다\.",
            r"고객님은 안전거래를.*?이용하실 수 있습니다\.",
            r"\[서비스가입정보확인\]",
            r"Copyright © .*All Rights Reserved.*",
            r"Hosting by Cafe24 Corp\.",
            r"삭제하려면 비밀번호를 입력하세요\.?",
            r"댓글 수정", r"댓글 입력", r"비밀댓글",
            r"영문 대소문자/숫자/특수문자.*",
            r"왼쪽의 문자를 공백없이.*",
            r"회원에게만 댓글 작성 권한이 있습니다\.",
            r"^추천\s+추천하기.*",
            r"이전\s*\[.*?\]\s*다음",
            r"관련글 모음",
        ]
        for pat in noise_patterns:
            content = re.sub(pat, "", content, flags=re.IGNORECASE)

        content = re.sub(r"^\[[\w._]+\.(jpg|jpeg|png|gif|webp)\](\s*,\s*\[[\w._]+\.(jpg|jpeg|png|gif|webp)\])*\s*$",
                        "", content, flags=re.MULTILINE)
        content = re.sub(r"^[가-힣]\*+\s*\(ip:.*?\)$", "", content, flags=re.MULTILINE)
        content = re.sub(r"^(추천|조회|평점|작성일|날짜)\s*[:\s].*$", "", content, flags=re.MULTILINE)
        content = re.sub(r"^https?://[^\s]+$", "", content, flags=re.MULTILINE)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        if len(content) < 5:
            content = ""

    # 이미지
    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "file_data" not in src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = BASE_URL + src
        elif src.startswith("nonohumble.com"):
            src = "https://" + src
        elif not src.startswith("http"):
            src = BASE_URL + "/" + src.lstrip("/")
        src = re.sub(r"^https?://nonohumble\.com/+nonohumble\.com/", "https://nonohumble.com/", src)
        if src not in images:
            images.append(src)

    return {
        "title": title,
        "content": content,
        "images": images,
        "product_name": detail_product_name,
        "product_link": detail_product_link,
        "written_at": written_at,
        "views": views,
    }


def main():
    if not os.path.isdir(DEBUG_DIR):
        print(f"❌ {DEBUG_DIR} 폴더가 없습니다.")
        return

    # 기존 data.json 로드
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"reviews": {}, "daily_logs": [], "last_updated": ""}

    files = [f for f in os.listdir(DEBUG_DIR) if f.endswith(".html")]
    print(f"🔍 {len(files)}개 디버그 HTML 발견")
    print()

    added = 0
    updated = 0
    skipped = 0
    skipped_dasvoida = 0
    empty_body_count = 0
    today_str = date.today().isoformat()

    for i, fn in enumerate(files, 1):
        post_id = fn.replace(".html", "")
        path = os.path.join(DEBUG_DIR, fn)

        try:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
        except Exception as e:
            print(f"  ⚠️  {fn} 읽기 실패: {e}")
            continue

        parsed = parse_html_string(html, post_id)

        # 다스뵈이다 점빵 필터
        if "다스뵈이다" in parsed["product_name"] or "점빵" in parsed["product_name"]:
            skipped_dasvoida += 1
            continue

        # 이미 있는 글이면 본문이 더 풍부한 쪽으로 갱신
        if post_id in data["reviews"]:
            existing = data["reviews"][post_id]
            # 기존에 본문 있으면 그냥 스킵, 없으면 새로 채움
            if existing.get("content") and len(existing["content"]) > len(parsed["content"]):
                skipped += 1
                continue
            # 새 데이터로 갱신
            existing["content"] = parsed["content"] or existing.get("content", "")
            existing["images"] = parsed["images"] or existing.get("images", [])
            if not existing.get("product_name") and parsed["product_name"]:
                existing["product_name"] = parsed["product_name"]
                existing["product_link"] = parsed["product_link"]
            if not existing.get("title") and parsed["title"]:
                existing["title"] = parsed["title"]
            # 해시태그 재계산
            existing["hashtags"] = extract_hashtags(
                existing.get("title", "") + " " + existing.get("content", "")
            )
            # 분류가 비어있으면 새로 분류
            if not existing.get("classification"):
                existing["classification"] = classify(
                    existing.get("title", ""),
                    existing.get("content", ""),
                    post_id
                )
            updated += 1
        else:
            # 새로 추가
            item = {
                "id": post_id,
                "product_name": parsed["product_name"],
                "product_link": parsed["product_link"],
                "product_img": "",
                "title": parsed["title"] or "(제목 없음)",
                "review_link": f"{BASE_URL}/article/상품-사용후기/4/{post_id}/",
                "has_photo": len(parsed["images"]) > 0,
                "written_at": parsed["written_at"],
                "views": parsed["views"],
                "content": parsed["content"],
                "images": parsed["images"],
                "hashtags": extract_hashtags(parsed["title"] + " " + parsed["content"]),
                "classification": classify(parsed["title"], parsed["content"], post_id),
                "crawled_date": today_str,
            }
            data["reviews"][post_id] = item
            added += 1

        if not parsed["content"]:
            empty_body_count += 1

        if i % 20 == 0:
            print(f"  진행: {i}/{len(files)} (추가 {added}, 갱신 {updated})")

    # 저장
    data["last_updated"] = data.get("last_updated", "") + f" (debug merge: {date.today()})"
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 50)
    print("✅ 완료")
    print("=" * 50)
    print(f"  새로 추가: {added}건")
    print(f"  기존 갱신: {updated}건")
    print(f"  스킵 (기존이 더 풍부): {skipped}건")
    print(f"  스킵 (다스뵈이다 점빵): {skipped_dasvoida}건")
    print(f"  본문 진짜로 빈 후기: {empty_body_count}건 (제목만 적은 케이스)")
    print(f"  총 후기 수: {len(data['reviews'])}건")
    print()
    print("debug_html/ 폴더는 이제 삭제해도 됩니다:")
    print(f"  rm -rf {DEBUG_DIR}")


if __name__ == "__main__":
    main()
