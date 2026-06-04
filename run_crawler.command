#!/bin/bash
# 크롤링 + NAS 배포 자동 실행
# NAS 경로에 직접 두고 더블클릭하면 동작

# 스크립트 위치로 이동 (NAS 경로의 공백/괄호 안전 처리)
cd "$(dirname "$0")" || exit 1

echo "════════════════════════════════════════"
echo "  🛍  겸손몰 후기 분석 — 업데이트"
echo "════════════════════════════════════════"
echo ""
echo "현재 위치: $(pwd)"
echo ""

# venv는 로컬에 두는 게 안전 (NAS에서 venv 만들면 권한/속도 문제)
# 사용자 홈에 .nonohumble_venv 폴더 만들어서 거기에 venv 보관
VENV_DIR="$HOME/.nonohumble_venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "⚠️  처음 실행 — venv 설치 중 (1-2분 소요)..."
  python3 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  pip install --quiet requests beautifulsoup4
  echo "  ✓ venv 설치 완료: $VENV_DIR"
else
  source "$VENV_DIR/bin/activate"
fi

# Publish 서버 시작 (백그라운드, 이미 실행 중이면 스킵)
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
if curl -s --connect-timeout 1 http://localhost:7878 > /dev/null 2>&1; then
  echo "  ✓ Publish 서버 이미 실행 중 (http://localhost:7878)"
else
  nohup python3 "$SCRIPT_ABS/server.py" >> /tmp/nonohumble_server.log 2>&1 &
  disown
  sleep 0.8
  if curl -s --connect-timeout 1 http://localhost:7878 > /dev/null 2>&1; then
    echo "  ✓ Publish 서버 시작: http://localhost:7878"
  else
    echo "  ⚠️  서버 시작 실패 (로그: /tmp/nonohumble_server.log)"
  fi
fi
echo ""

# .env 로드 (NAS 폴더의 .env)
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "⚠️  ANTHROPIC_API_KEY 미설정 — 키워드 분류로 진행"
  echo ""
fi

# ① 크롤링
echo "▶ 1/2 새 후기 수집..."
python3 crawl.py
if [ $? -ne 0 ]; then
  echo "❌ 크롤링 실패"
  read -p "Enter로 닫기..."
  exit 1
fi
echo ""

# ② NAS는 이미 현재 폴더라 그냥 빌드만
echo "▶ 2/2 대시보드 빌드..."
python3 deploy_nas.py
echo ""

echo "════════════════════════════════════════"
echo "  🎉 완료!"
echo "════════════════════════════════════════"
read -p "Enter로 닫기..."
