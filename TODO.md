# CoAI - 프로 퀀트 시스템 로드맵

프로 퀀트 시스템과의 차이를 기준으로 구현 항목을 정리한다.
`[x]` 완료 / `[ ]` 미구현

---

## 전략 (Strategy)

| 항목 | 상태 | 비고 |
|------|------|------|
| 기본 4전략 (oversold_bounce / golden_cross / macd_momentum / volume_breakout) | [x] | |
| 스타일별 지표 가중치 (scalping=MACD/거래량, long=RSI/EMA) | [x] | |
| 스타일별 전략 SL/TP 차등 | [x] | |
| AI 전략 자동 생성 (Ollama/Groq/Claude/Gemini) | [x] | |
| RSI 저점 반등 감지 (2봉 연속·단기·불리시 다이버전스) | [x] | |
| 캔들 패턴 (망치형·인걸핑·피어싱·도지·모닝스타) | [x] | |
| 급등 오버라이드 진입 (거래량 3배+ & 가격 3%+) | [x] | BTC 국면 무관 |
| 전략 빌더 ↔ 자동매매 봇 연동 | [x] | DB 전략 → 봇 실행 (5분 캐시, 진입 조건 실시간 평가) |
| 멀티 타임프레임 확인 | [x] | 1h 신호 + 4h 추세 확인, bearish HTF → min_score +10 |
| 고급 캔들 패턴 (삼병사·역H&S·이중바닥·볼린저 반등) | [x] | TODO 8 완료 |
| 자가 학습 전략 최적화 | [ ] | TODO 7 |
| 공매도(Short Selling) 지원 | [ ] | 현재 롱 전용 |
| 다중 거래소 지원 (Binance, Bybit 등) | [ ] | 현재 업비트 단일 |
| 동적 종목 발굴 (전체 업비트 스캔) | [x] | TODO 10 완료, 30분 캐시 갱신 |

---

## 포지션 (Position)

| 항목 | 상태 | 비고 |
|------|------|------|
| 다중 진입 (물타기 / 추매) | [x] | 최대 2회 |
| 포지션별 AI 스타일 자동 선택 | [x] | scalping/short/mid/long |
| 트레일링 스탑 | [x] | 고점 대비 N% 하락 시 청산 |
| 포지션 보유 중 전략 재평가·교체 | [x] | 스캔마다 |
| 신호 약화 시 SL 자동 상향 | [x] | pnl ≥ protect_pct*2 조건 |
| 포트폴리오 최대 노출 한도 | [x] | 총 자산의 80% 초과 진입 차단 |
| 포트폴리오 상관관계 체크 | [ ] | 동일 섹터 중복 보유 제한 |
| 포지션 비중 동적 조절 (Kelly Criterion) | [ ] | 승률 기반 최적 베팅 크기 |
| 피라미딩 (수익 구간 단계별 추가 진입) | [ ] | |
| 숏 포지션 관리 | [ ] | 공매도 연동 필요 |

---

## 리스크 관리 (Risk Management)

| 항목 | 상태 | 비고 |
|------|------|------|
| 개별 포지션 SL/TP | [x] | |
| 트레일링 스탑 | [x] | |
| 전략×스타일별 SL/TP 차등 | [x] | 4전략 × 4스타일 |
| 일일 최대 손실 한도 (Daily Loss Limit) | [x] | 총 자산 대비 5% 기본값 |
| 포트폴리오 최대 노출 한도 | [x] | 총 자산 대비 80% |
| 연속 손절 AI 자기 분석 + 파라미터 조정 | [x] | 3회 연속 손절 시 발동 |
| VaR (Value at Risk) 계산 | [ ] | 95% 신뢰구간 1일 VaR |
| 포지션 간 상관계수 리스크 | [ ] | 상관 높은 종목 동시 보유 제한 |
| 최대 낙폭(MDD) 기준 자동 거래 중단 | [ ] | MDD 20% 초과 시 봇 중지 |

---

## 성과 분석 (Performance Analysis)

| 항목 | 상태 | 비고 |
|------|------|------|
| 승률 / 평균 손익 | [x] | |
| 전략별 승률 추적 | [x] | 승률 30% 미만 전략 차단 |
| 최고/최저 거래 | [x] | |
| 샤프 비율 (Sharpe Ratio) | [x] | 거래 단위 연환산 |
| 소르티노 비율 (Sortino Ratio) | [x] | 하방 편차 기반 |
| 칼마 비율 (Calmar Ratio) | [x] | 수익 / MDD |
| 프로핏 팩터 (Profit Factor) | [x] | 총 수익 / 총 손실 |
| 기대값 (Expectancy) | [x] | 거래당 기대 손익률 |
| 최대 낙폭 (MDD) | [x] | 거래 기록 기반 |
| 일일 PnL 추적 + 시각화 | [x] | 게이지 표시 |
| 알파 / 베타 (Alpha / Beta) | [ ] | BTC 벤치마크 대비 |
| 정보 비율 (Information Ratio) | [ ] | |
| 월별 / 전략별 손익 히트맵 | [ ] | |
| 텔레그램 / 슬랙 실시간 알림 | [ ] | 진입·청산·손실 한도 도달 |
| 성과 리포트 PDF 내보내기 | [ ] | |

---

## AI 기능 (AI Features)

| 항목 | 상태 | 비고 |
|------|------|------|
| 진입 확인 (Entry Validation) | [x] | confidence < 65 차단 |
| 시장 국면 감지 (Regime Detection) | [x] | 실제 BTC OHLCV, 15분 캐시 |
| 손절 자기 분석 (Post-Loss Analysis) | [x] | 연속 3회 시 발동 |
| 청산 타이밍 보조 (Exit Assist) | [x] | 이익 구간 hold/close/tighten |
| 포지션별 스타일 자동 선택 | [x] | |
| AI 설정 UI (프로바이더/모델/키) | [x] | |
| 자가 학습 전략 최적화 | [ ] | 아래 TODO 7 참조 |

---

## 인프라 / 운영

| 항목 | 상태 | 비고 |
|------|------|------|
| 모의거래 (Paper Trading) | [x] | 실거래 전 의무 검증 |
| Walk-Forward 백테스트 | [x] | 과최적화 방지 |
| 슬리피지 시뮬레이션 | [x] | 백테스트 0.05% |
| GitHub 배포 (main / develop) | [x] | |
| 로컬 실행 (단일 서버) | [x] | |
| 서버 상시 구동 (클라우드 배포) | [ ] | Docker / Railway / EC2 |
| 봇 재시작 자동 복구 | [ ] | 프로세스 크래시 시 포지션 복원 |
| 거래소 연결 끊김 재시도 | [x] | WS 5초 재연결 |

---

---

## [ ] 7. 자가 학습 전략 최적화 (Self-Learning Strategy Optimizer)

**파일**: `bot.py`, `ai_analyst.py`, `scanner.py`, DB 신규 테이블
**우선순위**: 높음

### 구조 설계

#### 7-1. 신호 조합별 성과 추적 DB
```
신규 테이블: signal_performance
  - signals_key   : 신호 조합 해시 ("RSI과매도+망치형+MACD반등")
  - strategy_type : oversold_bounce / macd_momentum / ...
  - style         : scalping / short / mid / long
  - win_count, loss_count, total_pnl_pct, avg_hold_secs, updated_at
```
청산마다 신호 조합 키로 성과 기록 → 낮은 조합 자동 감점, 높은 조합 가점.

#### 7-2. LLM 피드백 루프
```
strategy_memory.json
  - 거래별 요약 (진입 신호, 보유시간, 손익률, 청산사유)
  - LLM 개선 제안 누적
  - 현재 적용 조정값 목록
```
흐름: 청산 → 메모리 기록 → 10건 누적 시 LLM 전달 → 가중치·파라미터 조정

#### 7-3. 점수 가중치 동적 조정
```python
# 신호별 성과에 따라 런타임에 STYLE_SCORE_WEIGHTS 자동 조정
# 예) "RSI 반등 시작" 최근 30건 승률 70% → rsi_bounce 가중치 +0.3
```

#### 7-4. 안전장치
- 가중치 조정 폭: 원본 대비 ±50% 이내
- 최소 샘플: 10건 미만 데이터 조정 불가
- Walk-Forward 검증: 최근 조정이 직전 20건에서 개선됐는지 확인
- 30일마다 가중치 부분 리셋 (드리프트 방지)

---

## [ ] 8. 캔들 패턴 고도화

**파일**: `scanner.py`

추가 예정:
- 상승장악형 (Bullish Harami)
- 상승 삼병사 (Three White Soldiers)
- 역헤드앤숄더 (Inverse H&S) — 5~10봉
- 이중 바닥 (Double Bottom)
- 볼린저밴드 하단 터치 + 반등 캔들 조합

---

## [ ] 9. 전략 빌더 ↔ 자동매매 봇 연동

**파일**: `bot.py`, `scanner.py`, `strategy/engine.py`

- DB에서 `is_active=True` 전략 목록을 봇 초기화 시 로드
- 내장 전략 점수와 함께 DB 전략 조건도 평가
- `strategy_type` 필드에 DB 전략 ID/이름 표기하여 실적 추적

---

## [ ] 10. 동적 종목 발굴

**파일**: `scanner.py`

- 업비트 전체 KRW 마켓 거래량 급증 상위 10종목 추출
- AI가 진입 가치 있는 종목 추천 → 해당 스캔 사이클 임시 추가

---

## AI 프로바이더 설정

```
# 무료 - Groq API (권장)
AI_PROVIDER=groq
GROQ_API_KEY=your_key_here   # https://console.groq.com

# 무료 - 로컬 Ollama
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2

# 유료 - Claude (가장 정확)
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
```
