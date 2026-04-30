from sqlalchemy import String, Integer, ForeignKey, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from ..core.database import Base


class Trade(Base):
    """완료된 거래 (진입 + 청산 쌍)"""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)

    symbol: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))    # long / short

    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    fee_total: Mapped[float] = mapped_column(Float, default=0.0)

    pnl: Mapped[float] = mapped_column(Float)             # 절대값 (USDT)
    pnl_pct: Mapped[float] = mapped_column(Float)         # %
    exit_reason: Mapped[str] = mapped_column(String(50))  # signal / stop_loss / take_profit

    is_paper: Mapped[bool] = mapped_column(default=True)
    entry_at: Mapped[DateTime] = mapped_column(DateTime)
    exit_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    strategy: Mapped["Strategy"] = relationship(back_populates="trades")
