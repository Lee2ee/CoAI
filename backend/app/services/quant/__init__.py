"""Quant research helpers for signal scoring and risk-aware sizing."""

from .optimizer import (
    calc_dynamic_sl_tp,
    calc_drawdown_throttle,
    calc_entry_rank,
    calc_quant_features,
    calc_quant_position_pct,
    calc_regime_fit,
    calc_risk_based_position_value,
    estimate_slippage_pct,
    score_backtest_result,
    score_walk_forward_results,
)

__all__ = [
    "calc_dynamic_sl_tp",
    "calc_drawdown_throttle",
    "calc_entry_rank",
    "calc_quant_features",
    "calc_quant_position_pct",
    "calc_regime_fit",
    "calc_risk_based_position_value",
    "estimate_slippage_pct",
    "score_backtest_result",
    "score_walk_forward_results",
]
