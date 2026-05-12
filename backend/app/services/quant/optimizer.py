"""
Quant overlay utilities.

The goal is not to predict a guaranteed winner. These helpers turn the
existing technical signal into a risk-adjusted decision using three
well-known research ideas:

- time-series momentum / moving-average confirmation
- volatility-managed exposure
- fractional Kelly sizing with drawdown throttling
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


STYLE_TARGET_VOL_PCT: dict[str, float] = {
    "scalping": 0.65,
    "short": 1.25,
    "mid": 2.20,
    "long": 3.50,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_pct_change(now: float, before: float) -> float:
    if before <= 0:
        return 0.0
    return (now / before - 1.0) * 100.0


def _atr_pct(df: pd.DataFrame, length: int = 14) -> float:
    if len(df) < length + 1:
        return 0.0

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(length).mean().dropna()
    price = float(close.iloc[-1])
    if atr.empty or price <= 0:
        return 0.0
    return float(atr.iloc[-1] / price * 100.0)


def calc_quant_features(
    df: pd.DataFrame,
    base_score: float = 50.0,
    style: str = "short",
) -> dict[str, float | int]:
    """
    Compute a compact quant overlay from OHLCV candles.

    Returns values are intentionally simple so they can be persisted or shown
    in scan results without tying callers to pandas objects.
    """
    if df is None or len(df) < 20:
        return {
            "momentum_20_pct": 0.0,
            "momentum_50_pct": 0.0,
            "realized_vol_pct": 0.0,
            "atr_pct": 0.0,
            "volatility_scalar": 1.0,
            "trend_score": 0.0,
            "expected_edge_pct": 0.0,
            "quant_score": int(_clamp(base_score, 0, 100)),
        }

    close = df["close"].astype(float)
    price = float(close.iloc[-1])
    returns = close.pct_change().dropna()

    momentum_20 = _safe_pct_change(price, float(close.iloc[-20]))
    momentum_50 = (
        _safe_pct_change(price, float(close.iloc[-50]))
        if len(close) >= 50
        else momentum_20
    )
    realized_vol = (
        float(returns.tail(20).std(ddof=1) * 100.0)
        if len(returns) >= 2
        else 0.0
    )
    atr = _atr_pct(df)

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    e20 = float(ema20.iloc[-1])
    e50 = float(ema50.iloc[-1])

    trend_score = 0.0
    if price > e20 > e50:
        trend_score += 18.0
    elif price < e20 < e50:
        trend_score -= 18.0

    if momentum_20 > 0:
        trend_score += min(14.0, momentum_20 * 1.3)
    else:
        trend_score += max(-14.0, momentum_20 * 1.0)

    if momentum_50 > 0:
        trend_score += min(8.0, momentum_50 * 0.45)
    else:
        trend_score += max(-8.0, momentum_50 * 0.35)

    target_vol = STYLE_TARGET_VOL_PCT.get(style, STYLE_TARGET_VOL_PCT["short"])
    effective_vol = max(realized_vol, atr * 0.65, 0.15)
    volatility_scalar = _clamp(target_vol / effective_vol, 0.35, 1.60)

    vol_penalty = min(
        28.0,
        max(0.0, atr - target_vol * 1.4) * 5.0
        + max(0.0, realized_vol - target_vol * 1.2) * 2.5,
    )

    signal_strength = (base_score - 50.0) / 50.0
    expected_edge = (
        signal_strength * 1.2
        + _clamp(momentum_20 / 10.0, -1.0, 1.5)
        + _clamp((trend_score - vol_penalty) / 30.0, -1.0, 1.0)
    )
    quant_score = int(
        round(_clamp(base_score + trend_score - vol_penalty, 0.0, 100.0))
    )

    return {
        "momentum_20_pct": round(momentum_20, 2),
        "momentum_50_pct": round(momentum_50, 2),
        "realized_vol_pct": round(realized_vol, 2),
        "atr_pct": round(atr, 2),
        "volatility_scalar": round(volatility_scalar, 3),
        "trend_score": round(trend_score, 2),
        "expected_edge_pct": round(expected_edge, 2),
        "quant_score": quant_score,
    }


def calc_drawdown_throttle(
    max_drawdown_pct: float,
    soft_limit_pct: float = 8.0,
    hard_limit_pct: float = 20.0,
    min_throttle: float = 0.35,
) -> float:
    """Reduce exposure as realized drawdown approaches the hard stop."""
    if max_drawdown_pct <= soft_limit_pct:
        return 1.0
    if max_drawdown_pct >= hard_limit_pct:
        return min_throttle
    span = hard_limit_pct - soft_limit_pct
    used = (max_drawdown_pct - soft_limit_pct) / span
    return round(1.0 - used * (1.0 - min_throttle), 4)


def calc_regime_fit(regime: str, strategy_type: str) -> float:
    """Score how well a strategy type fits the current market regime."""
    matrix = {
        "trending": {
            "macd_momentum": 90,
            "golden_cross": 85,
            "volume_breakout": 80,
            "standard": 55,
            "oversold_bounce": 45,
            "mean_reversion": 35,
        },
        "ranging": {
            "mean_reversion": 85,
            "oversold_bounce": 75,
            "volume_breakout": 60,
            "standard": 55,
            "golden_cross": 50,
            "macd_momentum": 45,
        },
        "downtrend": {
            "mean_reversion": 45,
            "volume_breakout": 40,
            "oversold_bounce": 35,
            "golden_cross": 30,
            "standard": 25,
            "macd_momentum": 20,
        },
        "volatile": {
            "volume_breakout": 75,
            "macd_momentum": 60,
            "oversold_bounce": 55,
            "mean_reversion": 35,
            "standard": 35,
        },
    }
    return float(matrix.get(regime, matrix["ranging"]).get(strategy_type, 50))


def estimate_slippage_pct(candidate: dict[str, Any], base_slippage_pct: float = 0.05) -> float:
    """Conservative trade-cost estimate from volatility and volume context."""
    atr_pct = float(candidate.get("atr_pct", 0.0) or 0.0)
    volume_ratio = float(candidate.get("volume_ratio", 1.0) or 1.0)
    volatility_penalty = min(0.20, atr_pct * 0.03)
    liquidity_penalty = 0.0 if volume_ratio >= 1.0 else min(0.12, (1.0 - volume_ratio) * 0.08)
    return round(base_slippage_pct + volatility_penalty + liquidity_penalty, 4)


def calc_entry_rank(
    candidate: dict[str, Any],
    performance: dict[str, float],
    regime: str,
    fee_rate: float,
    base_slippage_pct: float = 0.05,
) -> tuple[float, dict[str, float]]:
    """
    Cost-adjusted candidate ranking used by live entry and future backtests.
    """
    raw_score = float(candidate.get("score", 0.0) or 0.0)
    quant_score = float(candidate.get("quant_score", raw_score) or raw_score)
    expected_edge = float(candidate.get("expected_edge_pct", 0.0) or 0.0)
    volatility_scalar = float(candidate.get("volatility_scalar", 1.0) or 1.0)
    strategy_type = candidate.get("strategy_type", "standard")

    historical_edge = float(performance.get("adjusted_expectancy_pct", 0.0) or 0.0)
    profit_factor = float(performance.get("profit_factor", 1.0) or 1.0)
    sample_confidence = float(performance.get("sample_confidence", 0.0) or 0.0)

    fee_pct = fee_rate * 2 * 100
    slippage_pct = estimate_slippage_pct(candidate, base_slippage_pct)
    edge_after_cost = expected_edge + historical_edge - fee_pct - slippage_pct
    regime_fit = calc_regime_fit(regime, strategy_type)
    vol_penalty = max(0.0, 1.0 - volatility_scalar) * 15.0

    rank_score = (
        raw_score * 0.25
        + quant_score * 0.30
        + regime_fit * 0.15
        + _clamp(edge_after_cost * 10.0, -20.0, 25.0)
        + _clamp((profit_factor - 1.0) * 10.0, -10.0, 15.0) * max(0.35, sample_confidence)
        - vol_penalty
    )

    return round(rank_score, 4), {
        "edge_after_cost_pct": round(edge_after_cost, 4),
        "historical_edge_pct": round(historical_edge, 4),
        "fee_pct": round(fee_pct, 4),
        "slippage_pct": slippage_pct,
        "regime_fit": round(regime_fit, 2),
        "sample_confidence": round(sample_confidence, 4),
        "rank_score": round(rank_score, 4),
    }


def calc_quant_position_pct(
    base_position_pct: float,
    quant_score: float,
    volatility_scalar: float = 1.0,
    kelly_fraction: float | None = None,
    confidence_multiplier: float = 1.0,
    max_position_pct: float = 30.0,
    min_position_pct: float = 1.0,
    max_drawdown_pct: float = 0.0,
) -> float:
    """
    Convert signal quality and volatility into a portfolio allocation percent.

    Kelly is treated as an upper bound when available. That keeps the growth
    objective from overriding realized performance.
    """
    if base_position_pct <= 0:
        return 0.0

    score_mult = _clamp(0.45 + quant_score / 100.0, 0.45, 1.45)
    vol_mult = _clamp(volatility_scalar, 0.35, 1.60)
    conf_mult = _clamp(confidence_multiplier, 0.50, 1.30)
    throttle = calc_drawdown_throttle(max_drawdown_pct)

    anchor_pct = base_position_pct
    if kelly_fraction is not None and kelly_fraction > 0:
        anchor_pct = min(anchor_pct, kelly_fraction * 100.0)

    dynamic_cap = min(max_position_pct, base_position_pct * 1.35)
    if kelly_fraction is not None and kelly_fraction > 0:
        dynamic_cap = min(dynamic_cap, kelly_fraction * 100.0)
    if dynamic_cap <= 0:
        return 0.0
    floor = min(min_position_pct, dynamic_cap)
    position_pct = anchor_pct * score_mult * vol_mult * conf_mult * throttle
    return round(_clamp(position_pct, floor, dynamic_cap), 4)


def calc_risk_based_position_value(
    total_value: float,
    available_cash: float,
    sl_pct: float,
    quant_position_pct: float,
    risk_per_trade_pct: float,
    max_position_pct: float,
    atr_pct: float = 0.0,
    kelly_fraction: float | None = None,
) -> tuple[float, dict[str, float]]:
    """Size by expected loss if the stop is hit, with quant and Kelly caps."""
    if total_value <= 0 or available_cash <= 0:
        return 0.0, {}

    risk_budget = total_value * risk_per_trade_pct / 100
    stop_distance_pct = max(sl_pct, atr_pct * 1.2, 0.5)
    by_risk = risk_budget / (stop_distance_pct / 100)
    by_quant = total_value * quant_position_pct / 100
    by_cash = available_cash * 0.95
    by_max_position = total_value * max_position_pct / 100
    candidates = [by_risk, by_quant, by_cash, by_max_position]
    if kelly_fraction is not None and kelly_fraction > 0:
        candidates.append(total_value * kelly_fraction)

    position_value = max(0.0, min(candidates))
    return round(position_value, 4), {
        "risk_budget": round(risk_budget, 4),
        "stop_distance_pct": round(stop_distance_pct, 4),
        "by_risk": round(by_risk, 4),
        "by_quant": round(by_quant, 4),
        "by_cash": round(by_cash, 4),
        "by_max_position": round(by_max_position, 4),
        "position_value": round(position_value, 4),
    }


def calc_dynamic_sl_tp(
    candidate: dict[str, Any],
    entry_price: float,
    style: str,
    fallback_sl_pct: float,
    fallback_tp_pct: float,
) -> tuple[float, float, dict[str, float | str]]:
    """ATR-based stop and R-multiple target with strategy-specific handling."""
    atr_pct = float(candidate.get("atr_pct", 0.0) or 0.0)
    strategy_type = candidate.get("strategy_type", "standard")
    cfg = {
        "scalping": {"atr_mult": 1.2, "min_sl": 0.6, "max_sl": 2.0, "tp_r": 1.5},
        "short": {"atr_mult": 1.7, "min_sl": 1.2, "max_sl": 4.0, "tp_r": 2.4},
        "mid": {"atr_mult": 2.4, "min_sl": 3.0, "max_sl": 8.0, "tp_r": 2.8},
        "long": {"atr_mult": 3.0, "min_sl": 6.0, "max_sl": 15.0, "tp_r": 3.0},
    }.get(style, {"atr_mult": 1.7, "min_sl": 1.2, "max_sl": 4.0, "tp_r": 2.4})

    if atr_pct <= 0:
        return fallback_sl_pct, fallback_tp_pct, {
            "basis": "fallback",
            "atr_pct": round(atr_pct, 4),
            "risk_reward_r": round(fallback_tp_pct / max(fallback_sl_pct, 0.1), 4),
        }

    sl_pct = _clamp(atr_pct * cfg["atr_mult"], cfg["min_sl"], cfg["max_sl"])
    if strategy_type == "mean_reversion":
        bb_mid = float(candidate.get("bb_mid", 0.0) or 0.0)
        if bb_mid > entry_price > 0:
            tp_pct = max((bb_mid - entry_price) / entry_price * 100, sl_pct * 1.2)
        else:
            tp_pct = sl_pct * 1.5
    else:
        tp_pct = sl_pct * cfg["tp_r"]

    return round(sl_pct, 2), round(tp_pct, 2), {
        "basis": "atr_r_multiple",
        "atr_pct": round(atr_pct, 4),
        "risk_reward_r": round(tp_pct / max(sl_pct, 0.1), 4),
    }


def _metric(result: Any, name: str, default: float = 0.0) -> float:
    if isinstance(result, dict):
        value = result.get(name, default)
    else:
        value = getattr(result, name, default)
    try:
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def score_backtest_result(result: Any, min_trades: int = 5) -> float:
    """
    Robust objective for parameter search.

    It rewards return, Sharpe, profit factor and win rate, while penalizing
    max drawdown and too-few trades. It is deliberately bounded to avoid one
    lucky high-return run dominating the grid search.
    """
    total_trades = _metric(result, "total_trades")
    if total_trades <= 0:
        return -100.0

    total_return = _metric(result, "total_pnl_pct")
    sharpe = _metric(result, "sharpe_ratio")
    max_dd = _metric(result, "max_drawdown_pct")
    profit_factor = _metric(result, "profit_factor")
    win_rate = _metric(result, "win_rate")
    if (
        profit_factor <= 0
        and _metric(result, "loss_trades") == 0
        and _metric(result, "win_trades") > 0
    ):
        profit_factor = 3.0

    trade_penalty = _clamp(total_trades / min_trades, 0.25, 1.0)
    dd_penalty = 1.0 / (1.0 + max_dd / 25.0)

    return_term = math.tanh(total_return / 45.0) * 45.0
    sharpe_term = math.tanh(sharpe / 2.0) * 25.0
    pf_term = _clamp((profit_factor - 1.0) * 10.0, -12.0, 18.0)
    win_term = _clamp((win_rate - 50.0) / 2.5, -12.0, 12.0)

    score = (
        (return_term + sharpe_term + pf_term + win_term)
        * dd_penalty
        * trade_penalty
    )
    return round(score, 4)


def score_walk_forward_results(results: list[Any]) -> dict[str, float]:
    """Summarize walk-forward stability for optimization diagnostics."""
    if not results:
        return {
            "walk_forward_score": 0.0,
            "positive_splits_pct": 0.0,
            "mean_split_pnl_pct": 0.0,
            "std_split_pnl_pct": 0.0,
        }

    pnls = np.array([_metric(r, "total_pnl_pct") for r in results], dtype=float)
    scores = np.array([score_backtest_result(r) for r in results], dtype=float)
    positive = float(np.mean(pnls > 0) * 100.0)
    stability_penalty = float(np.std(pnls))
    wf_score = float(
        np.mean(scores) - stability_penalty * 0.35 + (positive - 50.0) * 0.15
    )

    return {
        "walk_forward_score": round(wf_score, 4),
        "positive_splits_pct": round(positive, 2),
        "mean_split_pnl_pct": round(float(np.mean(pnls)), 4),
        "std_split_pnl_pct": round(stability_penalty, 4),
    }
