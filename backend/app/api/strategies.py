from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..models.user import User
from ..models.strategy import Strategy
from ..schemas.strategy import StrategyCreate, StrategyRead, StrategyUpdate
from ..services.strategy.scheduler import get_scheduler
from .deps import get_current_user

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/", response_model=list[StrategyRead])
async def list_strategies(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=StrategyRead, status_code=201)
async def create_strategy(
    data: StrategyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    strategy = Strategy(
        user_id=user.id,
        exchange_account_id=data.exchange_account_id,
        name=data.name,
        description=data.description,
        config=data.config,
        is_paper=data.is_paper,
        is_active=False,
    )
    db.add(strategy)
    await db.flush()
    return strategy


# ── 고정 경로는 반드시 /{strategy_id} 앞에 등록해야 함 ──────────────────────

@router.get("/bot-status")
async def get_bot_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """현재 실행 중인 모든 전략의 봇 상태 + 포지션 반환"""
    result = await db.execute(
        select(Strategy).where(Strategy.user_id == user.id, Strategy.is_active == True)
    )
    active = result.scalars().all()

    scheduler = get_scheduler()
    states = {s["strategy_id"]: s for s in scheduler.get_all_states()}

    return [
        {
            "strategy_id": s.id,
            "name": s.name,
            "symbol": s.config.get("symbol"),
            "timeframe": s.config.get("timeframe"),
            "is_paper": s.is_paper,
            "position": states.get(s.id, {}).get("position"),
        }
        for s in active
    ]


# ── 동적 경로 (:id) ──────────────────────────────────────────────────────────

@router.get("/{strategy_id}", response_model=StrategyRead)
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.patch("/{strategy_id}", response_model=StrategyRead)
async def update_strategy(
    strategy_id: int,
    data: StrategyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if data.name is not None:
        strategy.name = data.name
    if data.description is not None:
        strategy.description = data.description
    if data.config is not None:
        strategy.config = data.config

    if data.is_active is not None and data.is_active != strategy.is_active:
        if data.is_active:
            if not strategy.is_paper:
                raise HTTPException(
                    status_code=400,
                    detail="Live trading requires prior paper trading validation. Set is_paper=True first.",
                )
            await get_scheduler().activate_strategy(strategy)
        else:
            await get_scheduler().deactivate_strategy(strategy_id)
        strategy.is_active = data.is_active

    await db.flush()
    return strategy


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if strategy.is_active:
        await get_scheduler().deactivate_strategy(strategy_id)

    await db.delete(strategy)


@router.get("/{strategy_id}/state")
async def get_strategy_state(
    strategy_id: int,
    user: User = Depends(get_current_user),
):
    scheduler = get_scheduler()
    states = scheduler.get_all_states()
    state = next((s for s in states if s["strategy_id"] == strategy_id), None)
    return state or {"strategy_id": strategy_id, "running": False, "position": None}
