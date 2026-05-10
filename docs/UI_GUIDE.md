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

### AutoBot 백엔드 가격 모니터링 주기

AutoBot이 **서버 내부**에서 가격을 확인하는 주기입니다 (UI 갱신과 별개).

| 동작 | 코드 | 주기 |
|------|------|------|
| 보유 포지션 현재가 조회 (SL/TP/트레일링 체크) | `bot.py` `_rest_price_monitor_loop()` — `asyncio.sleep(1)` | **1초** |
| 오류 발생 시 재시도 대기 | 동일 함수 — `asyncio.sleep(5)` | 5초 |
| 새 종목 진입 신호 스캔 (scalping) | APScheduler `IntervalTrigger(minutes=1)` | 1분 |
| 새 종목 진입 신호 스캔 (short) | APScheduler `IntervalTrigger(minutes=5)` | 5분 |
| 새 종목 진입 신호 스캔 (mid) | APScheduler `IntervalTrigger(minutes=15)` | 15분 |
| 새 종목 진입 신호 스캔 (long) | APScheduler `IntervalTrigger(minutes=60)` | 60분 |

> **요약**: 이미 포지션을 보유 중이면 **1초마다** 가격을 확인합니다. 새 진입 기회는 타임프레임(scalping~long)에 따라 1~60분 주기로 스캔합니다.

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

---

## 11. AI 호출 상세 분석

AI 기능이 활성화된 경우, 어느 시점에 얼마나 호출되고 토큰을 얼마나 쓰는지 정리합니다.

**코드 위치**: `backend/app/services/auto_trade/ai_analyst.py`

---

### 11-1. AI 호출 종류 및 발생 조건

#### (1) 시장 국면 감지 — `detect_regime()`

| 항목 | 내용 |
|------|------|
| 발생 조건 | 봇 실행 중 매 사이클마다 체크, **15분 이내 재호출 차단** |
| 추가 조건 | `ai_regime_detection` 설정 ON + `is_ai_available()` |
| 캐시 TTL | 15분 (`CACHE_TTL["regime"] = 900`), BTC 가격 1% 단위로 캐시 키 생성 |
| 실제 호출 주기 | BTC 가격이 1% 이상 변동할 때마다 (하루 20~40회) |
| 입력 토큰 | ~120~150 tokens (BTC 최근 10봉 종가 + RSI + 거래량 비율) |
| 출력 max_tokens | 100 |
| 실제 출력 | ~40~60 tokens (JSON only) |
| **호출당 총 토큰** | **~160~210 tokens** |
| 코드 | `bot.py:_run_regime_detection()` line ~918, `ai_analyst.py:detect_regime()` |

#### (2) 진입 확인 — `check_entry()`

| 항목 | 내용 |
|------|------|
| 발생 조건 | 스캔 후 진입 후보 종목마다 1회 (캐시 미스 시) |
| 추가 조건 | `ai_entry_validation` 설정 ON + 후보 점수 ≥ min_score |
| 캐시 TTL | 10분 (`CACHE_TTL["entry"] = 600`), 키: `entry:{symbol}:{score}:{strategy_type}` |
| 입력 토큰 | ~80~100 tokens (종목명, 점수, 전략 타입, RSI, 신호 최대 3개) |
| 출력 max_tokens | 80 |
| 실제 출력 | ~40~60 tokens |
| **호출당 총 토큰** | **~120~160 tokens** |
| 결과 활용 | `confidence < 65` 시 진입 차단, `≥ 90` 시 포지션 크기 1.2배 |
| 코드 | `bot.py:_enter_from_scan()` line ~1369, `ai_analyst.py:check_entry()` |

#### (3) 포지션 스타일 선택 — `choose_position_style()`

| 항목 | 내용 |
|------|------|
| 발생 조건 | 진입 확인(check_entry) 직후 동일 후보 종목에 연속 호출 |
| 추가 조건 | `ai_entry_validation` ON + 급등 종목 아닌 경우 (급등 시 short 고정) |
| 캐시 TTL | 10분, 키: `pstyle:{symbol}:{strategy_type}:{int(rsi)}` |
| 입력 토큰 | ~120~150 tokens (종목, 전략, RSI, 점수, 신호, 스타일 힌트) |
| 출력 max_tokens | 60 |
| 실제 출력 | ~30~50 tokens |
| **호출당 총 토큰** | **~150~200 tokens** |
| 결과 활용 | scalping / short / mid / long 중 선택 → 해당 포지션 SL/TP/트레일링 기준 적용 |
| 코드 | `bot.py:_enter_from_scan()` line ~1421, `ai_analyst.py:choose_position_style()` |

> 진입 1건당 (2)+(3) 합산: **~270~360 tokens**

#### (4) 청산 타이밍 보조 — `check_exit()`

| 항목 | 내용 |
|------|------|
| 발생 조건 | 이익 중인 포지션 + 트레일링 미활성 + 스타일별 최소 수익 도달 시 |
| 최소 수익 기준 | scalping 0.8% / short 1.5% / mid 3.0% / long 5.0% |
| 체크 주기 | 15초(REST 폴링)마다 조건 확인 → 캐시로 실제 AI 호출 절약 |
| 캐시 TTL | 5분 (`CACHE_TTL["exit"] = 300`), 키: `exit:{symbol}:{int(pnl_pct*10)}` |
| 실제 호출 주기 | 수익률 0.1% 변동마다 캐시 키 변경 → 최대 5분마다 1회 |
| 입력 토큰 | ~90~110 tokens (종목, PnL%, 전략, SL 여유 %, 신호) |
| 출력 max_tokens | 80 |
| 실제 출력 | ~30~60 tokens |
| **호출당 총 토큰** | **~120~170 tokens** |
| 결과 활용 | `close_now` → 즉시 청산, `tighten_sl` → SL 상향, `hold` → 유지 |
| 코드 | `bot.py:_check_positions()` line ~1198, `ai_analyst.py:check_exit()` |

#### (5) 연속 손절 자기 분석 — `analyze_losses()`

| 항목 | 내용 |
|------|------|
| 발생 조건 | stop_loss로 청산된 횟수가 **연속 3회** 달성 시 1회만 실행 |
| 추가 조건 | `ai_loss_analysis` ON + 직전 손실 거래 최대 5건 전달 |
| 캐시 | 없음 (실행 후 `_consecutive_losses = 0` 리셋) |
| 입력 토큰 | ~100~130 tokens (최근 5건 거래 요약 + 현재 SL/min_score 설정) |
| 출력 max_tokens | 100 |
| 실제 출력 | ~50~80 tokens |
| **호출당 총 토큰** | **~150~210 tokens** |
| 결과 활용 | SL % 자동 상향 (최대 +2.0%), min_score 자동 상향 (최대 +10) |
| 코드 | `bot.py:_close_position()` line ~1943, `ai_analyst.py:analyze_losses()` |

#### (6) AI 전략 자동 생성 — `_call_llm()` (auto_strategy)

| 항목 | 내용 |
|------|------|
| 발생 조건 | 사용자가 대시보드 → "AI 전략 생성" 버튼 클릭 시 |
| 빈도 | 수동 트리거, 자동 호출 없음 |
| system prompt | ~400 tokens (전략 JSON 형식, 조건 규칙 설명) |
| user prompt | ~250~300 tokens (종목 시세 + RSI/EMA/MACD/BB/Stoch/거래량) |
| 입력 총 토큰 | **~650~700 tokens** |
| 출력 max_tokens | 1500 |
| 실제 출력 | ~400~800 tokens (전략 JSON) |
| **호출당 총 토큰** | **~1,050~1,500 tokens** |
| 코드 | `backend/app/api/auto_strategy.py:generate()` |

---

### 11-2. 하루 예상 호출 횟수 및 토큰 (단타 스타일 기준)

> 단타 스타일 (scan_interval=5분, max_positions=4) 기준. 실제 시장 상황에 따라 다름.

| 기능 | 하루 예상 호출 | 호출당 토큰 | 하루 예상 토큰 |
|------|:----------:|:---------:|:----------:|
| 시장 국면 감지 | 20~40회 | ~185 | ~3,700~7,400 |
| 진입 확인 | 10~30회 | ~140 | ~1,400~4,200 |
| 포지션 스타일 | 10~30회 | ~175 | ~1,750~5,250 |
| 청산 타이밍 보조 | 20~60회 | ~145 | ~2,900~8,700 |
| 연속 손절 분석 | 0~2회 | ~180 | ~0~360 |
| **합계** | **60~162회** | — | **~9,750~25,910 tokens** |

> 캐시 효과: 실제 API 호출은 위 수치의 30~50% 수준. 나머지는 인메모리 캐시에서 응답.

---

### 11-3. 프로바이더별 무료 한도 및 예상 비용

#### Ollama (로컬 무료)

- 비용: **완전 무료** (로컬 GPU/CPU 자원만 사용)
- 응답 속도: CPU 전용 시 5~30초/호출, GPU 있으면 1~5초
- 권장 모델: `llama3.2` (3B, 빠름) / `llama3.1` (8B, 품질 우수)
- 주의: Ollama 프로세스가 항상 실행 중이어야 함

#### Groq (무료 API, 추천)

- 무료 한도: 분당 ~6,000 tokens, **일일 무제한** (실사용 무제한에 가까움)
- 하루 예상 토큰: ~10,000~26,000 → **무료 한도 내**
- 응답 속도: 평균 0.5~2초 (매우 빠름)
- 주의: 분당 요청 수 제한 있음. 동시 다발 진입 시 429 오류 가능 → 자동 폴백 처리됨

#### Gemini Flash (무료 티어)

- 무료 한도: **분당 15회, 일 1,500회**
- 하루 예상 호출: 60~162회 → **무료 한도 내**
- 응답 속도: 평균 1~3초
- 권장 모델: `gemini-2.0-flash` (무료 Flash 모델)

#### Anthropic Claude

| 모델 | 입력 단가 | 출력 단가 | 하루 예상 비용 |
|------|:--------:|:--------:|:----------:|
| claude-haiku-4-5 | $0.80/1M | $4.00/1M | ~$0.01~0.02 |
| claude-sonnet-4-6 | $3.00/1M | $15.00/1M | ~$0.04~0.10 |

> 월 30일 기준: Haiku ~$0.30~0.60, Sonnet ~$1.20~3.00

#### OpenAI GPT

| 모델 | 입력 단가 | 출력 단가 | 하루 예상 비용 |
|------|:--------:|:--------:|:----------:|
| gpt-4o-mini | $0.15/1M | $0.60/1M | ~$0.003~0.008 |
| gpt-4o | $2.50/1M | $10.00/1M | ~$0.04~0.10 |

> 월 30일 기준: gpt-4o-mini ~$0.10~0.24, gpt-4o ~$1.20~3.00

---

### 11-4. 캐시 동작 원리

모든 AI 호출에는 인메모리 캐시(`_cache` dict)가 적용됩니다. 동일 조건 재요청 시 LLM을 호출하지 않고 캐시된 결과를 반환합니다.

```
캐시 키 구조:
  진입 확인:      "entry:{symbol}:{score}:{strategy_type}"
  스타일 선택:    "pstyle:{symbol}:{strategy_type}:{rsi_int}"
  시장 국면:      "regime:{btc_price_1pct_bucket}"
  청산 보조:      "exit:{symbol}:{pnl_pct_x10_int}"

TTL:
  entry / pstyle:  600초 (10분)
  regime:          900초 (15분)
  exit:            300초 (5분)
```

캐시가 초기화되는 시점:
- AI 설정 변경 시 (`ai_analyst.set_config()` 호출 시 `_cache.clear()`)
- 서버 재시작 시 (메모리 휘발)

---

### 11-5. AI 실패 시 폴백 동작

AI 호출이 실패해도 **봇은 정상 동작**합니다. 각 기능의 폴백:

| 기능 | 실패 시 동작 |
|------|-------------|
| 시장 국면 감지 | ADX 규칙 기반 결과 유지 (AI 보완 없이 규칙만 사용) |
| 진입 확인 | `enter=True, confidence=70` → 진입 허용, 포지션 크기 조정 없음 |
| 포지션 스타일 | 규칙 기반 스타일 선택 (`_choose_style_rules()`) 결과 유지 |
| 청산 타이밍 | `action=hold` → 청산 없이 기존 SL/TP 유지 |
| 손절 분석 | 기본값 적용 (SL +0.5%, min_score +5) |
| 전략 자동 생성 | UI에 오류 메시지 표시, 전략 미생성 |

실패 원인: 타임아웃(25초), 네트워크 오류, API 키 없음, 요청 한도 초과(429)

---

### 11-6. AI 없이 동작하는 기능 (규칙 기반)

AI를 설정하지 않아도 다음 기능은 규칙 기반으로 정상 동작합니다:

| 기능 | 규칙 기반 대체 |
|------|--------------|
| 시장 국면 감지 | ADX < 20 → 횡보장, ADX ≥ 20 → 추세장 |
| 포지션 스타일 | RSI + 신호 키워드 + 점수로 선택 (`_choose_style_rules()`) |
| 진입 여부 | 점수 ≥ min_score + MTF 확인만으로 진입 |
| 청산 | SL/TP/트레일링 스탑 규칙으로만 운영 |

**AI 미설정 시 비활성화되는 기능:**
- 진입 신뢰도 검증 (confidence 기반 진입 차단)
- 포지션 크기 자동 확대 (size_multiplier)
- 연속 손절 자기 분석 (파라미터 자동 조정)
- 청산 타이밍 AI 보조 (조기 청산 / SL 상향)
- AI 전략 자동 생성 버튼
