from pydantic import BaseModel
from typing import Optional, Any


class BacktestRequest(BaseModel):
    strategy_config: dict[str, Any]
    exchange: str = "upbit"
    start_date: Optional[str] = None   # ISO 날짜 문자열
    end_date: Optional[str] = None
    initial_capital: float = 10_000.0
    fee_rate: float = 0.001
    walk_forward: bool = False
    n_splits: int = 5


class BacktestTradeResult(BaseModel):
    entry_at: str
    exit_at: str
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    exit_reason: str


class BacktestResponse(BaseModel):
    total_trades: int
    win_rate: float
    total_pnl_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    avg_trade_pnl_pct: float
    max_consecutive_losses: int
    equity_curve: list[float]
    timestamps: list[str]
    trades: list[BacktestTradeResult]
    walk_forward_results: Optional[list[dict]] = None
