from fastapi import APIRouter, HTTPException, Depends
from ..schemas.backtest import BacktestRequest, BacktestResponse, BacktestTradeResult
from ..services.backtest.engine import BacktestEngine, BacktestConfig
from ..services.exchange.connector import ExchangeConnector
from .deps import get_current_user
from ..models.user import User
import pandas as pd

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(
    req: BacktestRequest,
    user: User = Depends(get_current_user),
):
    try:
        connector = ExchangeConnector(exchange_id=req.exchange, is_paper=True)
        symbol = req.strategy_config.get("symbol", "BTC/USDT")
        timeframe = req.strategy_config.get("timeframe", "1h")

        df = await connector.fetch_ohlcv(symbol, timeframe, limit=1500)
        await connector.close()

        if req.start_date:
            df = df[df.index >= pd.Timestamp(req.start_date)]
        if req.end_date:
            df = df[df.index <= pd.Timestamp(req.end_date)]

        if len(df) < 60:
            raise HTTPException(status_code=400, detail="Not enough data for backtest (need 60+ candles)")

        bt_config = BacktestConfig(
            initial_capital=req.initial_capital,
            fee_rate=req.fee_rate,
            position_size_pct=req.strategy_config.get("risk", {}).get("position_size_pct", 10.0),
        )

        engine = BacktestEngine(req.strategy_config, bt_config)

        walk_forward_results = None
        if req.walk_forward:
            wf_results = engine.run_walk_forward(df, n_splits=req.n_splits)
            walk_forward_results = [
                {
                    "total_trades": r.total_trades,
                    "win_rate": r.win_rate,
                    "total_pnl_pct": r.total_pnl_pct,
                    "max_drawdown_pct": r.max_drawdown_pct,
                    "sharpe_ratio": r.sharpe_ratio,
                }
                for r in wf_results
            ]

        result = engine.run(df)

        return BacktestResponse(
            total_trades=result.total_trades,
            win_rate=result.win_rate,
            total_pnl_pct=result.total_pnl_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            sharpe_ratio=result.sharpe_ratio,
            profit_factor=result.profit_factor,
            avg_trade_pnl_pct=result.avg_trade_pnl_pct,
            max_consecutive_losses=result.max_consecutive_losses,
            equity_curve=result.equity_curve,
            timestamps=result.timestamps,
            trades=[
                BacktestTradeResult(
                    entry_at=t.entry_at,
                    exit_at=t.exit_at,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    pnl=t.pnl,
                    pnl_pct=t.pnl_pct,
                    exit_reason=t.exit_reason,
                )
                for t in result.trades
            ],
            walk_forward_results=walk_forward_results,
            indicator_snapshot=result.indicator_snapshot or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
