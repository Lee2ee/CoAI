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
import pandas_ta as ta
import pandas as pd
from ..exchange.connector import ExchangeConnector
from ..quant.optimizer import calc_quant_features
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
        "scalping": {"sl_pct": 1.0,  "tp_pct": 2.5},   # 5분봉 — 타이트
        "short":    {"sl_pct": 2.5,  "tp_pct": 7.0},
        "mid":      {"sl_pct": 5.0,  "tp_pct": 15.0},
        "long":     {"sl_pct": 10.0, "tp_pct": 30.0},
    },
    "golden_cross": {
        "scalping": {"sl_pct": 0.8,  "tp_pct": 2.0},   # 5분봉 골든크로스 — 작은 폭
        "short":    {"sl_pct": 4.0,  "tp_pct": 10.0},
        "mid":      {"sl_pct": 6.0,  "tp_pct": 20.0},
        "long":     {"sl_pct": 12.0, "tp_pct": 36.0},
    },
    "macd_momentum": {
        "scalping": {"sl_pct": 0.8,  "tp_pct": 1.8},   # scalping 최적
        "short":    {"sl_pct": 3.0,  "tp_pct": 9.0},
        "mid":      {"sl_pct": 5.0,  "tp_pct": 16.0},
        "long":     {"sl_pct": 11.0, "tp_pct": 32.0},
    },
    "volume_breakout": {
        "scalping": {"sl_pct": 1.0,  "tp_pct": 2.5},
        "short":    {"sl_pct": 3.5,  "tp_pct": 12.0},
        "mid":      {"sl_pct": 5.5,  "tp_pct": 18.0},
        "long":     {"sl_pct": 10.0, "tp_pct": 30.0},
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
        weights = STYLE_SCORE_WEIGHTS.get(style, STYLE_SCORE_WEIGHTS["short"])
        close = df["close"]
        volume = df["volume"]
        score = 0
        signals = []

        # ── RSI (기본 30점, 가중치 적용) ────────────────────────────────────
        rsi_s = ta.rsi(close, length=14)
        rsi = float(rsi_s.iloc[-1]) if rsi_s is not None and not rsi_s.empty else 50.0

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
            elif ml_now > sg_now:
                macd_pts = 15
                signals.append("MACD 강세 구간")
                macd_bull = True
            elif ml_now > ml_prev:
                macd_pts = 5
                signals.append("MACD 반등 중")
        score += int(macd_pts * weights["macd"])

        # ── 거래량 (기본 20점, 가중치 적용) ────────────────────────────────
        volume_breakout = False
        vol_pts = 0
        vol_ratio_val = 0.0
        if len(volume) >= 21:
            vol_avg = float(volume.iloc[-21:-1].mean())
            vol_now = float(volume.iloc[-1])
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
        price_now = float(close.iloc[-1])
        price_3ago = float(close.iloc[-4]) if len(close) >= 4 else price_now
        price_change_pct_val = (price_now - price_3ago) / price_3ago * 100 if price_3ago > 0 else 0.0

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

        # ── 퀀트 오버레이: 추세 모멘텀 + 변동성 페널티 ─────────────────────
        quant = calc_quant_features(df, base_score=min(score, 100), style=style)
        quant_score = int(quant["quant_score"])
        if quant_score >= min(score, 100) + 10:
            signals.append(f"퀀트 우호 (Q {quant_score}, vol×{quant['volatility_scalar']})")
        elif quant_score <= min(score, 100) - 10:
            signals.append(f"퀀트 경고 (Q {quant_score}, ATR {quant['atr_pct']}%)")

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
        elif macd_cross:
            strategy_type = "macd_momentum"
        elif volume_breakout and (above_ema20 or rsi_is_bounce):
            strategy_type = "volume_breakout"
        elif macd_bull and adx_val >= 25 and ema_pts >= 12:
            # 추세 지속: MACD 강세 구간 + 강한 추세 + EMA 정배열
            strategy_type = "macd_momentum"
        elif rsi_is_bounce:
            strategy_type = "oversold_bounce"
        else:
            strategy_type = "standard"

        # 스타일별 SL/TP 적용
        style_cfg = STRATEGY_STYLE_CONFIGS.get(strategy_type, {}).get(style, {})
        sl_pct = style_cfg.get("sl_pct")
        tp_pct = style_cfg.get("tp_pct")

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
            "price":            float(close.iloc[-1]),
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
            # 퀀트 오버레이
            "quant_score":      quant_score,
            "expected_edge_pct": quant["expected_edge_pct"],
            "volatility_scalar": quant["volatility_scalar"],
            "atr_pct":          quant["atr_pct"],
            "realized_vol_pct": quant["realized_vol_pct"],
            "momentum_20_pct":  quant["momentum_20_pct"],
            "momentum_50_pct":  quant["momentum_50_pct"],
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
            "quant_score": 0, "expected_edge_pct": 0.0, "volatility_scalar": 1.0,
            "atr_pct": 0.0, "realized_vol_pct": 0.0, "momentum_20_pct": 0.0,
            "momentum_50_pct": 0.0,
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


async def scan_futures_market(
    connector,          # BinanceFuturesConnector
    timeframe: str = "1h",
    style: str = "short",
) -> list[dict]:
    """
    Binance Futures USDT-M 종목 스캔.
    롱/숏 양방향 신호 감지 + 펀딩비 조정.
    반환 dict에 'side': 'long'|'short' 필드 추가.
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

            # 기존 _score() 로 롱 신호 점수 계산
            result = _score(df, symbol, style, htf_df=None)

            # ── 숏 신호 계산 ──────────────────────────────────────────────────
            close  = df["close"]
            volume = df["volume"]

            rsi_series = ta.rsi(close, length=14)
            rsi = float(rsi_series.iloc[-1]) if rsi_series is not None and len(rsi_series) > 0 else 50.0

            ema20 = ta.ema(close, length=20)
            ema50 = ta.ema(close, length=50)
            vol_avg = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else 0.0
            vol_now = float(volume.iloc[-1])
            vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

            short_score   = 0
            short_signals: list[str] = []

            if rsi > 70:
                short_score += 25
                short_signals.append(f"RSI 과매수 ({rsi:.1f})")
            elif rsi > 65:
                short_score += 12
                short_signals.append(f"RSI 과열 ({rsi:.1f})")

            if (ema20 is not None and ema50 is not None
                    and len(ema20.dropna()) > 1 and len(ema50.dropna()) > 1):
                e20_now  = float(ema20.iloc[-1])
                e50_now  = float(ema50.iloc[-1])
                e20_prev = float(ema20.iloc[-2])
                e50_prev = float(ema50.iloc[-2])
                if e20_now < e50_now and e20_prev >= e50_prev:
                    short_score += 20
                    short_signals.append("EMA 데드크로스 ✕")
                elif e20_now < e50_now:
                    short_score += 10
                    short_signals.append("하락추세 (EMA20 < EMA50)")

            macd_df = ta.macd(close, fast=12, slow=26, signal=9)
            if macd_df is not None and len(macd_df.dropna()) >= 2:
                cols   = macd_df.columns.tolist()
                ml_now  = float(macd_df[cols[0]].iloc[-1])
                ml_prev = float(macd_df[cols[0]].iloc[-2])
                sg_now  = float(macd_df[cols[2]].iloc[-1])
                sg_prev = float(macd_df[cols[2]].iloc[-2])
                if ml_now < sg_now and ml_prev >= sg_prev:
                    short_score += 20
                    short_signals.append("MACD 데드크로스 ↓")
                elif ml_now < sg_now:
                    short_score += 8
                    short_signals.append("MACD 약세")

            if vol_ratio < 0.7:
                short_score += 8
                short_signals.append(f"거래량 감소 ({vol_ratio:.1f}x)")

            # ── 펀딩비 조정 ───────────────────────────────────────────────────
            funding_rate = 0.0
            try:
                funding_rate = await asyncio.wait_for(
                    connector.get_funding_rate(symbol), timeout=5
                )
            except Exception:
                pass
            result["funding_rate"] = funding_rate

            if funding_rate > 0.001:      # 롱 비용 증가 → 롱 점수 차감
                result["score"] = max(0, result["score"] - 10)
                result["signals"].append(f"펀딩비 높음 ({funding_rate * 100:.4f}%)")
            elif funding_rate < -0.001:   # 숏 비용 증가 → 숏 점수 차감
                short_score = max(0, short_score - 10)
                short_signals.append(f"음수 펀딩비 ({funding_rate * 100:.4f}%)")

            # ── 더 강한 방향 선택 ─────────────────────────────────────────────
            if short_score > result["score"] and short_score >= 40:
                result["score"]   = short_score
                result["signals"] = short_signals
                result["side"]    = "short"
            else:
                result["side"] = "long"

            results.append(result)
            await asyncio.sleep(0.2)
        except asyncio.TimeoutError:
            logger.debug(f"Timeout scanning futures {symbol}")
        except Exception as e:
            logger.debug(f"Skip futures {symbol}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
