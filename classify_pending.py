#!/usr/bin/env python3
"""
미분류 후기를 Claude Code(구독)로 배치 분류한다. (Anthropic API 키 대신 사용)

흐름:
  crawl.py 가 CLASSIFY_MODE=claude 로 수집만 하고(분류 안 함) → 후기는 미분류로 저장됨.
  이 스크립트가 미분류 후기를 모아 `claude -p` 헤드리스로 한 번에 분류 → data.json 갱신.

사용법:
  python3 classify_pending.py            # 미분류분 분류 후 저장
  python3 classify_pending.py --dry-run  # 저장하지 않고 결과만 출력
  DATA_FILE=/path/data.json python3 classify_pending.py   # 대상 파일 지정(테스트용)

분류 기준(CLASSIFY_SYSTEM)은 crawl.py 에서 그대로 가져와 단일 출처를 유지한다.
"""
import json, os, re, sys, shutil, subprocess
from datetime import datetime

from crawl import CLASSIFY_SYSTEM  # 분류 기준 단일 출처

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
BATCH_LIMIT = int(os.environ.get("CLASSIFY_BATCH_LIMIT", "40"))   # 1회 실행당 최대 처리 건수
CONTENT_MAX = 800                                                 # 후기 본문 프롬프트 길이 상한
CLAUDE_MODEL = os.environ.get("CLASSIFY_CLAUDE_MODEL", "").strip()  # 비우면 Claude Code 기본 모델
DRY_RUN = "--dry-run" in sys.argv

# 분류 가이드 v2 의 6개 카테고리. 이 외 값이 나오면 통계가 오염되므로 검토 큐로 보낸다.
VALID_CATEGORIES = {"긍정", "부정", "중립/단순수령", "양도/거래", "교환/반품", "배송관련불편"}


def find_claude() -> str:
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def is_unclassified(rv: dict) -> bool:
    clf = rv.get("classification") or {}
    return not clf.get("segments")


def build_prompt(batch: list) -> str:
    lines = [
        CLASSIFY_SYSTEM,
        "",
        "=== 배치 분류 ===",
        "아래는 여러 개의 후기입니다. 각 후기를 위 기준으로 분류해",
        "id를 키로 하는 JSON 객체 하나만 반환하세요. 다른 텍스트 없이 JSON만.",
        '형식: {"<id>": {"segments":[...], "needs_review": false, "reasoning":"..."}, ...}',
        "",
    ]
    for rv in batch:
        content = (rv.get("content") or "(본문 없음)")[:CONTENT_MAX]
        lines.append(f"id={rv['id']}")
        lines.append(f"제목: {rv.get('title','')}")
        lines.append(f"본문: {content}")
        lines.append("")
    return "\n".join(lines)


def claude_env() -> dict:
    """Claude Code 가 '구독'으로 인증되도록 API 키 계열 변수를 제거한 환경을 만든다.
    ANTHROPIC_API_KEY 가 남아 있으면 Claude Code 가 그 키(종량 과금)를 우선 사용하고,
    잔액이 없으면 'Credit balance is too low' 로 실패한다. (auto_crawl.sh 가 .env 를 export 하므로 필수)"""
    env = os.environ.copy()
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        env.pop(k, None)
    return env


def run_claude(prompt: str) -> str:
    cmd = [find_claude(), "-p", prompt, "--output-format", "text"]
    if CLAUDE_MODEL:
        cmd += ["--model", CLAUDE_MODEL]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=claude_env())
    if res.returncode != 0:
        # stdout 에도 실패 이유가 담긴다("Not logged in" 등) → 둘 다 남긴다
        raise RuntimeError(
            f"claude -p 실패(rc={res.returncode})\n"
            f"  stdout: {res.stdout.strip()[:400]}\n"
            f"  stderr: {res.stderr.strip()[:400]}"
        )
    return res.stdout


def parse_json_obj(raw: str) -> dict:
    raw = raw.strip()
    # ```json ... ``` 펜스 제거
    raw = re.sub(r"```json\s*|```", "", raw).strip()
    # 첫 { ~ 마지막 } 만 취함(앞뒤 잡텍스트 방지)
    i, j = raw.find("{"), raw.rfind("}")
    if i != -1 and j != -1:
        raw = raw[i:j + 1]
    return json.loads(raw)


def postprocess(clf: dict) -> dict:
    """crawl.classify_review 와 동일한 후처리(최소 confidence·해시태그 합집합·_v2)."""
    segs = clf.get("segments", []) or []
    if segs:
        min_conf = min(s.get("confidence", 0.9) for s in segs)
        clf["confidence"] = min_conf
        clf["needs_review"] = min_conf < 0.8
    clf["_v2"] = True
    # 규격 외 카테고리(모델이 해시태그를 카테고리 칸에 넣는 등)는 사람이 보게 검토 큐로
    off_spec = [s.get("category") for s in segs if s.get("category") not in VALID_CATEGORIES]
    if off_spec:
        clf["needs_review"] = True
        clf["off_spec_categories"] = off_spec
    all_tags = []
    for s in segs:
        for t in s.get("hashtags", []):
            if t not in all_tags:
                all_tags.append(t)
    clf["hashtags"] = all_tags
    return clf


def main():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    reviews = data["reviews"]

    pending = [rv for rv in reviews.values() if is_unclassified(rv)]
    if not pending:
        print("✅ 미분류 후기 없음. 할 일 없음.")
        return

    total = len(pending)
    batch = pending[:BATCH_LIMIT]
    if total > BATCH_LIMIT:
        print(f"⚠️  미분류 {total}건 중 이번 실행은 {BATCH_LIMIT}건만 처리(나머지는 다음 실행에서).")
    print(f"🤖 Claude Code로 {len(batch)}건 분류 중...")

    raw = run_claude(build_prompt(batch))
    try:
        result = parse_json_obj(raw)
    except Exception as e:
        print(f"❌ 응답 JSON 파싱 실패: {e}\n--- 원문 앞부분 ---\n{raw[:500]}")
        sys.exit(1)

    done, missing = 0, []
    for rv in batch:
        rid = rv["id"]
        clf = result.get(rid) or result.get(str(rid))
        if not clf or not clf.get("segments"):
            missing.append(rid)
            continue
        clf = postprocess(clf)
        rv["classification"] = clf
        rv["hashtags"] = clf.get("hashtags", [])
        done += 1
        cats = ", ".join(s.get("category", "?") for s in clf["segments"])
        flag = "⚠️검토" if clf.get("needs_review") else "✅"
        print(f"  {flag} #{rid} [{cats}]")

    if missing:
        print(f"⚠️  응답에 누락된 {len(missing)}건은 미분류 유지(다음 실행에서 재시도): {missing}")

    if DRY_RUN:
        print(f"\n[DRY-RUN] 저장 안 함. 분류 성공 {done}/{len(batch)}건.")
        return

    data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 저장 완료: {DATA_FILE} (분류 {done}/{len(batch)}건)")


if __name__ == "__main__":
    main()
