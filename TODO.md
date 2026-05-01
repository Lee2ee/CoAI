# CoAI - TODO

## AI 활용 고도화 로드맵

현재 AI는 전략 자동 생성(`/api/v1/auto-strategy/generate`) 한 곳에만 붙어 있음.
자동매매 봇(`bot.py`)은 규칙 기반 점수로만 동작 중.
아래 항목을 순서대로 구현하면 수익 극대화 가능.

---

## [x] 1. AI 진입 확인 (Entry Validation)

**파일**: `backend/app/services/auto_trade/bot.py`, `scanner.py`
**우선순위**: 높음 / 비용: Groq 무료 티어로 운영 가능

### 목표
스캔 점수만으로 진입하는 현재 방식 개선.
상위 후보 종목을 AI에게 최종 검증받아 타이밍이 나쁜 진입을 차단.

### 구현 내용
- `_enter_from_scan`에서 score 상위 후보(최대 3종목)를 AI에 전달
- AI 입력: 최근 20봉 OHLCV + RSI/MACD/EMA 수치 + 현재 전략 타입
- AI 출력: `{ "enter": true/false, "confidence": 0~100, "reason": "..." }`
- confidence 70 이상일 때만 실제 진입 허용
- confidence는 포지션 크기 조정에도 활용 (70~80 → 표준, 80~90 → +10%, 90+ → +20%)

### 기대 효과
- 점수는 높지만 타이밍이 나쁜 진입 차단
- 손절 횟수 감소, 평균 손익비 개선

---

## [x] 2. 시장 국면 자동 감지 (Market Regime Detection)

**파일**: `backend/app/services/auto_trade/bot.py`
**우선순위**: 높음 / 비용: 스캔 사이클당 AI 1회 호출

### 목표
추세장/횡보장/급등장 등 시장 국면을 AI가 판단해
봇의 `trading_style`과 `min_score`를 자동으로 조정.

### 구현 내용
- `_cycle` 시작 시 BTC/KRW 1h 최근 50봉을 AI에 전달
- AI 출력: `{ "regime": "trending/ranging/volatile", "recommended_style": "scalping/short/mid/long", "min_score_adjustment": +5/-5 }`
- 추천 스타일이 현재 설정과 다르면 `update_settings` 자동 호출
- 국면 변경 이력을 trade_log에 기록

### 기대 효과
- 횡보장에서의 과매매 방지
- 추세장에서 스타일 자동 공격화 (scalping/short 전환)

---

## [x] 3. 손절 후 자기 분석 (Post-Loss Analysis)

**파일**: `backend/app/services/auto_trade/bot.py`
**우선순위**: 중간 / 비용: 손절 발생 시에만 AI 호출

### 목표
연속 손절 발생 시 AI가 원인을 분석하고 파라미터 조정을 제안.
사람이 직접 보지 않아도 봇이 스스로 튜닝.

### 구현 내용
- `_close_position`에서 `stop_loss` 사유로 청산 시 연속 손절 카운터 증가
- 연속 손절 3회 도달 시 최근 패배 거래 5건을 AI에 전달
- AI 출력: `{ "issue": "SL_TOO_TIGHT/WRONG_STRATEGY/BAD_TIMING", "adjust": { "stop_loss_pct": +0.5, "min_score": +5 } }`
- 조정값을 `update_settings`에 반영, 연속 손절 카운터 리셋
- 분석 결과를 별도 `analysis_log`에 저장하여 API로 조회 가능하게

### 기대 효과
- 시장 변화에 따른 자동 파라미터 적응
- 연속 손절 구간 조기 탈출

---

## [x] 4. 청산 타이밍 AI 보조 (Exit Timing Assist)

**파일**: `backend/app/services/auto_trade/bot.py`
**우선순위**: 중간 / 비용: 포지션 보유 중 스캔마다 호출

### 목표
트레일링 스탑 미활성 구간에서 AI가 청산 타이밍을 보조.
신호 역전 감지 시 TP를 기다리지 않고 조기 청산.

### 구현 내용
- `_check_positions`에서 이익 중인 포지션에 대해 AI 분석
- AI 입력: 진입가, 현재가, pnl_pct, 최근 지표, 현재 전략 타입
- AI 출력: `{ "action": "hold/tighten_sl/close_now", "reason": "..." }`
- `close_now` 응답 시 수동 청산과 동일하게 처리
- `tighten_sl` 응답 시 현재 SL을 AI 추천값으로 상향

### 기대 효과
- 추세 역전 시 이익 보전
- 트레일링 스탑 보완

---

## [ ] 5. 전략 빌더 ↔ 자동매매 봇 연동 (Strategy Integration)

**파일**: `backend/app/services/auto_trade/bot.py`, `scanner.py`, `backend/app/services/strategy/engine.py`
**우선순위**: 높음 / 비용: 없음 (내부 연동)

### 현재 상태
두 시스템이 완전히 분리되어 독립 동작 중:
- **자동매매 봇**: `scanner.py`에 하드코딩된 4가지 내장 전략만 사용 (oversold_bounce / golden_cross / volume_breakout / macd_momentum)
- **전략 빌더**: 사용자가 직접 만들거나 AI가 생성한 전략을 DB에 저장 → APScheduler로 별도 실행 → 별도 거래 기록

### 목표
DB에 저장된 사용자 전략(직접 작성 또는 AI 생성)을 자동매매 봇 스캔 사이클에서도 활용.

### 구현 내용
- DB에서 `is_active=True`인 전략 목록을 봇 초기화 시 로드
- `scanner.py`에서 내장 전략 점수와 함께 DB 전략 조건도 평가
- DB 전략 신호 발생 시 내장 전략과 동일하게 진입 후보로 추가
- `strategy_type` 필드에 DB 전략 ID/이름 표기하여 실적 추적 가능하게
- 전략 활성화/비활성화 시 봇에 즉시 반영 (캐시 갱신)

### 기대 효과
- AI가 생성한 커스텀 전략이 실제 자동매매에 사용됨
- 백테스트에서 검증된 전략을 봇에 바로 적용 가능
- 전략 빌더의 존재 의미가 생김

---

## [ ] 6. 동적 종목 확장 (Dynamic Symbol Discovery)

**파일**: `backend/app/services/auto_trade/scanner.py`
**우선순위**: 낮음 / 비용: 스캔 사이클당 AI 1회 호출

### 목표
현재 고정 25종목 리스트에서 벗어나
업비트 전체 종목 중 AI가 급등 전 패턴을 가진 종목을 추가 발굴.

### 구현 내용
- 업비트 전체 KRW 마켓 티커를 조회해 거래량 급증 상위 10종목 추출
- 해당 종목의 기본 지표를 AI에 전달
- AI가 `SCAN_SYMBOLS`에 없는 종목 중 진입 가치 있는 것을 추천
- 추천 종목을 해당 스캔 사이클에 한해 임시 추가

### 기대 효과
- 고정 리스트 밖의 급등 종목 포착
- 기회 손실 감소

---

## AI 프로바이더 설정 (`.env`)

```
# 무료 - Groq API (권장: 1~4번 구현에 충분)
AI_PROVIDER=groq
GROQ_API_KEY=your_key_here       # https://console.groq.com 무료 발급

# 무료 - 로컬 Ollama (인터넷 없이 사용 가능, 속도 느림)
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2

# 유료 - Claude (가장 정확, 1~5번 모두 최고 품질)
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
```

---

---

## [ ] 7. 자가 학습 전략 최적화 (Self-Learning Strategy Optimizer)

**파일**: `backend/app/services/auto_trade/bot.py`, `ai_analyst.py`, `scanner.py`, DB 신규 테이블
**우선순위**: 높음 / 비용: 청산마다 LLM 1회 호출 (캐시 적용)

### 배경 및 목표

현재 AI는 진입 확인·국면 감지·손절 분석 등 **반응형** 역할만 수행한다.
손절이 났을 때 원인을 분석하고 파라미터를 즉시 수정하지만, **거래 결과가 장기 전략 자체에 반영되지 않는다.**

목표: 매 청산 결과를 학습 데이터로 축적 → 신호 조합별 승률 통계 + LLM 피드백으로
점수 가중치와 진입 조건을 자동 업그레이드하여 수익을 극대화한다.

### 구조 설계

#### 7-1. 신호 조합별 성과 추적 DB (통계 기반 학습)

```
신규 테이블: signal_performance
  - signals_key   : 신호 조합 해시 (예: "RSI과매도+망치형+MACD반등")
  - strategy_type : oversold_bounce / macd_momentum / ...
  - style         : scalping / short / mid / long
  - win_count     : 승리 횟수
  - loss_count    : 패배 횟수
  - total_pnl_pct : 누적 손익률
  - avg_hold_secs : 평균 보유 시간(초)
  - updated_at    : 마지막 업데이트
```

청산마다 해당 포지션의 신호 조합을 키로 성과를 기록.
승률이 낮은 신호 조합은 스캔 점수에서 자동 감점, 높은 조합은 가점 적용.

#### 7-2. LLM 피드백 루프 (장기 메모리 기반)

```
strategy_memory.json (로컬 파일 또는 DB)
  - 거래별 요약: 진입 신호, 보유 시간, 손익률, 청산 사유
  - LLM이 도출한 개선 제안 누적
  - 현재 적용 중인 조정값 목록
```

흐름:
  1. 청산 발생 → 결과 + 신호 조합을 메모리 파일에 기록
  2. 누적 거래 10건마다 (또는 연속 손절 2회마다) LLM에 전달
  3. LLM 출력: 어떤 신호 조합이 잘 작동하는지 / 어떤 조건을 강화·완화할지
  4. 제안을 `scanner.py` 가중치와 봇 파라미터에 반영
  5. 변경 이력을 AI 활동 로그에 표시

#### 7-3. 점수 가중치 동적 조정

```python
# 현재: 스타일별 고정 가중치
STYLE_SCORE_WEIGHTS = {
    "short": {"rsi": 1.0, "ema": 1.0, "macd": 1.0, ...}
}

# 목표: 신호별 성과에 따라 런타임에 가중치 자동 조정
# 예) "RSI 반등 시작" 신호의 최근 30건 승률 70% → rsi_bounce 가중치 +0.3
#     "MACD 강세 구간" 신호의 최근 30건 승률 35% → macd 가중치 -0.2
```

#### 7-4. 안전장치 (과최적화 방지)

- 가중치 조정 폭 제한: 원본 대비 ±50% 이내
- 최소 샘플 수 보장: 10건 미만 데이터는 조정 불가
- 인간 승인 모드: 조정 제안을 UI에 표시하고 수동 승인 후 적용 (옵션)
- Walk-Forward 검증: 최근 조정이 직전 20건에서 개선됐는지 자동 확인
- 주기적 리셋: 30일마다 가중치를 기본값으로 부분 복원 (드리프트 방지)

### 구현 순서

```
Phase 1 (기반): signal_performance 테이블 생성 + 청산마다 신호 조합 기록
Phase 2 (통계): 신호 조합 승률 기반 가중치 자동 조정 (LLM 없이도 동작)
Phase 3 (LLM):  strategy_memory.json 생성 + 10건 누적 시 LLM 피드백 요청
Phase 4 (UI):   학습 현황 대시보드 (어떤 신호가 잘 작동하는지 시각화)
```

### 기대 효과

- 시간이 지날수록 수익성 높은 신호 조합 위주로 진입 자동 집중
- 손실 패턴 재발 방지 (동일한 신호 조합에서 반복 손실 시 자동 감점)
- 시장 국면 변화에 따른 전략 자동 진화
- 사람이 개입하지 않아도 장기적으로 전략이 개선됨

### 한계 및 주의사항

- **과최적화 위험**: 특정 기간 데이터에 맞게 과도하게 조정되면 미래 성과 저하 가능
  → 안전장치(7-4) 필수
- **충분한 데이터 필요**: 신호 조합당 최소 10~30건의 거래 없이는 통계적으로 무의미
  → 초기 수주간은 학습보다 데이터 수집 모드로 운영
- **LLM은 기억이 없음**: 반드시 외부 파일(strategy_memory.json)에 누적 저장 필요
- **강화학습(RL)과의 차이**: 이 방식은 규칙 기반 + LLM 보조로 RL보다 안전하나
  완전 자율 최적화는 아님. RL은 백테스트 환경에서만 별도 검토 필요

---

## [ ] 8. 캔들 패턴 고도화 (Advanced Pattern Recognition)

**파일**: `backend/app/services/auto_trade/scanner.py`
**우선순위**: 중간

### 현재 상태
망치형·인걸핑·피어싱·도지·모닝스타 5종 기본 패턴 구현 완료.

### 추가 예정 패턴
- 상승장악형 (Bullish Harami)
- 상승 삼병사 (Three White Soldiers)
- 역헤드앤숄더 (Inverse H&S) — 5~10봉 패턴
- 이중 바닥 (Double Bottom) — 지지선 재확인
- 볼린저밴드 하단 터치 + 반등 캔들 조합

---

## [ ] 9. 전략 빌더 ↔ 자동매매 봇 연동 (Strategy Integration)

**파일**: `backend/app/services/auto_trade/bot.py`, `scanner.py`, `backend/app/services/strategy/engine.py`
**우선순위**: 높음 / 비용: 없음 (내부 연동)

### 현재 상태
두 시스템이 완전히 분리되어 독립 동작 중:
- **자동매매 봇**: `scanner.py`에 하드코딩된 4가지 내장 전략만 사용
- **전략 빌더**: 사용자가 직접 만들거나 AI가 생성한 전략을 DB에 저장 → APScheduler로 별도 실행

### 목표
DB에 저장된 사용자 전략을 자동매매 봇 스캔 사이클에서도 활용.

### 구현 내용
- DB에서 `is_active=True`인 전략 목록을 봇 초기화 시 로드
- `scanner.py`에서 내장 전략 점수와 함께 DB 전략 조건도 평가
- DB 전략 신호 발생 시 내장 전략과 동일하게 진입 후보로 추가
- `strategy_type` 필드에 DB 전략 ID/이름 표기하여 실적 추적 가능하게

---

## [ ] 10. 동적 종목 확장 (Dynamic Symbol Discovery)

**파일**: `backend/app/services/auto_trade/scanner.py`
**우선순위**: 낮음

### 목표
현재 고정 25종목 리스트에서 벗어나 업비트 전체 종목 중 급등 전 패턴 종목 자동 발굴.

### 구현 내용
- 업비트 전체 KRW 마켓 티커를 조회해 거래량 급증 상위 10종목 추출
- 기본 지표를 AI에 전달 → AI가 진입 가치 있는 종목 추천
- 추천 종목을 해당 스캔 사이클에 한해 임시 추가

---

## AI 프로바이더 설정 (`.env`)

```
# 무료 - Groq API (권장: 1~7번 구현에 충분)
AI_PROVIDER=groq
GROQ_API_KEY=your_key_here       # https://console.groq.com 무료 발급

# 무료 - 로컬 Ollama (인터넷 없이 사용 가능, 속도 느림)
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2

# 유료 - Claude (가장 정확, 자가 학습 품질 최고)
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
```

---

## 구현 완료 항목

- [x] 스타일별 지표 가중치 (scalping=MACD/거래량, long=RSI/EMA)
- [x] 스타일별 전략 SL/TP 차등 적용
- [x] 트레일링 스탑 (이익 구간 진입 시 TP 상한 제거 + 고점 추적)
- [x] 스타일별 선호 전략 정렬 (STYLE_PREFERRED_STRATEGIES)
- [x] 전략 실적 추적 + 승률 30% 미만 전략 진입 차단
- [x] 포지션 보유 중 전략 교체 (스캔마다 재평가)
- [x] 신호 약화 시 SL 자동 상향 (이익 보호)
- [x] AI 전략 자동 생성 (Ollama / Groq / Claude / OpenAI / Gemini)
- [x] AI 진입 확인 — confidence < 65 차단, 높으면 포지션 크기 자동 증가
- [x] AI 시장 국면 감지 — 15분 캐시, trading_style / min_score 자동 조정
- [x] AI 손절 자기 분석 — 연속 손절 3회 시 원인 분석 → 파라미터 자동 조정
- [x] AI 청산 보조 — 이익 구간에서 청산/SL상향 판단
- [x] AI 설정 UI (설정 메뉴에서 프로바이더/모델/키 변경, 연결 테스트)
- [x] 포지션별 AI 매매 스타일 자동 선택 (종목 특성에 따라 scalping/short/mid/long 결정)
- [x] RSI 저점 반등 감지 (2봉 연속 반등, 단기 반등, 불리시 다이버전스)
- [x] 캔들 패턴 감지 (망치형·불리시 인걸핑·피어싱·도지·모닝스타)
- [x] 거래 내역 매매일지 형식 표시 (진입가·청산가·보유기간·투입금액 상세)
- [x] GitHub 배포 (main / develop 브랜치)
