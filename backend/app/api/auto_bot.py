from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, Body, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc
from ..services.auto_trade.bot import get_auto_bot, TRADING_STYLE_PRESETS, RISK_PROFILE_ADJUSTMENTS
from ..services.risk.manager import calc_var
from ..models.user import User
from ..models.auto_bot_trade import AutoBotTrade
from ..core.database import get_db
from .deps import get_current_user

router = APIRouter(prefix="/auto-bot", tags=["auto-bot"])


@router.get("/status")
async def bot_status(user: User = Depends(get_current_user)):
    return get_auto_bot().get_status()


@router.post("/start")
async def start_bot(
    settings: Optional[dict] = Body(default=None),
    user: User = Depends(get_current_user),
):
    bot = get_auto_bot()
    bot.start(settings)
    return {"ok": True, "running": bot.is_running}


@router.post("/stop")
async def stop_bot(user: User = Depends(get_current_user)):
    bot = get_auto_bot()
    bot.stop()
    return {"ok": True, "running": bot.is_running}


@router.post("/pause")
async def pause_bot(user: User = Depends(get_current_user)):
    """일시정지: 신규 진입 차단, 기존 포지션 SL/TP 모니터 유지"""
    bot = get_auto_bot()
    bot.pause()
    return {"ok": True, "paused": bot.is_paused}


@router.post("/resume")
async def resume_bot(user: User = Depends(get_current_user)):
    """일시정지 해제: 정상 매매 복귀"""
    bot = get_auto_bot()
    bot.resume()
    return {"ok": True, "paused": bot.is_paused}


@router.post("/full-stop")
async def full_stop_bot(
    body: dict = Body(default={}),
    user: User = Depends(get_current_user),
):
    """
    중단:
    - is_paper=True (모의): 전체 포지션 청산 + 잔고·기록 초기화 후 정지
    - is_paper=False (실거래): 전체 포지션 청산 후 정지 (잔고 유지)
    """
    bot = get_auto_bot()
    is_paper = body.get("is_paper", True)
    await bot.full_stop(is_paper=is_paper)
    return {"ok": True, "running": bot.is_running}


@router.post("/scan")
async def manual_scan(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    bot = get_auto_bot()
    if bot._scan_in_progress:
        return {"ok": False, "message": "스캔이 이미 진행 중입니다."}
    background_tasks.add_task(bot.run_scan_now)
    return {"ok": True, "message": "시장 스캔을 시작했습니다."}


@router.get("/style-presets")
async def style_presets(user: User = Depends(get_current_user)):
    """매매 스타일 프리셋 목록 반환"""
    return {
        key: {**preset, "key": key}
        for key, preset in TRADING_STYLE_PRESETS.items()
    }


@router.get("/risk-profiles")
async def risk_profiles(user: User = Depends(get_current_user)):
    """투자 성향 프로파일 목록 반환"""
    return {
        key: {**adj, "key": key}
        for key, adj in RISK_PROFILE_ADJUSTMENTS.items()
    }


@router.patch("/settings")
async def update_settings(
    settings: dict,
    user: User = Depends(get_current_user),
):
    bot = get_auto_bot()
    bot.update_settings(settings)
    return {"ok": True, "settings": bot.settings}


@router.patch("/balance")
async def set_paper_balance(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
):
    """모의거래 KRW 잔고 설정"""
    krw = body.get("krw")
    if krw is None or not isinstance(krw, (int, float)):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="krw 값이 필요합니다.")
    bot = get_auto_bot()
    try:
        bot.set_paper_balance(float(krw))
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "krw": bot._broker.balance.get(bot._quote_currency, 0)}


# ── 포지션 수동 조작 ────────────────────────────────────────────────────────

@router.post("/position/{symbol}/add")
async def position_add(
    symbol: str,
    user: User = Depends(get_current_user),
):
    """수동 추매 (현재가로 추가 매수)"""
    symbol = symbol.replace("-", "/")  # BTC-KRW → BTC/KRW
    return await get_auto_bot().manual_add(symbol, "add")


@router.post("/position/{symbol}/avg-down")
async def position_avg_down(
    symbol: str,
    user: User = Depends(get_current_user),
):
    """수동 물타기 (현재가로 평단 낮추기)"""
    symbol = symbol.replace("-", "/")
    return await get_auto_bot().manual_add(symbol, "avg_down")


@router.post("/position/{symbol}/close")
async def position_close(
    symbol: str,
    user: User = Depends(get_current_user),
):
    """수동 청산"""
    symbol = symbol.replace("-", "/")
    return await get_auto_bot().manual_close(symbol)


# ── 거래 내역 (DB 영속) ─────────────────────────────────────────────────────

@router.get("/trades")
async def get_trades(
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """DB에 저장된 전체 거래 내역 (최신순)"""
    result = await db.execute(
        select(AutoBotTrade).order_by(AutoBotTrade.exit_at.desc()).limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "avg_price": t.avg_price,
            "exit_price": t.exit_price,
            "total_amount": t.total_amount,
            "entries": t.entries,
            "pnl_pct": t.pnl_pct,
            "pnl_krw": t.pnl_krw,
            "exit_reason": t.exit_reason,
            "strategy_type": t.strategy_type,
            "strategy_label": t.strategy_label,
            "score": t.score,
            "avg_down_count": t.avg_down_count,
            "add_count": t.add_count,
            "entry_at": t.entry_at,
            "exit_at": t.exit_at or "",
            "is_paper": t.is_paper,
        }
        for t in trades
    ]


@router.post("/futures/settings")
async def update_futures_settings(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
):
    """선물 레버리지·마진모드 설정 갱신."""
    bot = get_auto_bot()
    leverage    = body.get("leverage")
    margin_mode = body.get("margin_mode")

    from fastapi import HTTPException
    if leverage is not None:
        if not isinstance(leverage, int) or not (1 <= leverage <= 20):
            raise HTTPException(status_code=400, detail="leverage는 1~20 사이 정수여야 합니다.")
        bot.settings["leverage"] = leverage
    if margin_mode is not None:
        if margin_mode not in ("cross", "isolated"):
            raise HTTPException(status_code=400, detail="margin_mode는 'cross' 또는 'isolated'여야 합니다.")
        bot.settings["margin_mode"] = margin_mode

    return {
        "ok": True,
        "leverage":    bot.settings["leverage"],
        "margin_mode": bot.settings["margin_mode"],
    }


@router.get("/futures/positions")
async def get_futures_positions(user: User = Depends(get_current_user)):
    """현재 선물 포지션 목록 (청산가·펀딩비·레버리지 포함)."""
    bot = get_auto_bot()
    return list(bot._futures_positions.values())


@router.get("/trades/stats")
async def get_trade_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """DB 기반 실현 손익 통계"""
    result = await db.execute(select(AutoBotTrade))
    trades = result.scalars().all()
    if not trades:
        return {
            "total": 0, "win_trades": 0, "loss_trades": 0,
            "win_rate": 0.0, "total_pnl_krw": 0,
            "avg_pnl_pct": 0.0, "best_trade_pct": 0.0, "worst_trade_pct": 0.0,
        }
    wins = [t for t in trades if t.pnl_krw > 0]
    pnl_pct_list = [t.pnl_pct for t in trades]
    return {
        "total": len(trades),
        "win_trades": len(wins),
        "loss_trades": len(trades) - len(wins),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "total_pnl_krw": round(sum(t.pnl_krw for t in trades)),
        "avg_pnl_pct": round(sum(pnl_pct_list) / len(trades), 2),
        "best_trade_pct": round(max(pnl_pct_list), 2),
        "worst_trade_pct": round(min(pnl_pct_list), 2),
        "var_95": calc_var(pnl_pct_list),
    }
