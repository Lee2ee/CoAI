# CoAI — Coin Auto-Trading System

코인 자동매매 시스템. 전략 빌더 UI, 백테스트, AI 보조 분석, 실시간 자동매매를 제공합니다.

---

## Features

- **전략 빌더**: RSI, MACD, EMA, 볼린저밴드 등 보조지표 조합으로 진입/청산 조건을 UI에서 직접 설정
- **백테스트**: Walk-Forward 검증 포함, 과최적화 방지
- **자동매매 봇 (AutoBot)**: 종목 자동 스캔 → 전략 평가 → 자동 진입/청산
  - 매매 스타일 자동 선택 (스캘핑 / 단기 / 중기 / 장기)
  - 멀티 타임프레임 추세 확인 (상위봉 HTF)
  - 물타기(avg down) / 불타기(add) 자동 관리
  - 트레일링 스탑, 포트폴리오 리스크 관리
  - 동적 종목 발굴 (업비트 전체 KRW 거래량 상위 자동 선별)
- **AI 보조**:
  - 시장 국면 감지 (상승장 / 하락장 / 횡보)
  - 포지션별 매매 스타일 AI 결정
  - 진입 검증 / 손실 분석 / 청산 보조
  - 지원 프로바이더: Ollama (로컬 무료) · Groq (무료 API) · Anthropic · OpenAI · Gemini
- **성과 분석**: Sharpe · Sortino · Calmar · MDD · Expectancy · Profit Factor
- **모의거래 필수**: 전략 검증 전 실거래 차단 (PaperBroker 강제 적용)
- **모의/실거래 전환**: AutoBot 패널에서 토글로 전환 — 실거래 전환 시 계좌 등록·잔고 유무 자동 검증
- **안전 확인 UI**: 전략 삭제·봇 중단·포지션 청산 등 위험 동작 시 커스텀 확인 다이얼로그
- **용어 툴팁**: RSI·MACD·HTF·마진모드·물타기 등 전문 용어에 마우스 오버 시 설명 표시

---

## Tech Stack

| Layer | Stack |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite (aiosqlite) |
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| Chart | lightweight-charts 4, Recharts |
| State | Zustand, TanStack Query |
| Exchange | ccxt 4 (Upbit · Binance · Bybit) |
| AI | Ollama / Groq / Anthropic / OpenAI / Gemini (선택) |
| Scheduler | APScheduler 3 |

---

## Quick Start

### Prerequisites

- Python 3.11 이상
- Node.js 18 이상
- (AI 사용 시) Ollama 또는 API 키 — 없으면 AI 기능 비활성화, 나머지는 정상 동작

---

### 1. Clone

```bash
git clone https://github.com/Lee2ee/CoAI.git
cd CoAI
```

---

### 2. 설정 파일 준비 (필수)

#### `backend/.env` 생성

```bash
cp backend/.env.example backend/.env
```

그런 다음 `backend/.env`를 열어 **SECRET_KEY를 반드시 변경**하세요:

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
BACKEND_PORT=8000
FRONTEND_PORT=5173
```

> `.env` 파일은 `.gitignore`에 포함되어 있어 저장소에 올라가지 않습니다.
> `.env.example`을 참고하여 모든 설정을 확인하세요.

---

#### `backend/ai_settings.json` — AI 기능 사용 시

이 파일은 **자동으로 생성**됩니다. 수동으로 만들 필요가 없습니다.

- 방법 1: 서버 실행 후 UI 우측 상단 **AI 설정** 버튼에서 프로바이더/키 입력 → 저장
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

```bash
# 백엔드 (Python 가상환경 권장)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt

# 프론트엔드
cd frontend && npm install && cd ..
```

---

### 4. 실행

```bash
# 백엔드 + 프론트엔드 동시 실행 (Linux/macOS/Git Bash)
bash start.sh
```

`start.sh`는 `backend/.env`의 `BACKEND_PORT` / `FRONTEND_PORT` 값을 읽어 자동으로 적용합니다.

또는 각각 실행:

```bash
# 백엔드
cd backend
../venv/Scripts/python -m uvicorn app.main:app --reload --port 8000   # Windows
# source ../venv/bin/activate && uvicorn app.main:app --reload --port 8000  # macOS/Linux

# 프론트엔드 (포트와 프록시 대상을 env로 전달)
cd frontend
BACKEND_PORT=8000 FRONTEND_PORT=5173 npm run dev
```

기본 접속 URL (포트를 변경하지 않은 경우):

| 서비스 | URL |
|---|---|
| Frontend UI | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

### 5. 첫 실행 체크리스트

```
[ ] backend/.env 생성 및 SECRET_KEY 변경
[ ] 백엔드 + 프론트엔드 실행 확인
[ ] UI 접속 → 회원가입 (이메일/비밀번호 자유 입력, 로컬 DB 저장)
[ ] (선택) AI 설정 버튼 → 프로바이더 선택 및 키 입력 → 연결 테스트
[ ] (선택) 거래소 계좌 → 업비트 API 키 등록 (모의거래용, 출금 권한 불필요)
[ ] AutoBot 탭 → 스타일 선택 → 봇 시작 (기본값: 모의거래)
```

> **회원가입**: 별도 이메일 인증 없이 로컬 DB에만 저장됩니다.
> 이 계정은 API 접근 인증(JWT)용이며 외부로 전송되지 않습니다.

---

## 설정 파일 요약

| 파일 | 저장소 포함 | 설명 | 생성 방법 |
|------|:-----------:|------|-----------|
| `backend/.env` | ❌ gitignore | 앱 설정, JWT 키, **포트** | `.env.example` 복사 후 수정 |
| `backend/ai_settings.json` | ❌ gitignore | AI 프로바이더/키 | UI에서 자동 생성 또는 직접 작성 |
| `backend/coai.db` | ❌ gitignore | SQLite DB | 최초 실행 시 자동 생성 |
| `backend/.env.example` | ✅ 포함 | 설정 템플릿 | 참고용 |

---

## 포트 변경

`backend/.env` 한 곳에서만 수정합니다. `start.sh`와 Vite 개발 서버 프록시에 자동으로 반영됩니다.

```env
BACKEND_PORT=9000
FRONTEND_PORT=3000
```

변경 후 `bash start.sh`를 다시 실행하면 적용됩니다.

---

## AI 설정 (선택)

AI 기능 없이도 자동매매 봇은 정상 동작합니다 (신호 기반 진입/청산만 사용).
AI를 활성화하면 시장 국면 감지, 진입 검증, 손절 분석이 추가됩니다.

### Ollama (무료, 로컬 실행)

```bash
# Ollama 설치 후 모델 다운로드
ollama pull llama3.2
```

UI → AI 설정 → `ollama` 선택 → URL `http://localhost:11434` → 저장

### Groq (무료 API, 추천)

[console.groq.com](https://console.groq.com) 에서 키 발급 후 UI → AI 설정 → `groq` 선택 → 키 입력

---

## 거래소 계좌 연동

1. UI 상단 **거래소 계좌** 메뉴 → 계좌 추가
2. 업비트 API 키 입력 (AES-256 암호화하여 DB 저장)
3. **모의거래(is_paper=true)** 로 먼저 전략 검증 필수
4. 충분한 백테스트 및 모의거래 검증 후 실거래 전환

> **주의**: 실거래 전환 시 실제 자산이 거래됩니다. 반드시 소액으로 테스트하세요.
> API 키는 **출금 권한 없이** 거래 권한만 부여하세요.

---

## Environment Variables

| 변수 | 설명 | 기본값 |
|---|---|---|
| `BACKEND_PORT` | 백엔드 서버 포트 | `8000` |
| `FRONTEND_PORT` | 프론트엔드 개발 서버 포트 | `5173` |
| `SECRET_KEY` | JWT 서명 키 **(필수 변경)** | `change-me-...` |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite+aiosqlite:///./coai.db` |
| `DEBUG` | 디버그 모드 | `false` |
| `PAPER_TRADING_DEFAULT` | 기본 모의거래 여부 | `true` |
| `AI_PROVIDER` | AI 프로바이더 | `ollama` |
| `GROQ_API_KEY` | Groq API 키 | `` |
| `ANTHROPIC_API_KEY` | Anthropic API 키 | `` |
| `MAX_POSITION_SIZE_PCT` | 최대 포지션 비율(%) | `10.0` |
| `MAX_DAILY_LOSS_PCT` | 일일 최대 손실 제한(%) | `5.0` |

> AI 키는 `.env`에 넣거나 UI의 AI 설정(`ai_settings.json`)에 넣는 두 가지 방법 모두 지원됩니다.
> UI 설정이 `.env`보다 우선 적용됩니다.

---

## Project Structure

```
CoAI/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, lifespan
│   │   ├── core/                 # config, database, security, encryption
│   │   ├── api/                  # 라우터 (auth, strategies, backtest, auto_bot ...)
│   │   ├── models/               # SQLAlchemy ORM 모델
│   │   ├── schemas/              # Pydantic 스키마
│   │   └── services/
│   │       ├── exchange/connector.py   # ccxt 래퍼, PaperBroker
│   │       ├── indicator/engine.py     # RSI, MACD, EMA, BB, ...
│   │       ├── strategy/engine.py      # 조건 평가 Rule Engine
│   │       ├── backtest/engine.py      # Walk-Forward 백테스트
│   │       ├── risk/manager.py         # SL/TP, 포지션/포트폴리오 리스크
│   │       └── auto_trade/
│   │           ├── bot.py              # AutoTradeBot 메인 루프
│   │           ├── scanner.py          # 종목 스캔·스코어링·HTF 분석
│   │           └── ai_analyst.py       # AI 분석 레이어
│   ├── requirements.txt
│   ├── .env.example              # 설정 템플릿 (이것을 복사해서 .env 생성)
│   └── ai_settings.json          # ← gitignore (UI에서 자동 생성)
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── types/index.ts
│   │   └── components/
│   │       ├── common/           # Modal, ConfirmModal, Tooltip
│   │       ├── AutoBot/          # AutoTradePanel, PositionDetailModal
│   │       ├── Exchange/         # ExchangeAccountForm
│   │       ├── Strategy/         # StrategyForm, ConditionBuilder, StrategyCard
│   │       └── Chart/            # TradingChart
│   ├── vite.config.ts            # 포트·프록시 설정 (env에서 자동 읽음)
│   └── package.json
├── start.sh                      # 개발 서버 동시 실행 (.env 포트 자동 적용)
└── README.md
```

---

## Security Notes

- `backend/.env` 파일은 절대 커밋하지 마세요 (`.gitignore` 포함)
- `SECRET_KEY`는 반드시 `openssl rand -hex 32` 로 생성한 값으로 교체하세요
- `backend/ai_settings.json`에 실제 API 키가 저장되므로 커밋 금지 (`.gitignore` 포함)
- 거래소 API 키는 DB에 AES-256 암호화 저장됩니다
- `coai.db`에 사용자 정보·거래 내역이 저장되므로 커밋 금지

---

## License

MIT
