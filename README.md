# CoAI — Coin Auto-Trading System

코인 자동매매 시스템. 전략 빌더 UI, 백테스트, AI 보조 분석, 실시간 자동매매를 제공합니다.

---

## Features

### 전략 빌더
- RSI, MACD, EMA, 볼린저밴드 등 보조지표 조합으로 진입/청산 조건을 UI에서 직접 설정
- AI 자동 생성: 종목·타임프레임 선택 시 AI가 지표 분석 후 전략 자동 구성

### 백테스트
- Walk-Forward 검증 포함, 과최적화 방지
- 거래소 선택 시 수수료율 자동 적용 (Upbit 0.05% / Binance·Bybit 0.10%)
- 총 수익금(₩) 및 최종 자본 표시
- 0거래 시 지표 스냅샷으로 미충족 조건 진단

### 자동매매 봇 (AutoBot)
- 종목 자동 스캔 → 전략 평가 → 자동 진입/청산
- 매매 스타일 자동 선택: 초단타(5m) / 단타(1h) / 중장기(4h) / 장기(1d)
- 멀티 타임프레임 추세 확인 (상위봉 HTF)
- 물타기(avg down) / 불타기(add) / 피라미딩 자동 관리
- 트레일링 스탑, 부분 청산 전략 (목표가 N% 도달 시 일부 청산 후 트레일링)
- 동적 종목 발굴: 업비트 전체 KRW 거래량 상위 자동 선별
- 업비트(현물) / Binance·Bybit(현물·선물) 지원

### 리스크 관리
- 일일 최대 손실 한도 (총자산 대비 %)
- 포트폴리오 최대 노출 한도 (투자 비중 %)
- 포지션 간 상관계수 체크 (고상관 종목 진입 차단)
- MDD 자동 중단 (최대 낙폭 초과 시 봇 자동 정지)
- Historical VaR 95% 산출
- Half-Kelly Criterion 투자 비중 계산

### AI 보조
- 시장 국면 감지: ADX + AI 복합 분석 (추세장 / 횡보장 / 급등락)
- 횡보장 자동 전환: ADX < 20 감지 시 평균 회귀 전략(BB/RSI 기반)으로 전환
- 포지션별 매매 스타일 AI 결정
- 진입 검증 / 연속 손절 자기 분석 / 청산 타이밍 보조
- 지원 프로바이더: Ollama (로컬 무료) · Groq (무료 API) · Anthropic · OpenAI · Gemini
- 서버 재시작 시 DB에서 AI 설정 자동 복원

### 성과 분석
- Sharpe · Sortino · Calmar · MDD · Expectancy · Profit Factor · VaR 95%

### 안전 기능
- 모의거래 필수: 전략 검증 전 실거래 차단 (PaperBroker 강제 적용)
- 모의/실거래 전환: 실거래 전환 시 계좌 등록·잔고 유무 자동 검증
- 포지션 열린 전략 삭제 차단
- 미등록 거래소 선택·시작 차단
- 위험 동작 시 커스텀 확인 다이얼로그

---

## Tech Stack

| Layer | Stack |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, SQLite (aiosqlite) |
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| Chart | lightweight-charts 4, Recharts |
| State | Zustand, TanStack Query |
| Exchange | ccxt 4 (Upbit · Binance · Bybit) |
| AI | Ollama / Groq / Anthropic / OpenAI / Gemini (선택) |
| Scheduler | APScheduler 3 |

---

## Quick Start

### Prerequisites

- Python 3.13 이상
- Node.js 18 이상
- (AI 사용 시) Ollama 또는 API 키 — 없으면 AI 기능 비활성화, 나머지는 정상 동작

---

### 1. Clone

```bash
git clone https://github.com/Lee2ee/CoAI.git
cd CoAI
git checkout develop   # 최신 개발 브랜치
```

---

### 2. 설정 파일 준비 (필수)

#### `backend/.env` 생성

```bash
cp backend/.env.example backend/.env
```

`backend/.env`를 열어 **SECRET_KEY를 반드시 변경**하세요:

```bash
# SECRET_KEY 생성 명령어
openssl rand -hex 32
```

```env
# backend/.env 최소 필수 설정
SECRET_KEY=여기에_openssl로_생성한_값_입력   # 필수 변경
DATABASE_URL=sqlite+aiosqlite:///./coai.db  # 기본값 유지 가능
DEBUG=false
PAPER_TRADING_DEFAULT=true

# 포트 설정 — 이 두 값만 바꾸면 start.sh와 Vite 프록시에 자동 반영됩니다
BACKEND_PORT=8001
FRONTEND_PORT=5173
```

> `.env` 파일은 `.gitignore`에 포함되어 있어 저장소에 올라가지 않습니다.

---

#### `backend/ai_settings.json` — AI 기능 사용 시

이 파일은 **자동으로 생성**됩니다. 수동으로 만들 필요가 없습니다.

- 방법 1: 서버 실행 후 UI → **설정** → AI 설정에서 프로바이더/키 입력 → 저장
- 방법 2: 아래 형식으로 직접 생성 (`backend/ai_settings.json`)

```json
{
  "provider": "groq",
  "model": "llama-3.3-70b-versatile",
  "api_key": "여기에_API_키_입력",
  "ollama_url": "http://localhost:11434"
}
```

| provider | 설명 | 키 발급 |
|----------|------|---------|
| `ollama` | 로컬 무료 (키 불필요) | [ollama.com](https://ollama.com) |
| `groq` | 무료 API | [console.groq.com](https://console.groq.com) |
| `anthropic` | 유료 | [console.anthropic.com](https://console.anthropic.com) |
| `openai` | 유료 | [platform.openai.com](https://platform.openai.com/api-keys) |
| `gemini` | 무료 티어 포함 | [aistudio.google.com](https://aistudio.google.com/apikey) |

> `ai_settings.json`은 `.gitignore`에 포함됩니다. API 키가 저장소에 노출되지 않습니다.

---

#### `backend/coai.db` — 자동 생성

DB 파일은 백엔드 최초 실행 시 자동으로 생성됩니다. 별도 설치나 마이그레이션 불필요.

---

### 3. 패키지 설치

**Windows (CMD / PowerShell)**

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r backend\requirements.txt
```

**Windows (Git Bash) / macOS / Linux**

```bash
python -m venv venv
source venv/Scripts/activate        # macOS/Linux: source venv/bin/activate
pip install -r backend/requirements.txt
```

**프론트엔드 (공통)**

```bash
cd frontend && npm install && cd ..
```

---

### 4. 실행

**Git Bash / macOS / Linux (권장)**

```bash
# 백엔드 + 프론트엔드 동시 실행
bash start.sh
```

`start.sh`는 `backend/.env`의 `BACKEND_PORT` / `FRONTEND_PORT` 값을 읽어 자동으로 적용합니다.

> **Windows 참고**: `start.sh`는 Git Bash 환경에서 실행합니다. CMD/PowerShell에서는 아래 명령어를 사용하세요.

**Windows CMD / PowerShell (개별 실행)**

터미널 2개를 열어 각각 실행:

```cmd
REM [터미널 1] 백엔드
cd backend
..\venv\Scripts\python -m uvicorn app.main:app --reload --port 8001

REM [터미널 2] 프론트엔드
cd frontend
npm run dev
```

**Git Bash 개별 실행**

```bash
# 백엔드
cd backend
../venv/Scripts/python -m uvicorn app.main:app --reload --port 8001

# 프론트엔드
cd frontend
npm run dev
```

기본 접속 URL (포트를 변경하지 않은 경우):

| 서비스 | URL |
|---|---|
| Frontend UI | http://localhost:5173 |
| Backend API | http://localhost:8001 |
| API Docs (Swagger) | http://localhost:8001/docs |

---

### 5. 첫 실행 체크리스트

```
[ ] backend/.env 생성 및 SECRET_KEY 변경
[ ] 백엔드 + 프론트엔드 실행 확인
[ ] UI 접속 → 회원가입 (이메일/비밀번호 자유 입력, 로컬 DB 저장)
[ ] (선택) 설정 → AI 설정 → 프로바이더 선택 및 키 입력 → 연결 테스트
[ ] (선택) 거래소 → 거래소 계정 추가 → 업비트 API 키 등록
[ ] 대시보드 → AutoBot 패널 → 스타일 선택 → 봇 시작 (기본값: 모의거래)
```

> **회원가입**: 별도 이메일 인증 없이 로컬 DB에만 저장됩니다.

---

## 설정 파일 요약

| 파일 | 저장소 포함 | 설명 | 생성 방법 |
|------|:-----------:|------|-----------|
| `backend/.env` | ❌ gitignore | 앱 설정, JWT 키, 포트 | `.env.example` 복사 후 수정 |
| `backend/ai_settings.json` | ❌ gitignore | AI 프로바이더/키 | UI에서 자동 생성 또는 직접 작성 |
| `backend/coai.db` | ❌ gitignore | SQLite DB | 최초 실행 시 자동 생성 |
| `backend/.env.example` | ✅ 포함 | 설정 템플릿 | 참고용 |

---

## 포트 변경

`backend/.env` 한 곳에서만 수정합니다.

```env
BACKEND_PORT=9000
FRONTEND_PORT=3000
```

변경 후 `bash start.sh`를 다시 실행하면 적용됩니다.

---

## AI 설정 (선택)

AI 기능 없이도 자동매매 봇은 정상 동작합니다 (신호 기반 진입/청산만 사용).

### Ollama (무료, 로컬 실행)

```bash
ollama pull llama3.2
```

UI → 설정 → `ollama` 선택 → URL `http://localhost:11434` → 저장

### Groq (무료 API, 추천)

[console.groq.com](https://console.groq.com) 에서 키 발급 후 UI → 설정 → `groq` 선택 → 키 입력

---

## 거래소 계좌 연동

1. UI 상단 **거래소** 메뉴 → 계정 추가
2. 거래소 및 API 키 입력 (AES-256 암호화하여 DB 저장)
3. **모의거래(is_paper=true)** 로 먼저 전략 검증 필수
4. 충분한 검증 후 실거래 전환

> **주의**: 실거래 전환 시 실제 자산이 거래됩니다. 반드시 소액으로 테스트하세요.
> API 키는 **출금 권한 없이** 거래 권한만 부여하세요.

---

## AutoBot 설정 항목

| 항목 | 설명 | 기본값 |
|------|------|--------|
| `trading_style` | 매매 스타일 (scalping/short/mid/long) | short |
| `stop_loss_pct` | 손절 비율 (%) | 2.5 |
| `take_profit_pct` | 익절 비율 (%) | 5.0 |
| `min_score` | 진입 최소 점수 (0~100) | 48 |
| `max_positions` | 최대 동시 포지션 수 | 4 |
| `position_size_pct` | 잔고 대비 포지션 크기 (%) | 25.0 |
| `auto_avg_down` | 자동 물타기 활성화 | true |
| `avg_down_threshold_pct` | 물타기 발동 하락률 (%) | 3.0 |
| `max_avg_down` | 최대 물타기 횟수 | 2 |
| `trailing_stop` | 트레일링 스탑 활성화 | true |
| `trailing_activate_pct` | 트레일링 활성화 수익률 (%) | 4.0 |
| `trailing_pct` | 고점 대비 트레일링 간격 (%) | 2.0 |
| `partial_exit_enabled` | 부분 청산 활성화 | false |
| `partial_exit_ratio` | 부분 청산 비율 | 0.4 (40%) |
| `partial_exit_trigger_pct` | TP까지 거리의 N% 도달 시 발동 | 0.6 (60%) |
| `max_daily_loss_pct` | 일일 최대 손실 한도 (%) | 5.0 |
| `max_portfolio_exposure_pct` | 최대 포트폴리오 노출 (%) | 90.0 |
| `correlation_threshold` | 상관계수 진입 차단 임계값 | 0.85 |
| `mdd_limit_pct` | MDD 자동 중단 임계값 (%) | 20.0 |
| `risk_per_trade_pct` | 거래당 최대 손실 한도 (잔고 대비 %) — `position_size_pct × stop_loss_pct` 기반 실질 손실이 이 값을 초과하면 포지션 크기를 자동으로 줄여 리스크를 제한 | 1.2 |

선물 모드는 별도 안전 프리셋을 사용합니다. 기본값은 `leverage=3`, `max_positions=2`, `position_size_pct=12.0`, 레버리지 입력 상한은 `5x`입니다.

> **주의**: AutoBot 설정은 서버 재시작 시 기본값으로 초기화됩니다. 설정 영속화는 추후 지원 예정입니다.

---

## Environment Variables

| 변수 | 설명 | 기본값 |
|---|---|---|
| `BACKEND_PORT` | 백엔드 서버 포트 | `8001` |
| `FRONTEND_PORT` | 프론트엔드 개발 서버 포트 | `5173` |
| `SECRET_KEY` | JWT 서명 키 **(필수 변경)** | `change-me-...` |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite+aiosqlite:///./coai.db` |
| `DEBUG` | 디버그 모드 | `false` |
| `PAPER_TRADING_DEFAULT` | 기본 모의거래 여부 | `true` |

---

## Project Structure

```
CoAI/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app, lifespan, 로그 설정
│   │   ├── core/                     # config, database, security, encryption
│   │   ├── api/                      # 라우터
│   │   │   ├── auth.py               # 회원가입/로그인 (JWT)
│   │   │   ├── auto_bot.py           # AutoBot 제어 API
│   │   │   ├── ai_config.py          # AI 설정 저장/테스트 API
│   │   │   ├── auto_strategy.py      # AI 전략 자동 생성 API
│   │   │   ├── backtest.py           # 백테스트 실행 API
│   │   │   ├── exchange_accounts.py  # 거래소 계좌 관리 API
│   │   │   ├── market.py             # 시세/종목 조회 API
│   │   │   ├── strategies.py         # 전략 CRUD API
│   │   │   ├── trades.py             # 거래 내역 API
│   │   │   └── ws.py                 # WebSocket (실시간 시세)
│   │   ├── models/                   # SQLAlchemy ORM 모델
│   │   ├── schemas/                  # Pydantic 스키마
│   │   └── services/
│   │       ├── exchange/connector.py     # ccxt 래퍼, PaperBroker
│   │       ├── indicator/engine.py       # RSI, MACD, EMA, BB, ADX ...
│   │       ├── strategy/engine.py        # 조건 평가 Rule Engine
│   │       ├── backtest/engine.py        # Walk-Forward 백테스트
│   │       ├── risk/manager.py           # SL/TP, VaR, 상관관계, Kelly
│   │       └── auto_trade/
│   │           ├── bot.py                # AutoTradeBot 메인 루프
│   │           ├── scanner.py            # 종목 스캔·스코어링·HTF·ADX
│   │           └── ai_analyst.py         # AI 분석 레이어
│   ├── requirements.txt
│   ├── .env.example
│   └── ai_settings.json              # gitignore (UI에서 자동 생성)
├── frontend/
│   ├── src/
│   │   ├── App.tsx                   # 라우팅 (/, /exchange, /settings)
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx         # 로그인/회원가입
│   │   │   ├── DashboardPage.tsx     # 메인 대시보드
│   │   │   ├── ExchangePage.tsx      # 거래소 계좌 관리
│   │   │   ├── SettingsPage.tsx      # AI 설정
│   │   │   └── BacktestPage.tsx      # 백테스트 (모달)
│   │   ├── components/
│   │   │   ├── AutoBot/
│   │   │   │   ├── AutoTradePanel.tsx    # AutoBot 메인 패널
│   │   │   │   └── PositionDetailModal.tsx
│   │   │   ├── Strategy/
│   │   │   │   ├── StrategyCard.tsx
│   │   │   │   ├── StrategyForm.tsx
│   │   │   │   └── ConditionBuilder.tsx
│   │   │   ├── Dashboard/
│   │   │   │   ├── TickerBar.tsx
│   │   │   │   ├── EquityChart.tsx
│   │   │   │   └── TradeHistory.tsx
│   │   │   ├── Chart/TradingChart.tsx
│   │   │   └── common/               # Modal, ConfirmModal, Tooltip
│   │   ├── store/                    # Zustand (auth, settings)
│   │   ├── hooks/useWebSocket.ts
│   │   ├── utils/api.ts              # axios 인스턴스
│   │   └── types/index.ts            # 공통 타입 정의
│   ├── vite.config.ts
│   └── package.json
├── start.sh                          # 개발 서버 동시 실행
├── README.md
└── docs/
    └── UI_GUIDE.md                   # 화면별 기능 및 코드 매핑
```

---

## Security Notes

- `backend/.env` 파일은 절대 커밋하지 마세요 (`.gitignore` 포함)
- `SECRET_KEY`는 반드시 `openssl rand -hex 32` 로 생성한 값으로 교체하세요
- `backend/ai_settings.json`에 실제 API 키가 저장되므로 커밋 금지
- 거래소 API 키는 DB에 AES-256 암호화 저장됩니다
- `coai.db`에 사용자 정보·거래 내역이 저장되므로 커밋 금지
- 실거래 API 키는 출금 권한 없이 거래 권한만 부여하세요

---

## License

MIT
