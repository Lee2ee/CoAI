from sqlalchemy import String, Integer, Float, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class AutoBotTrade(Base):
    """자동매매봇 청산 거래 기록 (DB 영속화)"""
    __tablename__ = "auto_bot_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    avg_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    total_amount: Mapped[float] = mapped_column(Float)
    entries: Mapped[list] = mapped_column(JSON, default=list)
    pnl_pct: Mapped[float] = mapped_column(Float)
    pnl_krw: Mapped[float] = mapped_column(Float)
    exit_reason: Mapped[str] = mapped_column(String(50))
    strategy_type: Mapped[str] = mapped_column(String(50), default="standard")
    strategy_label: Mapped[str] = mapped_column(String(100), default="표준")
    score: Mapped[int] = mapped_column(Integer, default=0)
    avg_down_count: Mapped[int] = mapped_column(Integer, default=0)
    add_count: Mapped[int] = mapped_column(Integer, default=0)
    entry_at: Mapped[str] = mapped_column(String(50))
    exit_at: Mapped[str] = mapped_column(String(50), default="")
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
