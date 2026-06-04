#!/bin/bash
# 대시보드 실행 스크립트
# 사용법: 더블클릭하거나 터미널에서 ./run_dashboard.command

# 스크립트가 있는 폴더로 이동
cd "$(dirname "$0")"

echo "════════════════════════════════════════"
echo "  🛍  겸손은힘들다 후기 대시보드"
echo "════════════════════════════════════════"
echo ""

# data.json 존재 확인
if [ ! -f "data.json" ]; then
  echo "⚠️  data.json이 없습니다."
  echo "   먼저 ./run_crawler.command 를 실행해 데이터를 수집하세요."
  echo ""
  read -p "Enter 키를 눌러 닫기..."
  exit 1
fi

# 포트 8000 사용 중인지 확인
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "⚠️  포트 8000이 이미 사용 중입니다."
  echo "   다른 대시보드가 켜져 있는지 확인하세요."
  echo ""
  echo "기존 서버 종료 후 다시 시작하려면 Enter, 그냥 닫으려면 Ctrl+C"
  read
  # 기존 프로세스 종료
  lsof -ti :8000 | xargs kill -9 2>/dev/null
  sleep 1
fi

echo "🌐 로컬 서버 시작..."
echo "   주소: http://localhost:8000"
echo ""
echo "ℹ️  창을 닫으면 서버가 종료됩니다."
echo "   대시보드를 새로고침하려면 브라우저에서 새로고침(Cmd+R)"
echo ""

# 2초 후 브라우저 자동 열기 (백그라운드)
(sleep 2 && open "http://localhost:8000") &

# 서버 실행 (포그라운드, Ctrl+C로 종료)
python3 -m http.server 8000
