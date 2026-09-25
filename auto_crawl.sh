#!/bin/bash
# Mac 로그인(켤 때) 트리거 → 크롤링(수집만) → Claude Code 분류 → 배포 → 대기 → 홈페이지 오픈
# launchd(com.nonohumble.crawl, RunAtLoad)가 실행
# 분류: Anthropic API 키 대신 Claude Code(구독)로 처리 (classify_pending.py)

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJ="$HOME/nonohumble-review"
VENV="$HOME/.nonohumble_venv"
SITE="https://nonohumble-review.pages.dev"
cd "$PROJ" || exit 1

# venv
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"; source "$VENV/bin/activate"
  pip install --quiet requests beautifulsoup4 anthropic python-dotenv
else
  source "$VENV/bin/activate"
fi

# .env (CF_* 등). git push/gh 인증엔 불필요하나 유지.
set -a; [ -f .env ] && source .env; set +a

# ⚠️ ANTHROPIC_API_KEY 는 환경에서 제거한다.
#    남아 있으면 Claude Code 가 구독 대신 그 키(종량 과금)를 우선 사용하고,
#    잔액이 없으면 "Credit balance is too low" 로 분류가 실패한다. (2026-08-23 실제 발생)
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

# 분류는 Claude Code(구독): crawl.py 는 수집만
export CLASSIFY_MODE=claude

ERRLOG="/tmp/nonohumble_crawl_error.log"
# 무인 실행이라 실패를 사람이 못 본다 → 화면 로그 + 파일 로그 + 알림을 항상 같이 남긴다.
notify() {   # notify "<알림 문구>" "<로그 본문>"
  echo "❌ $1"
  { echo "=== $(date '+%Y-%m-%d %H:%M:%S') $1 ==="; [ -n "$2" ] && echo "$2"; } >> "$ERRLOG"
  osascript -e "display notification \"$1\" with title \"NONOHUMBLE\"" 2>/dev/null
}

# 최신 동기화 — 실패하면(충돌 등) 리베이스 중단 상태가 남아 이후 커밋·push가 전부 실패한다.
if ! PULL_OUT=$(git pull --rebase origin main 2>&1); then
  git rebase --abort 2>/dev/null   # 리베이스 잔재를 남기지 않는다
  notify "겸손몰 git pull(rebase) 실패 — 수동 확인 필요. 로그: $ERRLOG" "$PULL_OUT"
  exit 1
fi

# 1) 크롤링 (수집만, 분류 안 함)
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 크롤링(수집) 시작 ==="
if ! python3 crawl.py; then
  notify "겸손몰 크롤링 실패 — 새 후기를 못 가져왔습니다. 로그: $ERRLOG" "crawl.py 종료코드 비정상"
  exit 1
fi

# 2) 미분류 후기를 Claude Code(구독)로 분류
#    실패하면(인증·잔액·JSON 오류) 후기가 미분류로 남아 Review 큐에 쌓이므로 반드시 알린다.
echo "=== Claude Code 분류 시작 ==="
if ! python3 classify_pending.py; then
  notify "겸손몰 후기 분류 실패 — 미분류(검토 큐)로 쌓임. 로그: $ERRLOG" "classify_pending.py 종료코드 비정상"
fi

echo "=== 감정 2차 판정 (구독) ==="
if ! python3 verify_sentiment.py --new; then
  echo "⚠️ 2차 판정 실패 — 1차 분류는 그대로 살아있다. 다음 실행에서 재시도."
fi

# 3) 실질 변경(후기 추가/분류 변경)이 있을 때만 커밋 + push(최대 3회 재시도)
#    last_updated 타임스탬프만 바뀐 경우는 커밋하지 않는다(매일 빈 커밋·불필요 배포 방지)
PUSHED=0
STAGED=0
if ! git diff --quiet data.json 2>/dev/null; then
  # data.json 변경 라인 중 last_updated 외에 다른 게 있는지 확인
  REAL_CHANGE=$(git diff -U0 data.json | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE '"last_updated"' | head -1)
  if [ -n "$REAL_CHANGE" ]; then
    git add data.json; STAGED=1
  else
    echo "✅ 새 후기 없음 (타임스탬프만 변경 → 커밋 생략)"
    git checkout -- data.json 2>/dev/null
  fi
fi
# groups.json 도 함께 커밋한다(변경됐을 때만) — data.json 만 올리면 그룹 정보가 어긋난다
if ! git diff --quiet groups.json 2>/dev/null; then
  git add groups.json; STAGED=1
fi
if [ "$STAGED" -eq 1 ]; then
  git commit -m "🤖 Auto crawl $(date '+%Y-%m-%d %H:%M')" >/dev/null 2>&1
fi
# 아직 원격에 안 올라간 커밋이 있으면 push 시도
if [ -n "$(git log --oneline origin/main..HEAD 2>/dev/null)" ]; then
  for i in 1 2 3; do
    if git push origin main >/dev/null 2>&1; then
      echo "✅ push 완료"
      PUSHED=1
      break
    fi
    echo "⚠️ git push 실패(시도 $i/3) — 네트워크 대기 후 재시도"
    sleep 15
    git fetch origin -q 2>/dev/null
  done
  if [ "$PUSHED" -eq 0 ]; then
    notify "겸손몰 크롤 push 3회 실패 — 로컬 커밋 남음. 수동 push 필요" "git push origin main 재실행 필요"
  fi
else
  echo "✅ 새 후기 없음 (이미 최신)"
fi

# 4) 배포 완료까지 대기 (push 했을 때만)
if [ "$PUSHED" -eq 1 ]; then
  echo "▶ Cloudflare 배포 대기 중..."
  # 방금 push한 커밋의 run 을 SHA 로 특정한다.
  # (-L1 로 '최신 run 1개'를 잡으면 아직 큐에 안 올라왔을 때 전날 run 을 보고 성공으로 오판한다)
  SHA=$(git rev-parse HEAD)
  RUN=""
  for i in 1 2 3 4 5 6; do
    sleep 10
    RUN=$(gh run list --workflow=build_deploy.yml -L20 --json databaseId,headSha \
          --jq "[.[]|select(.headSha==\"$SHA\")][0].databaseId" 2>/dev/null)
    [ -n "$RUN" ] && [ "$RUN" != "null" ] && break
    RUN=""
  done
  if [ -n "$RUN" ]; then
    if gh run watch "$RUN" --exit-status >/dev/null 2>&1; then
      echo "✅ 배포 완료 (run $RUN / $SHA)"
    else
      notify "겸손몰 배포 워크플로우 실패 — 대시보드가 갱신되지 않았을 수 있음" "run $RUN / $SHA"
    fi
  else
    echo "⚠️ 이 커밋($SHA)의 배포 run 을 찾지 못함 — 배포 성공 여부 미확인"
  fi
  sleep 5
fi

# 5) 완전 자동 모드: 브라우저를 띄우지 않는다(사람 개입 불필요).
#    확인이 필요하면 언제든 $SITE 접속. OPEN_SITE=1 로 실행하면 예전처럼 창을 연다.
if [ "${OPEN_SITE:-0}" = "1" ]; then
  echo "▶ 홈페이지 여는 중: $SITE"
  open "$SITE"
else
  [ "$PUSHED" -eq 1 ] && echo "▶ 대시보드 갱신됨: $SITE"
fi
echo "=== 종료 ==="
