#!/usr/bin/env python3
"""
겸손은힘들다 상품 사용후기 크롤러
사용법: python3 crawl.py
"""

import requests
from bs4 import BeautifulSoup
import json, os, re, time
from datetime import datetime, date

try:
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    _ai_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    AI_AVAILABLE = True
except Exception:
    AI_AVAILABLE = False
    _ai_client = None

# ── 설정 ─────────────────────────────────────────────
BASE_URL   = "https://nonohumble.com"
BOARD_URL  = f"{BASE_URL}/board/상품-사용후기/4/"
DATA_FILE  = "data.json"
DELAY      = 0.5

TEST_MODE  = False
DEBUG_MODE = False

_ARTICLE_ID_RE = re.compile(r"/article/[^/]+/\d+/(\d+)/?")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


# ── 상세 페이지 파싱 ──────────────────────────────────
def parse_detail(url: str) -> dict:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
    except Exception:
        return {"content": "", "images": [], "product_name": "", "product_link": ""}

    soup = BeautifulSoup(resp.text, "html.parser")

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

    content = ""

    selectors = [
        ".xans-board-readbody",
        ".readContents",
        ".board-view-content",
        ".content-area",
        "#contents .board-view",
        "td.read-content",
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
            if (len(txt) > 8 and
                not any(skip in txt for skip in [
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
                       "WORLD SHIPPING", "SEARCH", "현재 결제가 진행중입니다."]:
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

    if content:
        noise_patterns = [
            r"전체상품목록 바로가기.*?(?=\n|$)",
            r"본문 바로가기.*?(?=\n|$)",
            r"첫 쇼핑을 지원하는.*?쿠폰.*?(?=\n|$)",
            r"오늘 하루 보지 않기",
            r"상세보기\s*상품정보선택\s*주문상품선택",
            r"상세보기[\s|]*상품정보선택[\s|]*주문상품선택",
            r"상품정보선택",
            r"주문상품선택",
            r"PLEASE SELECT THE DESTINATION.*",
            r"SHIPPING TO\s*:.*",
            r"LANGUAGE\s*:.*",
            r"WORLD SHIPPING",
            r"현재 결제가 진행중입니다\.",
            r"본 결제 창은.*?마시기 바랍니다\.",
            r"고객님은 안전거래를.*?이용하실 수 있습니다\.",
            r"\[서비스가입정보확인\]",
            r"Copyright © .*All Rights Reserved.*",
            r"Hosting by Cafe24 Corp\.",
            r"삭제하려면 비밀번호를 입력하세요\.?",
            r"댓글 수정",
            r"댓글 입력",
            r"비밀댓글",
            r"영문 대소문자/숫자/특수문자.*",
            r"왼쪽의 문자를 공백없이.*",
            r"회원에게만 댓글 작성 권한이 있습니다\.",
            r"^추천\s+추천하기.*",
            r"이전\s*\[.*?\]\s*다음",
            r"관련글 모음",
        ]
        for pat in noise_patterns:
            content = re.sub(pat, "", content, flags=re.IGNORECASE | re.DOTALL if "SHIPPING" in pat or "결제" in pat else re.IGNORECASE)

        content = re.sub(r"^\[[\w._]+\.(jpg|jpeg|png|gif|webp)\](\s*,\s*\[[\w._]+\.(jpg|jpeg|png|gif|webp)\])*\s*$",
                        "", content, flags=re.MULTILINE)
        content = re.sub(r"^[가-힣]\*+\s*\(ip:.*?\)$", "", content, flags=re.MULTILINE)
        content = re.sub(r"^(추천|조회|평점|작성일|날짜)\s*[:\s].*$", "", content, flags=re.MULTILINE)
        content = re.sub(r"^https?://[^\s]+$", "", content, flags=re.MULTILINE)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        if len(content) < 5:
            content = ""

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
        "content": content,
        "images": images,
        "raw_html": resp.text,
        "product_name": detail_product_name,
        "product_link": detail_product_link,
    }


CLASSIFY_SYSTEM = """당신은 쇼핑몰 후기 분류 전문가입니다. 후기를 분석해 아래 형식의 JSON만 반환하세요. 다른 텍스트 없이 JSON만.

카테고리 6개:
- 긍정: 상품 만족·칭찬
- 부정: 상품 자체 불만 (배송 문제 제외)
- 중립/단순수령: 단순 수령 알림, 이유 없는 짧은 호평 (단독만 가능, hashtags 반드시 빈 배열)
- 양도/거래: 구매자끼리 양도·판매
- 교환/반품: 회사에 교환·환불 요청
- 배송관련불편: 박스손상·지연·오배송·포장 문제

해시태그 14개 (해당하는 것만):
#사이즈 #핏 #색상 #마감 #재질 #내구성 #디자인 #퀄리티 #가격 #구성 #기획 #무게감 #또사고싶다 #사용성

규칙:
- 중립/단순수령은 단독만, hashtags는 반드시 []
- 행동(양도/교환)과 사유(불만)는 별도 segment로 분리
- #배송 태그 절대 사용 금지
- "예쁘다" 단독에는 #디자인 붙이지 않음
- confidence: 0.9=명확, 0.8=약간 애매, 0.7 이하=많이 애매

반환 형식:
{
  "segments": [
    {"category": "긍정", "summary": "한 줄 요약", "hashtags": ["#디자인"], "confidence": 0.9}
  ],
  "needs_review": false,
  "reasoning": "판단 근거 한 줄"
}"""

class APIExhaustedError(Exception):
    """Anthropic API 잔액 부족 시 발생하는 예외"""
    pass


def classify_review(title: str, content: str) -> dict:
    """AI로 후기 분류. 실패 시 빈 dict 반환. 잔액 부족 시 APIExhaustedError 발생."""
    if not AI_AVAILABLE or not _ai_client:
        return {}
    text = f"제목: {title}\n본문: {content or '(본문 없음)'}"
    try:
        resp = _ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": text}]
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        # 전체 confidence = segments 중 최솟값
        segs = result.get("segments", [])
        if segs:
            min_conf = min(s.get("confidence", 0.9) for s in segs)
            result["confidence"] = min_conf
            result["needs_review"] = min_conf < 0.8
        result["_v2"] = True
        # 전체 hashtags 합집합
        all_tags = []
        for s in segs:
            for t in s.get("hashtags", []):
                if t not in all_tags:
                    all_tags.append(t)
        result["hashtags"] = all_tags
        return result
    except Exception as e:
        err_str = str(e).lower()
        # 잔액 부족 에러 감지 (402, credit_balance_too_low, insufficient_quota 등)
        if any(k in err_str for k in ["credit_balance_too_low", "402", "insufficient_quota",
                                       "billing", "payment", "balance", "quota"]):
            raise APIExhaustedError(f"API 잔액 부족: {e}")
        print(f"     ⚠️  분류 실패: {e}")
        return {}


def save_debug_html(post_id: str, html: str):
    if not DEBUG_MODE:
        return
    os.makedirs("debug_html", exist_ok=True)
    path = f"debug_html/{post_id}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"     🐛 디버그용 HTML 저장: {path}")


# ── 마지막 페이지 자동 감지 ──────────────────────────
def get_last_page() -> int:
    try:
        resp = requests.get(f"{BOARD_URL}?board_no=4&page=1", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
        nums = []
        for a in soup.find_all("a"):
            text = a.get_text(strip=True).lower()
            href = a.get("href", "")
            if any(k in text for k in ["마지막", "last", "끝", "맨끝"]):
                m = re.search(r"page=(\d+)", href)
                if m:
                    nums.append(int(m.group(1)))
        for a in soup.find_all("a", href=True):
            m = re.search(r"page=(\d+)", a["href"])
            if m:
                nums.append(int(m.group(1)))
        if nums:
            last = max(nums)
            print(f"  📌 마지막 페이지 자동 감지: {last}페이지")
            if last <= 10:
                print(f"  ⚠️  10페이지 이하 감지됨 — 페이지네이션이 축약되어 있을 수 있음")
                last = probe_last_page(last)
                print(f"  📌 실제 마지막 페이지: {last}페이지")
            return last
    except Exception as e:
        print(f"  ⚠️  페이지 수 감지 실패 ({e}), 999로 설정")
    return 999


def probe_last_page(start: int = 10) -> int:
    print(f"  🔍 끝까지 탐색 중... (잠시만 기다려주세요)")
    current = start
    for i in range(50):
        try:
            url = f"{BOARD_URL}?board_no=4&page={current}"
            resp = requests.get(url, headers=HEADERS, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")
            max_visible = current
            for a in soup.find_all("a", href=True):
                m = re.search(r"page=(\d+)", a["href"])
                if m:
                    n = int(m.group(1))
                    if n > max_visible:
                        max_visible = n
            print(f"     ... 페이지 {current} 확인 (다음 단서: {max_visible})")
            if max_visible <= current:
                return current
            current = max_visible
            time.sleep(0.3)
        except Exception as e:
            print(f"     ⚠️  탐색 중 오류: {e}")
            break
    return current


# ── 목록 파싱 ─────────────────────────────────────────
def parse_list(page: int) -> list:
    url = f"{BOARD_URL}?board_no=4&page={page}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [오류] 페이지 {page}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    for row in soup.select("table tbody tr"):
        try:
            title_td = row.select_one("td:nth-child(3)")
            if not title_td:
                continue

            post_id = review_link = title = ""
            for a in title_td.find_all("a"):
                m = _ARTICLE_ID_RE.search(a.get("href", ""))
                if m:
                    post_id = m.group(1)
                    href = a["href"]
                    review_link = (BASE_URL + href) if href.startswith("/") else href
                    title = a.get_text(strip=True)
                    break
            if not post_id:
                continue

            prod_td = row.select_one("td:nth-child(2)")
            product_name = product_link = product_img = ""
            if prod_td:
                a = prod_td.find("a")
                img = prod_td.find("img")
                if a:
                    h = a.get("href","")
                    product_link = (BASE_URL+h) if h.startswith("/") else h
                if img:
                    s = img.get("src","")
                    product_img = (BASE_URL+s) if s.startswith("/") else s
                    product_name = img.get("alt","").strip()
                    if not product_name:
                        product_name = img.get("title","").strip()
                if not product_name and a:
                    product_name = a.get_text(strip=True)
                if not product_name and product_link:
                    m = re.search(r"/product/([^/?]+)/\d+/?", product_link)
                    if m:
                        from urllib.parse import unquote
                        cand = unquote(m.group(1))
                        if cand and "detail" not in cand:
                            product_name = cand

            has_photo = bool(title_td.find("img", src=lambda s: s and "attach" in s))
            date_td = row.select_one("td:nth-child(6)")
            view_td = row.select_one("td:nth-child(7)")
            written_at = date_td.get_text(strip=True) if date_td else ""
            views = view_td.get_text(strip=True).replace("조회","").strip() if view_td else "0"

            items.append({
                "id": post_id, "product_name": product_name,
                "product_link": product_link, "product_img": product_img,
                "title": title, "review_link": review_link,
                "has_photo": has_photo, "written_at": written_at, "views": views,
                "content": "", "images": [], "hashtags": [], "classification": {},
            })
        except Exception:
            continue

    return items


# ── 데이터 IO ─────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"reviews": {}, "daily_logs": [], "last_updated": ""}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 저장 완료: {DATA_FILE}")


# ── 메인 ─────────────────────────────────────────────
def main():
    print("=" * 55)
    print("🛍  겸손은힘들다 후기 크롤러")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    data = load_data()
    existing_ids = set(data["reviews"].keys())
    today_str = date.today().isoformat()
    new_ids = []

    # ── 잔액 부족으로 중단됐던 경우: 미분류 후기 먼저 처리 ──
    if data.get("api_exhausted"):
        unclassified = [
            r for r in data["reviews"].values()
            if not r.get("classification") or not r["classification"].get("segments")
        ]
        if unclassified and AI_AVAILABLE:
            print(f"\n🔄 이전에 잔액 부족으로 중단됐던 미분류 후기 {len(unclassified)}건 먼저 처리합니다...")
            done = 0
            try:
                for r in unclassified:
                    print(f"  🤖 #{r['id']} 분류 중...", end=" ", flush=True)
                    clf = classify_review(r["title"], r.get("content", ""))
                    if clf:
                        r["classification"] = clf
                        r["hashtags"] = clf.get("hashtags", [])
                        flag = "⚠️ 검토필요" if clf.get("needs_review") else "✅"
                        cats = ", ".join(s["category"] for s in clf.get("segments", []))
                        print(f"{flag} [{cats}]")
                    else:
                        print("실패 → 검토 큐로")
                        r["classification"] = {"needs_review": True, "_v2": True}
                    done += 1
                    time.sleep(DELAY)
                # 모두 처리 완료 → 잔액 부족 플래그 해제
                data.pop("api_exhausted", None)
                data["api_exhausted_at"] = None
                print(f"\n✅ 미분류 후기 {done}건 처리 완료. 잔액 부족 상태 해제!")
            except APIExhaustedError as e:
                print(f"\n⚠️  재분류 중 또 잔액 부족: {e}")
                print(f"   {done}건 처리 후 중단. 잔액 충전 후 다시 실행하세요.")
                data["api_exhausted"] = True
                data["api_exhausted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_data(data)
                return
        elif not unclassified:
            # 미분류 없으면 플래그 해제
            data.pop("api_exhausted", None)
            print("✅ 미분류 후기 없음. 잔액 부족 상태 해제!")

    if TEST_MODE:
        max_pages = 5
        print("⚙️  [테스트 모드] 최신 5페이지만 수집")
    elif not existing_ids:
        max_pages = get_last_page()
        print(f"⚙️  [최초 수집 모드] 전체 {max_pages}페이지 수집 시작 (30분~1시간 소요 예상)")
    else:
        max_pages = 999
        print(f"⚙️  [업데이트 모드] 기존 {len(existing_ids)}건 — 새 후기만 수집")

    api_exhausted = False  # 이번 실행에서 잔액 부족 발생 여부

    for page in range(1, max_pages + 1):
        print(f"\n📄 페이지 {page} 수집 중...")
        items = parse_list(page)
        if not items:
            print("  항목 없음 → 중단")
            break

        stop = False
        for item in items:
            pid = item["id"]
            if pid in existing_ids:
                print(f"  ✓ 기수집 글 발견 (#{pid}) → 중단")
                stop = True
                break

            pname = item["product_name"] or "?"
            print(f"  → #{pid} [{pname}] {item['title'][:28]}...")

            detail = parse_detail(item["review_link"])
            item["content"] = detail["content"]
            item["images"]  = detail["images"]

            if not item["product_name"] and detail.get("product_name"):
                item["product_name"] = detail["product_name"]
                print(f"     📌 상품명 보강: '{detail['product_name']}'")
            if not item["product_link"] and detail.get("product_link"):
                item["product_link"] = detail["product_link"]

            if "다스뵈이다" in item["product_name"] or "점빵" in item["product_name"]:
                print(f"     ⏭  다스뵈이다 점빵 → 제외")
                continue

            if not item["content"]:
                print(f"     ○ 본문 없음 (제목만 작성된 후기)")
            else:
                preview = item["content"][:60].replace("\n", " ")
                print(f"     ✓ 본문 {len(item['content'])}자: \"{preview}...\"")

            item["classification"] = {}
            item["hashtags"] = []
            item["crawled_date"] = today_str

            # AI 분류
            if AI_AVAILABLE and not api_exhausted:
                print(f"     🤖 분류 중...", end=" ", flush=True)
                try:
                    clf = classify_review(item["title"], item["content"])
                    if clf:
                        item["classification"] = clf
                        item["hashtags"] = clf.get("hashtags", [])
                        flag = "⚠️ 검토필요" if clf.get("needs_review") else "✅"
                        cats = ", ".join(s["category"] for s in clf.get("segments", []))
                        print(f"{flag} [{cats}]")
                    else:
                        print("실패 → 검토 큐로")
                        item["classification"] = {"needs_review": True, "_v2": True}
                except APIExhaustedError as e:
                    print(f"\n\n{'='*55}")
                    print(f"💳 API 잔액 부족! 크롤링을 중단합니다.")
                    print(f"   {e}")
                    print(f"   지금까지 수집한 {len(new_ids)}건은 저장됩니다.")
                    print(f"   잔액 충전 후 run_crawler.command 다시 실행하면")
                    print(f"   이어서 분류됩니다.")
                    print(f"{'='*55}\n")
                    # 이 후기는 미분류로 저장 (크롤링은 됐으니까)
                    item["classification"] = {"needs_review": True, "_v2": True}
                    data["reviews"][pid] = item
                    new_ids.append(pid)
                    api_exhausted = True
                    stop = True
                    break
            elif api_exhausted:
                # 잔액 부족 이후엔 분류 없이 크롤링만 계속 (미분류로 저장)
                print(f"     ○ 잔액 부족 상태 → 미분류로 저장")
                item["classification"] = {"needs_review": True, "_v2": True}
            else:
                print(f"     ○ AI 없음 → 검토 큐로")
                item["classification"] = {"needs_review": True, "_v2": True}

            data["reviews"][pid] = item
            new_ids.append(pid)
            time.sleep(DELAY)

        if stop:
            break

    # 잔액 부족 플래그 저장
    if api_exhausted:
        data["api_exhausted"] = True
        data["api_exhausted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        data.pop("api_exhausted", None)
        data["api_exhausted_at"] = None

    if new_ids:
        log = next((l for l in data["daily_logs"] if l["date"] == today_str), None)
        if log:
            merged = set(log.get("new_ids",[])) | set(new_ids)
            log["new_ids"] = list(merged)
            log["count"] = len(merged)
        else:
            data["daily_logs"].append({"date":today_str,"count":len(new_ids),"new_ids":new_ids})
        print(f"\n✅ 새로 수집: {len(new_ids)}개")
    else:
        print("\n✅ 새 후기 없음")

    data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_data(data)
    if api_exhausted:
        print("⚠️  잔액 부족으로 일부 후기가 미분류 상태입니다. 충전 후 다시 실행하세요.")
    else:
        print("🎉 완료!" + (" AI 분류 포함." if AI_AVAILABLE else " Review 탭에서 분류해주세요."))


if __name__ == "__main__":
    main()
