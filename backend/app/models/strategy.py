from sqlalchemy import String, Boolean, Integer, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from ..core.database import Base


class Strategy(Base):
    """
    전략은 JSON으로 저장되는 조건 기반 규칙 집합.
    하드코딩 금지 - 모든 전략은 config으로 구성.

    config 예시:
    {
      "symbol": "BTC/USDT",
      "timeframe": "1h",
      "entry_conditions": [
        {"indicator": "RSI", "params": {"length": 14}, "operator": "<", "value": 30},
        {"indicator": "EMA", "params": {"fast": 9, "slow": 21}, "operator": "cross_above"}
      ],
      "exit_conditions": [
        {"indicator": "RSI", "params": {"length": 14}, "operator": ">", "value": 70}
      ],
      "risk": {
        "stop_loss_pct": 2.0,
        "take_profit_pct": 4.0,
        "position_size_pct": 5.0,
        "trailing_stop": false
      }
    }
    """
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exchange_account_id: Mapped[int] = mapped_column(
        ForeignKey("exchange_accounts.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON)          # 전략 설정 전체
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)

    # 성과 지표 (캐시)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="strategies")
    exchange_account: Mapped["ExchangeAccount"] = relationship(back_populates="strategies")
    orders: Mapped[list["Order"]] = relationship(back_populates="strategy")
    trades: Mapped[list["Trade"]] = relationship(back_populates="strategy")
