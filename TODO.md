# CoAI - 구현 TODO

`[x]` 완료 / `[ ]` 미구현
미구현 항목은 각 **TODO 번호**의 상세 섹션을 참조한다.

---

## 요약 테이블

### 전략 (Strategy)

| 항목 | 상태 | 상세 |
|------|------|------|
| 기본 4전략 (oversold_bounce / golden_cross / macd_momentum / volume_breakout) | [x] | `scanner.py:_score()` |
| 스타일별 지표 가중치 (scalping=MACD/거래량, long=RSI/EMA) | [x] | `scanner.py:_score()` |
| 스타일별 전략 SL/TP 차등 | [x] | `bot.py:AutoTradeBot` |
| AI 전략 자동 생성 (Ollama/Groq/Claude/Gemini) | [x] | `ai_analyst.py` |
| RSI 저점 반등 감지 | [x] | `scanner.py:_detect_rsi_bounce()` |
| 캔들 패턴 (망치형·인걸핑·피어싱·도지·모닝스타) | [x] | `scanner.py:_detect_candle_patterns()` |
| 급등 오버라이드 진입 (거래량 3배+ & 가격 3%+) | [x] | `scanner.py:_score()` |
| 전략 빌더 ↔ 자동매매 봇 연동 | [x] | `bot.py`, `strategy/engine.py` |
| 멀티 타임프레임 확인 (1h 신호 + 4h 추세) | [x] | `scanner.py:scan_market()` |
| 고급 캔들 패턴 (삼병사·역H&S·이중바닥·볼린저 반등) | [x] | `scanner.py:_detect_advanced_patterns()` |
| 동적 종목 발굴 (전체 업비트 스캔, 30분 캐시) | [x] | `scanner.py:_fetch_dynamic_symbols()` |
| 자가 학습 전략 최적화 | [ ] | → **TODO 7** |
| 다중 거래소 지원 (Binance, Bybit) | [x] | `connector.py`, `scanner.py`, `bot.py` |

### 포지션 (Position)

| 항목 | 상태 | 상세 |
|------|------|------|
| 다중 진입 (물타기 / 추매, 최대 2회) | [x] | `bot.py:AutoTradeBot` |
| 포지션별 AI 스타일 자동 선택 | [x] | `ai_analyst.py:choose_position_style()` |
| 트레일링 스탑 (고점 대비 N% 하락 시 청산) | [x] | `bot.py:AutoTradeBot` |
| 포지션 보유 중 전략 재평가·교체 | [x] | `bot.py:AutoTradeBot` |
| 신호 약화 시 SL 자동 상향 (pnl ≥ protect_pct*2) | [x] | `bot.py:AutoTradeBot` |
| 포트폴리오 최대 노출 한도 (총 자산 80%) | [x] | `risk/manager.py:RiskManager` |
| 포트폴리오 상관관계 체크 | [ ] | → **TODO 10** |
| 포지션 비중 동적 조절 (Kelly Criterion) | [ ] | → **TODO 11** |
| 피라미딩 (수익 구간 단계별 추가 진입) | [ ] | → **TODO 12** |

### 리스크 관리 (Risk Management)

| 항목 | 상태 | 상세 |
|------|------|------|
| 개별 포지션 SL/TP | [x] | `bot.py:AutoTradeBot` |
| 전략×스타일별 SL/TP 차등 (4×4) | [x] | `bot.py:AutoTradeBot` |
| 일일 최대 손실 한도 (총 자산 5%) | [x] | `risk/manager.py:RiskManager` |
| 포트폴리오 최대 노출 한도 (80%) | [x] | `risk/manager.py:RiskManager` |
| 연속 손절 AI 자기 분석 (3회 연속 시 발동) | [x] | `ai_analyst.py:analyze_losses()` |
| VaR (Value at Risk, 95% 신뢰구간 1일) | [ ] | → **TODO 13** |
| 포지션 간 상관계수 리스크 | [ ] | → **TODO 10** (상관관계 체크와 통합) |
| 최대 낙폭(MDD) 기준 자동 거래 중단 | [ ] | → **TODO 13** |

### 성과 분석 (Performance Analysis)

| 항목 | 상태 | 상세 |
|------|------|------|
| 승률·평균 손익·최고/최저 거래 | [x] | `risk/manager.py:calc_performance()` |
| 전략별 승률 추적 (30% 미만 차단) | [x] | `bot.py:AutoTradeBot` |
| 샤프·소르티노·칼마·프로핏팩터·기대값·MDD | [x] | `risk/manager.py:calc_performance()` |
| 일일 PnL 추적 + 게이지 시각화 | [x] | `auto_bot.py:get_trade_stats()` |
| 알파 / 베타 (BTC 벤치마크 대비) | [ ] | → **TODO 14** |
| 정보 비율 (Information Ratio) | [ ] | → **TODO 14** |
| 월별 / 전략별 손익 히트맵 | [ ] | → **TODO 15** |
| 디스코드 실시간 알림 | [ ] | → **TODO 16** |
| 성과 리포트 PDF 내보내기 | [ ] | → **TODO 17** |

### AI 기능 (AI Features)

| 항목 | 상태 | 상세 |
|------|------|------|
| 진입 확인 (confidence < 65 차단) | [x] | `ai_analyst.py:check_entry()` |
| 시장 국면 감지 (BTC OHLCV, 15분 캐시) | [x] | `ai_analyst.py:detect_regime()` |
| 손절 자기 분석 (연속 3회 시 발동) | [x] | `ai_analyst.py:analyze_losses()` |
| 청산 타이밍 보조 (hold/close/tighten) | [x] | `ai_analyst.py:check_exit()` |
| 포지션별 스타일 자동 선택 | [x] | `ai_analyst.py:choose_position_style()` |
| AI 설정 UI (프로바이더/모델/키) | [x] | `api/ai_config.py`, `user_ai_config.py` |
| 자가 학습 전략 최적화 | [ ] | → **TODO 7** |
| 멀티 에이전트 시스템 | [ ] | → **TODO 18** |

### 바이낸스 선물거래 (Binance Futures)

| 항목 | 상태 | 상세 |
|------|------|------|
| Binance Futures CCXT 커넥터 | [x] | `connector.py:BinanceFuturesConnector` |
| 레버리지 설정 (포지션별, 기본 5x) | [x] | `bot.py:_open_futures_position()` |
| 마진 모드 선택 (Cross / Isolated) | [x] | `bot.py:_open_futures_position()` |
| 청산가(Liquidation Price) 계산 및 모니터링 | [x] | `connector.py:FuturesPaperBroker`, `bot.py:_check_single_futures_position()` |
| 펀딩비(Funding Rate) 모니터링 | [x] | `bot.py:_check_funding_rates()` |
| 롱/숏 양방향 포지션 관리 | [x] | `scanner.py:scan_futures_market()`, `bot.py:_cycle_futures()` |
| 선물 전용 심볼 스캔 (USDT 페어) | [x] | `scanner.py:FUTURES_SYMBOLS`, `scan_futures_market()` |
| Binance Futures Testnet 지원 | [x] | `config.py:BINANCE_FUTURES_TESTNET`, `connector.py:set_sandbox_mode()` |
| 선물 거래 UI (레버리지·마진모드 설정) | [x] | `AutoTradePanel.tsx:FuturesPositionCard` |

### UI / UX

| 항목 | 상태 | 상세 |
|------|------|------|
| 전문 용어 툴팁 (RSI·HTF·마진모드 등) | [x] | `Tooltip.tsx` — AutoTradePanel, PositionDetailModal |
| 커스텀 확인 모달 (confirm() 전면 교체) | [x] | `ConfirmModal.tsx` — 전략삭제·봇중단·포지션청산·계정삭제 |
| 모의/실거래 전환 토글 (계좌·잔고 검증) | [x] | `AutoTradePanel.tsx:LiveSwitchModal` |
| 설정 모달 스크롤 레이아웃 수정 | [x] | `SettingsModal` flex 레이아웃 (선물모드 확장 시 정상 스크롤) |

### 인프라 / 운영

| 항목 | 상태 | 상세 |
|------|------|------|
| 모의거래 (Paper Trading) | [x] | `bot.py:AutoTradeBot` |
| Walk-Forward 백테스트 (슬리피지 0.05%) | [x] | `backtest/engine.py` |
| GitHub 배포 (main / develop) | [x] | |
| 로컬 실행 (단일 서버, `start.sh`) | [x] | |
| 거래소 연결 끊김 재시도 (WS 5초) | [x] | `exchange/connector.py` |
| 서버 상시 구동 (클라우드 배포) | [ ] | → **TODO 19** |
| 봇 재시작 자동 복구 | [ ] | → **TODO 20** |

---

## [ ] TODO 7. 자가 학습 전략 최적화

**수정 파일**
- `backend/app/services/auto_trade/bot.py` — 청산 후 `_record_signal_performance()` 호출
- `backend/app/services/auto_trade/scanner.py` — `_score()` 반환값에 `signals_key` 해시 추가
- `backend/app/services/auto_trade/ai_analyst.py` — `optimize_weights()` 함수 신규 추가
- `backend/app/models/` — `SignalPerformance` 모델 신규 추가
- `backend/app/core/database.py` — 마이그레이션 반영

**7-1. DB 테이블 추가**

`backend/app/models/signal_performance.py` 신규 생성:
```python
class SignalPerformance(Base):
    __tablename__ = "signal_performance"
    id           = Column(Integer, primary_key=True)
    signals_key  = Column(String(128), index=True)   # "RSI과매도+망치형+MACD반등" SHA256 앞 16자
    strategy_type= Column(String(64))                # oversold_bounce / macd_momentum / ...
    style        = Column(String(16))                # scalping / short / mid / long
    win_count    = Column(Integer, default=0)
    loss_count   = Column(Integer, default=0)
    total_pnl_pct= Column(Float, default=0.0)
    avg_hold_secs= Column(Float, default=0.0)
    updated_at   = Column(DateTime, default=func.now(), onupdate=func.now())
```

**7-2. `scanner.py:_score()` 수정**

반환 dict에 `"signals_key"` 필드 추가:
```python
import hashlib
signals_text = "+".join(sorted(signals))           # signals 리스트는 이미 존재
signals_key  = hashlib.sha256(signals_text.encode()).hexdigest()[:16]
return { ..., "signals_key": signals_key }
```

**7-3. `bot.py` 청산 처리 부분 수정**

포지션 청산 직후 `_record_signal_performance()` 호출:
```python
async def _record_signal_performance(self, pos: dict, pnl_pct: float, db):
    key = pos.get("signals_key", "unknown")
    row = db.query(SignalPerformance).filter_by(
        signals_key=key, strategy_type=pos["strategy"], style=pos["style"]
    ).first()
    if not row:
        row = SignalPerformance(signals_key=key, ...)
        db.add(row)
    if pnl_pct > 0: row.win_count  += 1
    else:           row.loss_count += 1
    row.total_pnl_pct += pnl_pct
    db.commit()
```

**7-4. `ai_analyst.py` — `optimize_weights()` 신규 추가**

```python
async def optimize_weights(db, min_samples: int = 10) -> dict:
    """
    신호별 최근 성과를 조회해 가중치 조정 제안을 반환한다.
    반환: {"rsi_bounce": +0.2, "macd_cross": -0.1, ...}
    LLM에 signal_performance 상위/하위 5개를 전달 → JSON 파싱.
    조정 폭 제한: 원본 대비 ±50%.
    최소 샘플 10건 미만인 key는 제외.
    """
```

호출 시점: `bot.py`의 청산 누적 10건마다 `optimize_weights()` 실행 후 `STYLE_SCORE_WEIGHTS` 런타임 갱신.

**7-5. 안전장치**
- 가중치 조정 폭: 원본 대비 ±50% 이내로 클리핑
- 최소 샘플: `win_count + loss_count < 10`인 key 제외
- 30일마다 가중치 부분 리셋: `bot.py`의 일일 루프에서 `last_weight_reset` 타임스탬프 확인

**완료 기준**
- [ ] `signal_performance` 테이블이 청산마다 upsert됨
- [ ] `optimize_weights()` 가 10건 누적 시 호출되고 결과가 로그에 출력됨
- [ ] 가중치 조정 후 다음 `_score()` 호출에 반영됨

---

## [ ] TODO 9. 다중 거래소 지원

**수정 파일**
- `backend/app/services/exchange/connector.py` — 거래소별 분기 처리
- `backend/app/models/exchange_account.py` — `exchange` 필드 확인 (이미 존재 예상)
- `backend/app/api/exchange_accounts.py` — Binance/Bybit 계정 등록 UI 지원

**구현 내용**

`connector.py` 의 `ExchangeConnector.__init__()` 에서 `exchange` 파라미터로 분기:
```python
if self.exchange == "upbit":
    self.client = pyupbit.Upbit(access, secret)
elif self.exchange in ("binance", "bybit"):
    import ccxt
    self.client = ccxt.binance({"apiKey": access, "secret": secret})
    # 또는 ccxt.bybit(...)
```

공통 인터페이스 메서드 유지: `get_balance()`, `buy_market()`, `sell_market()`, `get_ohlcv()`
각 거래소 응답 포맷 → 내부 표준 포맷으로 정규화하는 어댑터 함수 작성.

**완료 기준**
- [ ] Binance 계정으로 `get_balance()` 호출 성공
- [ ] Binance `get_ohlcv("BTC/USDT", "1h")` 가 upbit와 동일한 DataFrame 구조 반환
- [ ] 봇 시작 시 거래소 종류에 따라 자동으로 커넥터 선택

---

## [ ] TODO 10. 포트폴리오 상관관계 체크

**수정 파일**
- `backend/app/services/risk/manager.py` — `PortfolioRiskManager` 클래스에 메서드 추가
- `backend/app/services/auto_trade/bot.py` — 진입 직전 상관관계 체크 호출

**구현 내용**

`risk/manager.py:PortfolioRiskManager` 에 메서드 추가:
```python
def check_correlation(
    self,
    new_symbol: str,
    open_positions: list[str],   # 현재 보유 종목 리스트 e.g. ["KRW-BTC", "KRW-ETH"]
    ohlcv_cache: dict,           # symbol → pd.DataFrame (1h 기준 최근 60봉)
    threshold: float = 0.8       # 상관계수 임계값
) -> tuple[bool, str]:
    """
    new_symbol 의 수익률과 open_positions 각각의 수익률 간 pearson 상관계수 계산.
    threshold 초과 종목이 1개 이상이면 (False, "KRW-ETH 상관계수 0.91 초과") 반환.
    모든 상관계수가 threshold 이하이면 (True, "") 반환.
    """
```

`bot.py` 진입 판단 직전 호출:
```python
allowed, reason = portfolio_risk.check_correlation(symbol, open_symbols, ohlcv_cache)
if not allowed:
    logger.info(f"[상관관계 차단] {symbol}: {reason}")
    continue
```

**완료 기준**
- [ ] 상관계수 0.8 초과 종목 진입 시도 시 로그에 차단 메시지 출력
- [ ] `check_correlation()` 단위 테스트 통과 (BTC/ETH 상관 높음, BTC/DOGE 낮음)

---

## [ ] TODO 11. 포지션 비중 동적 조절 (Kelly Criterion)

**수정 파일**
- `backend/app/services/risk/manager.py` — `calc_kelly_fraction()` 함수 추가
- `backend/app/services/auto_trade/bot.py` — 진입 금액 계산 시 Kelly 비중 적용

**구현 내용**

`risk/manager.py` 에 함수 추가:
```python
def calc_kelly_fraction(
    win_rate: float,        # 최근 30건 승률 (0.0~1.0)
    avg_win: float,         # 평균 수익률 (e.g. 0.03 = 3%)
    avg_loss: float,        # 평균 손실률 (e.g. 0.015 = 1.5%, 양수)
    max_fraction: float = 0.25   # 안전 상한선 25%
) -> float:
    """
    Kelly fraction = win_rate - (1 - win_rate) / (avg_win / avg_loss)
    음수이면 0 반환, max_fraction 초과이면 max_fraction 반환 (half-Kelly 적용).
    """
```

`bot.py` 의 진입 금액 계산 로직에서:
```python
kelly = calc_kelly_fraction(win_rate, avg_win, avg_loss)
invest_krw = total_balance * kelly   # 기존 고정 비율 대체
```

승률·평균 손익은 `auto_bot_trades` 테이블의 최근 30건에서 계산.
최소 샘플 10건 미만이면 Kelly 무시, 기존 고정 비율 사용.

**완료 기준**
- [ ] `calc_kelly_fraction(0.6, 0.03, 0.015)` → 약 `0.3` (half-Kelly 0.15) 반환
- [ ] 최근 30건 승률이 50% 미만이면 투자 금액이 기존 대비 감소
- [ ] 10건 미만 데이터 시 기존 고정 비율 유지 확인

---

## [ ] TODO 12. 피라미딩 (수익 구간 단계별 추가 진입)

**수정 파일**
- `backend/app/services/auto_trade/bot.py` — `_check_pyramid_entry()` 메서드 추가

**구현 내용**

`bot.py:AutoTradeBot` 에 메서드 추가:
```python
async def _check_pyramid_entry(self, pos: dict, current_price: float):
    """
    조건: pnl_pct >= pyramid_threshold (기본 3%) AND 피라미딩 횟수 < 2회 AND 스코어 >= min_score
    충족 시 초기 투자금의 50% 추가 매수.
    pos dict에 "pyramid_count" 필드 관리.
    """
```

`_scan_loop()` 에서 포지션 모니터링 시 `_check_pyramid_entry()` 호출.
피라미딩 후 `avg_price` 재계산 및 SL 재조정 필수.

**완료 기준**
- [ ] PnL 3% 이상 포지션에서 피라미딩 자동 실행 로그 확인
- [ ] 피라미딩 횟수가 2회 초과하지 않음
- [ ] 피라미딩 후 `avg_price` 가 올바르게 재계산됨

---

## [ ] TODO 13. VaR 계산 및 MDD 자동 거래 중단

**수정 파일**
- `backend/app/services/risk/manager.py` — `calc_var()` 추가, `calc_performance()` 에 VaR 필드 추가
- `backend/app/services/auto_trade/bot.py` — MDD 초과 시 봇 자동 중지 로직 추가
- `backend/app/api/auto_bot.py:get_trade_stats()` — VaR 필드 응답에 포함

**13-1. VaR 계산**

`risk/manager.py` 에 함수 추가:
```python
def calc_var(
    pnl_list: list[float],   # 거래별 손익률 리스트
    confidence: float = 0.95
) -> float:
    """
    Historical VaR: pnl_list를 정렬해 (1-confidence) 분위수 반환.
    예) [-0.05, -0.03, 0.02, ...] → 95% VaR = 하위 5% 분위수 절댓값
    """
    import numpy as np
    return float(abs(np.percentile(pnl_list, (1 - confidence) * 100)))
```

`calc_performance()` 반환 dict에 `"var_95": calc_var(pnl_list)` 추가.

**13-2. MDD 기준 자동 거래 중단**

`bot.py:AutoTradeBot._scan_loop()` 루프 시작 시 MDD 체크:
```python
stats = calc_performance(self._trade_log())
if stats["mdd"] >= 0.20:           # MDD 20% 초과
    logger.warning("MDD 20% 초과 — 봇 자동 중지")
    await self.stop()
    # 디스코드 알림 전송 (TODO 16 연동)
    return
```

**완료 기준**
- [ ] `calc_var([...])` 단위 테스트 통과
- [ ] `/api/auto-bot/stats` 응답에 `"var_95"` 필드 존재
- [ ] MDD 20% 시뮬레이션 시 봇이 자동 중지됨

---

## [ ] TODO 14. 알파 / 베타 / 정보 비율

**수정 파일**
- `backend/app/services/risk/manager.py:calc_performance()` — 3개 지표 추가
- `backend/app/api/auto_bot.py:get_trade_stats()` — 응답에 포함
- `frontend/src/components/AutoBot/AutoTradePanel.tsx` — UI 표시 추가

**구현 내용**

`calc_performance()` 내부에 추가:
```python
# BTC 벤치마크 수익률은 호출자가 btc_returns: list[float] 로 전달
# Alpha = 포트폴리오 수익률 - Beta * BTC 수익률
# Beta  = Cov(포트폴리오, BTC) / Var(BTC)
# Information Ratio = (포트폴리오 수익률 - BTC 수익률) / Tracking Error

import numpy as np
if btc_returns and len(btc_returns) == len(daily_returns):
    cov_matrix = np.cov(daily_returns, btc_returns)
    beta  = cov_matrix[0][1] / cov_matrix[1][1]
    alpha = np.mean(daily_returns) - beta * np.mean(btc_returns)
    tracking_error = np.std(np.array(daily_returns) - np.array(btc_returns))
    info_ratio = (np.mean(daily_returns) - np.mean(btc_returns)) / tracking_error if tracking_error else 0
```

`calc_performance()` 시그니처 변경:
```python
def calc_performance(trade_log: list[dict], initial_capital: float = 1_000_000, btc_returns: list[float] = None) -> dict:
```

**완료 기준**
- [ ] `get_trade_stats()` 응답에 `"alpha"`, `"beta"`, `"information_ratio"` 포함
- [ ] `btc_returns` 미전달 시 3개 필드 `null` 로 반환 (에러 없음)
- [ ] 프론트엔드 통계 카드에 3개 지표 표시

---

## [ ] TODO 15. 월별 / 전략별 손익 히트맵

**신규 파일**
- `backend/app/api/auto_bot.py` — `GET /api/auto-bot/heatmap` 엔드포인트 추가

**수정 파일**
- `frontend/src/components/AutoBot/AutoTradePanel.tsx` — 히트맵 컴포넌트 추가

**API 스펙**

`GET /api/auto-bot/heatmap?type=monthly|strategy`

응답 예시 (월별):
```json
{
  "type": "monthly",
  "data": [
    {"label": "2025-01", "pnl_pct": 12.3},
    {"label": "2025-02", "pnl_pct": -4.1}
  ]
}
```

응답 예시 (전략별):
```json
{
  "type": "strategy",
  "data": [
    {"label": "oversold_bounce", "win_rate": 0.62, "total_pnl_pct": 23.1},
    {"label": "macd_momentum",   "win_rate": 0.48, "total_pnl_pct": -5.2}
  ]
}
```

`auto_bot.py` 쿼리:
```python
# auto_bot_trades 테이블에서 closed 상태 거래 집계
# 월별: GROUP BY strftime('%Y-%m', closed_at)
# 전략별: GROUP BY strategy_type
```

프론트엔드: `recharts` 의 `BarChart` 또는 색상 그리드(CSS grid + 배경색 분기)로 구현.
양수 PnL → 초록, 음수 → 빨강, 0 근접 → 회색.

**완료 기준**
- [ ] `GET /api/auto-bot/heatmap?type=monthly` 가 올바른 JSON 반환
- [ ] `GET /api/auto-bot/heatmap?type=strategy` 가 전략별 집계 반환
- [ ] 프론트엔드에서 탭 전환으로 월별/전략별 히트맵 표시

---

## [ ] TODO 16. 디스코드 실시간 알림

**신규 파일**
- `backend/app/services/notification/discord.py`

**수정 파일**
- `backend/app/services/auto_trade/bot.py` — 진입·청산·리스크 이벤트 시 알림 호출
- `backend/app/core/config.py` — `DISCORD_WEBHOOK_URL` 환경변수 추가
- `backend/.env.example` — `DISCORD_WEBHOOK_URL=` 항목 추가

**`discord.py` 구현**

```python
import httpx
from app.core.config import settings

async def send_discord(message: str) -> None:
    """
    settings.DISCORD_WEBHOOK_URL 이 비어 있으면 조용히 스킵.
    Discord Webhook POST: {"content": message}
    실패 시 예외 발생하지 않고 logger.warning 으로만 기록.
    """
    if not settings.DISCORD_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(settings.DISCORD_WEBHOOK_URL, json={"content": message})
    except Exception as e:
        logger.warning(f"[Discord] 알림 전송 실패: {e}")
```

**알림 발송 위치 (bot.py)**

| 이벤트 | 위치 | 메시지 형식 |
|--------|------|-------------|
| 진입 성공 | 매수 주문 완료 직후 | `[매수] KRW-BTC 10,000원 @ 95,000,000 (oversold_bounce / scalping)` |
| 청산 성공 | 매도 주문 완료 직후 | `[청산] KRW-BTC PnL +2.3% / +230원 (보유 4h32m)` |
| 일일 손실 한도 도달 | `RiskManager.check()` 차단 시 | `[경고] 일일 손실 한도 도달 (-5.0%) — 당일 거래 중단` |
| MDD 20% 초과 봇 중지 | TODO 13 연동 | `[긴급] MDD 20% 초과 — 봇 자동 중지` |
| 연속 손절 3회 | `analyze_losses()` 발동 시 | `[분석] 연속 손절 3회 — AI 파라미터 재조정 중` |

**완료 기준**
- [ ] `DISCORD_WEBHOOK_URL` 설정 시 진입/청산마다 디스코드 메시지 수신
- [ ] `DISCORD_WEBHOOK_URL` 미설정 시 봇 정상 동작 (에러 없음)
- [ ] 알림 실패 시 봇 프로세스에 영향 없음

---

## [ ] TODO 17. 성과 리포트 PDF 내보내기

**신규 파일**
- `backend/app/api/auto_bot.py` — `GET /api/auto-bot/report/pdf` 엔드포인트 추가

**수정 파일**
- `backend/requirements.txt` — `reportlab` 또는 `weasyprint` 추가

**구현 내용**

`reportlab` 사용:
```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

@router.get("/report/pdf")
async def export_pdf(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stats = calc_performance(trade_log)
    # A4 캔버스에 통계 텍스트 + 간단한 PnL 바 차트 출력
    # StreamingResponse(pdf_bytes, media_type="application/pdf") 반환
```

PDF 포함 내용:
1. 리포트 생성 날짜·기간
2. 총 수익률, 승률, 샤프/소르티노/칼마 비율, MDD
3. 전략별 승률 표
4. 누적 PnL 꺾은선 (reportlab Drawing)
5. 최고/최저 거래 5건 표

**완료 기준**
- [ ] `GET /api/auto-bot/report/pdf` 호출 시 PDF 파일 다운로드
- [ ] PDF 에 통계 수치와 전략별 표 포함
- [ ] 거래 기록 0건 시 빈 리포트 PDF 반환 (에러 없음)

---

## [ ] TODO 18. 멀티 에이전트 시스템

**신규 파일**
```
backend/app/services/agents/
  __init__.py
  base.py             # AgentBase 추상 클래스
  data_agent.py       # DataAgent
  quant_agent.py      # QuantAgent
  sentiment_agent.py  # SentimentAgent
  risk_agent.py       # RiskAgent
  commander_agent.py  # CommanderAgent
  pipeline.py         # AgentPipeline (오케스트레이터)
  prompts/
    data_agent.txt
    quant_agent.txt
    sentiment_agent.txt
    risk_agent.txt
    commander_agent.txt
```

**신규 DB 테이블**
```python
class AgentDecisionLog(Base):
    __tablename__ = "agent_decision_log"
    id              = Column(Integer, primary_key=True)
    symbol          = Column(String(32))
    timestamp       = Column(DateTime, default=func.now())
    quant_score     = Column(Float)        # 0~100
    sentiment_score = Column(Float)        # -1~+1
    risk_level      = Column(String(8))    # low / mid / high
    final_action    = Column(String(8))    # buy / sell / hold
    confidence      = Column(Integer)      # 0~100
    reasoning       = Column(Text)
    trade_id        = Column(Integer, ForeignKey("auto_bot_trades.id"), nullable=True)
```

**에이전트 역할 및 JSON 응답 스키마**

| 에이전트 | 입력 | 응답 JSON 스키마 |
|----------|------|-----------------|
| DataAgent | OHLCV DataFrame | `{"symbol": str, "features": {...}}` |
| QuantAgent | features | `{"score": int, "signals": [str], "reason": str}` |
| SentimentAgent | symbol | `{"score": float, "sources": [str], "reason": str}` |
| RiskAgent | portfolio, var | `{"risk_level": str, "max_position_pct": float, "sl_pct": float}` |
| CommanderAgent | 위 4개 출력 전체 | `{"action": str, "confidence": int, "reasoning": str}` |

**`base.py` 추상 클래스**
```python
class AgentBase(ABC):
    prompt_file: str   # prompts/ 하위 파일명

    async def run(self, input_data: dict) -> dict:
        prompt = self._build_prompt(input_data)
        raw    = await _call(prompt)          # ai_analyst._call() 재사용
        result = _parse_json(raw)             # ai_analyst._parse_json() 재사용
        self._validate(result)                # 스키마 검증, 실패 시 ValueError
        return result
```

**`pipeline.py` 오케스트레이터**
```python
async def run_pipeline(symbol: str, ohlcv_df, portfolio: dict, db) -> dict:
    data      = await DataAgent().run({"symbol": symbol, "df": ohlcv_df})
    quant, sentiment = await asyncio.gather(
        QuantAgent().run(data),
        SentimentAgent().run({"symbol": symbol})
    )
    risk      = await RiskAgent().run({"portfolio": portfolio, ...})
    decision  = await CommanderAgent().run({**quant, **sentiment, **risk})
    _log_decision(db, symbol, quant, sentiment, risk, decision)
    return decision
```

**하드코딩 리스크 오버라이드** (`pipeline.py` 내 `run_pipeline()` 반환 직전):
```python
OVERRIDE_RULES = [
    lambda p, d: (p["single_position_pct"] > 0.30, "단일 종목 비중 30% 초과"),
    lambda p, d: (p["daily_loss_pct"] <= -0.05,    "일일 손실 한도 초과"),
    lambda p, d: (p["consec_losses"] >= 3 and not p["cooldown_passed"], "연속 손절 쿨다운"),
]
for rule_fn in OVERRIDE_RULES:
    blocked, reason = rule_fn(portfolio, decision)
    if blocked:
        decision["action"] = "hold"
        decision["override_reason"] = reason
        await send_discord(f"[오버라이드] {symbol} 차단: {reason}")
        break
```

**`bot.py` 연동**

기존 `ai_analyst.check_entry()` 호출을 `pipeline.run_pipeline()` 으로 대체:
```python
# 기존
ai_result = await check_entry(symbol, score_data, ...)
# 변경
ai_result = await run_pipeline(symbol, ohlcv_df, portfolio, db)
```

**완료 기준**
- [ ] `run_pipeline()` 호출 시 5개 에이전트가 순서대로 실행되고 `agent_decision_log` 에 기록됨
- [ ] CommanderAgent 응답 파싱 실패 시 `{"action": "hold", "confidence": 0}` 폴백 반환
- [ ] 오버라이드 조건 충족 시 디스코드 알림 전송
- [ ] `bot.py` 가 `run_pipeline()` 을 사용해 정상 매매 동작

---

## [ ] TODO 19. 서버 상시 구동 (클라우드 배포)

**수정 파일**
- `docker-compose.yml` — 현재 파일 기반으로 프로덕션 설정 분리
- `docker-compose.prod.yml` — 신규 생성

**구현 내용**

`docker-compose.prod.yml`:
```yaml
services:
  backend:
    restart: always
    environment:
      - ENV=production
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      retries: 3
  frontend:
    restart: always
```

`backend/app/main.py` 에 헬스체크 엔드포인트 추가:
```python
@app.get("/health")
def health(): return {"status": "ok"}
```

Railway 배포 시 `railway.json` 신규 생성:
```json
{
  "build": {"builder": "DOCKERFILE"},
  "deploy": {"restartPolicyType": "ON_FAILURE", "restartPolicyMaxRetries": 3}
}
```

**완료 기준**
- [ ] `docker-compose -f docker-compose.prod.yml up -d` 로 정상 기동
- [ ] `GET /health` → `{"status": "ok"}` 응답
- [ ] 컨테이너 크래시 후 `restart: always` 에 의해 자동 재시작 확인

---

## [ ] TODO 20. 봇 재시작 자동 복구

**수정 파일**
- `backend/app/services/auto_trade/bot.py` — `AutoTradeBot.restore_positions()` 메서드 추가
- `backend/app/models/auto_bot_trade.py` — `status` 컬럼 확인 (`open` / `closed`)

**구현 내용**

`bot.py:AutoTradeBot` 에 메서드 추가:
```python
async def restore_positions(self, db: Session) -> int:
    """
    봇 시작 시 auto_bot_trades 에서 status='open' 레코드를 읽어
    self._positions dict 에 복원한다.
    복원된 포지션 수를 반환.
    """
    open_trades = db.query(AutoBotTrade).filter_by(status="open", user_id=self.user_id).all()
    for t in open_trades:
        self._positions[t.symbol] = {
            "symbol": t.symbol, "entry_price": t.entry_price,
            "amount": t.amount, "strategy": t.strategy_type,
            "style": t.style, "sl": t.sl_price, "tp": t.tp_price,
            ...
        }
    return len(open_trades)
```

`AutoTradeBot.start()` 내부 초기화 직후 `await self.restore_positions(db)` 호출.
복원된 포지션이 있으면 디스코드 알림 전송 (TODO 16 연동):
```
[복구] 봇 재시작 — 미결 포지션 3건 복원 완료
```

**완료 기준**
- [ ] 봇 강제 종료 후 재시작 시 `open` 상태 포지션이 메모리에 복원됨
- [ ] 복원된 포지션이 이후 스캔 루프에서 정상 모니터링됨
- [ ] 복원 포지션 0건이면 알림 생략

---

## [x] TODO 21. 바이낸스 선물거래 (Binance Futures)

> **선행 의존성**: TODO 9(다중 거래소)의 ccxt 커넥터 기반 위에 구현.
> 업비트는 현물 전용이므로 선물거래는 Binance Futures 전용 커넥터로 분리한다.

**수정 파일**
- `backend/app/services/exchange/connector.py` — `BinanceFuturesConnector` 클래스 추가
- `backend/app/services/auto_trade/scanner.py` — `scan_futures_market()` 함수 추가
- `backend/app/services/auto_trade/bot.py` — `AutoTradeBot` 에 선물 모드 분기 추가
- `backend/app/services/risk/manager.py` — 레버리지 고려 리스크 계산 추가
- `backend/app/models/auto_bot_trade.py` — 선물 관련 컬럼 추가
- `backend/app/api/auto_bot.py` — 레버리지·마진모드 설정 엔드포인트 추가
- `backend/app/core/config.py` — `BINANCE_FUTURES_TESTNET` 환경변수 추가
- `frontend/src/components/AutoBot/AutoTradePanel.tsx` — 선물 설정 UI 추가

---

### 21-1. Binance Futures 커넥터

`backend/app/services/exchange/connector.py` 에 클래스 추가:

```python
import ccxt.async_support as ccxt

class BinanceFuturesConnector:
    """
    Binance USDT-M 선물 전용 커넥터.
    testnet=True 이면 https://testnet.binancefuture.com 사용.
    """

    def __init__(self, api_key: str, secret: str, testnet: bool = False):
        options = {"defaultType": "future"}
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": secret,
            "options": options,
        })
        if testnet:
            self.exchange.set_sandbox_mode(True)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """심볼별 레버리지 설정. leverage: 1~125 (기본 5)."""
        await self.exchange.set_leverage(leverage, symbol)

    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        """mode: 'cross' | 'isolated'"""
        await self.exchange.set_margin_mode(mode, symbol)

    async def open_long(self, symbol: str, usdt_amount: float, leverage: int) -> dict:
        """USDT 기준 매수. quantity = usdt_amount * leverage / mark_price."""
        mark_price = await self.get_mark_price(symbol)
        qty = (usdt_amount * leverage) / mark_price
        order = await self.exchange.create_market_buy_order(symbol, qty)
        return order

    async def open_short(self, symbol: str, usdt_amount: float, leverage: int) -> dict:
        mark_price = await self.get_mark_price(symbol)
        qty = (usdt_amount * leverage) / mark_price
        order = await self.exchange.create_market_sell_order(symbol, qty, {"reduceOnly": False})
        return order

    async def close_position(self, symbol: str, side: str, qty: float) -> dict:
        """side: 'long' | 'short'. reduceOnly=True 로 포지션만 청산."""
        if side == "long":
            order = await self.exchange.create_market_sell_order(symbol, qty, {"reduceOnly": True})
        else:
            order = await self.exchange.create_market_buy_order(symbol, qty, {"reduceOnly": True})
        return order

    async def get_mark_price(self, symbol: str) -> float:
        ticker = await self.exchange.fetch_ticker(symbol)
        return ticker["markPrice"]

    async def get_liquidation_price(self, symbol: str) -> float | None:
        positions = await self.exchange.fetch_positions([symbol])
        for p in positions:
            if p["symbol"] == symbol and p["contracts"] > 0:
                return p["liquidationPrice"]
        return None

    async def get_funding_rate(self, symbol: str) -> float:
        """현재 펀딩비 반환. 양수=롱이 숏에게 지불, 음수=숏이 롱에게 지불."""
        info = await self.exchange.fetch_funding_rate(symbol)
        return info["fundingRate"]

    async def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
        bars = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    async def get_balance(self) -> dict:
        """{'total': float, 'free': float, 'used': float} — USDT 기준."""
        bal = await self.exchange.fetch_balance()
        usdt = bal["USDT"]
        return {"total": usdt["total"], "free": usdt["free"], "used": usdt["used"]}
```

---

### 21-2. DB 모델 수정

`backend/app/models/auto_bot_trade.py` 에 컬럼 추가:

```python
# 기존 컬럼 유지, 아래 추가
market_type      = Column(String(8),  default="spot")    # "spot" | "futures"
side             = Column(String(8),  default="long")    # "long" | "short"
leverage         = Column(Integer,    default=1)
margin_mode      = Column(String(16), default="cross")   # "cross" | "isolated"
liquidation_price= Column(Float,      nullable=True)
funding_paid     = Column(Float,      default=0.0)       # 누적 펀딩비 (USDT)
```

---

### 21-3. 선물 전용 스캐너

`backend/app/services/auto_trade/scanner.py` 에 함수 추가:

```python
FUTURES_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
    "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
]

async def scan_futures_market(
    connector: BinanceFuturesConnector,
    timeframe: str = "1h",
    style: str = "short"
) -> list[dict]:
    """
    FUTURES_SYMBOLS 를 순회하며 기존 _score() 로 점수 계산.
    추가 조건: funding_rate 절댓값 > 0.001 (0.1%) 이면 해당 방향 신호 차감 -10.
    반환: [{"symbol": str, "score": int, "side": "long"|"short", "funding_rate": float, ...}]
    """
```

펀딩비 로직:
- `funding_rate > +0.001` → 롱 신호 -10 (롱 포지션 비용 증가)
- `funding_rate < -0.001` → 숏 신호 -10 (숏 포지션 비용 증가)

---

### 21-4. bot.py 선물 모드 분기

`AutoTradeBot` 초기화 시 `market_type` 설정:

```python
class AutoTradeBot:
    def __init__(self, ..., market_type: str = "spot"):
        self.market_type = market_type  # "spot" | "futures"
        if market_type == "futures":
            self.futures_connector = BinanceFuturesConnector(
                api_key=settings.BINANCE_API_KEY,
                secret=settings.BINANCE_SECRET,
                testnet=settings.BINANCE_FUTURES_TESTNET,
            )
```

진입 로직 분기:
```python
async def _execute_entry(self, signal: dict):
    if self.market_type == "futures":
        await self.futures_connector.set_leverage(signal["symbol"], self.leverage)
        await self.futures_connector.set_margin_mode(signal["symbol"], self.margin_mode)
        if signal["side"] == "long":
            order = await self.futures_connector.open_long(signal["symbol"], invest_usdt, self.leverage)
        else:
            order = await self.futures_connector.open_short(signal["symbol"], invest_usdt, self.leverage)
        liq_price = await self.futures_connector.get_liquidation_price(signal["symbol"])
        # liq_price 를 포지션 dict 에 저장
    else:
        # 기존 업비트 현물 로직
```

---

### 21-5. 청산가 모니터링

`_scan_loop()` 내 포지션 모니터링 루프에서 선물 포지션에 한해 청산가 체크:

```python
if self.market_type == "futures":
    mark = await self.futures_connector.get_mark_price(pos["symbol"])
    liq  = pos.get("liquidation_price")
    if liq:
        # 청산가까지 남은 거리 (%)
        distance_pct = abs(mark - liq) / mark * 100
        if distance_pct < 5.0:   # 청산가 5% 이내 접근
            logger.warning(f"[청산가 경고] {pos['symbol']} 청산가 {liq:.2f} 까지 {distance_pct:.1f}% 남음")
            await send_discord(f"[긴급] {pos['symbol']} 청산가 {distance_pct:.1f}% 이내 — 강제 청산 검토")
            await self._close_position(pos)   # 강제 청산
```

---

### 21-6. 펀딩비 모니터링

`_scan_loop()` 에서 8시간마다 (UTC 00:00, 08:00, 16:00) 펀딩비 체크:

```python
async def _check_funding_rates(self):
    for symbol, pos in self._positions.items():
        if pos.get("market_type") != "futures":
            continue
        rate = await self.futures_connector.get_funding_rate(symbol)
        pos["funding_rate"] = rate
        # 펀딩비 > 0.05% 이면 디스코드 알림
        if abs(rate) > 0.0005:
            await send_discord(f"[펀딩비] {symbol} {rate*100:.4f}% — 포지션 방향 재검토 권장")
```

---

### 21-7. 리스크 관리 (레버리지 고려)

`backend/app/services/risk/manager.py:RiskManager` 에 레버리지 고려 메서드 추가:

```python
def calc_futures_position_size(
    self,
    usdt_balance: float,
    leverage: int,
    risk_pct: float = 0.02,    # 계좌 대비 최대 손실 허용 2%
    sl_pct: float = 0.03       # 손절선 3%
) -> float:
    """
    실제 손실 = 투자금 * sl_pct * leverage
    투자금 = risk_pct * balance / (sl_pct * leverage)
    레버리지가 높을수록 투자금이 작아져 리스크 일정 유지.
    """
    invest = (risk_pct * usdt_balance) / (sl_pct * leverage)
    max_invest = usdt_balance * 0.2   # 계좌 20% 상한
    return min(invest, max_invest)
```

---

### 21-8. API 엔드포인트

`backend/app/api/auto_bot.py` 에 추가:

```python
@router.post("/futures/settings")
async def update_futures_settings(
    leverage: int = Body(..., ge=1, le=20),       # 1~20배
    margin_mode: str = Body(..., pattern="^(cross|isolated)$"),
    user: User = Depends(get_current_user)
):
    """봇의 선물 레버리지·마진모드 설정 갱신."""
    bot = get_auto_bot()
    bot.leverage    = leverage
    bot.margin_mode = margin_mode
    return {"leverage": leverage, "margin_mode": margin_mode}

@router.get("/futures/positions")
async def get_futures_positions(user: User = Depends(get_current_user)):
    """현재 선물 포지션 목록 (청산가·펀딩비 포함)."""
```

---

### 21-9. 환경변수

`backend/app/core/config.py` 에 추가:

```python
BINANCE_API_KEY: str = ""
BINANCE_SECRET: str  = ""
BINANCE_FUTURES_TESTNET: bool = True   # 기본 테스트넷, 실거래 시 False
```

`backend/.env.example` 에 추가:
```bash
BINANCE_API_KEY=
BINANCE_SECRET=
BINANCE_FUTURES_TESTNET=true
```

---

### 21-10. 프론트엔드 UI

`frontend/src/components/AutoBot/AutoTradePanel.tsx` 에 선물 설정 섹션 추가:

- **거래 모드 토글**: `현물(업비트)` / `선물(Binance Futures)` 라디오 버튼
- **레버리지 슬라이더**: 1x ~ 20x (선물 모드 선택 시 활성화)
- **마진 모드 셀렉트**: Cross / Isolated
- **포지션 카드 추가 표시 필드**: 청산가, 펀딩비, 레버리지

`frontend/src/types/index.ts` 에 타입 추가:
```typescript
export interface FuturesPosition {
  symbol: string;
  side: "long" | "short";
  leverage: number;
  marginMode: "cross" | "isolated";
  liquidationPrice: number | null;
  fundingRate: number;
  markPrice: number;
  pnlPct: number;
}
```

---

### 완료 기준

- [x] `BinanceFuturesConnector` 가 Binance Testnet 에서 `get_balance()` 성공
- [x] `set_leverage(5)` + `open_long("BTC/USDT", 100, 5)` → 테스트넷 주문 체결 확인
- [x] 청산가 5% 이내 접근 시 강제 청산 (시뮬레이션)
- [x] `scan_futures_market()` 이 FUTURES_SYMBOLS 스캔 후 점수 리스트 반환
- [x] `POST /api/auto-bot/futures/settings` 가 레버리지·마진모드 갱신
- [x] `BINANCE_FUTURES_TESTNET=true` 설정 시 실계좌 영향 없음 확인
- [x] 프론트엔드에서 선물 모드 전환 후 레버리지 슬라이더 활성화

---

## AI 프로바이더 설정

```bash
# 무료 - Groq API (권장)
AI_PROVIDER=groq
GROQ_API_KEY=your_key_here

# 무료 - 로컬 Ollama
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2

# 유료 - Claude (가장 정확)
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here

# 디스코드 알림 (TODO 16)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```
