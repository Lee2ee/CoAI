#!/bin/bash
# CoAI 개발 서버 시작 스크립트

echo "=== CoAI Trading System ==="

mkdir -p logs

# backend/.env 에서 포트 읽기 (없으면 기본값 사용)
if [ -f backend/.env ]; then
  BACKEND_PORT=$(grep -E '^BACKEND_PORT=' backend/.env | cut -d= -f2 | tr -d ' \r')
  FRONTEND_PORT=$(grep -E '^FRONTEND_PORT=' backend/.env | cut -d= -f2 | tr -d ' \r')
fi
BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-5173}

# 백엔드 시작
echo "[1/2] 백엔드 시작 (http://localhost:${BACKEND_PORT})"
cd backend
../venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" > ../logs/backend.log 2>&1 &
BACKEND_PID=$!

# 프론트엔드 시작 (포트와 프록시 대상을 env로 전달)
echo "[2/2] 프론트엔드 시작 (http://localhost:${FRONTEND_PORT})"
cd ../frontend
BACKEND_PORT="$BACKEND_PORT" FRONTEND_PORT="$FRONTEND_PORT" npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!

echo ""
echo "서버 실행 중..."
echo "  API: http://localhost:${BACKEND_PORT}/docs"
echo "  UI:  http://localhost:${FRONTEND_PORT}"
echo ""
echo "로그 확인:"
echo "  tail -f logs/backend.log"
echo "  tail -f logs/frontend.log"
echo "  tail -f logs/backend.log logs/frontend.log  (동시 확인)"
echo ""
echo "종료: Ctrl+C"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
