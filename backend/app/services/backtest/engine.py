"""
백테스트 엔진.
과최적화 방지를 위해 Walk-Forward 분석 지원.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from ..indicator.engine import evaluate_conditions
from ..risk.manager import RiskManager


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    fee_rate: float = 0.0005      # 0.05% 수수료 (업비트 KRW 기준)
    slippage_pct: float = 0.05    # 0.05% 슬리피지
    position_size_pct: float = 10.0


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
    def __init__(self, strategy_config: dict, bt_config: Optional[BacktestConfig] = None):
        self.config = strategy_config
        self.bt_config = bt_config or BacktestConfig(
            position_size_pct=strategy_config.get("risk", {}).get("position_size_pct", 10.0)
        )
        self.risk = RiskManager(strategy_config.get("risk", {}))

    def run(self, df: pd.DataFrame) -> BacktestResult:
        """전체 데이터셋으로 백테스트 실행"""
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
                    amount = (capital * self.bt_config.position_size_pct / 100) / fill_price
                    fee = amount * fill_price * self.bt_config.fee_rate
                    capital -= (amount * fill_price + fee)

                    sl_price, tp_price = self.risk.calc_levels(fill_price, "long")
                    position = {
                        "entry_price": fill_price,
                        "amount": amount,
                        "entry_index": i,
                        "entry_at": ts,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "fee_entry": fee,
                    }
            else:
                exit_reason = None

                # 손절/익절 체크
                risk_reason = self.risk.check_exit(position["entry_price"], current_price, "long")
                if risk_reason:
                    exit_reason = risk_reason
                elif evaluate_conditions(window, exit_conds):
                    exit_reason = "signal"

                if exit_reason:
                    fill_price = current_price * (1 - self.bt_config.slippage_pct / 100)
                    fee_exit = position["amount"] * fill_price * self.bt_config.fee_rate
                    gross = position["amount"] * fill_price
                    capital += gross - fee_exit

                    pnl = gross - (position["amount"] * position["entry_price"]) - position["fee_entry"] - fee_exit
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

    def run_walk_forward(self, df: pd.DataFrame, n_splits: int = 5) -> list[BacktestResult]:
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
        all_conds = self.config.get("entry_conditions", []) + self.config.get("exit_conditions", [])
        for cond in all_conds:
            key = f"{cond['indicator']}_{cond.get('params', {})}"
            if key in seen:
                current_val = seen[key]
            else:
                try:
                    result = compute_indicator(df, cond["indicator"], cond.get("params", {}))
                    if result is None:
                        current_val = "계산 불가"
                    elif isinstance(result, pd.DataFrame):
                        import pandas_ta as ta  # noqa: F401 – already imported at top
                        col = next((c for c in result.columns if c.startswith("MACDh")), result.columns[0])
                        v = result[col].dropna()
                        current_val = round(float(v.iloc[-1]), 4) if not v.empty else "데이터 부족"
                    else:
                        v = result.dropna()
                        current_val = round(float(v.iloc[-1]), 4) if not v.empty else "데이터 부족"
                except Exception as e:
                    current_val = f"오류: {e}"
                seen[key] = current_val
            rows.append({
                "label": f"{cond['indicator']}({cond.get('params', {})})",
                "current_value": current_val,
                "operator": cond["operator"],
                "threshold": cond.get("value"),
            })
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
        result.profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else 0.0

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
