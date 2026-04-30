from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TradeRead(BaseModel):
    id: int
    strategy_id: int
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    is_paper: bool
    entry_at: datetime
    exit_at: datetime

    model_config = {"from_attributes": True}
