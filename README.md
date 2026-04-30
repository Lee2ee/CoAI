# CoAI — Coin Auto-Trading System

코인 자동매매 시스템. 전략 빌더 UI, 백테스트, AI 보조 분석, 실시간 자동매매를 제공합니다.

---

## Features

- **전략 빌더**: RSI, MACD, EMA, 볼린저밴드 등 보조지표 조합으로 진입/청산 조건을 UI에서 직접 설정
- **백테스트**: Walk-Forward 검증 포함, 과최적화 방지
- **자동매매 봇 (AutoBot)**: 종목 자동 스캔 → 전략 평가 → 자동 진입/청산
  - 매매 스타일 자동 선택 (스캘핑 / 단기 / 중기 / 장기)
  - 물타기(avg down) / 불타기(add) 자동 관리
  - 트레일링 스탑
- **AI 보조**:
  - 시장 국면 감지 (상승장 / 하락장 / 횡보)
  - 포지션별 매매 스타일 AI 결정
  - 진입 검증 / 손실 분석 / 청산 보조
  - 지원 프로바이더: Ollama (로컬 무료) · Groq (무료 API) · Anthropic (유료)
- **실시간 차트**: lightweight-charts 기반, KST 시간 표시, 타임프레임별 스마트 줌
- **모의거래 필수**: 전략 검증 전 실거래 차단 (PaperBroker 강제 적용)
- **포트폴리오**: 업비트 계좌 연동, 실시간 잔고/손익 조회

---

## Tech Stack

| Layer | Stack |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, SQLite (aiosqlite) |
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| Chart | lightweight-charts 4, Recharts |
| State | Zustand, TanStack Query |
| Exchange | ccxt 4.3.11 (Upbit) |
| AI | Ollama / Groq / Anthropic (선택) |
| Scheduler | APScheduler 3 |

---

## Project Structure

```
CoAI/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, lifespan
│   │   ├── core/
│   │   │   ├── config.py         # Settings (pydantic-settings)
│   │   │   ├── database.py       # SQLAlchemy async engine
│   │   │   ├── security.py       # JWT, password hashing
│   │   │   └── encryption.py     # API key 암호화
│   │   ├── api/                  # FastAPI 라우터
│   │   │   ├── auth.py
│   │   │   ├── strategies.py
│   │   │   ├── backtest.py
│   │   │   ├── market.py
│   │   │   ├── trades.py
│   │   │   ├── auto_bot.py
│   │   │   ├── exchange_accounts.py
│   │   │   ├── auto_strategy.py
│   │   │   ├── ai_config.py
│   │   │   └── ws.py             # WebSocket (ticker, strategy)
│   │   ├── models/               # SQLAlchemy ORM 모델
│   │   ├── schemas/              # Pydantic 스키마
│   │   └── services/
│   │       ├── exchange/
│   │       │   └── connector.py  # ccxt 래퍼, PaperBroker
│   │       ├── indicator/
│   │       │   └── engine.py     # RSI, MACD, EMA, BB, Stoch, ...
│   │       ├── strategy/
│   │       │   ├── engine.py     # 조건 평가 Rule Engine
│   │       │   └── scheduler.py  # APScheduler 기반 전략 실행
│   │       ├── backtest/
│   │       │   └── engine.py     # Walk-Forward 백테스트
│   │       ├── risk/
│   │       │   └── manager.py    # SL/TP, 포지션 크기, 일일 손실 제한
│   │       └── auto_trade/
│   │           ├── bot.py        # AutoTradeBot 메인 루프
│   │           ├── scanner.py    # 종목 스캔 & 스코어링
│   │           └── ai_analyst.py # AI 분석 레이어 (캐시 포함)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── types/index.ts
│   │   ├── utils/api.ts
│   │   ├── store/                # Zustand 스토어
│   │   ├── hooks/
│   │   ├── pages/
│   │   └── components/
│   │       ├── Chart/            # TradingChart, SymbolPicker
│   │       ├── Strategy/         # StrategyForm, ConditionBuilder
│   │       ├── AutoBot/          # AutoTradePanel, PositionDetailModal
│   │       └── Dashboard/        # EquityChart, TradeHistory, TickerBar
│   └── package.json
├── start.sh                      # 개발 서버 동시 실행
├── ARCHITECTURE.md
├── ALGORITHM.md
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- (AI 사용 시) [Ollama](https://ollama.com) 또는 Groq / Anthropic API 키

### 1. Clone & Setup

```bash
git clone https://github.com/your-repo/CoAI.git
cd CoAI
```

### 2. Backend

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r backend/requirements.txt

# 환경 변수 설정
cp backend/.env.example backend/.env
# backend/.env 를 열어 SECRET_KEY 등 필수 값 입력
```

**SECRET_KEY 생성:**
```bash
openssl rand -hex 32
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. Run (개발 서버)

```bash
# 루트에서 백엔드+프론트엔드 동시 실행
bash start.sh
```

또는 각각 실행:

```bash
# 백엔드
cd backend
../venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# 프론트엔드
cd frontend
npm run dev
```

| 서비스 | URL |
|---|---|
| Frontend UI | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

## AI 설정

`backend/.env`에서 프로바이더 선택:

### Ollama (무료, 로컬)
```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```
```bash
# Ollama 설치 후 모델 다운로드
ollama pull llama3.2
```

### Groq (무료 API)
```env
AI_PROVIDER=groq
GROQ_API_KEY=your_key_here
```
[https://console.groq.com](https://console.groq.com) 에서 무료 키 발급.

### Anthropic (유료)
```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
```

---

## 거래소 계좌 연동

1. UI 상단 **거래소 계좌** 메뉴 → 계좌 추가
2. 업비트 API 키 입력 (API 키는 AES-256 암호화하여 DB 저장)
3. **모의거래(is_paper=true)** 로 먼저 전략 검증 필수
4. 충분한 백테스트 및 모의거래 검증 후 실거래 전환

> **주의**: 실거래 전환 시 실제 자산이 거래됩니다. 반드시 소액으로 테스트하세요.

---

## Environment Variables

| 변수 | 설명 | 기본값 |
|---|---|---|
| `SECRET_KEY` | JWT 서명 키 (필수 변경) | `change-me-...` |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite+aiosqlite:///./coai.db` |
| `DEBUG` | 디버그 모드 | `true` |
| `PAPER_TRADING_DEFAULT` | 기본 모의거래 여부 | `true` |
| `AI_PROVIDER` | AI 프로바이더 선택 | `ollama` |
| `GROQ_API_KEY` | Groq API 키 | `` |
| `ANTHROPIC_API_KEY` | Anthropic API 키 | `` |
| `MAX_POSITION_SIZE_PCT` | 최대 포지션 비율(%) | `10.0` |
| `MAX_DAILY_LOSS_PCT` | 일일 최대 손실 제한(%) | `5.0` |

---

## Security Notes

- `.env` 파일은 절대 커밋하지 마세요 (`.gitignore` 에 포함됨)
- `SECRET_KEY`는 반드시 `openssl rand -hex 32` 로 생성한 값으로 교체하세요
- 거래소 API 키는 DB에 AES-256 암호화 저장됩니다
- 실거래 API 키는 **출금 권한 없이** 거래 권한만 부여하세요
- `coai.db` 파일(사용자 데이터, 거래 내역 포함)도 커밋하지 마세요

---

## License

MIT
