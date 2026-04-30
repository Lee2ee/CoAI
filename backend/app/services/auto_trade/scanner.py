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

logger = logging.getLogger(__name__)

# 스캔 대상: 업비트 거래량 상위 주요 종목
SCAN_SYMBOLS = [
    "BTC/KRW", "ETH/KRW", "XRP/KRW", "SOL/KRW", "DOGE/KRW",
    "ADA/KRW", "AVAX/KRW", "LINK/KRW", "DOT/KRW", "ATOM/KRW",
    "MATIC/KRW", "LTC/KRW", "BCH/KRW", "ETC/KRW", "TRX/KRW",
    "NEAR/KRW", "APT/KRW", "OP/KRW", "SUI/KRW", "SEI/KRW",
    "SAND/KRW", "MANA/KRW", "ALGO/KRW", "HBAR/KRW", "VET/KRW",
]

# 매매 스타일별 최소 일 거래대금 (KRW)
STYLE_MIN_DAILY_VOLUME_KRW: dict[str, float] = {
    "scalping": 5_000_000_000,   # 50억  — 상위 10~15종목
    "short":    2_000_000_000,   # 20억  — 상위 15~20종목
    "mid":        500_000_000,   # 5억   — 상위 20~25종목
    "long":       100_000_000,   # 1억   — 전체 스캔
}

TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440,
}

# ── 스타일별 지표 가중치 ─────────────────────────────────────────────────────
# scalping : MACD/거래량 중심 (빠른 모멘텀 포착)
# short    : 균형 (모든 지표 동등)
# mid      : EMA/RSI 중심 (추세 추종)
# long     : RSI/EMA 중심 (과매도 반등 + 추세 전환)
STYLE_SCORE_WEIGHTS: dict[str, dict[str, float]] = {
    "scalping": {"rsi": 0.4, "ema": 0.5, "macd": 1.6, "volume": 1.5},
    "short":    {"rsi": 1.0, "ema": 1.0, "macd": 1.0, "volume": 1.0},
    "mid":      {"rsi": 1.3, "ema": 1.5, "macd": 0.8, "volume": 0.7},
    "long":     {"rsi": 1.6, "ema": 1.8, "macd": 0.5, "volume": 0.5},
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


def _score(df: pd.DataFrame, symbol: str, style: str = "short") -> dict:
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
        if len(volume) >= 21:
            vol_avg = float(volume.iloc[-21:-1].mean())
            vol_now = float(volume.iloc[-1])
            if vol_avg > 0:
                ratio = vol_now / vol_avg
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

        # ── 전략 자동 분류 (스타일에 따라 자연스럽게 다른 전략이 선택됨) ──
        # 가중치로 인해:
        #   scalping → MACD/거래량 점수가 높아 macd_momentum/volume_breakout 빈번
        #   long     → RSI/EMA 점수가 높아 oversold_bounce/golden_cross 빈번
        if rsi_strong_oversold:
            strategy_type = "oversold_bounce"
        elif golden_cross:
            strategy_type = "golden_cross"
        elif macd_cross and volume_breakout:
            strategy_type = "volume_breakout"
        elif macd_cross:
            strategy_type = "macd_momentum"
        elif volume_breakout and above_ema20:
            strategy_type = "volume_breakout"
        else:
            strategy_type = "standard"

        # 스타일별 SL/TP 적용
        style_cfg = STRATEGY_STYLE_CONFIGS.get(strategy_type, {}).get(style, {})
        sl_pct = style_cfg.get("sl_pct")
        tp_pct = style_cfg.get("tp_pct")

        return {
            "symbol":         symbol,
            "score":          min(score, 100),
            "rsi":            round(rsi, 1),
            "price":          float(close.iloc[-1]),
            "signals":        signals,
            "strategy_type":  strategy_type,
            "strategy_label": _STRATEGY_LABELS[strategy_type],
            "sl_pct":         sl_pct,
            "tp_pct":         tp_pct,
            "style":          style,
        }

    except Exception as e:
        logger.debug(f"Score error {symbol}: {e}")
        return {
            "symbol": symbol, "score": 0, "rsi": 50.0, "price": 0.0, "signals": [],
            "strategy_type": "standard", "strategy_label": "표준",
            "sl_pct": None, "tp_pct": None, "style": style,
        }


async def scan_market(timeframe: str = "1h", style: str = "short") -> list[dict]:
    """
    전체 종목 스캔. 스타일별 거래량 필터 + 가중치 점수 적용 후 내림차순 정렬.
    """
    connector = ExchangeConnector(exchange_id="upbit", is_paper=True)
    min_vol = STYLE_MIN_DAILY_VOLUME_KRW.get(style, 10_000_000_000)
    results = []

    for symbol in SCAN_SYMBOLS:
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

            results.append(_score(df, symbol, style))
            await asyncio.sleep(0.15)
        except asyncio.TimeoutError:
            logger.debug(f"Timeout scanning {symbol}")
        except Exception as e:
            logger.debug(f"Skip {symbol}: {e}")

    await connector.close()
    results.sort(key=lambda x: x["score"], reverse=True)
    return results
