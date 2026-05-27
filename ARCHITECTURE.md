# CoAI 시스템 아키텍처

## 1. 시스템 개요

기술 지표 기반 규칙 엔진 + LLM AI 보조 + 전략 빌더를 통합한 암호화폐 자동매매 플랫폼입니다.

| 레이어 | 설명 |
|--------|------|
| **자동매매봇** | 규칙 기반 스캐너 + AI 보조 진입/청산 결정 |
| **전략 빌더** | 사용자 정의 조건 전략 → 백테스트 → 실행 (자동매매봇과 연동) |
| **AI 레이어** | LLM 멀티 프로바이더 지원 (Ollama / Groq / Claude / OpenAI / Gemini) |
| **시장 데이터** | ccxt를 통한 업비트 REST API (현물) / Binance REST API (선물) |

---

## 2. 전체 구조

```
FastAPI 단일 프로세스 (단일 asyncio 이벤트 루프)
│
├── [서브시스템 A] 자동매매봇 (AutoTradeBot)
│     ├── [루프 1] APScheduler ─── 스캔 사이클 (설정된 주기)
│     │     └── _cycle()
│     │           ├── scan_market()  → OHLCV + 지표 계산 + 점수화
│     │           ├── AI 시장 국면 감지 (15분 캐시)
│     │           ├── AI 진입 검증 (종목당 10분 캐시)
│     │           ├── 포지션 진입/물타기/추매/전략 재평가
│     │           └── AI 청산 보조 (수익 포지션, 5분 캐시)
│     │
│     └── [루프 2] asyncio Task ─── SL/TP/트레일링 감시 (0.5초)
│           └── _price_monitor_loop()
│                 ├── 업비트 현재가 병렬 조회
│                 ├── 손절 / 익절 즉시 체결
│                 └── 트레일링 스탑 고점 업데이트 + 청산
│
├── [서브시스템 B] 전략 빌더 (Strategy Builder)
│     ├── APScheduler → strategy scheduler (전략별 타임프레임 주기)
│     ├── 조건 평가 엔진 (evaluate_conditions)
│     ├── 백테스트 엔진 (Walk-Forward 지원)
│     └── 리스크 매니저 (RiskManager)
│
└── [공유 서비스]
      ├── ExchangeConnector (ccxt / Upbit REST)
      ├── AI Analyst (멀티 프로바이더 LLM)
      ├── Indicator Engine (pandas-ta)
      └── Database (SQLAlchemy + SQLite)
```

---

## 3. 자동매매봇 — 루프 1: 스캔 사이클 (APScheduler)

**역할:** 어떤 종목을 살 것인가 + 보유 포지션 관리

### 처리 흐름

```
매 N분마다 실행 (trading_style 프리셋 또는 사용자 설정)
        │
        ▼
scan_market(style, timeframe)
  ├─ SCAN_SYMBOLS 25개 순차 처리 (종목 간 0.15초 지연)
  ├─ 일 거래대금 필터 (스타일별 기준)
  ├─ OHLCV 150캔들 조회
  ├─ RSI / EMA / MACD / 거래량 지표 계산 (pandas-ta)
  ├─ 스타일별 가중치 적용 점수 산출 (0~100점)
  └─ 전략 자동 분류 (5종) + 신호 목록 반환
        │
        ▼
AI 시장 국면 감지 (ai_regime_detection=True, 15분 캐시)
  └─ 국면(trending/ranging/volatile) → 매매 스타일 / min_score 자동 조정
        │
        ▼
점수 ≥ min_score → 신규 진입 후보
  └─ AI 진입 검증 (ai_entry_validation=True, 10분 캐시)
        ├─ 신뢰도 ≥ 0.6 → 진입 허용
        └─ 신뢰도 < 0.6 → 진입 차단 + AI 로그 기록
        │
        ▼
보유 포지션 점검
  ├─ 전략 재평가 → 전략 변경 시 SL/TP 재조정
  ├─ 자동 물타기 (avg_down_threshold_pct% 하락, 최대 2회)
  ├─ 자동 추매  (add_threshold_pct% 상승, 기본 OFF)
  ├─ 신호 약화 감지 → 이익 구간 SL 상향 보호
  └─ AI 청산 보조 (ai_exit_assist=True, 5분 캐시)
        ├─ close_now  → 즉시 청산
        └─ tighten_sl → SL 상향 조정
```

### 처리 모델

- **I/O 바운드**: ccxt API 호출 → asyncio `await`
- **CPU 바운드**: pandas-ta 지표 계산 → 동기, 수 ms 수준
- 종목 간 0.15초 지연으로 레이트 리밋 대응
- `_scan_in_progress` 플래그로 중복 사이클 방지

---

## 4. 자동매매봇 — 루프 2: 실시간 모니터 (asyncio Task)

**역할:** 언제 팔 것인가 (손절 / 익절 / 트레일링 스탑)

### 처리 흐름

```
while running (0.5초마다):
        │
        ▼
asyncio.gather() → 보유 종목 현재가 병렬 조회
        │
        ├─ price ≤ stop_loss_price   → 즉시 시장가 청산 (stop_loss)
        ├─ price ≥ take_profit_price → 즉시 시장가 청산 (take_profit)
        │
        └─ 트레일링 스탑 처리 (trailing_stop=True)
              ├─ pnl_pct ≥ trailing_activate_pct → 활성화
              ├─ 활성화 후 고점(peak_price) 갱신
              └─ price ≤ peak_price × (1 - trailing_pct/100) → 청산 (trailing_stop)
```

### 처리 모델

- 순수 I/O 바운드: 숫자 비교만 수행
- `asyncio.gather()`로 전체 포지션 동시 요청
- `asyncio.wait_for(timeout=3)`으로 개별 종목 지연 처리

---

## 5. AI 레이어

### 지원 프로바이더

| 프로바이더 | 티어 | 특징 |
|-----------|------|------|
| Ollama | 무료 | 로컬 실행, 인터넷 불필요 |
| Groq | 무료 | 무료 API 티어, 빠른 추론 |
| Anthropic (Claude) | 유료 | 높은 추론 품질 |
| OpenAI (GPT) | 유료 | 범용 우수 |
| Gemini | 무료/유료 | Flash 모델 무료 포함 |

### AI 전략 생성 규칙

- `cross_above` / `cross_below` 신호는 **단독 조건**으로만 사용 (pulse 신호)
- `<`, `>`, `<=`, `>=` 신호는 **다중 조건 AND** 조합 가능 (state 신호)
- 두 종류를 AND 조합하면 동시 충족이 사실상 불가능 → 0거래 발생 (SYSTEM_PROMPT에서 차단)

### AI 기능 4종 (개별 ON/OFF)

| 기능 | 설정 키 | 캐시 TTL | 트리거 |
|------|---------|---------|--------|
| 진입 신뢰도 검증 | `ai_entry_validation` | 10분/종목 | 진입 후보 발생 시 |
| 시장 국면 감지 | `ai_regime_detection` | 15분 | 스캔 사이클마다 |
| 연속 손절 자기 분석 | `ai_loss_analysis` | 없음 | 연속 손절 3회마다 1회 |
| 청산 타이밍 보조 | `ai_exit_assist` | 5분/종목 | 수익 중 포지션 점검 시 |

### AI 호출 빈도 (일간 예상)

- 무료 티어(Groq/Ollama): 충분히 운영 가능
- 유료 티어: 수백 회/일 수준 → 소액 과금

### 설정 저장 경로

```
backend/ai_settings.json  (재시작 없이 즉시 반영)
```

---

## 6. 전략 빌더 서브시스템

자동매매봇과 **완전히 분리된** 독립 시스템입니다.

```
사용자 → 조건 기반 전략 정의 (UI)
       ↓
Strategy DB (SQLite)
       ├─ 백테스트 (Walk-Forward 분석)
       │     ├─ 거래소별 수수료율 자동 적용 (Upbit 0.05% / Binance·Bybit 0.10%)
       │     ├─ 총 수익금(₩) · 최종 자본 계산 및 반환
       │     └─ 0거래 시 _snapshot(): 마지막 캔들 지표값 반환 (미충족 조건 진단)
       ├─ 지표 엔진 (compute_indicator / evaluate_conditions)
       │     └─ MACD cross_above/cross_below: MACDh_* 컬럼 기반 교차 판정
       └─ APScheduler → 활성 전략 자동 실행 (paper/live)
```

> 전략 빌더의 DB 전략은 자동매매봇 스캐너에서 활용 가능 (`bot.py`, `strategy/engine.py` 연동 완료).

---

## 7. 두 루프의 관계 (공유 메모리)

```
루프 1 (APScheduler)        루프 2 (asyncio Task)
         │                           │
         │       _positions          │
         │    ┌─────────────┐        │
         └───▶│  공유 dict  │◀───────┘
              │  (메모리)   │
              └─────────────┘
```

- 단일 asyncio 이벤트 루프 → `await` 지점에서만 컨텍스트 스위칭
- 별도 Lock 없이 동시 쓰기 충돌 구조적 불가능
- Python GIL이 추가 보호

---

## 8. 데이터 흐름 전체

```
업비트 REST API (ccxt)
        │ OHLCV 150캔들
        ▼
scanner.py  scan_market()
  └─ _score()  →  score, strategy_type, signals
        │
        ▼                        ai_analyst.py
bot.py  _cycle()      ◀─────── detect_regime()     (15분 캐시)
  _enter_from_scan()  ◀─────── check_entry()        (10분 캐시)
  _check_positions()  ◀─────── check_exit()          (5분 캐시)
  _close_position()   ◀─────── analyze_losses()     (연속 3회)
        │
        ▼
PaperBroker.execute_market_order()
  └─ 가상 체결 (잔고 차감, 수수료 0.05%)
        │
        ▼
_positions dict
  ├─ 루프 2: 0.5초마다 SL/TP/트레일링 판단
  └─ API: 프론트엔드에 실시간 상태 노출

청산 → AutoBotTrade DB (SQLite) 영속 저장
```

---

## 9. API 레이어

| 라우터 | prefix | 주요 엔드포인트 |
|--------|--------|---------------|
| auth | `/api/v1/auth` | register, login |
| strategies | `/api/v1/strategies` | CRUD, 활성화/비활성화 |
| backtest | `/api/v1/backtest` | run |
| market | `/api/v1/market` | ohlcv, indicators, ticker, markets, exchanges |
| trades | `/api/v1/trades` | 거래 내역, 통계 |
| exchange_accounts | `/api/v1/exchange-accounts` | 거래소 계정 관리 |
| auto_strategy | `/api/v1/auto-strategy` | AI 전략 생성 (generate) |
| auto_bot | `/api/v1/auto-bot` | status, start, stop, scan, settings, 포지션 조작, 거래 내역 |
| ai_config | `/api/v1/ai-config` | 프로바이더 설정, 연결 테스트 |
| ws | `/ws` | ticker, strategies WebSocket |

---

## 10. 데이터베이스 모델

| 모델 | 용도 |
|------|------|
| User | 사용자 계정 |
| Strategy | 전략 빌더 전략 (JSON config) |
| Order | 전략 실행 주문 내역 |
| Trade | 전략 실행 거래 내역 |
| Position | 전략 실행 포지션 |
| AutoBotTrade | 자동매매봇 청산 내역 (DB 영속) · market_type / side / leverage / margin_mode 포함 |
| ExchangeAccount | 거래소 API 계정 (AES-256 암호화 저장) · is_paper 플래그로 모의/실거래 구분 |

### 스키마 마이그레이션

`Base.metadata.create_all`은 기존 테이블에 새 컬럼을 추가하지 않습니다.
`init_db()` 호출 시 `_migrate(conn)`이 실행되어 누락된 컬럼을 `ALTER TABLE ADD COLUMN`으로 자동 추가합니다.

---

## 11. 외부 의존성

| 구성 요소 | 역할 |
|----------|------|
| 업비트 REST API (ccxt 4.5.50) | OHLCV, 현재가 데이터 |
| pandas-ta 0.4.71b0 | RSI / EMA / MACD / BB / STOCH / ATR 지표 계산 |
| APScheduler | 스캔 사이클 + 전략 실행 타이머 |
| asyncio | 실시간 가격 모니터 루프 |
| SQLAlchemy 2.0 + SQLite (aiosqlite) | 데이터 영속화 |
| FastAPI | HTTP API / WebSocket |
| httpx | AI 프로바이더 HTTP 클라이언트 |

---

## 12. 확장 가능성 (Extension Points)

### 단기 확장
- **거래소 추가**: `ExchangeConnector`의 `exchange_id` 파라미터만 변경 (ccxt 지원 거래소 전체)
- **AI 프로바이더 추가**: `ai_analyst.py`의 `_call_llm()` 분기 + `PROVIDERS_META` 항목 추가
- **스캔 종목 확장**: `SCAN_SYMBOLS` 리스트 또는 동적 조회 (TODO #6)
- **지표 추가**: `indicator/engine.py`의 `SUPPORTED_INDICATORS`에 항목 추가

### 중기 확장
- **전략 빌더 ↔ 자동매매봇 통합**: DB 전략을 봇 스캐너에서 평가 (TODO #5)
- **실투자 모드**: `PaperBroker` → 업비트 실제 주문 API 전환 (`is_paper=False`)
- **웹훅 / Push 알림**: 청산 이벤트 → Slack / 텔레그램 연동
- **멀티 거래소 포트폴리오**: 거래소별 독립 봇 인스턴스

### 장기 확장
- **ML 모델 통합**: XGBoost / LSTM 진입 확률 추론으로 AI 검증 대체
- **강화학습 에이전트**: 지표 가중치 자동 최적화
- **실시간 WebSocket 시세**: REST 폴링 → WebSocket push로 전환 (레이턴시 개선)
- **분산 처리**: 종목 스캔을 Worker Pool로 병렬화
