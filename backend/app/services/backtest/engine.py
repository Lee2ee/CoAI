"""
백테스트 엔진.
과최적화 방지를 위해 Walk-Forward 분석 지원.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field, replace
from typing import Optional
from ..indicator.engine import evaluate_conditions
from ..risk.manager import RiskManager
from ..quant.optimizer import (
    calc_dynamic_sl_tp,
    calc_quant_features,
    calc_quant_position_pct,
    calc_risk_based_position_value,
    score_backtest_result,
    score_walk_forward_results,
)


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    fee_rate: float = 0.0005  # 0.05% 수수료 (업비트 KRW 기준)
    slippage_pct: float = 0.05  # 0.05% 슬리피지
    position_size_pct: float = 10.0
    # 몬테카를로 시뮬레이션 추가
    monte_carlo_runs: int = 100  # 100회 시뮬레이션
    confidence_level: float = 0.95  # 95% 신뢰구간
    use_quant_sizing: bool = False


@dataclass
class BacktestTrade:
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    entry_at: str
    exit_at: str


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)

    indicator_snapshot: list = field(default_factory=list)

    # 성과 지표
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl_pct: float = 0.0
    max_consecutive_losses: int = 0


class BacktestEngine:
    def __init__(
        self, strategy_config: dict, bt_config: Optional[BacktestConfig] = None
    ):
        self.config = strategy_config
        self.bt_config = bt_config or BacktestConfig(
            position_size_pct=(strategy_config.get("risk") or {}).get(
                "position_size_pct", 10.0
            )
        )
        self.risk = RiskManager(strategy_config.get("risk") or {})

    def run(self, df: pd.DataFrame) -> BacktestResult:
        """전체 데이터셋으로 백테스트 실행"""
        self.risk = RiskManager(self.config.get("risk") or {})
        result = BacktestResult()
        capital = self.bt_config.initial_capital
        position = None

        entry_conds = self.config.get("entry_conditions", [])
        exit_conds = self.config.get("exit_conditions", [])

        equity = [capital]
        timestamps = [str(df.index[0])]

        for i in range(50, len(df)):
            window = df.iloc[: i + 1]
            current = df.iloc[i]
            current_price = float(current["close"])
            ts = str(df.index[i])

            if position is None:
                if evaluate_conditions(window, entry_conds):
                    # 슬리피지 적용
                    fill_price = current_price * (1 + self.bt_config.slippage_pct / 100)
                    position_size_pct = self._entry_position_size_pct(window, capital)
                    amount = (
                        capital * position_size_pct / 100
                    ) / fill_price
                    fee = amount * fill_price * self.bt_config.fee_rate
                    capital -= amount * fill_price + fee

                    risk_cfg = self.config.get("risk") or {}
                    sl_pct = risk_cfg.get("stop_loss_pct", self.risk.stop_loss_pct)
                    tp_pct = risk_cfg.get("take_profit_pct", self.risk.take_profit_pct)
                    if self.bt_config.use_quant_sizing or risk_cfg.get(
                        "dynamic_sl_tp_enabled", False
                    ):
                        style = self.config.get("trading_style") or self.config.get("style", "short")
                        quant = calc_quant_features(window, base_score=65, style=style)
                        sl_pct, tp_pct, _ = calc_dynamic_sl_tp(
                            candidate={
                                "atr_pct": quant["atr_pct"],
                                "strategy_type": self.config.get("strategy_type", "standard"),
                            },
                            entry_price=fill_price,
                            style=style,
                            fallback_sl_pct=sl_pct,
                            fallback_tp_pct=tp_pct,
                        )
                    sl_price = fill_price * (1 - sl_pct / 100)
                    tp_price = fill_price * (1 + tp_pct / 100)
                    self.risk._peak_price = fill_price
                    position = {
                        "entry_price": fill_price,
                        "amount": amount,
                        "entry_index": i,
                        "entry_at": ts,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "fee_entry": fee,
                        "position_size_pct": position_size_pct,
                        "dynamic_exit": bool(
                            self.bt_config.use_quant_sizing
                            or risk_cfg.get("dynamic_sl_tp_enabled", False)
                        ),
                        "peak_price": fill_price,
                    }
            else:
                exit_reason = None
                risk_reason = None

                # 손절/익절 체크
                if current_price <= position["sl_price"]:
                    risk_reason = "stop_loss"
                elif current_price >= position["tp_price"]:
                    risk_reason = "take_profit"
                else:
                    if position.get("dynamic_exit"):
                        if current_price > position.get("peak_price", current_price):
                            position["peak_price"] = current_price
                        if self.risk.trailing_stop:
                            trail = position["peak_price"] * (1 - self.risk.trailing_pct / 100)
                            if current_price <= trail:
                                risk_reason = "trailing_stop"
                    else:
                        risk_reason = self.risk.check_exit(
                            position["entry_price"], current_price, "long"
                        )
                if risk_reason:
                    exit_reason = risk_reason
                elif evaluate_conditions(window, exit_conds):
                    exit_reason = "signal"

                if exit_reason:
                    fill_price = current_price * (1 - self.bt_config.slippage_pct / 100)
                    fee_exit = position["amount"] * fill_price * self.bt_config.fee_rate
                    gross = position["amount"] * fill_price
                    capital += gross - fee_exit

                    pnl = (
                        gross
                        - (position["amount"] * position["entry_price"])
                        - position["fee_entry"]
                        - fee_exit
                    )
                    pnl_pct = pnl / (position["amount"] * position["entry_price"]) * 100

                    trade = BacktestTrade(
                        entry_index=position["entry_index"],
                        exit_index=i,
                        entry_price=position["entry_price"],
                        exit_price=fill_price,
                        amount=position["amount"],
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason,
                        entry_at=position["entry_at"],
                        exit_at=ts,
                    )
                    result.trades.append(trade)
                    position = None

            total_value = capital + (
                (position["amount"] * current_price) if position else 0
            )
            equity.append(total_value)
            timestamps.append(ts)

        result.equity_curve = equity
        result.timestamps = timestamps
        self._compute_stats(result)
        if result.total_trades == 0:
            result.indicator_snapshot = self._snapshot(df)
        return result

    def _entry_position_size_pct(self, window: pd.DataFrame, capital: float) -> float:
        """Fixed or quant-managed allocation for the next entry."""
        risk_cfg = self.config.get("risk") or {}
        use_quant = self.bt_config.use_quant_sizing or risk_cfg.get(
            "quant_sizing_enabled", False
        )
        if not use_quant:
            return self.bt_config.position_size_pct

        style = self.config.get("trading_style") or self.config.get("style", "short")
        quant = calc_quant_features(window, base_score=65, style=style)
        quant_position_pct = calc_quant_position_pct(
            base_position_pct=self.bt_config.position_size_pct,
            quant_score=quant["quant_score"],
            volatility_scalar=quant["volatility_scalar"],
            max_position_pct=risk_cfg.get("max_position_size_pct", 30.0),
            min_position_pct=risk_cfg.get("min_position_size_pct", 1.0),
        )
        risk_per_trade = risk_cfg.get("risk_per_trade_pct")
        if not risk_per_trade:
            return quant_position_pct

        candidate = {
            "atr_pct": quant["atr_pct"],
            "strategy_type": self.config.get("strategy_type", "standard"),
        }
        sl_pct, _, _ = calc_dynamic_sl_tp(
            candidate=candidate,
            entry_price=float(window["close"].iloc[-1]),
            style=style,
            fallback_sl_pct=risk_cfg.get("stop_loss_pct", 2.5),
            fallback_tp_pct=risk_cfg.get("take_profit_pct", 6.0),
        )
        position_value, _ = calc_risk_based_position_value(
            total_value=capital,
            available_cash=capital,
            sl_pct=sl_pct,
            quant_position_pct=quant_position_pct,
            risk_per_trade_pct=risk_per_trade,
            max_position_pct=risk_cfg.get("max_position_size_pct", 30.0),
            atr_pct=quant["atr_pct"],
        )
        return round(position_value / max(capital, 1.0) * 100, 4)

    def run_walk_forward(
        self, df: pd.DataFrame, n_splits: int = 5
    ) -> list[BacktestResult]:
        """
        Walk-Forward 분석 - 과최적화 방지.
        데이터를 n_splits 구간으로 나눠 각각 백테스트.
        """
        results = []
        chunk_size = len(df) // n_splits
        for i in range(n_splits):
            start = i * chunk_size
            end = start + chunk_size if i < n_splits - 1 else len(df)
            chunk = df.iloc[start:end]
            if len(chunk) > 60:
                results.append(self.run(chunk))
        return results

    def _snapshot(self, df: pd.DataFrame) -> list[dict]:
        """마지막 캔들 기준 각 조건의 지표 현재값 반환 (0거래 진단용)"""
        from ..indicator.engine import compute_indicator

        seen: dict[str, float | str] = {}
        rows = []
        all_conds = self.config.get("entry_conditions", []) + self.config.get(
            "exit_conditions", []
        )
        for cond in all_conds:
            key = f"{cond['indicator']}_{cond.get('params', {})}"
            if key in seen:
                current_val = seen[key]
            else:
                try:
                    result = compute_indicator(
                        df, cond["indicator"], cond.get("params", {})
                    )
                    if result is None:
                        current_val = "계산 불가"
                    elif isinstance(result, pd.DataFrame):
                        import pandas_ta as ta  # noqa: F401 – already imported at top

                        col = next(
                            (c for c in result.columns if c.startswith("MACDh")),
                            result.columns[0],
                        )
                        v = result[col].dropna()
                        current_val = (
                            round(float(v.iloc[-1]), 4)
                            if not v.empty
                            else "데이터 부족"
                        )
                    else:
                        v = result.dropna()
                        current_val = (
                            round(float(v.iloc[-1]), 4)
                            if not v.empty
                            else "데이터 부족"
                        )
                except Exception as e:
                    current_val = f"오류: {e}"
                seen[key] = current_val
            rows.append(
                {
                    "label": f"{cond['indicator']}({cond.get('params', {})})",
                    "current_value": current_val,
                    "operator": cond["operator"],
                    "threshold": cond.get("value"),
                }
            )
        return rows

    def _compute_stats(self, result: BacktestResult):
        if not result.trades:
            return

        result.total_trades = len(result.trades)
        result.win_trades = sum(1 for t in result.trades if t.pnl > 0)
        result.loss_trades = result.total_trades - result.win_trades
        result.win_rate = result.win_trades / result.total_trades * 100

        pnls = [t.pnl for t in result.trades]
        result.total_pnl = sum(pnls)
        result.avg_trade_pnl_pct = np.mean([t.pnl_pct for t in result.trades])

        initial = result.equity_curve[0] if result.equity_curve else 1
        final = result.equity_curve[-1] if result.equity_curve else 1
        result.total_pnl_pct = (final - initial) / initial * 100

        # Max Drawdown
        equity = np.array(result.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak * 100
        result.max_drawdown_pct = float(np.max(drawdown))

        # Sharpe Ratio (일별 수익률 기준)
        returns = np.diff(equity) / equity[:-1]
        if returns.std() > 0:
            result.sharpe_ratio = float(np.mean(returns) / returns.std() * np.sqrt(252))

        # Profit Factor
        gross_profit = sum(t.pnl for t in result.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in result.trades if t.pnl < 0))
        result.profit_factor = (
            round(gross_profit / gross_loss, 4) if gross_loss > 0 else 0.0
        )

        # Max consecutive losses
        streak = 0
        max_streak = 0
        for t in result.trades:
            if t.pnl < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        result.max_consecutive_losses = max_streak

    def run_monte_carlo(self, df: pd.DataFrame) -> dict:
        """
        몬테카를로 시뮬레이션 - 전략 견고성 평가.
        실제 백테스트 거래 손익률을 부트스트랩해 순서 리스크를 추정.
        """
        base_result = self.run(df)
        if not base_result.trades:
            return {
                "mean_pnl_pct": 0.0,
                "std_pnl_pct": 0.0,
                "pnl_confidence_interval": [0.0, 0.0],
                "mean_win_rate": 0.0,
                "mean_max_drawdown": 0.0,
                "mean_sharpe": 0.0,
                "robustness_score": 0.0,
            }

        trade_returns = np.array([t.pnl_pct / 100 for t in base_result.trades])
        results = []
        runs = max(1, self.bt_config.monte_carlo_runs)
        for _ in range(runs):
            sampled = np.random.choice(
                trade_returns, size=len(trade_returns), replace=True
            )
            equity = [self.bt_config.initial_capital]
            for r in sampled:
                equity.append(equity[-1] * (1 + r))
            equity_arr = np.array(equity)
            peak = np.maximum.accumulate(equity_arr)
            max_dd = float(np.max((peak - equity_arr) / peak * 100))
            returns = np.diff(equity_arr) / equity_arr[:-1]
            sharpe = 0.0
            if returns.std() > 0:
                sharpe = float(np.mean(returns) / returns.std() * np.sqrt(252))
            results.append(
                {
                    "total_pnl_pct": (equity[-1] / equity[0] - 1) * 100,
                    "win_rate": float(np.mean(sampled > 0) * 100),
                    "max_drawdown_pct": max_dd,
                    "sharpe_ratio": sharpe,
                }
            )

        # 통계 계산
        pnls = [r["total_pnl_pct"] for r in results]
        win_rates = [r["win_rate"] for r in results]
        drawdowns = [r["max_drawdown_pct"] for r in results]
        sharpes = [r["sharpe_ratio"] for r in results]

        return {
            "mean_pnl_pct": round(float(np.mean(pnls)), 4),
            "std_pnl_pct": round(float(np.std(pnls)), 4),
            "pnl_confidence_interval": [
                round(float(x), 4) for x in np.percentile(pnls, [5, 95])
            ],
            "mean_win_rate": round(float(np.mean(win_rates)), 4),
            "mean_max_drawdown": round(float(np.mean(drawdowns)), 4),
            "mean_sharpe": round(float(np.mean(sharpes)), 4),
            "robustness_score": len([p for p in pnls if p > 0])
            / len(pnls)
            * 100,  # 양수 수익률 비율
        }

    def optimize_parameters(self, df: pd.DataFrame, param_ranges: dict) -> dict:
        """
        전략 파라미터 최적화 - 그리드 서치.
        param_ranges 예시: {'rsi_period': [14, 21], 'stop_loss_pct': [1.0, 1.5, 2.0]}
        """
        best_result = None
        best_score = -float("inf")
        best_params = {}
        best_config = None

        # 모든 파라미터 조합 생성
        import copy
        import itertools

        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())
        combinations = list(itertools.product(*param_values))

        for combo in combinations:
            # 전략 설정에 파라미터 적용
            test_config = copy.deepcopy(self.config)
            if not isinstance(test_config.get("risk"), dict):
                test_config["risk"] = {}
            for name, value in zip(param_names, combo):
                if name in [
                    "stop_loss_pct",
                    "take_profit_pct",
                    "position_size_pct",
                    "quant_sizing_enabled",
                    "risk_per_trade_pct",
                    "dynamic_sl_tp_enabled",
                    "max_position_size_pct",
                    "min_position_size_pct",
                ]:
                    test_config["risk"][name] = value
                elif name.startswith("rsi"):
                    # RSI 파라미터 업데이트
                    for cond in test_config.get("entry_conditions", []):
                        if cond.get("indicator") == "RSI":
                            cond["params"] = {"length": value}
                    for cond in test_config.get("exit_conditions", []):
                        if cond.get("indicator") == "RSI":
                            cond["params"] = {"length": value}
                # 다른 지표 파라미터들도 추가 가능

            # 백테스트 실행
            test_bt_config = replace(
                self.bt_config,
                position_size_pct=test_config["risk"].get(
                    "position_size_pct", self.bt_config.position_size_pct
                ),
                use_quant_sizing=(
                    self.bt_config.use_quant_sizing
                    or bool(test_config["risk"].get("quant_sizing_enabled", False))
                ),
            )
            test_engine = BacktestEngine(test_config, test_bt_config)
            result = test_engine.run(df)

            # 수익률을 보되 MDD/거래수/샤프를 같이 반영한 견고성 점수
            score = score_backtest_result(result)

            if score > best_score:
                best_score = score
                best_result = result
                best_params = dict(zip(param_names, combo))
                best_config = test_config

        selected_config = best_config or self.config
        selected_risk = selected_config.get("risk") or {}
        best_bt_config = replace(
            self.bt_config,
            position_size_pct=selected_risk.get(
                "position_size_pct", self.bt_config.position_size_pct
            ),
            use_quant_sizing=(
                self.bt_config.use_quant_sizing
                or bool(selected_risk.get("quant_sizing_enabled", False))
            ),
        )
        wf_engine = BacktestEngine(selected_config, best_bt_config)
        return {
            "best_parameters": best_params,
            "best_score": best_score,
            "optimized_result": {
                "total_pnl_pct": best_result.total_pnl_pct,
                "win_rate": best_result.win_rate,
                "max_drawdown_pct": best_result.max_drawdown_pct,
                "sharpe_ratio": best_result.sharpe_ratio,
                "profit_factor": best_result.profit_factor,
            },
            "walk_forward_diagnostics": score_walk_forward_results(
                wf_engine.run_walk_forward(df)
            ),
        }
