"""
시장 스캐너 - 업비트 KRW 종목을 기술 지표로 분석하여 점수화 + 전략 자동 분류.

점수 기준 (총 100점, 스타일별 가중치 적용):
  RSI 과매도         기본 30점  (long에서 가중↑, scalping에서 가중↓)
  EMA 상승추세       기본 20점  (long에서 가중↑, scalping에서 가중↓)
  MACD 골든크로스    기본 30점  (scalping에서 가중↑, long에서 가중↓)
  거래량 증가        기본 20점  (scalping에서 가중↑, long에서 가중↓)

전략 자동 분류 (스타일별 SL/TP 차등 적용):
  oversold_bounce  - RSI 과매도 반등  (scalping 부적합, long에 유리)
  golden_cross     - EMA 골든크로스   (scalping 부적합, long에 유리)
  macd_momentum    - MACD 모멘텀      (scalping에 최적)
  volume_breakout  - 거래량 돌파      (scalping/short에 유리)
  standard         - 기본 글로벌 설정 사용

거래량 필터 (매매 스타일별):
  초단타(scalping) : 일 거래대금 50억 이상  → 상위 10~15종목
  단타  (short)    : 일 거래대금 20억 이상
  중장기(mid)      : 일 거래대금  5억 이상
  장기  (long)     : 일 거래대금  1억 이상
"""
import asyncio
import logging
import math
import pandas_ta as ta
import pandas as pd
from ..exchange.connector import ExchangeConnector
from typing import Optional

logger = logging.getLogger(__name__)

# 스캔 대상 고정 목록 (동적 발굴 실패 시 fallback)
SCAN_SYMBOLS = [
    "BTC/KRW", "ETH/KRW", "XRP/KRW", "SOL/KRW", "DOGE/KRW",
    "ADA/KRW", "AVAX/KRW", "LINK/KRW", "DOT/KRW", "ATOM/KRW",
    "MATIC/KRW", "LTC/KRW", "BCH/KRW", "ETC/KRW", "TRX/KRW",
    "NEAR/KRW", "APT/KRW", "OP/KRW", "SUI/KRW", "SEI/KRW",
    "SAND/KRW", "MANA/KRW", "ALGO/KRW", "HBAR/KRW", "VET/KRW",
]

# Binance / Bybit USDT 고정 목록 (동적 발굴 실패 시 fallback)
SCAN_SYMBOLS_USDT = [
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "DOGE/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "ATOM/USDT",
    "LTC/USDT", "BCH/USDT", "ETC/USDT", "TRX/USDT", "NEAR/USDT",
    "APT/USDT", "OP/USDT", "SUI/USDT", "ARB/USDT", "MATIC/USDT",
]

# 동적 종목 캐시 (업비트 전체 KRW 거래량 순위, 30분 갱신)
_dyn_all_krw: list[str] = []
_dyn_all_ts: float = 0.0
# 동적 종목 캐시 (Binance/Bybit USDT 거래량 순위, 30분 갱신)
_dyn_all_usdt: list[str] = []
_dyn_all_usdt_ts: float = 0.0
_DYN_TTL: float = 1800.0

# 매매 스타일별 최소 일 거래대금 (KRW)
STYLE_MIN_DAILY_VOLUME_KRW: dict[str, float] = {
    "scalping": 5_000_000_000,   # 50억  — 상위 10~15종목
    "short":    2_000_000_000,   # 20억  — 상위 15~20종목
    "mid":        500_000_000,   # 5억   — 상위 20~25종목
    "long":       100_000_000,   # 1억   — 전체 스캔
}

# 매매 스타일별 최소 일 거래대금 (USDT) — Binance/Bybit 기준
STYLE_MIN_DAILY_VOLUME_USDT: dict[str, float] = {
    "scalping": 3_500_000,   # $3.5M
    "short":    1_500_000,   # $1.5M
    "mid":        350_000,   # $350K
    "long":        70_000,   # $70K
}

TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440,
}

# 멀티 타임프레임 상위봉 매핑 (신호 확인용)
HTF_MAP: dict[str, str] = {
    "1m": "15m", "3m": "15m", "5m": "1h",
    "15m": "1h",  "30m": "4h", "1h": "4h",
    "4h": "1d",   "1d": "1d",
}

# ── 스타일별 지표 가중치 ─────────────────────────────────────────────────────
# scalping : MACD/거래량 중심 (빠른 모멘텀 포착)
# short    : 균형 (모든 지표 동등)
# mid      : EMA/RSI 중심 (추세 추종)
# long     : RSI/EMA 중심 (과매도 반등 + 추세 전환)
STYLE_SCORE_WEIGHTS: dict[str, dict[str, float]] = {
    "scalping": {"rsi": 0.4, "ema": 0.5, "macd": 1.6, "volume": 1.5, "candle": 0.8, "rsi_bounce": 0.7},
    "short":    {"rsi": 1.0, "ema": 1.0, "macd": 1.0, "volume": 1.0, "candle": 1.0, "rsi_bounce": 1.0},
    "mid":      {"rsi": 1.3, "ema": 1.5, "macd": 0.8, "volume": 0.7, "candle": 1.3, "rsi_bounce": 1.3},
    "long":     {"rsi": 1.6, "ema": 1.8, "macd": 0.5, "volume": 0.5, "candle": 1.5, "rsi_bounce": 1.5},
}

# ── 전략별 × 스타일별 SL/TP ─────────────────────────────────────────────────
# 같은 전략이라도 타임프레임이 다르면 적정 리스크 폭이 다름
STRATEGY_STYLE_CONFIGS: dict[str, dict[str, dict]] = {
    "oversold_bounce": {
        "scalping": {"sl_pct": 1.0,  "tp_pct": 2.0},
        "short":    {"sl_pct": 2.5,  "tp_pct": 4.0},   # 7.0 → 4.0: 15m에서 실현 가능한 수준
        "mid":      {"sl_pct": 5.0,  "tp_pct": 10.0},  # 15.0 → 10.0
        "long":     {"sl_pct": 10.0, "tp_pct": 22.0},  # 30.0 → 22.0
    },
    "golden_cross": {
        "scalping": {"sl_pct": 0.8,  "tp_pct": 1.8},
        "short":    {"sl_pct": 3.0,  "tp_pct": 5.5},   # 4.0/10.0 → 3.0/5.5
        "mid":      {"sl_pct": 5.0,  "tp_pct": 12.0},  # 6.0/20.0 → 5.0/12.0
        "long":     {"sl_pct": 10.0, "tp_pct": 25.0},  # 12.0/36.0 → 10.0/25.0
    },
    "macd_momentum": {
        "scalping": {"sl_pct": 0.8,  "tp_pct": 1.6},
        "short":    {"sl_pct": 2.5,  "tp_pct": 4.5},   # 3.0/9.0 → 2.5/4.5
        "mid":      {"sl_pct": 4.5,  "tp_pct": 9.0},   # 5.0/16.0 → 4.5/9.0
        "long":     {"sl_pct": 9.0,  "tp_pct": 20.0},  # 11.0/32.0 → 9.0/20.0
    },
    "volume_breakout": {
        "scalping": {"sl_pct": 1.0,  "tp_pct": 2.2},
        "short":    {"sl_pct": 2.5,  "tp_pct": 5.0},   # 3.5/12.0 → 2.5/5.0
        "mid":      {"sl_pct": 4.5,  "tp_pct": 10.0},  # 5.5/18.0 → 4.5/10.0
        "long":     {"sl_pct": 8.0,  "tp_pct": 20.0},  # 10.0/30.0 → 8.0/20.0
    },
    "standard": {
        "scalping": {"sl_pct": None, "tp_pct": None},
        "short":    {"sl_pct": None, "tp_pct": None},
        "mid":      {"sl_pct": None, "tp_pct": None},
        "long":     {"sl_pct": None, "tp_pct": None},
    },
}

_STRATEGY_LABELS: dict[str, str] = {
    "oversold_bounce": "RSI 과매도 반등",
    "golden_cross":    "EMA 골든크로스",
    "macd_momentum":   "MACD 모멘텀",
    "volume_breakout": "거래량 돌파",
    "standard":        "표준",
}

# bot.py 하위 호환용 (short 기준 SL/TP)
STRATEGY_CONFIGS: dict[str, dict] = {
    k: {
        "label":   _STRATEGY_LABELS[k],
        "sl_pct":  v["short"]["sl_pct"],
        "tp_pct":  v["short"]["tp_pct"],
    }
    for k, v in STRATEGY_STYLE_CONFIGS.items()
}


def _detect_candle_patterns(df: pd.DataFrame) -> tuple[list[str], int]:
    """
    주요 반등 캔들 패턴 감지 (최근 3봉 기준).

    감지 패턴:
      망치형(Hammer)         - 아래 꼬리 ≥ 2 × 몸통, 위 꼬리 작음
      불리시 인걸핑           - 이전 하락봉을 현재 상승봉이 완전히 감쌈
      피어싱 라인             - 이전 하락봉의 중간 이상 상승 마감
      도지 저점 반전          - 몸통 극소 + 아래 꼬리 존재 → 매도세 소진
      모닝스타               - 하락봉 → 도지 → 상승봉 3봉 패턴

    Returns: (signals, score_bonus)
    """
    if len(df) < 3:
        return [], 0

    signals: list[str] = []
    score = 0

    o0, h0, l0, c0 = (float(df[c].iloc[-1]) for c in ("open", "high", "low", "close"))
    o1, h1, l1, c1 = (float(df[c].iloc[-2]) for c in ("open", "high", "low", "close"))
    o2, _,  _,  c2 = (float(df[c].iloc[-3]) for c in ("open", "high", "low", "close"))

    body0  = abs(c0 - o0)
    total0 = h0 - l0 if h0 > l0 else 1e-9
    body1  = abs(c1 - o1)

    lower_wick0 = min(o0, c0) - l0
    upper_wick0 = h0 - max(o0, c0)

    # ── 망치형 / 핀바 ──────────────────────────────────────────────────────
    if lower_wick0 >= 2.0 * body0 and upper_wick0 <= 0.5 * body0 and body0 > 0:
        signals.append("망치형 캔들")
        score += 15

    # ── 불리시 인걸핑 ──────────────────────────────────────────────────────
    if (c1 < o1              # 이전: 하락봉
            and c0 > o0      # 현재: 상승봉
            and o0 <= c1     # 현재 시가 ≤ 이전 종가
            and c0 >= o1):   # 현재 종가 ≥ 이전 시가
        signals.append("불리시 인걸핑")
        score += 18

    # ── 피어싱 라인 ────────────────────────────────────────────────────────
    mid1 = (o1 + c1) / 2
    if (c1 < o1 and c0 > o0
            and o0 < l1          # 시가가 이전 저가 아래
            and c0 > mid1        # 종가가 이전 봉 중간 이상
            and c0 < o1):        # 종가가 이전 시가 미만(인걸핑과 구분)
        signals.append("피어싱 라인")
        score += 12

    # ── 도지 저점 반전 ─────────────────────────────────────────────────────
    if body0 / total0 < 0.15 and lower_wick0 > total0 * 0.3:
        signals.append("도지 저점 반전")
        score += 10

    # ── 모닝스타 (3봉) ─────────────────────────────────────────────────────
    if (c2 < o2                         # 1봉: 하락
            and body1 < body0 * 0.5     # 2봉: 작은 몸통(도지성)
            and c0 > o0                 # 3봉: 상승
            and c0 > (o2 + c2) / 2):    # 3봉 종가가 1봉 중간 이상
        signals.append("모닝스타")
        score += 20

    return signals, score


def _detect_rsi_bounce(
    close: pd.Series, rsi_series: pd.Series
) -> tuple[list[str], int, bool]:
    """
    RSI 저점 반등 및 불리시 다이버전스 감지.

    감지 항목:
      과매도 반등   - RSI가 45 이하에서 2봉 연속 상승 (추세 전환 초입)
      단기 반등     - RSI < 35에서 1봉 반등
      불리시 다이버전스 - 가격은 전 저점 근처인데 RSI는 전 저점보다 높음
                        (매도세 약화 신호)

    Returns: (signals, score_bonus, is_bounce)
    """
    if len(close) < 10 or rsi_series is None:
        return [], 0, False

    rsi_vals = rsi_series.dropna()
    if len(rsi_vals) < 4:
        return [], 0, False

    signals: list[str] = []
    score = 0
    is_bounce = False

    rsi_now   = float(rsi_vals.iloc[-1])
    rsi_prev  = float(rsi_vals.iloc[-2])
    rsi_prev2 = float(rsi_vals.iloc[-3])

    # ── 과매도 구간 2봉 연속 RSI 상승 ─────────────────────────────────────
    if rsi_now > rsi_prev > rsi_prev2 and rsi_prev2 < 45:
        signals.append(f"RSI 반등 시작 ({rsi_prev2:.1f}→{rsi_now:.1f})")
        score += 14
        is_bounce = True

    # ── 단기 과매도 1봉 반등 ──────────────────────────────────────────────
    elif rsi_prev < 35 and rsi_now > rsi_prev:
        signals.append(f"RSI 과매도 반등 ({rsi_prev:.1f}→{rsi_now:.1f})")
        score += 10
        is_bounce = True

    # ── 불리시 다이버전스 ─────────────────────────────────────────────────
    # 최근 5~14봉 구간에서 가격 저점 vs RSI 저점 비교
    lookback = min(14, len(close) - 1)
    if lookback >= 5:
        window_close = close.iloc[-lookback - 1:-1]
        window_rsi   = rsi_vals.iloc[-lookback - 1:-1] if len(rsi_vals) > lookback else rsi_vals

        if len(window_close) > 0 and len(window_rsi) > 0:
            prev_low_price = float(window_close.min())
            prev_low_rsi   = float(window_rsi.min())
            close_now      = float(close.iloc[-1])

            # 가격은 이전 저점 근처인데 RSI는 더 높음 → 하락 모멘텀 약화
            if (close_now <= prev_low_price * 1.03
                    and rsi_now > prev_low_rsi + 4
                    and rsi_now < 55):
                signals.append(f"RSI 불리시 다이버전스 ({prev_low_rsi:.1f}→{rsi_now:.1f})")
                score += 18
                is_bounce = True

    return signals, score, is_bounce


def _detect_advanced_patterns(df: pd.DataFrame) -> tuple[list[str], int]:
    """
    고급 캔들 패턴 감지 (TODO 8).

    감지 패턴:
      상승 하라미          - 이전 큰 하락봉 안에 현재 작은 상승봉
      상승 삼병사          - 3봉 연속 상승, 종가·시가 계속 상승
      이중 바닥            - 최근 20봉 내 유사한 두 저점 + 중간 고점
      볼린저밴드 하단 반등 - 이전봉 BB 하단 터치 → 현재봉 상승 마감
      역헤드앤숄더         - 최근 15봉 중앙 저점이 양측보다 낮고 유사한 어깨
    """
    if len(df) < 20:
        return [], 0

    signals: list[str] = []
    score = 0

    o0 = float(df["open"].iloc[-1]);  c0 = float(df["close"].iloc[-1])
    o1 = float(df["open"].iloc[-2]);  c1 = float(df["close"].iloc[-2])
    o2 = float(df["open"].iloc[-3]);  c2 = float(df["close"].iloc[-3])

    body0 = abs(c0 - o0)
    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)

    # ── 상승 하라미 ─────────────────────────────────────────────────────────
    if (c1 < o1                              # 이전: 하락봉
            and c0 > o0                      # 현재: 상승봉
            and min(o0, c0) >= min(o1, c1)   # 현재 몸통이 이전 몸통 내부
            and max(o0, c0) <= max(o1, c1)
            and body0 < body1 * 0.7):        # 현재 몸통이 이전의 70% 미만
        signals.append("상승 하라미")
        score += 12

    # ── 상승 삼병사 ─────────────────────────────────────────────────────────
    if (c0 > o0 and c1 > o1 and c2 > o2   # 3봉 모두 상승봉
            and c0 > c1 > c2               # 종가 계속 상승
            and o0 > o1 > o2):             # 시가도 계속 상승
        signals.append("상승 삼병사")
        score += 20

    # ── 이중 바닥 ───────────────────────────────────────────────────────────
    window = df.iloc[-20:]
    lows  = window["low"].values
    highs = window["high"].values
    low1_idx = int(lows[:10].argmin())
    low2_idx = int(lows[10:].argmin()) + 10
    low1 = float(lows[low1_idx])
    low2 = float(lows[low2_idx])
    if low2_idx > low1_idx + 2 and low1 > 0:
        mid_high = float(highs[low1_idx + 1: low2_idx].max()) if low2_idx > low1_idx + 1 else 0.0
        if (abs(low1 - low2) / low1 < 0.03          # 두 저점 3% 이내
                and mid_high > max(low1, low2) * 1.03  # 중간 고점이 저점보다 3% 이상
                and c0 > low2 * 1.005):                # 현재 종가가 두 번째 저점 위
            signals.append("이중 바닥")
            score += 22

    # ── 볼린저밴드 하단 반등 ────────────────────────────────────────────────
    try:
        bb = ta.bbands(df["close"], length=20, std=2.0)
        if bb is not None and not bb.empty and len(bb.dropna()) >= 2:
            bb_lower = float(bb.iloc[-2, 0])   # 이전봉 하단 밴드
            l1 = float(df["low"].iloc[-2])
            if l1 <= bb_lower and c0 > o0:
                signals.append("볼린저밴드 하단 반등")
                score += 16
    except Exception:
        pass

    # ── 역헤드앤숄더 ────────────────────────────────────────────────────────
    if len(df) >= 15:
        lows_15 = df["low"].iloc[-15:].values
        head_idx = int(lows_15.argmin())
        if 3 <= head_idx <= 11:
            head = float(lows_15[head_idx])
            left_min  = float(lows_15[:head_idx].min())
            right_min = float(lows_15[head_idx + 1:].min()) if head_idx < 14 else head
            if (head > 0 and left_min > head * 1.015
                    and right_min > head * 1.015
                    and abs(left_min - right_min) / left_min < 0.06   # 양 어깨 6% 이내
                    and c0 > float(df["close"].iloc[-15 + head_idx])): # 현재가 head보다 위
                signals.append("역헤드앤숄더")
                score += 25

    return signals, score


def _score_mean_reversion(df: pd.DataFrame) -> tuple[list[str], int, float, float]:
    """
    평균 회귀 신호 점수화.
    BB 하단 접근 + RSI 과매도 + 거래량 감소 조합으로 횡보장 매수 진입점 포착.
    Returns: (signals, score, bb_mid, bb_lower)
    """
    signals: list[str] = []
    score = 0
    close = df["close"]
    bb_mid = 0.0
    bb_lower = 0.0

    # BB 하단 접근 (최대 35점)
    try:
        bb = ta.bbands(close, length=20, std=2.0)
        if bb is not None and not bb.empty:
            cols = bb.columns.tolist()   # [BBL, BBM, BBU, BBB, BBP]
            bbl = float(bb[cols[0]].iloc[-1])
            bbm = float(bb[cols[1]].iloc[-1])
            bbu = float(bb[cols[2]].iloc[-1])
            price = float(close.iloc[-1])
            if math.isnan(bbl) or math.isnan(bbm) or math.isnan(bbu):
                raise ValueError("BB NaN")
            bb_mid = bbm
            bb_lower = bbl
            if bbu > bbl:
                bb_pos = (price - bbl) / (bbu - bbl)   # 0 = 하단, 1 = 상단
                if bb_pos <= 0.10:
                    score += 35
                    signals.append(f"BB 하단 터치 ({bb_pos:.2f})")
                elif bb_pos <= 0.20:
                    score += 22
                    signals.append(f"BB 하단 접근 ({bb_pos:.2f})")
                elif bb_pos <= 0.30:
                    score += 10
                    signals.append(f"BB 하단 근접 ({bb_pos:.2f})")
    except Exception:
        pass

    # RSI 과매도 (최대 30점)
    try:
        rsi_s = ta.rsi(close, length=14)
        if rsi_s is not None and not rsi_s.empty:
            rsi = float(rsi_s.iloc[-1])
            if rsi <= 25:
                score += 30
                signals.append(f"MR RSI 극과매도 ({rsi:.1f})")
            elif rsi <= 32:
                score += 22
                signals.append(f"MR RSI 강과매도 ({rsi:.1f})")
            elif rsi <= 40:
                score += 12
                signals.append(f"MR RSI 과매도 ({rsi:.1f})")
    except Exception:
        pass

    # 거래량 감소 (횡보장 특성, +10점)
    try:
        volume = df["volume"]
        if len(volume) >= 6:
            recent_avg = float(volume.iloc[-6:-1].mean())
            vol_now = float(volume.iloc[-1])
            if recent_avg > 0 and vol_now / recent_avg < 0.7:
                score += 10
                signals.append("거래량 감소 (횡보 확인)")
    except Exception:
        pass

    return signals, min(score, 75), bb_mid, bb_lower


def _daily_volume_krw(df: pd.DataFrame, timeframe: str) -> float:
    """캔들 OHLCV로 일 거래대금(KRW) 추정."""
    tf_min = TIMEFRAME_MINUTES.get(timeframe, 60)
    candles_per_day = max(1, int(1440 / tf_min))
    n = min(candles_per_day, len(df))
    recent = df.tail(n)
    vol_sum = float((recent["volume"] * recent["close"]).sum())
    if n < candles_per_day:
        vol_sum = vol_sum * candles_per_day / n
    return vol_sum


def _score(df: pd.DataFrame, symbol: str, style: str = "short", htf_df: Optional[pd.DataFrame] = None) -> dict:
    """
    기술 지표 점수 계산 + 전략 자동 분류.
    스타일별 가중치를 적용하여 해당 매매 방식에 맞는 신호를 우선시한다.
    """
    try:
        # ── 미완성 현재봉 제외 (bar-close strategy) ──────────────────────────
        # 신호 감지는 반드시 닫힌 봉 기준으로만 수행.
        # 미완성봉 포함 시: MACD 크로스가 봉 마감 전 사라지거나 고점 진입 유발.
        # 진입 가격은 _open_position에서 실시간 ticker로 별도 조회하므로 무관.
        current_price = float(df["close"].iloc[-1])
        df = df.iloc[:-1]
        if len(df) < 60:
            return {
                "symbol": symbol, "score": 0, "rsi": 50.0, "price": current_price,
                "signals": [], "strategy_type": "standard", "strategy_label": "표준",
                "sl_pct": None, "tp_pct": None, "style": style,
                "volume_ratio": 0.0, "price_change_pct": 0.0,
                "mtf_trend": "neutral", "mtf_confirmed": True,
                "adx": 0.0, "mr_score": 0, "mr_signals": [], "bb_mid": 0.0, "bb_lower": 0.0,
                "macd_direction": "neutral", "bb_pos": 0.5, "atr_pct": 1.0,
            }

        weights = STYLE_SCORE_WEIGHTS.get(style, STYLE_SCORE_WEIGHTS["short"])
        close = df["close"]
        volume = df["volume"]
        score = 0
        signals = []

        # ── RSI (기본 30점, 가중치 적용) ────────────────────────────────────
        rsi_s = ta.rsi(close, length=14)
        rsi = float(rsi_s.iloc[-1]) if rsi_s is not None and not rsi_s.empty else 50.0
        if math.isnan(rsi):
            rsi = 50.0

        rsi_strong_oversold = False
        rsi_oversold = False
        rsi_pts = 0
        if 20 <= rsi <= 35:
            rsi_pts = max(int(30 * (1 - abs(rsi - 30) / 10)), 10)
            signals.append(f"RSI 강한 과매도 ({rsi:.1f})")
            rsi_strong_oversold = True
        elif 35 < rsi <= 45:
            rsi_pts = 15
            signals.append(f"RSI 과매도 ({rsi:.1f})")
            rsi_oversold = True
        elif 45 < rsi <= 55:
            rsi_pts = 5
        elif 55 < rsi <= 70:
            rsi_pts = 8
            signals.append(f"RSI 상승 모멘텀 ({rsi:.1f})")
        score += int(rsi_pts * weights["rsi"])

        # ── EMA 추세 (기본 20점, 가중치 적용) ──────────────────────────────
        ema20 = ta.ema(close, length=20)
        ema50 = ta.ema(close, length=50)
        golden_cross = False
        above_ema20 = False
        ema_pts = 0
        if ema20 is not None and ema50 is not None and len(ema20.dropna()) > 1 and len(ema50.dropna()) > 1:
            e20_now  = float(ema20.iloc[-1])
            e50_now  = float(ema50.iloc[-1])
            e20_prev = float(ema20.iloc[-2])
            e50_prev = float(ema50.iloc[-2])
            curr = float(close.iloc[-1])
            if e20_now > e50_now:
                ema_pts += 12
                signals.append("상승추세 (EMA20 > EMA50)")
            if e20_now > e50_now and e20_prev <= e50_prev:
                golden_cross = True
                signals.append("EMA 골든크로스 ✓")
            if curr > e20_now:
                ema_pts += 8
                signals.append("가격 EMA20 상단")
                above_ema20 = True
        score += int(ema_pts * weights["ema"])

        # ── MACD (기본 30점, 가중치 적용) ───────────────────────────────────
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        macd_cross = False
        macd_bull = False
        macd_pts = 0
        macd_direction = "neutral"
        if macd_df is not None and len(macd_df.dropna()) >= 2:
            cols = macd_df.columns.tolist()
            ml_now  = float(macd_df[cols[0]].iloc[-1])
            ml_prev = float(macd_df[cols[0]].iloc[-2])
            sg_now  = float(macd_df[cols[2]].iloc[-1])
            sg_prev = float(macd_df[cols[2]].iloc[-2])
            if ml_now > sg_now and ml_prev <= sg_prev:
                macd_pts = 30
                signals.append("MACD 골든크로스 ↑")
                macd_cross = True
                macd_direction = "cross_up"
            elif ml_now > sg_now:
                macd_pts = 15
                signals.append("MACD 강세 구간")
                macd_bull = True
                macd_direction = "bullish"
            elif ml_now > ml_prev:
                macd_pts = 5
                signals.append("MACD 반등 중")
                macd_direction = "recovering"
            elif ml_now < sg_now and ml_prev >= sg_prev:
                macd_direction = "cross_down"
            elif ml_now < sg_now:
                macd_direction = "bearish"
        score += int(macd_pts * weights["macd"])

        # ── 거래량 (기본 20점, 가중치 적용) ────────────────────────────────
        volume_breakout = False
        vol_pts = 0
        vol_ratio_val = 0.0
        if len(volume) >= 22:
            vol_avg = float(volume.iloc[-22:-2].mean())
            vol_now = float(volume.iloc[-2])
            if vol_avg > 0:
                ratio = vol_now / vol_avg
                vol_ratio_val = ratio
                if ratio >= 3.0:
                    vol_pts = 20
                    signals.append(f"거래량 급증 ({ratio:.1f}x)")
                    volume_breakout = True
                elif ratio >= 2.0:
                    vol_pts = 12
                    signals.append(f"거래량 증가 ({ratio:.1f}x)")
                elif ratio >= 1.5:
                    vol_pts = 6
                    signals.append(f"거래량 소폭 증가 ({ratio:.1f}x)")
        score += int(vol_pts * weights["volume"])

        # ── 최근 3봉 가격 변화율 (급등 감지용) ─────────────────────────────
        # current_price: 실시간 현재가 / close.iloc[-3]: 3 확정봉 전 종가
        price_3ago = float(close.iloc[-3]) if len(close) >= 4 else current_price
        price_change_pct_val = (current_price - price_3ago) / price_3ago * 100 if price_3ago > 0 else 0.0

        # ── 기본 캔들 패턴 감지 ─────────────────────────────────────────────
        candle_signals, candle_pts = _detect_candle_patterns(df)
        signals.extend(candle_signals)
        score += int(candle_pts * weights["candle"])
        has_reversal_candle = len(candle_signals) > 0

        # ── 고급 캔들 패턴 (TODO 8) ──────────────────────────────────────────
        adv_signals, adv_pts = _detect_advanced_patterns(df)
        signals.extend(adv_signals)
        score += int(adv_pts * weights["candle"])
        has_reversal_candle = has_reversal_candle or len(adv_signals) > 0

        # ── RSI 저점 반등 / 불리시 다이버전스 ──────────────────────────────
        rsi_bounce_signals, rsi_bounce_pts, rsi_is_bounce = _detect_rsi_bounce(close, rsi_s)
        signals.extend(rsi_bounce_signals)
        score += int(rsi_bounce_pts * weights["rsi_bounce"])

        # ── ADX (횡보/추세 강도) ─────────────────────────────────────────
        adx_val = 0.0
        try:
            adx_df = ta.adx(df["high"], df["low"], close, length=14)
            if adx_df is not None and not adx_df.empty:
                adx_col = [c for c in adx_df.columns if c.startswith("ADX_")]
                if adx_col:
                    adx_val = float(adx_df[adx_col[0]].dropna().iloc[-1])
        except Exception:
            pass

        # ── 추세 지속 점수 (ADX + EMA 정배열) ───────────────────────────────
        # RSI 과매도 신호 없이도 추세장에서 진입 기회를 포착하기 위한 보정.
        # ADX >= 25: 추세 진행 중, ADX >= 35: 강한 추세.
        # EMA20 > EMA50 (ema_pts >= 12) 조건을 함께 요구해 과진입 방지.
        if adx_val >= 25 and ema_pts >= 12:
            trend_bonus = 20 if adx_val >= 35 else 12
            score += trend_bonus
            signals.append(f"{'강한 ' if adx_val >= 35 else ''}추세장 (ADX {adx_val:.0f})")

        # RSI 추세 구간 (50~70) + MACD 강세 → 추세 지속 확인 신호
        # 과매도(rsi_oversold) 신호와 중복 방지
        if 50 <= rsi <= 70 and (macd_bull or macd_cross) and not rsi_oversold and not rsi_strong_oversold:
            score += int(8 * weights["rsi"])
            signals.append(f"RSI 추세 구간 ({rsi:.0f})")

        # ── 평균 회귀 점수 계산 ──────────────────────────────────────────
        mr_signals, mr_score, bb_mid, bb_lower = _score_mean_reversion(df)

        # ── 전략 자동 분류 ──────────────────────────────────────────────────
        # 우선순위:
        #   1. RSI 강한 과매도 → oversold_bounce
        #   2. RSI 반등 + 캔들 패턴 → oversold_bounce (하락봉 저점 진입)
        #   3. EMA 골든크로스 → golden_cross
        #   4. MACD 크로스 + 거래량 돌파 → volume_breakout
        #   5. MACD 크로스 → macd_momentum
        #   6. 거래량 돌파 (EMA 상단 또는 RSI 반등 확인) → volume_breakout
        #   7. MACD 강세 + 강한 추세(ADX>=25) → macd_momentum
        #   8. RSI 반등만 단독 → oversold_bounce (낮은 신뢰도)
        if rsi_strong_oversold:
            strategy_type = "oversold_bounce"
        elif rsi_is_bounce and has_reversal_candle:
            strategy_type = "oversold_bounce"
        elif golden_cross:
            strategy_type = "golden_cross"
        elif macd_cross and volume_breakout:
            strategy_type = "volume_breakout"
        elif macd_cross and rsi <= 65:
            # RSI > 65: 이미 과매수 구간 — MACD 크로스라도 추격 진입 금지
            strategy_type = "macd_momentum"
        elif macd_cross:
            # RSI > 65 + MACD cross: 과매수 추격 진입 → standard로 분류 (SL/TP 기본값 사용)
            strategy_type = "standard"
        elif volume_breakout and (above_ema20 or rsi_is_bounce):
            strategy_type = "volume_breakout"
        elif macd_bull and adx_val >= 25 and ema_pts >= 12 and rsi <= 65:
            # 추세 지속: MACD 강세 구간 + 강한 추세 + EMA 정배열 (과매수 제외)
            strategy_type = "macd_momentum"
        elif rsi_is_bounce:
            strategy_type = "oversold_bounce"
        else:
            strategy_type = "standard"

        # 스타일별 SL/TP 적용
        style_cfg = STRATEGY_STYLE_CONFIGS.get(strategy_type, {}).get(style, {})
        sl_pct = style_cfg.get("sl_pct")
        tp_pct = style_cfg.get("tp_pct")

        # ── ATR 기반 SL 하한 보정 ───────────────────────────────────────────
        # 고정 SL이 코인 변동성(ATR)보다 좁으면 정상 흔들림에 손절 발동.
        # sl_pct < 1.5 * ATR% 이면 ATR 기준으로 확대하고 TP도 2:1 R:R 유지.
        atr_pct_val = 1.0
        try:
            atr_s = ta.atr(df["high"], df["low"], close, length=14)
            if atr_s is not None and not atr_s.empty:
                atr_pct_val = float(atr_s.dropna().iloc[-1]) / current_price * 100
                atr_pct = atr_pct_val
                if sl_pct is not None and sl_pct < atr_pct * 1.5:
                    sl_pct = round(atr_pct * 1.5, 2)
                    if tp_pct is not None:
                        tp_pct = max(tp_pct, round(sl_pct * 2.0, 2))
        except Exception:
            pass

        # ── BB 포지션 (0=하단, 0.5=중간, 1=상단) ────────────────────────────
        bb_pos_val = 0.5
        if bb_mid > 0 and bb_lower > 0:
            bb_upper_est = 2 * bb_mid - bb_lower
            _p = float(close.iloc[-1])
            if bb_upper_est > bb_lower:
                bb_pos_val = round(max(0.0, min(1.0, (_p - bb_lower) / (bb_upper_est - bb_lower))), 2)

        # ── 멀티 타임프레임 추세 확인 (TODO: 멀티TF) ────────────────────────
        mtf_trend = "neutral"
        mtf_confirmed = True
        if htf_df is not None and len(htf_df) >= 20:
            htf_close = htf_df["close"]
            htf_e20 = ta.ema(htf_close, length=20)
            htf_e50 = ta.ema(htf_close, length=50)
            if htf_e20 is not None and htf_e50 is not None:
                valid_e20 = htf_e20.dropna()
                valid_e50 = htf_e50.dropna()
                if len(valid_e20) > 0 and len(valid_e50) > 0:
                    e20 = float(valid_e20.iloc[-1])
                    e50 = float(valid_e50.iloc[-1])
                    htf_price = float(htf_close.iloc[-1])
                    if htf_price > e20 and e20 > e50:
                        mtf_trend = "bullish"
                    elif htf_price < e20 and e20 < e50:
                        mtf_trend = "bearish"
                        mtf_confirmed = False  # 상위봉 하락추세 → 진입 기준 강화

        return {
            "symbol":           symbol,
            "score":            min(score, 100),
            "rsi":              round(rsi, 1),
            "price":            current_price,
            "signals":          signals,
            "strategy_type":    strategy_type,
            "strategy_label":   _STRATEGY_LABELS[strategy_type],
            "sl_pct":           sl_pct,
            "tp_pct":           tp_pct,
            "style":            style,
            # 급등 감지용
            "volume_ratio":     round(vol_ratio_val, 2),
            "price_change_pct": round(price_change_pct_val, 2),
            # 멀티 타임프레임
            "mtf_trend":        mtf_trend,
            "mtf_confirmed":    mtf_confirmed,
            # ADX + 평균 회귀 (TODO 25)
            "adx":              round(adx_val, 1),
            "mr_score":         mr_score,
            "mr_signals":       mr_signals,
            "bb_mid":           round(bb_mid, 2),
            "bb_lower":         round(bb_lower, 2),
            # AI 분석용 추가 지표
            "macd_direction":   macd_direction,
            "bb_pos":           bb_pos_val,
            "atr_pct":          round(atr_pct_val, 2),
        }

    except Exception as e:
        logger.debug(f"Score error {symbol}: {e}")
        return {
            "symbol": symbol, "score": 0, "rsi": 50.0, "price": 0.0, "signals": [],
            "strategy_type": "standard", "strategy_label": "표준",
            "sl_pct": None, "tp_pct": None, "style": style,
            "volume_ratio": 0.0, "price_change_pct": 0.0,
            "mtf_trend": "neutral", "mtf_confirmed": True,
            "adx": 0.0, "mr_score": 0, "mr_signals": [], "bb_mid": 0.0, "bb_lower": 0.0,
            "macd_direction": "neutral", "bb_pos": 0.5, "atr_pct": 1.0,
        }


async def _fetch_dynamic_symbols(
    connector: ExchangeConnector, style: str, exchange_id: str = "upbit"
) -> list[str]:
    """
    24h 거래대금 기준 상위 종목 동적 발굴 (TODO 10).
    30분 캐시 적용 — 스타일별 상위 N 슬라이스만 다름.
    업비트: KRW 마켓, Binance/Bybit: USDT 마켓.
    """
    global _dyn_all_krw, _dyn_all_ts, _dyn_all_usdt, _dyn_all_usdt_ts
    import time

    top_n = {"scalping": 15, "short": 20, "mid": 30, "long": 40}.get(style, 20)
    is_upbit = exchange_id == "upbit"
    quote = "KRW" if is_upbit else "USDT"
    btc_sym = f"BTC/{quote}"
    fallback = SCAN_SYMBOLS if is_upbit else SCAN_SYMBOLS_USDT

    # 캐시 히트
    if is_upbit:
        if time.time() - _dyn_all_ts < _DYN_TTL and _dyn_all_krw:
            symbols = _dyn_all_krw[:top_n]
            if btc_sym not in symbols:
                symbols = [btc_sym] + symbols
            return symbols
    else:
        if time.time() - _dyn_all_usdt_ts < _DYN_TTL and _dyn_all_usdt:
            symbols = _dyn_all_usdt[:top_n]
            if btc_sym not in symbols:
                symbols = [btc_sym] + symbols
            return symbols

    try:
        # 마켓 목록을 먼저 로드해 quote 통화 심볼만 필터링.
        # fetch_tickers() 에 전체 마켓을 전달하면 URL이 너무 길어져 업비트 400 에러 발생.
        await asyncio.wait_for(connector._exchange.load_markets(), timeout=15)
        target_symbols = [
            s for s in connector._exchange.markets
            if s.endswith(f"/{quote}")
        ]
        tickers = await asyncio.wait_for(
            connector._exchange.fetch_tickers(target_symbols),
            timeout=20,
        )
        pairs = [
            (sym, float(data.get("quoteVolume") or 0))
            for sym, data in tickers.items()
        ]
        pairs.sort(key=lambda x: x[1], reverse=True)
        sym_list = [sym for sym, _ in pairs]

        if is_upbit:
            _dyn_all_krw = sym_list
            _dyn_all_ts = time.time()
            logger.info(f"동적 종목 발굴: 업비트 KRW {len(_dyn_all_krw)}개 갱신")
        else:
            _dyn_all_usdt = sym_list
            _dyn_all_usdt_ts = time.time()
            logger.info(f"동적 종목 발굴: {exchange_id} USDT {len(_dyn_all_usdt)}개 갱신")
    except Exception as e:
        logger.warning(f"동적 종목 발굴 실패, 고정 목록 사용: {e}")
        return fallback

    cache = _dyn_all_krw if is_upbit else _dyn_all_usdt
    symbols = cache[:top_n]
    if btc_sym not in symbols:
        symbols = [btc_sym] + symbols
    return symbols


async def scan_market(
    timeframe: str = "1h", style: str = "short", exchange_id: str = "upbit"
) -> list[dict]:
    """
    전체 종목 스캔.
    - TODO 10: 동적 종목 발굴 (거래량 상위 — KRW 또는 USDT 마켓)
    - 멀티 타임프레임: 상위봉 OHLCV 추가 fetch → mtf_confirmed 산출
    - 스타일별 거래량 필터 + 가중치 점수 → 내림차순 정렬
    - exchange_id: "upbit" | "binance" | "bybit"
    """
    connector = ExchangeConnector(exchange_id=exchange_id, is_paper=True)
    is_upbit = exchange_id == "upbit"
    vol_table = STYLE_MIN_DAILY_VOLUME_KRW if is_upbit else STYLE_MIN_DAILY_VOLUME_USDT
    min_vol = vol_table.get(style, 10_000_000_000 if is_upbit else 3_500_000)
    htf = HTF_MAP.get(timeframe, timeframe)
    results = []

    try:
        symbols = await _fetch_dynamic_symbols(connector, style, exchange_id)

        for symbol in symbols:
            try:
                df = await asyncio.wait_for(
                    connector.fetch_ohlcv(symbol, timeframe, limit=150),
                    timeout=12,
                )
                if len(df) < 60:
                    continue

                daily_vol = _daily_volume_krw(df, timeframe)
                if daily_vol < min_vol:
                    logger.debug(
                        f"Skip {symbol}: 거래대금 {daily_vol/1e8:.0f}억 < 기준 {min_vol/1e8:.0f}억"
                    )
                    continue

                # 멀티 타임프레임 확인 (HTF 가 주 TF와 다를 때만 추가 fetch)
                htf_df = None
                if htf != timeframe:
                    try:
                        htf_df = await asyncio.wait_for(
                            connector.fetch_ohlcv(symbol, htf, limit=60),
                            timeout=12,
                        )
                    except Exception:
                        pass  # HTF 실패 시 mtf_confirmed=True(기본) 유지

                results.append(_score(df, symbol, style, htf_df=htf_df))
                await asyncio.sleep(0.15)
            except asyncio.TimeoutError:
                logger.debug(f"Timeout scanning {symbol}")
            except Exception as e:
                logger.debug(f"Skip {symbol}: {e}")
    finally:
        await connector.close()

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── 선물 전용 스캔 ────────────────────────────────────────────────────────────

FUTURES_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
    "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
    "LINK/USDT", "DOT/USDT", "NEAR/USDT", "LTC/USDT",
    "BCH/USDT", "APT/USDT", "OP/USDT", "ARB/USDT",
]

# ── 선물 전용 전략 설정 ───────────────────────────────────────────────────────
# 선물은 레버리지 특성상 SL/TP 폭이 현물보다 좁음 (빠른 청산 방지)
FUTURES_STRATEGY_STYLE_CONFIGS: dict[str, dict[str, dict]] = {
    "futures_trend": {           # ADX 추세 추종 — 추세 지속 기대, 넓은 TP
        "scalping": {"sl_pct": 1.0,  "tp_pct": 2.5},
        "short":    {"sl_pct": 1.5,  "tp_pct": 5.0},
        "mid":      {"sl_pct": 2.5,  "tp_pct": 8.0},
        "long":     {"sl_pct": 4.0,  "tp_pct": 13.0},
    },
    "futures_breakout": {        # BB/ATR 돌파 — 빠른 진입·청산
        "scalping": {"sl_pct": 1.2,  "tp_pct": 3.0},
        "short":    {"sl_pct": 1.2,  "tp_pct": 3.5},
        "mid":      {"sl_pct": 2.0,  "tp_pct": 6.0},
        "long":     {"sl_pct": 3.5,  "tp_pct": 10.0},
    },
    "futures_momentum": {        # MACD+RSI 모멘텀 — 중간 보유
        "scalping": {"sl_pct": 1.1,  "tp_pct": 2.6},
        "short":    {"sl_pct": 1.3,  "tp_pct": 4.0},
        "mid":      {"sl_pct": 2.2,  "tp_pct": 6.5},
        "long":     {"sl_pct": 3.5,  "tp_pct": 11.0},
    },
}

FUTURES_STRATEGY_LABELS: dict[str, str] = {
    "futures_trend":    "추세 추종",
    "futures_breakout": "돌파 진입",
    "futures_momentum": "강한 모멘텀",
}


def _score_futures(df: pd.DataFrame, symbol: str, style: str = "short") -> dict:
    """
    선물 전용 전략 스코어링 (롱/숏 양방향).

    전략:
      futures_trend     — ADX 기반 추세 추종. 방향성 있는 시장에서 최적.
      futures_breakout  — BB/ATR 돌파. 변동성 확장 구간에서 최적.
      futures_momentum  — MACD+RSI 모멘텀. 추세 전환 초입에서 최적.

    3전략 × 롱/숏 = 6가지 후보 중 최고 점수 선택.
    """
    current_price = float(df["close"].iloc[-1])
    df = df.iloc[:-1]  # bar-close: 미완성봉 제외

    _empty = {
        "symbol": symbol, "score": 0, "rsi": 50.0, "price": current_price,
        "signals": ["전략 조건 미충족"], "strategy_type": "no_signal", "strategy_label": "관망",
        "sl_pct": None, "tp_pct": None, "style": style, "side": None,
        "volume_ratio": 0.0, "price_change_pct": 0.0,
        "mtf_trend": "neutral", "mtf_confirmed": True,
        "adx": 0.0, "mr_score": 0, "mr_signals": [], "bb_mid": 0.0, "bb_lower": 0.0,
        "macd_direction": "neutral", "bb_pos": 0.5, "atr_pct": 1.0,
    }
    if len(df) < 60:
        return {**_empty, "signals": ["데이터 부족"]}

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # ── 공통 지표 ────────────────────────────────────────────────────────────
    rsi_s = ta.rsi(close, length=14)
    rsi = float(rsi_s.iloc[-1]) if rsi_s is not None and not rsi_s.empty else 50.0
    if math.isnan(rsi):
        rsi = 50.0

    ema20  = ta.ema(close, length=20)
    ema50  = ta.ema(close, length=50)
    ema100 = ta.ema(close, length=100)
    e20  = float(ema20.iloc[-1])  if ema20  is not None and len(ema20.dropna())  > 0 else 0.0
    e50  = float(ema50.iloc[-1])  if ema50  is not None and len(ema50.dropna())  > 0 else 0.0
    e100 = float(ema100.iloc[-1]) if ema100 is not None and len(ema100.dropna()) > 0 else 0.0

    adx_df = ta.adx(high, low, close, length=14)
    adx = dmi_plus = dmi_minus = 0.0
    if adx_df is not None and len(adx_df.dropna()) > 0:
        cols = adx_df.columns.tolist()
        adx       = float(adx_df[cols[0]].iloc[-1])
        dmi_plus  = float(adx_df[cols[1]].iloc[-1])
        dmi_minus = float(adx_df[cols[2]].iloc[-1])

    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    macd_line = macd_hist = signal_line = 0.0
    crossed_up = crossed_down = False
    if macd_df is not None and len(macd_df.dropna()) >= 2:
        cols = macd_df.columns.tolist()
        macd_line  = float(macd_df[cols[0]].iloc[-1])
        macd_hist  = float(macd_df[cols[1]].iloc[-1])
        signal_line = float(macd_df[cols[2]].iloc[-1])
        macd_prev  = float(macd_df[cols[0]].iloc[-2])
        sig_prev   = float(macd_df[cols[2]].iloc[-2])
        crossed_up   = macd_line > signal_line and macd_prev <= sig_prev
        crossed_down = macd_line < signal_line and macd_prev >= sig_prev

    bb = ta.bbands(close, length=20)
    bb_upper = bb_lower = bb_mid = 0.0
    if bb is not None and len(bb.dropna()) > 0:
        bc = bb.columns.tolist()
        _bbl = float(bb[bc[0]].iloc[-1])
        _bbm = float(bb[bc[1]].iloc[-1])
        _bbu = float(bb[bc[2]].iloc[-1])
        if not any(math.isnan(v) for v in [_bbl, _bbm, _bbu]):
            bb_lower = _bbl
            bb_mid   = _bbm
            bb_upper = _bbu

    atr_s = ta.atr(high, low, close, length=14)
    atr = float(atr_s.iloc[-1]) if atr_s is not None and not atr_s.empty else 0.0
    atr_avg = float(atr_s.iloc[-14:-1].mean()) if atr_s is not None and len(atr_s) >= 14 else atr
    atr_expanding = atr > atr_avg * 1.2 if atr_avg > 0 else False

    vol_avg = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else 1.0
    vol_now = float(volume.iloc[-1])
    # Bybit API lag: 방금 닫힌 봉의 volume을 아직 확정하지 않고 0으로 반환하는 경우가 있음.
    # vol_now=0이면 neutral(1.0) 처리 — 스코어 페널티 없이 보너스도 없음.
    # vol_now=0을 그대로 두면 vol_ratio=0.0이 되어 volume 보너스를 못 받아
    # 본래 60점 이상이었을 신호도 60 미만으로 떨어져 진입 차단됨.
    if vol_avg > 0 and vol_now > 0:
        vol_ratio = vol_now / vol_avg
    else:
        vol_ratio = 1.0  # neutral: no bonus, no penalty
    price_now = float(close.iloc[-1])
    price_change_pct = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100) if len(close) >= 2 else 0.0

    # ── Strategy 1: futures_trend ─────────────────────────────────────────────
    def _trend(side: str) -> tuple[int, list[str]]:
        sc = 0; sg: list[str] = []
        if adx >= 35:
            sc += 35; sg.append(f"ADX 강한 추세 ({adx:.1f})")
        elif adx >= 25:
            sc += 20; sg.append(f"ADX 추세 ({adx:.1f})")
        else:
            return 0, []  # 추세 미확인 → 전략 무효

        if side == "long":
            if dmi_plus > dmi_minus:
                sc += 15; sg.append(f"+DI > -DI (상승)")
            if e20 > 0 and e50 > 0 and e100 > 0 and e20 > e50 > e100:
                sc += 20; sg.append("EMA 완전 정배열 ▲")
            elif e20 > 0 and e50 > 0 and e20 > e50:
                sc += 10; sg.append("EMA 상승 배열")
            if 45 <= rsi <= 65:
                sc += 20; sg.append(f"RSI 모멘텀 존 ({rsi:.1f})")
            elif 35 <= rsi < 45:
                sc += 8;  sg.append(f"RSI 회복 중 ({rsi:.1f})")
        else:  # short
            if dmi_minus > dmi_plus:
                sc += 15; sg.append(f"-DI > +DI (하락)")
            if e20 > 0 and e50 > 0 and e100 > 0 and e20 < e50 < e100:
                sc += 20; sg.append("EMA 완전 역배열 ▼")
            elif e20 > 0 and e50 > 0 and e20 < e50:
                sc += 10; sg.append("EMA 하락 배열")
            if 35 <= rsi <= 55:
                sc += 20; sg.append(f"RSI 하락 모멘텀 ({rsi:.1f})")
            elif 55 < rsi <= 65:
                sc += 8;  sg.append(f"RSI 과열 식는 중 ({rsi:.1f})")

        if vol_ratio >= 1.5:
            sc += 10; sg.append(f"거래량 증가 ({vol_ratio:.1f}x)")
        return sc, sg

    # ── Strategy 2: futures_breakout ─────────────────────────────────────────
    def _breakout(side: str) -> tuple[int, list[str]]:
        sc = 0; sg: list[str] = []
        # scalping: BB 돌파 단독은 신호 미약 — 거래량 확인 필수
        if style == "scalping" and vol_ratio < 1.3:
            return 0, []
        if side == "long":
            if bb_upper > 0 and price_now > bb_upper:
                sc += 30; sg.append("BB 상단 돌파 ↑")
            elif bb_mid > 0 and price_now > bb_mid and vol_ratio >= 1.8:
                sc += 15; sg.append("BB 중단 돌파 + 거래량 급증")
            else:
                return 0, []
            if rsi > 55:
                sc += 15; sg.append(f"RSI 모멘텀 ({rsi:.1f})")
        else:
            if bb_lower > 0 and price_now < bb_lower:
                sc += 30; sg.append("BB 하단 이탈 ↓")
            elif bb_mid > 0 and price_now < bb_mid and vol_ratio >= 1.8:
                sc += 15; sg.append("BB 중단 하락 돌파 + 거래량 급증")
            else:
                return 0, []
            if rsi < 45:
                sc += 15; sg.append(f"RSI 하락 모멘텀 ({rsi:.1f})")

        if vol_ratio >= 2.5:
            sc += 30; sg.append(f"거래량 급등 ({vol_ratio:.1f}x)")
        elif vol_ratio >= 1.8:
            sc += 20; sg.append(f"거래량 급증 ({vol_ratio:.1f}x)")
        elif vol_ratio >= 1.3:
            sc += 10; sg.append(f"거래량 증가 ({vol_ratio:.1f}x)")

        if atr_expanding:
            sc += 15; sg.append("변동성 확대 (ATR↑)")
        return sc, sg

    # ── Strategy 3: futures_momentum ─────────────────────────────────────────
    def _momentum(side: str) -> tuple[int, list[str]]:
        sc = 0; sg: list[str] = []
        if side == "long":
            if crossed_up:
                sc += 30; sg.append("MACD 골든크로스 ↑")
            elif macd_line > signal_line and macd_hist > 0:
                sc += 15; sg.append("MACD 상승 모멘텀")
            if 50 <= rsi <= 70:
                sc += 20; sg.append(f"RSI 상승 모멘텀 ({rsi:.1f})")
            elif 45 <= rsi < 50:
                sc += 10; sg.append(f"RSI 상승 전환 ({rsi:.1f})")
            if e20 > 0 and e50 > 0 and e20 > e50:
                sc += 10; sg.append("EMA 상승 배열")
        else:
            if crossed_down:
                sc += 30; sg.append("MACD 데드크로스 ↓")
            elif macd_line < signal_line and macd_hist < 0:
                sc += 15; sg.append("MACD 하락 모멘텀")
            if 30 <= rsi <= 50:
                sc += 20; sg.append(f"RSI 하락 모멘텀 ({rsi:.1f})")
            elif 50 < rsi <= 55:
                sc += 10; sg.append(f"RSI 하락 전환 ({rsi:.1f})")
            if e20 > 0 and e50 > 0 and e20 < e50:
                sc += 10; sg.append("EMA 하락 배열")

        if vol_ratio >= 1.5:
            sc += 20; sg.append(f"거래량 증가 ({vol_ratio:.1f}x)")
        elif vol_ratio >= 1.2:
            sc += 10; sg.append(f"거래량 소폭 증가 ({vol_ratio:.1f}x)")
        elif vol_ratio >= 1.0:
            sc += 5;  sg.append(f"거래량 보통 ({vol_ratio:.1f}x)")

        return (sc, sg) if sc >= 20 else (0, [])  # 최소 임계값 미달 → 무효

    # ── 최강 후보 선택 ────────────────────────────────────────────────────────
    # scalping: ADX 추세 신호는 5m봉에서 후발 진입 위험이 커서 제외.
    #           돌파 + MACD/RSI 모멘텀을 함께 보되, 리스크 필터에서 최종 차단한다.
    _allowed_strats = (
        [("futures_breakout", _breakout), ("futures_momentum", _momentum)]
        if style == "scalping"
        else [("futures_trend", _trend), ("futures_breakout", _breakout), ("futures_momentum", _momentum)]
    )
    # 전략별 이론적 최대 점수 (정규화 기준)
    _STRAT_MAX_SCORE = {
        "futures_trend":     100,  # ADX35+DMI15+EMA20+RSI20+vol10
        "futures_breakout":   90,  # BB30+RSI15+vol30+ATR15
        "futures_momentum":   80,  # MACD30+RSI20+EMA10+vol20
    }
    candidates: list[tuple[str, str, int, list[str]]] = []
    for strat, fn in _allowed_strats:
        for side in ("long", "short"):
            sc, sg = fn(side)
            if sc > 0:
                # 100점 기준으로 정규화하여 전략 간 공정 비교
                max_sc = _STRAT_MAX_SCORE.get(strat, 100)
                normalized_sc = round(sc / max_sc * 100)
                candidates.append((strat, side, normalized_sc, sg))

    # ── 선물 공통 파생 지표 ────────────────────────────────────────────────
    _f_macd_dir = (
        "cross_up"   if crossed_up   else
        "cross_down" if crossed_down else
        "bullish"    if macd_line > signal_line else
        "bearish"
    )
    _f_bb_pos = (
        round(max(0.0, min(1.0, (price_now - bb_lower) / (bb_upper - bb_lower))), 2)
        if bb_upper > bb_lower else 0.5
    )
    _f_atr_pct = round(atr / price_now * 100, 2) if price_now > 0 and atr > 0 else 1.0

    if not candidates:
        no_signal_reasons: list[str] = []
        if adx < 20:
            no_signal_reasons.append(f"ADX 약함 ({adx:.1f})")
        elif adx < 25:
            no_signal_reasons.append(f"ADX 추세 임계 미달 ({adx:.1f} < 25)")
        if vol_ratio < 0.8:
            no_signal_reasons.append(f"거래량 확인 부족 ({vol_ratio:.1f}x)")
        elif vol_ratio < 1.2:
            no_signal_reasons.append(f"거래량 평균 수준 ({vol_ratio:.1f}x)")
        if bb_upper > 0 and bb_lower > 0 and bb_lower <= price_now <= bb_upper:
            no_signal_reasons.append("BB 돌파 없음")
        if not crossed_up and not crossed_down and abs(macd_hist) <= abs(macd_line) * 0.05:
            no_signal_reasons.append("MACD 방향성 약함")
        if rsi >= 70:
            no_signal_reasons.append(f"RSI 과열, 추격 보류 ({rsi:.1f})")
        elif rsi <= 30:
            no_signal_reasons.append(f"RSI 과매도, 반전 확인 대기 ({rsi:.1f})")
        if not no_signal_reasons:
            no_signal_reasons.append("전략 조건 미충족")
        return {**_empty, "rsi": round(rsi, 1), "adx": round(adx, 1),
                "signals": no_signal_reasons[:4],
                "volume_ratio": round(vol_ratio, 2),
                "bb_mid": round(bb_mid, 2), "bb_lower": round(bb_lower, 2),
                "price_change_pct": round(price_change_pct, 2),
                "macd_direction": _f_macd_dir, "bb_pos": _f_bb_pos, "atr_pct": _f_atr_pct}

    strategy_type, side, score, signals = max(candidates, key=lambda x: x[2])
    cfg = FUTURES_STRATEGY_STYLE_CONFIGS.get(strategy_type, {}).get(style, {})

    # EMA 배열로 중기 추세 판단 (상위 타임프레임 대용)
    # e20 > e50 > e100 → 상승추세, e20 < e50 < e100 → 하락추세
    if e20 > 0 and e50 > 0 and e100 > 0:
        if e20 > e50 > e100:
            _mtf_trend = "bullish"
        elif e20 < e50 < e100:
            _mtf_trend = "bearish"
        else:
            _mtf_trend = "neutral"
    else:
        _mtf_trend = "neutral"
    # 신호 방향과 EMA 추세가 일치하는지 확인
    _mtf_confirmed = (
        (side == "long"  and _mtf_trend in ("bullish", "neutral")) or
        (side == "short" and _mtf_trend in ("bearish", "neutral"))
    )

    return {
        "symbol":           symbol,
        "score":            score,
        "rsi":              round(rsi, 1),
        "price":            current_price,
        "signals":          signals,
        "strategy_type":    strategy_type,
        "strategy_label":   FUTURES_STRATEGY_LABELS[strategy_type],
        "sl_pct":           cfg.get("sl_pct"),
        "tp_pct":           cfg.get("tp_pct"),
        "style":            style,
        "side":             side,
        "volume_ratio":     round(vol_ratio, 2),
        "price_change_pct": round(price_change_pct, 2),
        "mtf_trend":        _mtf_trend,
        "mtf_confirmed":    _mtf_confirmed,
        "adx":              round(adx, 1),
        "mr_score":         0,
        "mr_signals":       [],
        "bb_mid":           round(bb_mid, 2),
        "bb_lower":         round(bb_lower, 2),
        # AI 분석용 추가 지표
        "macd_direction":   _f_macd_dir,
        "bb_pos":           _f_bb_pos,
        "atr_pct":          _f_atr_pct,
    }


async def scan_futures_market(
    connector,
    timeframe: str = "1h",
    style: str = "short",
) -> list[dict]:
    """
    선물 종목 스캔 — 선물 전용 전략 3종 (추세/돌파/모멘텀) × 롱/숏 적용.
    펀딩비로 점수 보정 후 최고 점수 종목 반환.
    """
    results = []
    for symbol in FUTURES_SYMBOLS:
        try:
            df = await asyncio.wait_for(
                connector.fetch_ohlcv(symbol, timeframe, limit=150),
                timeout=12,
            )
            if len(df) < 60:
                continue

            result = _score_futures(df, symbol, style)

            # ── 펀딩비 보정 ───────────────────────────────────────────────────
            funding_rate = 0.0
            try:
                funding_rate = await asyncio.wait_for(
                    connector.get_funding_rate(symbol), timeout=5
                )
            except Exception:
                pass
            result["funding_rate"] = funding_rate

            # 펀딩비가 진입 방향에 불리하면 점수 차감
            if result["side"] == "long" and funding_rate > 0.001:
                result["score"] = max(0, result["score"] - 10)
                result["signals"].append(f"펀딩비 불리 ({funding_rate * 100:.4f}%)")
            elif result["side"] == "short" and funding_rate < -0.001:
                result["score"] = max(0, result["score"] - 10)
                result["signals"].append(f"음수 펀딩비 불리 ({funding_rate * 100:.4f}%)")

            results.append(result)
            await asyncio.sleep(0.2)
        except asyncio.TimeoutError:
            logger.debug(f"Timeout scanning futures {symbol}")
        except Exception as e:
            logger.debug(f"Skip futures {symbol}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
