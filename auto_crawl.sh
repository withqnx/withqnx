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

# .env (git push/gh 인증엔 불필요하나 유지)
set -a; [ -f .env ] && source .env; set +a

# 분류를 Claude Code로: crawl.py는 수집만 하도록 지시
export CLASSIFY_MODE=claude

# 최신 동기화
git pull --rebase origin main >/dev/null 2>&1

# 1) 크롤링 (수집만, 분류 안 함)
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 크롤링(수집) 시작 ==="
python3 crawl.py

# 2) 미분류 후기를 Claude Code(구독)로 분류
#    실패하면(인증·잔액·JSON 오류) 후기가 미분류로 남아 Review 큐에 쌓이므로 반드시 알린다.
echo "=== Claude Code 분류 시작 ==="
if ! python3 classify_pending.py; then
  echo "❌ 분류 실패 — 후기가 미분류(검토 큐)로 남았습니다. 로그: /tmp/nonohumble_crawl_error.log"
  osascript -e 'display notification "겸손몰 후기 분류 실패 — 미분류로 쌓임. 로그 확인 필요" with title "NONOHUMBLE"' 2>/dev/null
fi

# 3) 실질 변경(후기 추가/분류 변경)이 있을 때만 커밋 + push(최대 3회 재시도)
#    last_updated 타임스탬프만 바뀐 경우는 커밋하지 않는다(매일 빈 커밋·불필요 배포 방지)
PUSHED=0
if ! git diff --quiet data.json 2>/dev/null; then
  # data.json 변경 라인 중 last_updated 외에 다른 게 있는지 확인
  REAL_CHANGE=$(git diff -U0 data.json | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE '"last_updated"' | head -1)
  if [ -n "$REAL_CHANGE" ]; then
    git add data.json
    git commit -m "🤖 Auto crawl $(date '+%Y-%m-%d %H:%M')" >/dev/null 2>&1
  else
    echo "✅ 새 후기 없음 (타임스탬프만 변경 → 커밋 생략)"
    git checkout -- data.json 2>/dev/null
  fi
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
    echo "❌ git push 3회 실패 — 로컬 커밋은 남아있음. 네트워크 확인 후 'git push origin main' 재실행 필요."
    osascript -e 'display notification "겸손몰 크롤 push 실패 — 수동 push 필요" with title "NONOHUMBLE"' 2>/dev/null
  fi
else
  echo "✅ 새 후기 없음 (이미 최신)"
fi

# 4) 배포 완료까지 대기 (push 했을 때만)
if [ "$PUSHED" -eq 1 ]; then
  echo "▶ Cloudflare 배포 대기 중..."
  sleep 20
  RUN=$(gh run list --workflow=build_deploy.yml -L1 --json databaseId --jq '.[0].databaseId' 2>/dev/null)
  if [ -n "$RUN" ]; then
    if gh run watch "$RUN" --exit-status >/dev/null 2>&1; then
      echo "✅ 배포 완료"
    else
      echo "⚠️ 배포 상태 확인 실패 (그래도 사이트는 곧 갱신됨)"
    fi
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
