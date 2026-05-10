# CoAI UI 가이드 — 화면별 기능 및 코드 매핑

사용자가 보는 각 화면의 기능과, 그 기능이 연결된 프론트엔드/백엔드 코드를 정리합니다.

---

## 전체 화면 구조

```
/login          로그인 / 회원가입
/               대시보드 (메인)
  └─ 포트폴리오 요약
  └─ 봇 현황 (전략 봇)
  └─ 실시간 차트
  └─ 전략 목록
  └─ AutoBot 패널  ← 핵심
/exchange       거래소 계좌 관리
/settings       AI 설정
```

---

## 1. 로그인 / 회원가입

**파일**: `frontend/src/pages/LoginPage.tsx`

| 기능 | 동작 | API |
|------|------|-----|
| 로그인 | 이메일+비밀번호 → JWT 토큰 발급 | `POST /api/v1/auth/login` |
| 회원가입 | 이메일+비밀번호+사용자명 → 로컬 DB 저장 | `POST /api/v1/auth/register` |

- 토큰은 Zustand store(`frontend/src/store/auth.ts`)에 저장됩니다.
- 토큰 만료/없음(401, 403) 시 자동 로그아웃 처리 (`frontend/src/utils/api.ts`).
- 이메일 인증 없음. 로컬 DB(`coai.db`)에만 저장됩니다.

**백엔드**: `backend/app/api/auth.py`, 모델: `backend/app/models/user.py`

---

## 2. 헤더 + 티커 바

**파일**: `frontend/src/App.tsx`, `frontend/src/components/Dashboard/TickerBar.tsx`

### 헤더 (상단 네비게이션)

| 요소 | 설명 |
|------|------|
| CoAI 로고 | 없음 (텍스트) |
| 대시보드 / 거래소 / 설정 | 페이지 이동 |
| 사용자명 + 로그아웃 | Zustand auth store에서 표시 |

### 티커 바 (헤더 하단 흐르는 시세)

- 주요 코인 현재가·등락률을 실시간으로 표시
- **WebSocket**: `ws://localhost:{BACKEND_PORT}/ws/ticker` 연결
- 연결 실패 시 REST 폴백 → `GET /api/v1/market/ticker?symbols=...`

**백엔드**: `backend/app/api/ws.py`, `backend/app/api/market.py`

---

## 3. 대시보드 (`/`)

**파일**: `frontend/src/pages/DashboardPage.tsx`

대시보드는 6개 섹션으로 구성됩니다.

---

### 3-1. 포트폴리오 요약

총 자산 / 총 손익 / 승률 / 활성 봇 수를 4개 카드로 표시.

| 카드 | 데이터 출처 | 갱신 주기 |
|------|------------|----------|
| 총 자산 | `GET /api/v1/exchange-accounts/portfolio` | 60초 |
| 총 손익 | `GET /api/v1/trades/stats` | 30초 |
| 승률 | 위와 동일 | 30초 |
| 활성 봇 | `GET /api/v1/strategies/` (is_active 필터링) | 10초 |

**백엔드**:
- `backend/app/api/exchange_accounts.py` → `GET /portfolio`
- `backend/app/api/trades.py` → `GET /stats`

---

### 3-2. 봇 현황 (전략 봇)

전략 Builder로 만들고 활성화한 봇의 실행 현황. AutoBot(자동매매봇)과는 별개입니다.

- `GET /api/v1/strategies/bot-status` — 5초마다 갱신
- 각 봇의 종목·타임프레임·포지션 방향·미실현 손익·손절가·익절가 표시
- 포지션 없으면 "진입 조건 모니터링 중" 표시

**백엔드**: `backend/app/api/strategies.py`

---

### 3-3. 실시간 차트

**파일**: `frontend/src/components/Chart/TradingChart.tsx`

- lightweight-charts 4 기반 캔들스틱 차트
- 종목 변경: 우측 상단 심볼 선택기 (`SymbolPicker.tsx`)
- OHLCV 데이터: `GET /api/v1/market/ohlcv?symbol=BTC/KRW&timeframe=1h`
- 실시간 업데이트: WebSocket `ws://localhost:{port}/ws/ticker`

**백엔드**: `backend/app/api/market.py`, `backend/app/api/ws.py`

---

### 3-4. 전략 목록

**파일**: `frontend/src/components/Strategy/StrategyCard.tsx`

`GET /api/v1/strategies/` — 10초마다 갱신

각 전략 카드에서:

| 버튼/기능 | 동작 |
|-----------|------|
| 활성화 토글 | `PATCH /api/v1/strategies/{id}` (`is_active` 변경) → 봇 시작/중지 |
| 백테스트 | `BacktestPage` 모달 열기 |
| 실행 현황 | `StrategyDetailModal` → 차트 + 현재 포지션 + 거래 내역 |
| 편집 | `StrategyForm` 모달 → `PUT /api/v1/strategies/{id}` |
| 삭제 | `ConfirmModal` → `DELETE /api/v1/strategies/{id}` (포지션 있으면 차단) |

#### 새 전략 버튼 (우측 상단)

AI 사용 여부(`useSettingsStore.aiEnabled`)에 따라:
- AI 설정 시: "AI 자동 생성" / "직접 만들기" 드롭다운
- AI 미설정 시: "새 전략" 버튼 (직접 만들기만)

**백엔드**: `backend/app/api/strategies.py`, `backend/app/services/strategy/engine.py`

---

### 3-5. 전략 직접 만들기 (StrategyForm)

**파일**: `frontend/src/components/Strategy/StrategyForm.tsx`, `ConditionBuilder.tsx`

| 필드 | 설명 |
|------|------|
| 전략명 | 텍스트 |
| 종목 | 업비트 마켓 목록에서 선택 (`GET /api/v1/market/markets`) |
| 타임프레임 | 1m / 5m / 15m / 1h / 4h / 1d |
| 진입 조건 | 보조지표 + 연산자 + 임계값 조합 (여러 개 AND 조합) |
| 청산 조건 | 위와 동일 |
| 손절 % | 진입가 대비 손절 비율 |
| 익절 % | 진입가 대비 익절 비율 |
| 포지션 크기 % | 잔고 대비 포지션 크기 |
| 트레일링 스탑 | 활성화 시 트레일링 간격 % 설정 |

지원 지표: RSI, MACD, EMA, SMA, 볼린저밴드 상단/하단, 거래량

**백엔드**: `backend/app/services/indicator/engine.py`, `backend/app/services/strategy/engine.py`

---

### 3-6. AI 전략 자동 생성 (AutoStrategyModal)

**파일**: `DashboardPage.tsx` 내 `AutoStrategyModal`

1. 종목·타임프레임 선택
2. `POST /api/v1/auto-strategy/generate` 호출
3. 백엔드가 최근 OHLCV 데이터 조회 → AI에 지표 분석 요청 → 전략 자동 구성
4. 생성된 전략이 DB에 저장되고 전략 목록에 즉시 반영

**백엔드**: `backend/app/api/auto_strategy.py`, `backend/app/services/auto_trade/ai_analyst.py`

---

### 3-7. 백테스트 (BacktestPage)

**파일**: `frontend/src/pages/BacktestPage.tsx`

전략 카드의 "백테스트" 버튼 또는 직접 접근 시 모달로 표시.

| 설정 | 설명 |
|------|------|
| 종목 | 업비트 마켓에서 선택 |
| 타임프레임 | 1m ~ 1d |
| 거래소 | Upbit(0.05%) / Binance(0.10%) / Bybit(0.10%) |
| 초기 자본 | 원화 기준 |
| Walk-Forward | 활성화 시 훈련/검증 구간 분리 |
| 진입/청산 조건 | ConditionBuilder로 편집 |

결과 표시:
- 수익률 / 승률 / MDD / Sharpe / Profit Factor
- 자본 곡선 (EquityChart)
- Walk-Forward 구간별 결과
- 거래 내역 테이블
- 0거래 시 지표 스냅샷 (미충족 조건 진단)

`POST /api/v1/backtest/run`

**백엔드**: `backend/app/api/backtest.py`, `backend/app/services/backtest/engine.py`

---

## 4. AutoBot 패널

**파일**: `frontend/src/components/AutoBot/AutoTradePanel.tsx`

대시보드 하단에 항상 표시. 자동매매봇 전체를 제어하는 핵심 패널.

`GET /api/v1/auto-bot/status` — 3초마다 자동 갱신

---

### 4-1. 봇 제어 버튼

| 버튼 | API | 동작 |
|------|-----|------|
| 시작 | `POST /api/v1/auto-bot/start` | 봇 시작, 설정 전달 |
| 일시정지 | `POST /api/v1/auto-bot/pause` | 신규 진입 차단, 기존 포지션 모니터 유지 |
| 재개 | `POST /api/v1/auto-bot/resume` | 일시정지 해제 |
| 중단 | `POST /api/v1/auto-bot/full-stop` | 전체 포지션 청산 후 정지 |
| 수동 스캔 | `POST /api/v1/auto-bot/scan` | 즉시 시장 스캔 실행 |

**중단** 동작 차이:
- 모의거래: 포지션 청산 + 잔고/기록 초기화
- 실거래: 포지션 청산만 (잔고 유지)

**백엔드**: `backend/app/api/auto_bot.py`, `backend/app/services/auto_trade/bot.py`

---

### 4-2. 매매 스타일 선택

봇 시작 전에 4가지 스타일 중 선택:

| 스타일 | 타임프레임 | 손절 | 익절 | 적합 종목 |
|--------|-----------|------|------|----------|
| 초단타 (scalping) | 5m | 1% | 2% | 일 거래대금 50억+ |
| 단타 (short) | 1h | 2.5% | 6% | 일 거래대금 20억+ |
| 중장기 (mid) | 4h | 6% | 18% | 일 거래대금 5억+ |
| 장기 (long) | 1d | 12% | 35% | 전체 스캔 |

스타일 선택 시 → `GET /api/v1/auto-bot/style-presets` 로 프리셋 로드 → 봇 시작 시 설정 전달

**백엔드**: `bot.py` `TRADING_STYLE_PRESETS` (line 29)

---

### 4-3. 거래소 / 모의·실거래 선택

| 설정 | 설명 |
|------|------|
| 거래소 | Upbit(KRW 현물) / Binance·Bybit(USDT 현물·선물) |
| 모의거래 | PaperBroker 사용, 가상 잔고로 매매 시뮬레이션 |
| 실거래 | 등록된 거래소 계좌 API 키로 실제 주문 |

실거래 전환 시:
- 등록된 API 키 존재 여부 확인
- 잔고 조회 성공 여부 확인 (미등록 시 전환 차단)

---

### 4-4. 잔고 / 성과 요약

봇 실행 중 상단에 표시:

| 항목 | 설명 |
|------|------|
| 잔고 | 미투자 현금 (KRW 또는 USDT) |
| 총 자산 | 잔고 + 보유 포지션 평가액 |
| 미실현 손익 | 현재 보유 포지션 합산 |
| 실현 손익 | 청산 완료 거래 합산 |
| 동작 시간 | 봇 시작 후 경과 시간 |

---

### 4-5. AI 국면 표시

AI가 감지한 시장 국면을 상단에 표시:

| 국면 | 설명 |
|------|------|
| 추세장 (trending) | BTC ADX ≥ 20, 강한 방향성 |
| 횡보장 (ranging) | BTC ADX < 20, 방향성 없음 → 평균 회귀 전략 자동 전환 |
| 급등락 (volatile) | 단기 급변동 감지 |

**백엔드**: `bot.py` `_run_regime_detection()`, `scanner.py` ADX 계산

---

### 4-6. 현재 포지션 목록

보유 중인 각 포지션을 카드로 표시:

| 항목 | 설명 |
|------|------|
| 종목 / 전략 레이블 | 예: BTC/KRW — 골든크로스 |
| 평균 단가 | 물타기 포함 평균 진입가 |
| 미실현 손익 % / ₩ | 실시간 갱신 |
| 진행률 바 | SL ← 현재가 → TP 위치 표시 |
| 물타기 횟수 / 추매 횟수 | avg_down_count / add_count |
| 포지션 스타일 배지 | 해당 포지션에 적용된 매매 스타일 |

포지션 카드 클릭 → **PositionDetailModal** 열림

**수동 조작 버튼** (포지션 카드 내):

| 버튼 | API | 설명 |
|------|-----|------|
| 추매 | `POST /api/v1/auto-bot/position/{symbol}/add` | 현재가로 추가 매수 |
| 물타기 | `POST /api/v1/auto-bot/position/{symbol}/avg-down` | 현재가로 평단 낮추기 |
| 청산 | `POST /api/v1/auto-bot/position/{symbol}/close` | 즉시 시장가 청산 |

**파일**: `AutoTradePanel.tsx`, `PositionDetailModal.tsx`

---

### 4-7. PositionDetailModal (포지션 상세)

**파일**: `frontend/src/components/AutoBot/PositionDetailModal.tsx`

포지션 카드 클릭 시 표시되는 상세 모달:

- 진입 이력 테이블 (초기 진입 / avg_down / add / pyramid 구분)
- 각 진입의 가격·수량·시각
- SL·TP 가격 / 현재가 / 손익
- 신호 목록 (진입 당시 감지된 전략 신호)
- AI 분석 요약 (진입 시 AI 판단 이유)

---

### 4-8. 스캔 결과

시장 스캔에서 발굴된 후보 종목 목록:

| 항목 | 설명 |
|------|------|
| 종목 | 예: ETH/KRW |
| 점수 | 0~100 (신호 강도 합산) |
| 전략 레이블 | 예: 골든크로스, 거래량 돌파 |
| RSI | 현재 RSI 값 |
| SL / TP % | 예상 손절·익절 비율 |
| HTF 확인 | 상위봉 추세 일치 여부 |
| MR 점수 | 평균 회귀 신호 강도 (횡보장 모드) |

**백엔드**: `backend/app/services/auto_trade/scanner.py`
- `_score()`: 기술적 지표 → 점수 산출
- `_score_mean_reversion()`: 횡보장 MR 점수
- `_htf_trend()`: 상위봉 추세 확인

---

### 4-9. 거래 내역

AutoBot이 완료한 거래 목록:

- `GET /api/v1/auto-bot/trades` — DB 영속 (서버 재시작 후에도 유지)
- 청산 사유: stop_loss / take_profit / trailing_stop / full_stop / manual
- 물타기/추매 횟수, 평균 단가, 손익(%) 표시

**성과 통계**: `GET /api/v1/auto-bot/trades/stats`

| 지표 | 설명 |
|------|------|
| 총 거래 수 | 청산 완료 건수 |
| 승률 | 수익 거래 비율 |
| 총 손익 (₩) | 실현 손익 합산 |
| 평균 손익 % | 거래당 평균 |
| 최고/최저 거래 % | 최대 수익/손실 거래 |
| VaR 95% | 95% 신뢰구간 1일 최대 예상 손실 |

**백엔드**: `backend/app/api/auto_bot.py`, `backend/app/models/auto_bot_trade.py`

---

### 4-10. AI 분석 로그

AI가 내린 판단 이력 (최대 20건):

| 타입 | 설명 |
|------|------|
| `regime_change` | 시장 국면 변경 감지 |
| `loss_analysis` | 연속 손절 3회 후 원인 분석 + 파라미터 자동 조정 |
| `entry_blocked` | AI가 진입 거부한 종목 + 이유 |
| `exit_action` | AI가 조기 청산 또는 SL 상향 수행 |
| `surge_override` | 급등 감지로 AI 판단 무시하고 즉시 진입 |

**백엔드**: `backend/app/services/auto_trade/ai_analyst.py`

---

### 4-11. AutoBot 세부 설정 패널

패널 우측 상단 설정 아이콘 클릭 시 확장:

| 섹션 | 항목 |
|------|------|
| 기본 | 손절 % / 익절 % / 최소 점수 / 최대 포지션 수 / 포지션 크기 % |
| 물타기 | 활성화 / 발동 하락률 % / 최대 횟수 |
| 추매 | 활성화 / 발동 수익률 % / 최대 횟수 |
| 트레일링 스탑 | 활성화 / 활성화 수익률 % / 트레일링 간격 % |
| 부분 청산 | 활성화 / 청산 비율 / 발동 트리거 % |
| 피라미딩 | 활성화 / 발동 수익률 % / 최대 횟수 |
| 리스크 | 일일 최대 손실 % / 포트폴리오 노출 한도 % / 상관계수 임계값 / MDD 한도 % |
| 선물 (Binance/Bybit) | 레버리지 / 마진 모드 |

설정 변경 → `PATCH /api/v1/auto-bot/settings`

> 설정은 메모리에만 저장됩니다. 서버 재시작 시 기본값으로 초기화됩니다.

---

### 4-12. 모의거래 잔고 설정

모의거래 모드에서 가상 잔고를 직접 입력:
- `PATCH /api/v1/auto-bot/balance`
- Upbit: KRW, Binance/Bybit: USDT 단위

---

## 5. 거래소 계좌 (`/exchange`)

**파일**: `frontend/src/pages/ExchangePage.tsx`

### 계정 목록

`GET /api/v1/exchange-accounts/` — 등록된 계좌 목록

각 계좌 카드:

| 항목 | 설명 |
|------|------|
| 거래소명 / 거래 통화 | Upbit(KRW) / Binance(USDT) / Bybit(USDT) |
| 모의/실거래 배지 | is_paper 여부 |
| API Key (마스킹) | 앞 4자·뒤 4자만 표시 |
| 잔고 (실거래만) | `GET /api/v1/exchange-accounts/{id}/balance` |
| 연결 테스트 | `GET /api/v1/exchange-accounts/{id}/test` → BTC 현재가 조회로 확인 |
| 암호화폐 입금 | `GET /api/v1/exchange-accounts/{id}/deposit-address/{currency}` |
| 삭제 | `DELETE /api/v1/exchange-accounts/{id}` (ConfirmModal) |

### 계정 추가

**파일**: `frontend/src/components/Exchange/ExchangeAccountForm.tsx`

- 거래소 선택 (Upbit / Binance / Bybit)
- 레이블 입력
- Access Key / Secret Key 입력
- 모의/실거래 선택
- `POST /api/v1/exchange-accounts/` — API 키는 AES-256 암호화 후 DB 저장

**백엔드**: `backend/app/api/exchange_accounts.py`, `backend/app/services/exchange/connector.py`

---

## 6. 설정 (`/settings`)

**파일**: `frontend/src/pages/SettingsPage.tsx`

### AI 기능 개별 토글

봇이 실행 중일 때만 표시. 각 토글은 `PATCH /api/v1/auto-bot/settings`를 즉시 호출.

| 토글 | 기능 설명 |
|------|----------|
| 진입 확인 | AI가 진입 신호의 신뢰도를 검증. 낮으면 진입 차단 |
| 시장 국면 감지 | BTC ADX+AI 분석으로 추세장/횡보장 판단, 스타일 자동 전환 |
| 연속 손절 분석 | 3회 연속 손절 시 원인 분석 → SL·최소점수 자동 조정 |
| 청산 타이밍 보조 | 이익 포지션에서 추세 반전 감지 시 조기 청산 또는 SL 상향 |

### AI 프로바이더 설정

| 항목 | 설명 |
|------|------|
| 프로바이더 카드 | 무료(Ollama, Groq, Gemini) / 유료(Anthropic, OpenAI) 선택 |
| 모델 선택 | 프로바이더별 지원 모델 드롭다운 |
| API 키 입력 | 비밀번호 마스킹, 눈 아이콘으로 토글 |
| Ollama URL | Ollama 서버 주소 (기본: localhost:11434) |
| 연결 테스트 | `POST /api/v1/ai-config/test` — 실제 API 연결 확인 |
| 저장 | `POST /api/v1/ai-config` — DB 저장 + 런타임 즉시 반영 + ai_settings.json 갱신 |

**백엔드**: `backend/app/api/ai_config.py`, `backend/app/services/auto_trade/ai_analyst.py`

---

## 7. 공통 컴포넌트

**파일**: `frontend/src/components/common/`

| 컴포넌트 | 설명 |
|----------|------|
| `Modal.tsx` | 기본 모달 래퍼 (오버레이 + 닫기 버튼) |
| `ConfirmModal.tsx` | 위험 동작 확인 다이얼로그 (삭제, 청산 등) |
| `Tooltip.tsx` | 용어 툴팁 (RSI, MACD, HTF, 물타기 등 마우스 오버 설명) |

---

## 8. 데이터 흐름 요약

```
사용자 액션
    │
    ▼
React 컴포넌트 (TanStack Query useMutation)
    │  axios → /api/v1/...
    ▼
FastAPI 라우터 (backend/app/api/*.py)
    │
    ├─ 거래소 연동 ──→ ccxt (ExchangeConnector)
    │                   └─ Upbit REST API
    │                   └─ Binance REST API
    │
    ├─ 자동매매 ────→ AutoTradeBot (bot.py)
    │                   ├─ Scanner (scanner.py) — 종목 발굴·스코어링
    │                   ├─ AI Analyst (ai_analyst.py) — LLM 호출
    │                   ├─ RiskManager (risk/manager.py) — SL/TP
    │                   └─ PaperBroker / ExchangeConnector — 주문 실행
    │
    ├─ 백테스트 ────→ BacktestEngine (backtest/engine.py)
    │                   └─ StrategyEngine (strategy/engine.py)
    │
    └─ AI 설정 ─────→ ai_analyst.set_config() — 런타임 즉시 반영
                        └─ DB(UserAIConfig) + ai_settings.json 저장
```

---

## 9. 실시간 데이터 갱신 주기

| 데이터 | 방식 | 주기 |
|--------|------|------|
| 시세 티커 바 | WebSocket | 실시간 |
| 차트 OHLCV | REST | 초기 로드 후 갱신 없음 |
| AutoBot 상태 | REST 폴링 | 3초 |
| 전략 봇 현황 | REST 폴링 | 5초 |
| 전략 목록 | REST 폴링 | 10초 |
| 포트폴리오 | REST 폴링 | 60초 |
| 거래 통계 | REST 폴링 | 30초 |
| AutoBot 미실현 손익 | REST 폴링 (bot.py) | 15초 |

---

## 10. 주요 API 엔드포인트 빠른 참조

```
인증
  POST   /api/v1/auth/register        회원가입
  POST   /api/v1/auth/login           로그인 (JWT 발급)

전략
  GET    /api/v1/strategies/          전략 목록
  POST   /api/v1/strategies/          전략 생성
  PUT    /api/v1/strategies/{id}      전략 수정
  DELETE /api/v1/strategies/{id}      전략 삭제
  GET    /api/v1/strategies/bot-status 전략 봇 현황

백테스트
  POST   /api/v1/backtest/run         백테스트 실행

AI 자동 전략
  POST   /api/v1/auto-strategy/generate  AI 전략 생성

AutoBot
  GET    /api/v1/auto-bot/status      봇 상태 조회
  POST   /api/v1/auto-bot/start       봇 시작
  POST   /api/v1/auto-bot/stop        봇 중지
  POST   /api/v1/auto-bot/pause       일시정지
  POST   /api/v1/auto-bot/resume      재개
  POST   /api/v1/auto-bot/full-stop   전체 청산 후 중단
  POST   /api/v1/auto-bot/scan        수동 스캔
  PATCH  /api/v1/auto-bot/settings    설정 변경
  PATCH  /api/v1/auto-bot/balance     모의 잔고 설정
  GET    /api/v1/auto-bot/trades      거래 내역 (DB)
  GET    /api/v1/auto-bot/trades/stats 성과 통계
  POST   /api/v1/auto-bot/position/{symbol}/close   수동 청산
  POST   /api/v1/auto-bot/position/{symbol}/add     수동 추매
  POST   /api/v1/auto-bot/position/{symbol}/avg-down 수동 물타기

거래소
  GET    /api/v1/exchange-accounts/          계좌 목록
  POST   /api/v1/exchange-accounts/          계좌 추가
  DELETE /api/v1/exchange-accounts/{id}      계좌 삭제
  GET    /api/v1/exchange-accounts/{id}/test 연결 테스트
  GET    /api/v1/exchange-accounts/{id}/balance 잔고 조회
  GET    /api/v1/exchange-accounts/portfolio 포트폴리오 합산

AI 설정
  GET    /api/v1/ai-config            현재 AI 설정 조회
  POST   /api/v1/ai-config            AI 설정 저장
  POST   /api/v1/ai-config/test       연결 테스트

시세
  GET    /api/v1/market/markets       마켓 목록
  GET    /api/v1/market/ohlcv         OHLCV 데이터
  GET    /api/v1/market/ticker        현재가
  WS     /ws/ticker                   실시간 시세
```
