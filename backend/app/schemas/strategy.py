from pydantic import BaseModel, field_validator
from typing import Optional, Any


class StrategyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    config: dict[str, Any]
    is_paper: bool = True
    exchange_account_id: Optional[int] = None

    @field_validator("config")
    @classmethod
    def validate_config(cls, v):
        required = ["symbol", "timeframe", "entry_conditions", "risk"]
        for field in required:
            if field not in v:
                raise ValueError(f"config must include '{field}'")
        risk = v.get("risk", {})
        if "stop_loss_pct" not in risk:
            raise ValueError("config.risk must include 'stop_loss_pct'")
        if risk["stop_loss_pct"] <= 0:
            raise ValueError("stop_loss_pct must be > 0")
        return v


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class StrategyRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    config: dict[str, Any]
    is_active: bool
    is_paper: bool
    total_trades: int
    win_rate: float
    total_pnl_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float

    model_config = {"from_attributes": True}
