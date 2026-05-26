# CoAI 트레이딩 알고리즘 카탈로그

> 작성일: 2026-05-12
> 범위: `backend/app/services/` 하위 strategy / auto_trade / indicator / risk / backtest / exchange 모듈 + `backend/app/api/auto_strategy.py`, `backend/app/api/backtest.py`

## 개요

CoAI는 암호화폐 자동 매매 플랫폼으로, JSON 기반 설정 매매 엔진, AI 분석 모듈, 포트폴리오 리스크 관리, 백테스트 시스템을 통합한 구조입니다. 본 문서는 코드베이스에 구현된 모든 트레이딩 알고리즘을 카테고리별로 정리합니다.

---

## 1. 매매 진입 전략 (Entry Strategies)

### 1.1 스캐너 기반 동적 신호 분류

**위치:** [backend/app/services/auto_trade/scanner.py:451-692](../backend/app/services/auto_trade/scanner.py#L451)

**분류:** 매매 진입 / 신호 점수화

**목적:** 시장 스캔으로 24시간 거래대금 기준 상위 종목을 기술 지표로 분석하여 100점 만점 신호 점수를 산출하고, 자동으로 5가지 전략 유형으로 분류

**진입 신호 구성 (스타일별 가중치 차등 적용):**

- **RSI 과매도** (기본 30점): RSI 20-35 범위에서 점수 부여
  - 강한 과매도 (RSI ≤ 35): 15~30점
  - 과매도 구간 (35 < RSI ≤ 45): 15점
  - 중립 (45 < RSI ≤ 55): 5점
  - 추세 구간 (RSI 50-70) + MACD 강세: 8점 보너스
- **EMA 추세** (기본 20점): EMA20 > EMA50 시 12점 + 가격 > EMA20 시 8점
  - 골든크로스 (EMA20이 EMA50 상향 돌파): 30점
- **MACD 모멘텀** (기본 30점):
  - 골든크로스 (MACD > Signal 상향 돌파): 30점
  - MACD > Signal (진행 중): 15점
  - 반등 중 (MACD 상승): 5점
- **거래량** (기본 20점):
  - 3배 이상: 20점 ("거래량 급증")
  - 2배 이상: 12점 ("거래량 증가")
  - 1.5배 이상: 6점 ("거래량 소폭 증가")

**캔들 패턴 감지 (추가 점수):**

| 패턴 | 점수 |
|------|------|
| 망치형 캔들 | 15 |
| 불리시 인걸핑 | 18 |
| 피어싱 라인 | 12 |
| 도지 저점 반전 | 10 |
| 모닝스타 (3봉) | 20 |
| 상승 하라미 | 12 |
| 상승 삼병사 | 20 |
| 이중 바닥 | 22 |
| BB 하단 반등 | 16 |
| 역헤드앤숄더 | 25 |

**RSI 저점 반등 / 불리시 다이버전스 (추가 점수):**

- RSI 연속 2봉 상승 (RSI ≤ 45): 14점 + `is_bounce` 플래그
- 단기 과매도 반등 (RSI < 35): 10점
- RSI 불리시 다이버전스 (가격 저점 근처 but RSI 높음): 18점

**평균 회귀 신호 (Mean Reversion):**

- BB 하단 터치 (position ≤ 10%): 35점
- BB 하단 접근 (10-20%): 22점
- BB 하단 근접 (20-30%): 10점
- RSI 극과매도 (≤ 25): 30점
- RSI 강과매도 (25-32): 22점
- RSI 과매도 (32-40): 12점
- 거래량 감소 (최근 평균 70% 미만): 10점

**멀티 타임프레임 추세 확인:**

- 상위봉 EMA20 > EMA50: `bullish` → `mtf_confirmed=True`
- 상위봉 EMA20 < EMA50: `bearish` → `mtf_confirmed=False` (진입 기준 강화)

**전략 유형 자동 분류 (우선순위):**

| 유형 | 트리거 | scalping SL/TP | short SL/TP | mid SL/TP | long SL/TP |
|------|--------|---------------|-------------|-----------|------------|
| `oversold_bounce` | RSI ≤ 35 또는 반등+캔들 반전 | 1.0% / 2.5% | 2.5% / 7.0% | 5.0% / 15.0% | 10.0% / 30.0% |
| `golden_cross` | EMA20 상향 돌파 EMA50 | 0.8% / 2.0% | 4.0% / 10.0% | 6.0% / 20.0% | 12.0% / 36.0% |
| `macd_momentum` | MACD 골든크로스 또는 ADX ≥ 25 | 0.8% / 1.8% | 3.0% / 9.0% | 5.0% / 16.0% | 11.0% / 32.0% |
| `volume_breakout` | 거래량 급증 + MACD/EMA/RSI 보조 | 1.0% / 2.5% | 3.5% / 12.0% | 5.5% / 18.0% | 10.0% / 30.0% |
| `standard` | 위에 해당하지 않음 | 글로벌 설정 | 글로벌 설정 | 글로벌 설정 | 글로벌 설정 |

**거래량 필터 (스타일별 최소 일 거래대금):**

- scalping: KRW 50억 / USDT 350만 → 상위 10-15종목
- short: KRW 20억 / USDT 150만 → 상위 15-20종목
- mid: KRW 5억 / USDT 35만 → 상위 20-25종목
- long: KRW 1억 / USDT 7만 → 전체 스캔

**특이사항:**
- 스타일별 가중치 예시 (scalping: RSI 0.4, EMA 0.5, MACD 1.6, 거래량 1.5 / long: RSI 1.6, EMA 1.8, MACD 0.5, 거래량 0.5)
- 급등 감지 (거래량 3배+ & 3봉 가격 3%+ 상승) 시 별도 오버라이드 로직 적용

---

### 1.2 AI 진입 신뢰도 검증 (TODO 1)

**위치:** [backend/app/services/auto_trade/ai_analyst.py:204-256](../backend/app/services/auto_trade/ai_analyst.py#L204)

**분류:** 매매 진입 / AI 보조

**목적:** 스캐너 신호(점수, 전략 유형, RSI, 신호)를 AI에 전달해 진입 신뢰도를 최종 검증. 신뢰도가 낮으면 진입 차단, 높으면 포지션 크기 증가

**출력:**
```python
{
  "enter": bool,
  "confidence": int,          # 50-95
  "size_multiplier": float,   # confidence ≥90 → 1.2, ≥80 → 1.1, else 1.0
  "reason": str
}
```

**캐시:** 10분 (종목당 점수·전략 조합 기준)
**폴백:** confidence 70, enter=True (AI 실패 시 봇 정상 진행 보장)
**지원 프로바이더:** Ollama / Groq / Claude (claude-haiku-4-5-20251001) / OpenAI / Gemini

---

### 1.3 DB 전략 조건 평가 (TODO 9)

**위치:** [backend/app/services/auto_trade/bot.py:1087-1175](../backend/app/services/auto_trade/bot.py#L1087)

**분류:** 매매 진입 / 커스텀 조건식

**목적:** 사용자가 Strategy Builder 또는 API로 저장한 JSON `entry_conditions`/`exit_conditions`을 실시간으로 평가하여 스캔 결과와 병합

**동작:**
- DB 전략 `is_active=True`만 로드 (5분 캐시)
- 매 사이클마다 종목별 entry_conditions 평가
- 조건식 지표의 max 기간 추출 후 충분한 봉 수 확보 (max 150, 최소 `max_period*2 + 50`)
- 평가 결과 True면 신규 후보에 추가
  - 점수: `min_score + 15` (스캔 점수와 경합 방지)
  - 신호: `"DB전략 진입: {전략명}"`
  - SL/TP: DB 전략의 risk 설정 우선

**지원 연산자:** `<`, `>`, `<=`, `>=`, `==`, `cross_above`, `cross_below`

---

### 1.4 선물 신호 분류 (Futures)

**위치:** [backend/app/services/auto_trade/scanner.py:832-942](../backend/app/services/auto_trade/scanner.py#L832)

**분류:** 매매 진입 / 선물 양방향

**목적:** Binance Futures USDT-M 종목 스캔으로 롱/숏 양방향 신호 감지 및 펀딩비 조정

**숏 신호 점수:**
- RSI 과매수 (> 70): 25점
- RSI 과열 (> 65): 12점
- EMA 데드크로스 (EMA20 하향 EMA50): 20점
- EMA 하락추세 (EMA20 < EMA50): 10점
- MACD 데드크로스: 20점
- MACD 약세 (MACD < Signal): 8점
- 거래량 감소 (vol_ratio < 0.7): 8점

**펀딩비 조정:**
- `funding_rate > 0.1%`: 롱 점수 -10
- `funding_rate < -0.1%`: 숏 점수 -10

**방향 선택:** 숏 점수 > 롱 점수 AND 숏 점수 ≥ 40 → `side="short"`, 그 외 → `side="long"`

---

## 2. 청산 알고리즘 (Exit Strategies)

### 2.1 손절 / 익절 (기본 리스크 관리)

**위치:** [backend/app/services/risk/manager.py:15-71](../backend/app/services/risk/manager.py#L15)

**진입가 기반 계산:**

```python
# Long
stop_loss_price   = entry_price × (1 - stop_loss_pct / 100)
take_profit_price = entry_price × (1 + take_profit_pct / 100)

# Short
stop_loss_price   = entry_price × (1 + stop_loss_pct / 100)
take_profit_price = entry_price × (1 - take_profit_pct / 100)
```

**`check_exit` 판정:**
- Long: 현재가 ≤ SL → `stop_loss` / 현재가 ≥ TP → `take_profit`
- Short: 현재가 ≥ SL → `stop_loss` / 현재가 ≤ TP → `take_profit`

**기본값:**
```python
{
  "stop_loss_pct": 1.5,
  "take_profit_pct": 6.0,
  "trailing_stop": True,
  "trailing_pct": 1.0,
  "max_daily_loss_pct": 3.0
}
```

---

### 2.2 트레일링 스탑

**위치:** WS 처리 [backend/app/services/auto_trade/bot.py:741-763](../backend/app/services/auto_trade/bot.py#L741), REST 폴링 [backend/app/services/auto_trade/bot.py:617-653](../backend/app/services/auto_trade/bot.py#L617)

**활성화 조건:** `pnl_pct ≥ trailing_activate_pct`

**스타일별 파라미터:**

| 스타일 | 활성화 임계 | 트레일 폭 |
|--------|------------|----------|
| scalping | 1.5% | 0.8% |
| short | 4.0% | 2.0% |
| mid | 10.0% | 5.0% |
| long | 20.0% | 10.0% |

---

### 2.3 AI 청산 타이밍 보조 (TODO 4)

**위치:** [backend/app/services/auto_trade/ai_analyst.py:438-492](../backend/app/services/auto_trade/ai_analyst.py#L438)

**목적:** 이익 중인 포지션의 추가 수익 여부를 AI가 판단. 손절선까지 여유가 충분할 때만 발동 (손익비 보장)

**출력:** `action: "hold" | "tighten_sl" | "close_now"`

**발동 조건:**
- `pnl_pct ≥ max(스타일별_최소_수익률, sl_pct)`
- `trailing_active=False`
- `ai_exit_assist=True`

**스타일별 최소 수익률 임계값:** scalping 0.8% / short 1.5% / mid 3.0% / long 5.0%

**캐시:** 5분 / **폴백:** `action="hold"`

> **특이사항:** 최근 fix(3e5ced1) — 손절% 미만 수익에서 AI 조기 청산을 차단하여 손익비를 보장. [bot.py:1286-1287](../backend/app/services/auto_trade/bot.py#L1286)

---

### 2.4 신호 약화 시 SL 상향 보호

**위치:** [backend/app/services/auto_trade/bot.py:1266-1278](../backend/app/services/auto_trade/bot.py#L1266)

**목적:** 새 스캔 사이클에서 신호 점수가 급락하면 이익이 충분한 경우 SL을 위로 당겨 최소 수익 확보

**조건:**
- `new_score < min_score`
- `pnl_pct ≥ protect_pct × 2`
- `trailing_active=False`

**SL 상향:** `new_sl = avg_price × (1 + (pnl_pct - protect_pct) / 100)`

**스타일별 보호 폭:** scalping 0.3% / short 0.5% / mid 1.0% / long 2.0%

---

### 2.5 부분 청산 (TODO 22)

**위치:** [backend/app/services/auto_trade/bot.py:1900-1973](../backend/app/services/auto_trade/bot.py#L1900)

**발동:** `partial_exit_enabled=True` AND 현재가 ≥ `avg_price + (tp_price - avg_price) × partial_exit_trigger_pct` (기본 60% 지점)

**청산량:** `total_amount × partial_exit_ratio` (기본 40%)

**후처리:**
1. 부분 청산 손익을 일일 PnL에 누적
2. SL 상향: `avg_price × 1.005` (원금 보호)
3. 트레일링 활성화 + TP 상한 제거
4. `partial_exited=True` 플래그로 중복 방지

---

## 3. 보조 지표 계산 (Technical Indicators)

### 3.1 지표 계산 엔진

**위치:** [backend/app/services/indicator/engine.py:27-231](../backend/app/services/indicator/engine.py#L27)

**목적:** pandas-ta 기반 모든 지표를 JSON 설정으로 동적 계산. 전략별 커스텀 조건식 평가 지원

**지원 지표:**

| 지표 | 함수 | 파라미터 | 기본값 |
|------|------|----------|--------|
| RSI | `ta.rsi` | length | 14 |
| EMA | `ta.ema` | length | 20, 50 |
| SMA | `ta.sma` | length | 20, 50 |
| MACD | `ta.macd` | fast, slow, signal | 12, 26, 9 |
| BB | `ta.bbands` | length, std | 20, 2.0 |
| BB_UPPER / BB_LOWER / BB_WIDTH | (위) | length, std | — |
| STOCH | `ta.stoch` | k, d, smooth_k | 14, 3, 3 |
| ATR | `ta.atr` | length | 14 |
| VOLUME_SMA | `ta.sma(volume)` | length | 20 |
| EMA_CROSS | 커스텀 | fast, slow | — |

**조건 평가 (`evaluate_condition`):**

상태 연산자:
```json
{"indicator": "RSI", "params": {"length": 14}, "operator": "<", "value": 35}
```

크로스 연산자:
```json
{"indicator": "EMA_CROSS", "params": {"fast": 9, "slow": 21}, "operator": "cross_above"}
{"indicator": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}, "operator": "cross_above", "value": 0}
{"indicator": "BB_LOWER", "params": {"length": 20, "std": 2.0}, "operator": "cross_above"}
```

**조건 조합 주의:** 크로스 조건과 상태 조건을 동일 리스트에 섞으면 거의 발생 불가능 (동시성 요구). 별도 전략으로 분리할 것.

---

## 4. 리스크 관리 (Risk Management)

### 4.1 포트폴리오 리스크 관리자

**위치:** [backend/app/services/risk/manager.py:86-207](../backend/app/services/risk/manager.py#L86)

**4.1.1 일일 손실 한도**

```python
max_loss_krw = total_value_krw × max_daily_loss_pct / 100
if daily_pnl_krw < -max_loss_krw:
    # 신규 진입 차단
```

기본값: `max_daily_loss_pct = 5.0%`, KST 자정 리셋

**4.1.2 포트폴리오 최대 노출**

```python
exposure_pct = total_invested_krw / total_value_krw × 100
if exposure_pct >= max_exposure_pct:
    # 신규 진입 차단
```

기본값: `max_exposure_pct = 80.0%`

**4.1.3 종목 간 상관계수 필터 (TODO 10)**

위치: [backend/app/services/risk/manager.py:151-206](../backend/app/services/risk/manager.py#L151)

수익률 시계열의 피어슨 상관계수가 `threshold`(기본 0.85)를 넘으면 진입 차단. 데이터 < 10봉이거나 분산 0이면 스킵.

---

### 4.2 Kelly Criterion 기반 투자 비중

**위치:** [backend/app/services/risk/manager.py:233-256](../backend/app/services/risk/manager.py#L233)

```
Kelly fraction = win_rate - (1 - win_rate) / (avg_win / avg_loss)
Half-Kelly = Kelly / 2
```

**상한:** `max_fraction = 0.25`
**적용 시점:** 최근 30건 중 ≥ 10건일 때

---

### 4.3 퀀트 오버레이: 변동성 타깃 + 모멘텀 + 드로우다운 감속

**위치:** [backend/app/services/quant/optimizer.py](../backend/app/services/quant/optimizer.py), 스캐너 연동 [backend/app/services/auto_trade/scanner.py](../backend/app/services/auto_trade/scanner.py), 자동매매 sizing [backend/app/services/auto_trade/bot.py](../backend/app/services/auto_trade/bot.py), 백테스트 연동 [backend/app/services/backtest/engine.py](../backend/app/services/backtest/engine.py)

**목적:** 기존 기술지표 점수를 그대로 신뢰하지 않고, 추세 모멘텀과 최근 변동성을 반영해 진입 우선순위와 포지션 크기를 조정합니다. 수익률 극대화 시 흔히 발생하는 과최적화와 과도한 변동성 노출을 줄이는 것이 핵심입니다.

**참고한 연구 아이디어:**
- [Moskowitz, Ooi, Pedersen (2012), *Time Series Momentum*](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf): 1~12개월 수익률 지속성 기반 추세 추종 아이디어
- [Moreira, Muir (2017), *Volatility-Managed Portfolios*](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2928486_code1399128.pdf?abstractid=2659431&mirid=1): 변동성이 높을 때 노출을 줄이면 리스크 조정 성과가 개선될 수 있음
- [Brock, Lakonishok, LeBaron (1992), *Simple Technical Trading Rules*](https://econpapers.repec.org/RePEc%3Abla%3Ajfinan%3Av%3A47%3Ay%3A1992%3Ai%3A5%3Ap%3A1731-64): 이동평균/돌파 규칙의 통계적 검증
- [Kelly (1956), *A New Interpretation of Information Rate*](https://cir.nii.ac.jp/crid/1362262946085937664): 장기 성장률 기반 betting fraction, 실전 적용은 half-Kelly와 상한 필요

**신호 특징값:**
```python
momentum_20_pct     = close[-1] / close[-20] - 1
momentum_50_pct     = close[-1] / close[-50] - 1
realized_vol_pct    = std(최근 20봉 수익률)
atr_pct             = ATR(14) / 현재가
volatility_scalar   = target_vol_by_style / max(realized_vol, ATR*0.65)
quant_score         = 기존 점수 + 추세 점수 - 변동성 페널티
```

**스타일별 목표 봉 변동성:**
| 스타일 | target_vol_pct |
|--------|----------------|
| scalping | 0.65 |
| short | 1.25 |
| mid | 2.20 |
| long | 3.50 |

**포지션 비중:**
```python
score_mult = clamp(0.45 + quant_score / 100, 0.45, 1.45)
vol_mult   = clamp(volatility_scalar, 0.35, 1.60)
throttle   = drawdown_throttle(MDD, soft=8%, hard=20%)

position_pct = base_position_pct
             × score_mult
             × vol_mult
             × AI_confidence_multiplier
             × throttle
```

Kelly fraction이 계산되는 경우에는 Kelly를 비중 상한으로 사용합니다. 즉, 최근 실거래 성과가 낮으면 신호가 좋아도 포지션이 커지지 않습니다.

**진입 필터:**
- `final_entry_score = raw_score × 0.25 + quant_score × 0.30 + regime_fit × 0.15 + cost_adjusted_edge + historical_pf_bonus - vol_penalty`
- `edge_after_cost_pct = expected_edge_pct + historical_edge_pct - 왕복수수료 - 예상슬리피지`
- 기본값: `min_edge_after_cost_pct = 0.15`, `min_rank_score = 58`
- `effective_score = raw_score × 0.65 + quant_score × 0.35`
- 평균회귀/급등 오버라이드가 아닌 일반 진입에서 `quant_score < min_score - 12`이면 스킵
- 스캔 결과에는 `quant_score`, `expected_edge_pct`, `edge_after_cost_pct`, `volatility_scalar`, `atr_pct`, `momentum_20_pct`, `momentum_50_pct`가 포함됨

**전략/국면별 히스토리 보정:**
거래 로그를 `strategy_type + position_style + market_regime + strategy_mode + timeframe` 기준으로 우선 집계하고, 표본이 부족하면 `strategy_type` 단위로 폴백합니다.

```python
smoothed_win_rate = (wins + 2) / (trades + 4)
sample_confidence = min(1.0, trades / 30)
adjusted_expectancy = raw_expectancy * sample_confidence
```

**손실 허용액 기반 sizing:**
기본 quant 비중은 상한 후보로만 쓰고, 실제 주문 금액은 손절 시 잃을 금액을 먼저 정한 뒤 계산합니다.

```python
risk_budget = total_value * risk_per_trade_pct / 100
stop_distance_pct = max(sl_pct, atr_pct * 1.2, 0.5)
position_value = min(
    risk_budget / (stop_distance_pct / 100),
    total_value * quant_position_pct / 100,
    available_cash * 0.95,
    total_value * max_position_size_pct / 100,
    total_value * adjusted_kelly_fraction,
)
```

**ATR/R 기반 SL/TP:**
`dynamic_sl_tp_enabled=True`일 때 고정 SL/TP 대신 ATR 기반 손절폭과 R-multiple TP를 사용합니다.

| 스타일 | ATR 배수 | 최소 SL | 최대 SL | TP |
|--------|----------|---------|---------|----|
| scalping | 1.2 | 0.6% | 2.0% | 1.5R |
| short | 1.7 | 1.2% | 4.0% | 2.4R |
| mid | 2.4 | 3.0% | 8.0% | 2.8R |
| long | 3.0 | 6.0% | 15.0% | 3.0R |

**수익 상태 전환:**
- +1R 도달: SL을 본전권(`avg_price × 1.001`)으로 이동
- +2R 도달: TP 상한 제거 + trailing 활성화
- 피라미딩은 `breakeven_moved=True`, 1R 이상, `quant_score` 유지 조건에서만 허용
- 물타기는 `mean_reversion`/`oversold_bounce`에서만 허용하며, `quant_score >= 55`, 진입 점수 대비 90% 이상 유지, 상위봉 하락 가속 아님을 요구

---

### 4.4 성과 지표 계산

**위치:** [backend/app/services/risk/manager.py:281-376](../backend/app/services/risk/manager.py#L281)

| 지표 | 계산 |
|------|------|
| Sharpe Ratio | (평균 수익률 / 표준편차) × √252 |
| Sortino Ratio | (평균 수익률 / 하방편차) × √252 |
| Calmar Ratio | 연평균 수익률 / MDD |
| Profit Factor | 총 수익 / 총 손실 |
| Expectancy | (승률 × 평균 수익) - (패율 × 평균 손실) |
| Max Drawdown | (peak - trough) / peak × 100 |
| VaR 95 | 하위 5% 분위수 |
| Win Rate | 수익 거래 수 / 전체 거래 수 |

---

### 4.5 MDD 자동 거래 중단 (TODO 13)

**위치:** [backend/app/services/auto_trade/bot.py:787-797](../backend/app/services/auto_trade/bot.py#L787)

```python
if len(trade_log) >= 10:
    perf = calc_performance(trade_log)
    if perf["max_drawdown_pct"] >= mdd_limit_pct:
        self.stop()
```

기본값: `mdd_limit_pct = 20.0%`

---

## 5. 백테스트 엔진

### 5.1 기본 백테스트

**위치:** [backend/app/services/backtest/engine.py:61-163](../backend/app/services/backtest/engine.py#L61)

**진입 체결:**
```python
fill_price = current_price × (1 + slippage_pct/100)
amount = (capital × position_size_pct / 100) / fill_price
fee = amount × fill_price × fee_rate
capital -= amount × fill_price + fee
```

**청산 체결:**
```python
fill_price = current_price × (1 - slippage_pct/100)
gross = position["amount"] × fill_price
capital += gross - fee_exit
pnl_pct = pnl / (amount × entry_price) × 100
```

**출력:** trades, equity_curve, win_rate, total_pnl_pct, max_drawdown_pct, sharpe_ratio, profit_factor, max_consecutive_losses, indicator_snapshot

---

### 5.2 Walk-Forward 분석

**위치:** [backend/app/services/backtest/engine.py:165-180](../backend/app/services/backtest/engine.py#L165)

데이터를 `n_splits=5` 분할 후 각 구간 독립 백테스트 → 과최적화 여부 판단

---

### 5.3 몬테카를로 시뮬레이션

**위치:** [backend/app/services/backtest/engine.py:281-318](../backend/app/services/backtest/engine.py#L281)

실제 백테스트 거래 손익률을 부트스트랩으로 재표본추출해 100회 시뮬레이션. 출력: `mean_pnl_pct`, `std_pnl_pct`, `pnl_confidence_interval [5%, 95%]`, `mean_max_drawdown`, `robustness_score`

---

### 5.4 파라미터 최적화 (Grid Search)

**위치:** [backend/app/services/backtest/engine.py:320-378](../backend/app/services/backtest/engine.py#L320)

```python
param_ranges = {
  "stop_loss_pct": [1.0, 1.5, 2.0, 2.5],
  "take_profit_pct": [4.0, 5.0, 6.0, 7.0, 8.0],
  "position_size_pct": [5.0, 7.0, 10.0, 12.0]
}
# score = bounded_return + bounded_sharpe + profit_factor + win_rate
#         then penalize max_drawdown and too-few trades
```

최적화 결과에는 `walk_forward_diagnostics`가 포함되어 구간별 양수 수익 비율, 평균 구간 수익률, 구간 수익률 표준편차를 함께 확인할 수 있습니다.

---

## 6. AI 분석 모듈

### 6.1 시장 국면 감지 (TODO 2)

**규칙 기반 위치:** [backend/app/services/auto_trade/bot.py:898-960](../backend/app/services/auto_trade/bot.py#L898)
**AI 보완 위치:** [backend/app/services/auto_trade/ai_analyst.py:314-378](../backend/app/services/auto_trade/ai_analyst.py#L314)

| 국면 | 조건 | 추천 스타일 | `min_score_delta` |
|------|------|------------|-------------------|
| volatile (과열) | RSI > 78 또는 (거래량 2.5×+ & 변동성 3%+ in 5봉) | scalping | -5 |
| trending (강한 상승) | 20봉 +10% 초과 & RSI ≥ 60 | mid | +5 |
| trending (상승) | 20봉 +5~10% & RSI ≥ 50 | short | +3 |
| downtrend (하락) | 20봉 -8% 이상 | long (반등 대기) | +5 |
| ranging (약세 횡보) | 20봉 -3~0% & RSI < 45 | short | +3 |
| ranging (중립) | 기타 | short | 0 |

**`strategy_mode`:** ADX < 20 → `mean_reversion` / ADX ≥ 20 → `momentum`

**AI 캐시:** 15분 (BTC 가격 1% 단위 버킷)

---

### 6.2 손절 후 자기 분석 (TODO 3)

**위치:** [backend/app/services/auto_trade/ai_analyst.py:384-432](../backend/app/services/auto_trade/ai_analyst.py#L384)

**발동:** 연속 손절 3회마다 1회

**출력:**
```python
{
  "issue": "SL_TOO_TIGHT" | "WRONG_STRATEGY" | "BAD_TIMING" | "MARKET_CONDITION",
  "sl_pct_delta": float (0 ~ 2.0),
  "min_score_delta": int (0 ~ 10),
  "reason": str
}
```

---

### 6.3 포지션별 매매 스타일 선택

**규칙 기반 위치:** [backend/app/services/auto_trade/bot.py:1525-1550](../backend/app/services/auto_trade/bot.py#L1525)
**AI 보완 위치:** [backend/app/services/auto_trade/ai_analyst.py:262-308](../backend/app/services/auto_trade/ai_analyst.py#L262)

```python
def _choose_style_rules(candidate):
    rsi, signals, score = candidate["rsi"], candidate["signals"], candidate["score"]
    if rsi > 75 or rsi < 28:
        return "scalping"            # 극단 RSI → 빠른 반전
    strong = sum(1 for s in signals if any(kw in s for kw in
        ("MACD 골든크로스", "거래량 급증", "골든크로스", "강한 상승추세")))
    if strong >= 2 and score >= 70:
        return "mid"                 # 강한 모멘텀 → 추세 추종
    if strong >= 1 and score >= 60:
        return "short"               # 단일 강신호 → 단타
    return global_style              # 약신호 → 기본
```

---

### 6.4 전략 자동 생성 (API)

**위치:** [backend/app/api/auto_strategy.py:214-539](../backend/app/api/auto_strategy.py#L214)

**프로세스:**
1. 시장 데이터 200봉 수집
2. 기술 지표 요약 생성 (RSI, EMA, MACD, BB, Stochastic, 거래량)
3. 시스템 프롬프트 + 마켓 요약으로 LLM 호출
4. JSON 응답 파싱 및 검증
5. DB에 Strategy 저장

**LLM 가이드라인:**
- 진입 우선순위: ① RSI 과매도+확인 신호 ② EMA 골든크로스 ③ MACD 다이버전스+거래량 ④ BB 스퀴즈 돌파
- 익절 4-8% (손절의 2-3배)
- 손절 1.5-2.5%, 포지션 5-10%, 일일 손실 3-5%
- 크로스/상태 조건 혼합 금지

---

## 7. 자동 매매 봇 (AutoTradeBot)

### 7.1 매매 스타일 프리셋

**위치:** [backend/app/services/auto_trade/bot.py:181-273](../backend/app/services/auto_trade/bot.py#L181)

| 스타일 | TF | 스캔 간격 | SL/TP | min_score | max_pos | 물타기 | 추매 | 트레일 활성/폭 |
|--------|------|---------|-------|----------|--------|------|-----|--------------|
| scalping | 5m | 1분 | 1.0% / 2.0% | 55 | 5 | No | No | 1.5% / 0.8% |
| short | 1h | 5분 | 2.5% / 6.0% | 55 | 4 | Yes (3%, 2회) | No | 4.0% / 2.0% |
| mid | 4h | 15분 | 6.0% / 18.0% | 50 | 3 | Yes (7%, 2회) | No | 10.0% / 5.0% |
| long | 1d | 60분 | 12.0% / 35.0% | 45 | 3 | Yes (15%, 2회) | No | 20.0% / 10.0% |

### 7.2 투자 성향 프로파일

| 성향 | position_size | min_score Δ | max_pos Δ | SL × | TP × | 물타기 | 추매 |
|------|--|--|--|--|--|--|--|
| conservative | 60% | +10 | -1 | 0.7 | 0.8 | No | No |
| balanced | 100% | 0 | 0 | 1.0 | 1.0 | 기본 | 기본 |
| aggressive | 150% | -10 | +2 | 1.5 | 1.5 | Yes | Yes |

---

### 7.3 매 사이클 실행 흐름

**위치:** [backend/app/services/auto_trade/bot.py:782-875](../backend/app/services/auto_trade/bot.py#L782)

```
1. MDD 자동 중단 체크 (trade_log ≥ 10 & max_dd ≥ mdd_limit_pct → stop)
2. 시장 국면 감지 (_run_regime_detection) — 규칙+AI
3. 시장 스캔 (scan_market) — 거래량 상위 동적 발굴
4. DB 전략 평가 (_eval_db_strategies) — entry_conditions 충족 종목 병합
5. 기존 포지션 관리 (_check_positions)
   ├─ 부분 청산 체크 (TP 60% 도달)
   ├─ 전략 재평가 / 교체
   ├─ AI 청산 보조 (이익 중일 때)
   └─ 자동 물타기 / 추매 / 피라미딩
6. 신규 진입 (_enter_from_scan)
   ├─ 급등 오버라이드 (vol ≥3×, change ≥3%)
   ├─ 멀티 타임프레임 페널티
   ├─ 전략별 승률 게이팅 (≥3회 & 승률 <30% → 스킵)
   ├─ 상관계수 필터링
   ├─ AI 진입 검증 (confidence < 65 → 차단)
   └─ 포지션별 스타일 결정 + 진입
```

**스케줄링:**
```python
_scheduler.add_job(_cycle, IntervalTrigger(minutes=scan_interval_min))
```

기본 신규 진입 스캔 주기:

| 스타일 | 기본 주기 |
|---|---:|
| 초단타 | 1분 |
| 단타 | 1분 |
| 중장기 | 5분 |
| 장기 | 15분 |

---

### 7.4 실시간 가격 모니터

**위치:** [backend/app/services/auto_trade/bot.py:530-585](../backend/app/services/auto_trade/bot.py#L530)

REST 폴링 1초 간격으로 매 사이클 사이 SL/TP 즉시 체결.

```python
while self._running:
    for symbol in self._positions:
        price = (await connector.fetch_ticker(symbol))["last"]
        if price <= pos["stop_loss_price"]:
            await self._close_position(symbol, price, "stop_loss")
        elif not trailing_active and price >= pos["take_profit_price"]:
            await self._close_position(symbol, price, "take_profit")
        if trailing_stop and pnl_pct >= trailing_activate_pct:
            pos["trailing_active"] = True
            pos["take_profit_price"] = inf
        if trailing_active:
            trail_price = highest_price × (1 - trailing_pct / 100)
            if price <= trail_price:
                await self._close_position(symbol, price, "trailing_stop")
    await asyncio.sleep(1)
```

---

### 7.5 물타기 / 추매 / 피라미딩

**물타기 (Average Down)** — [backend/app/services/auto_trade/bot.py:1659-1691](../backend/app/services/auto_trade/bot.py#L1659)

```python
drop_pct = (avg_price - current_price) / avg_price × 100
threshold = settings["avg_down_threshold_pct"]   # 기본 3%

# 점수 붕괴 방어: score < min_score × 0.6 → 차단
# 반등 신호 ("과매도", "반등", "골든크로스", "BB 하단") + score≥min_score
#   → 임계값 절반에서 진입
# 그 외 → score ≥ min_score × 0.8 & drop_pct ≥ threshold
```

**추매 (Add)** — [backend/app/services/auto_trade/bot.py:1693-1717](../backend/app/services/auto_trade/bot.py#L1693)

```python
rise_pct = (current_price - avg_price) / avg_price × 100
# 모멘텀 신호 ("MACD 골든크로스", "거래량 급증", "골든크로스", "상승추세")
#   + score ≥ min_score+5 → 임계값 절반에서 추매
```

**피라미딩 (Pyramid)** — [backend/app/services/auto_trade/bot.py:1719-1745](../backend/app/services/auto_trade/bot.py#L1719)

```python
# 복합 강신호 (2개+) + score≥min_score+10 → 임계값 60%
# 단일 강신호 + score≥min_score+5    → 임계값 80%
```

**추가 매수 실행** — [backend/app/services/auto_trade/bot.py:1749-1796](../backend/app/services/auto_trade/bot.py#L1749)

- ratio: 물타기 0.5 / 추매 0.25
- 평단가 재계산: `(avg_price × total_amount + price × amount) / (total_amount + amount)`
- 물타기만 SL/TP를 새 평단 기준으로 재설정
- `entries[]` 리스트에 다중 진입 추적

---

### 7.6 선물 포지션 관리

**위치:** 스캔 [backend/app/services/auto_trade/bot.py:850-875](../backend/app/services/auto_trade/bot.py#L850)

- Binance Futures USDT-M 전용
- 롱/숏 양방향
- 레버리지 1~20배, 마진 모드 cross/isolated
- 펀딩비 모니터링 (8시간마다)
- `contracts = (usdt_amount × leverage) / mark_price`
- 청산 타입: stop_loss / take_profit / liquidation_warning (청산가 5% 이내)

---

## 8. 핵심 개선 사항 (최근 fix)

| 커밋 | 내용 | 위치 |
|------|------|------|
| 3e5ced1 | AI 청산 손익비 보장 — 손절% 미만 수익에서 AI 조기 청산 차단 | [bot.py:1286](../backend/app/services/auto_trade/bot.py#L1286) |
| 8d06f0b | DB 전략 진입 지연 — 스캔/DB 점수 충돌 시 max로 통합 | [bot.py:824-837](../backend/app/services/auto_trade/bot.py#L824) |
| — | 국면별 스타일 자동 조정 (규칙+AI) | [bot.py:1049-1063](../backend/app/services/auto_trade/bot.py#L1049) |
| — | 급등 오버라이드 — min_score & AI threshold 50으로 완화 | [bot.py:1399-1520](../backend/app/services/auto_trade/bot.py#L1399) |
| — | Kelly Criterion 적용 (최근 30건 ≥10건) | [bot.py:1570-1585](../backend/app/services/auto_trade/bot.py#L1570) |

---

## 9. TODO 구현 현황

| TODO | 항목 | 상태 |
|------|------|------|
| 1 | AI 진입 신뢰도 검증 | ✅ |
| 2 | 시장 국면 감지 | ✅ (규칙 + AI 하이브리드) |
| 3 | 손절 후 자기 분석 | ✅ |
| 4 | AI 청산 타이밍 | ✅ |
| 8 | 고급 캔들 패턴 (삼병사 등) | ✅ |
| 9 | DB 전략 조건 평가 | ✅ |
| 10 | 포트폴리오 상관관계 | ✅ |
| 13 | MDD 자동 중단 | ✅ |
| 22 | 부분 청산 | ✅ |
| 25 | 평균 회귀 전략 모드 | ✅ |
| 26 | 퀀트 오버레이 sizing / 견고성 최적화 | ✅ |
| 27 | 비용 차감 기대값 기반 진입 랭킹 | ✅ |
| 28 | 손실 허용액 기반 포지션 sizing | ✅ |
| 29 | ATR/R 기반 동적 SL/TP + 1R/2R 상태 전환 | ✅ |

---

## 10. 결론

CoAI 트레이딩 알고리즘의 큰 그림:

1. **진입:** 스캐너 → 지표 점수화 → 5가지 전략 자동 분류 → AI 신뢰도 검증
2. **청산:** 기본 SL/TP → 트레일링 스탑 → AI 타이밍 → 신호 약화 보호 → 부분 청산
3. **지표:** JSON 설정 기반 동적 계산 (RSI, EMA, MACD, BB, STOCH, ATR 등)
4. **리스크:** 개별 (SL/TP) + 포트폴리오 (일일 손실, 노출, 상관계수, MDD)
5. **분석:** 규칙 기반 + AI 하이브리드 (국면, 진입, 청산, 스타일, 손실 회고)
6. **백테스트:** 기본 → Walk-Forward → 몬테카를로 → 그리드 서치
7. **자동 매매:** 주기적 스캔 + 실시간 모니터 + 물타기/추매/피라미딩

모든 알고리즘은 거래소 중립적이며 (Upbit / Binance / Bybit), 현물과 선물을 모두 지원합니다.
