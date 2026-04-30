"""
지표 계산 엔진 - pandas-ta 기반.
모든 지표는 설정(params)으로 구동되며 하드코딩 없음.
"""
from typing import Any
import pandas as pd
import pandas_ta as ta
import numpy as np


SUPPORTED_INDICATORS = {
    "RSI": {"func": "rsi", "params": ["length"]},
    "EMA": {"func": "ema", "params": ["length"]},
    "SMA": {"func": "sma", "params": ["length"]},
    "MACD": {"func": "macd", "params": ["fast", "slow", "signal"]},
    "BB": {"func": "bbands", "params": ["length", "std"]},
    "BB_UPPER": {"func": "bbands_upper", "params": ["length", "std"]},
    "BB_LOWER": {"func": "bbands_lower", "params": ["length", "std"]},
    "BB_WIDTH": {"func": "bbands_width", "params": ["length", "std"]},
    "STOCH": {"func": "stoch", "params": ["k", "d", "smooth_k"]},
    "ATR": {"func": "atr", "params": ["length"]},
    "VOLUME_SMA": {"func": "sma_volume", "params": ["length"]},
    "EMA_CROSS": {"func": "ema_cross", "params": ["fast", "slow"]},
}


def compute_indicator(df: pd.DataFrame, indicator: str, params: dict) -> pd.Series | pd.DataFrame:
    """단일 지표 계산"""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    if indicator == "RSI":
        return ta.rsi(close, length=params.get("length", 14))

    elif indicator == "EMA":
        return ta.ema(close, length=params.get("length", 20))

    elif indicator == "SMA":
        return ta.sma(close, length=params.get("length", 20))

    elif indicator == "MACD":
        result = ta.macd(
            close,
            fast=params.get("fast", 12),
            slow=params.get("slow", 26),
            signal=params.get("signal", 9),
        )
        return result  # DataFrame: MACD_{fast}_{slow}_{signal}, MACDh_..., MACDs_...

    elif indicator == "BB":
        result = ta.bbands(
            close,
            length=params.get("length", 20),
            std=params.get("std", 2.0),
        )
        return result  # DataFrame: BBL, BBM, BBU, BBB, BBP

    elif indicator == "BB_UPPER":
        result = ta.bbands(close, length=params.get("length", 20), std=params.get("std", 2.0))
        col = [c for c in result.columns if c.startswith("BBU")][0]
        return result[col]

    elif indicator == "BB_LOWER":
        result = ta.bbands(close, length=params.get("length", 20), std=params.get("std", 2.0))
        col = [c for c in result.columns if c.startswith("BBL")][0]
        return result[col]

    elif indicator == "BB_WIDTH":
        result = ta.bbands(close, length=params.get("length", 20), std=params.get("std", 2.0))
        col = [c for c in result.columns if c.startswith("BBB")][0]
        return result[col]

    elif indicator == "STOCH":
        result = ta.stoch(
            high, low, close,
            k=params.get("k", 14),
            d=params.get("d", 3),
            smooth_k=params.get("smooth_k", 3),
        )
        return result

    elif indicator == "ATR":
        return ta.atr(high, low, close, length=params.get("length", 14))

    elif indicator == "VOLUME_SMA":
        return ta.sma(volume, length=params.get("length", 20))

    elif indicator == "EMA_CROSS":
        fast = ta.ema(close, length=params.get("fast", 9))
        slow = ta.ema(close, length=params.get("slow", 21))
        return pd.DataFrame({"fast": fast, "slow": slow})

    raise ValueError(f"Unsupported indicator: {indicator}")


def evaluate_condition(df: pd.DataFrame, condition: dict) -> bool:
    """
    조건 하나를 평가해서 True/False 반환.

    condition 형식:
    {
      "indicator": "RSI",
      "params": {"length": 14},
      "operator": "<",        # <, >, <=, >=, ==, cross_above, cross_below
      "value": 30             # 비교값 또는 indicator 이름
    }
    """
    indicator = condition["indicator"]
    params = condition.get("params", {})
    operator = condition["operator"]
    value = condition.get("value")

    result = compute_indicator(df, indicator, params)

    # BB 밴드 크로스: 가격(close) vs 밴드 비교
    if indicator in ("BB_UPPER", "BB_LOWER") and operator in ("cross_above", "cross_below"):
        band = result
        close_series = df["close"]
        if operator == "cross_above":
            return (
                float(close_series.iloc[-1]) > float(band.iloc[-1])
                and float(close_series.iloc[-2]) <= float(band.iloc[-2])
            )
        else:
            return (
                float(close_series.iloc[-1]) < float(band.iloc[-1])
                and float(close_series.iloc[-2]) >= float(band.iloc[-2])
            )

    # 마지막 값 추출
    if isinstance(result, pd.DataFrame):
        if operator in ("cross_above", "cross_below"):
            # EMA_CROSS 등
            series_fast = result["fast"]
            series_slow = result["slow"]
            if operator == "cross_above":
                return (
                    series_fast.iloc[-1] > series_slow.iloc[-1]
                    and series_fast.iloc[-2] <= series_slow.iloc[-2]
                )
            else:
                return (
                    series_fast.iloc[-1] < series_slow.iloc[-1]
                    and series_fast.iloc[-2] >= series_slow.iloc[-2]
                )
        # MACD 히스토그램 기준
        col = result.columns[0]
        current = result[col].iloc[-1]
    else:
        current = result.iloc[-1]

    if operator == "<":
        return float(current) < float(value)
    elif operator == ">":
        return float(current) > float(value)
    elif operator == "<=":
        return float(current) <= float(value)
    elif operator == ">=":
        return float(current) >= float(value)
    elif operator == "==":
        return float(current) == float(value)
    elif operator == "cross_above":
        prev = result.iloc[-2]
        return float(prev) <= float(value) < float(current)
    elif operator == "cross_below":
        prev = result.iloc[-2]
        return float(prev) >= float(value) > float(current)

    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_conditions(df: pd.DataFrame, conditions: list[dict]) -> bool:
    """모든 조건이 True여야 신호 발생 (AND 로직)"""
    if not conditions:
        return False
    return all(evaluate_condition(df, cond) for cond in conditions)


def get_indicator_values(df: pd.DataFrame, indicator_configs: list[dict]) -> dict[str, Any]:
    """차트 오버레이용 - 마지막 N개 지표값 반환"""
    results = {}
    for cfg in indicator_configs:
        name = cfg["indicator"]
        params = cfg.get("params", {})
        try:
            result = compute_indicator(df, name, params)
            key = f"{name}_{params}"
            if isinstance(result, pd.DataFrame):
                results[key] = {col: result[col].dropna().tolist() for col in result.columns}
            else:
                results[key] = result.dropna().tolist()
        except Exception as e:
            results[name] = {"error": str(e)}
    return results
