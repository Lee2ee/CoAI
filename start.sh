#!/bin/bash
# CoAI 개발 서버 시작 스크립트

echo "=== CoAI Trading System ==="

# 백엔드 시작
echo "[1/2] 백엔드 시작 (http://localhost:8000)"
cd backend
../venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 프론트엔드 시작
echo "[2/2] 프론트엔드 시작 (http://localhost:5173)"
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "서버 실행 중..."
echo "  API: http://localhost:8000/docs"
echo "  UI:  http://localhost:5173"
echo ""
echo "종료: Ctrl+C"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
