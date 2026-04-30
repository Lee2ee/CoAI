from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..models.user import User
from ..models.trade import Trade
from ..models.strategy import Strategy
from ..schemas.trade import TradeRead
from .deps import get_current_user

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/", response_model=list[TradeRead])
async def list_trades(
    strategy_id: int | None = Query(None),
    symbol: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(Trade)
        .join(Strategy, Strategy.id == Trade.strategy_id)
        .where(Strategy.user_id == user.id)
        .order_by(Trade.exit_at.desc())
        .limit(limit)
    )
    if strategy_id:
        query = query.where(Trade.strategy_id == strategy_id)
    if symbol:
        query = query.where(Trade.symbol == symbol)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def get_trade_stats(
    strategy_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(Trade)
        .join(Strategy, Strategy.id == Trade.strategy_id)
        .where(Strategy.user_id == user.id)
    )
    if strategy_id:
        query = query.where(Trade.strategy_id == strategy_id)

    result = await db.execute(query)
    trades = result.scalars().all()

    if not trades:
        return {"total": 0, "win_rate": 0, "total_pnl": 0}

    wins = [t for t in trades if t.pnl > 0]
    return {
        "total": len(trades),
        "win_trades": len(wins),
        "loss_trades": len(trades) - len(wins),
        "win_rate": len(wins) / len(trades) * 100,
        "total_pnl": sum(t.pnl for t in trades),
        "total_pnl_pct": sum(t.pnl_pct for t in trades),
        "avg_pnl_pct": sum(t.pnl_pct for t in trades) / len(trades),
        "best_trade_pct": max(t.pnl_pct for t in trades),
        "worst_trade_pct": min(t.pnl_pct for t in trades),
    }
