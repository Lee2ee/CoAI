from pydantic import BaseModel, model_validator
from typing import Optional, Any

# 거래소별 기본 수수료 (명시적으로 fee_rate 전달 시 오버라이드됨)
_EXCHANGE_DEFAULT_FEES: dict[str, float] = {
    "upbit":   0.0005,   # 0.05%
    "binance": 0.001,    # 0.10%
    "bybit":   0.001,    # 0.10%
    "bithumb": 0.0025,   # 0.25%
    "coinone": 0.002,    # 0.20%
}


class BacktestRequest(BaseModel):
    strategy_config: dict[str, Any]
    exchange: str = "upbit"
    start_date: Optional[str] = None   # ISO 날짜 문자열
    end_date: Optional[str] = None
    initial_capital: float = 10_000.0
    fee_rate: Optional[float] = None   # None 이면 거래소 기본값 자동 적용
    walk_forward: bool = False
    n_splits: int = 5

    @model_validator(mode="after")
    def _apply_exchange_fee(self) -> "BacktestRequest":
        if self.fee_rate is None:
            self.fee_rate = _EXCHANGE_DEFAULT_FEES.get(self.exchange, 0.001)
        return self


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
    # 거래 0건 진단용: 마지막 캔들의 진입/청산 조건별 지표값
    indicator_snapshot: Optional[list[dict]] = None
