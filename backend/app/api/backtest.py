from fastapi import APIRouter, HTTPException, Depends
from ..schemas.backtest import BacktestRequest, BacktestResponse, BacktestTradeResult
from ..services.backtest.engine import BacktestEngine, BacktestConfig
from ..services.exchange.connector import ExchangeConnector
from .deps import get_current_user
from ..models.user import User
import pandas as pd

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/optimize", response_model=dict)
async def optimize_strategy(
    req: BacktestRequest,
    user: User = Depends(get_current_user),
):
    """전략 파라미터 최적화"""
    connector = None
    try:
        connector = ExchangeConnector(exchange_id=req.exchange, is_paper=True)
        symbol = req.strategy_config.get("symbol", "BTC/USDT")
        timeframe = req.strategy_config.get("timeframe", "1h")

        df = await connector.fetch_ohlcv(symbol, timeframe, limit=1000)

        if req.start_date:
            df = df[df.index >= pd.Timestamp(req.start_date)]
        if req.end_date:
            df = df[df.index <= pd.Timestamp(req.end_date)]

        if len(df) < 200:
            raise HTTPException(
                status_code=400, detail="Need at least 200 candles for optimization"
            )

        bt_config = BacktestConfig(
            initial_capital=req.initial_capital,
            fee_rate=req.fee_rate,
            position_size_pct=(req.strategy_config.get("risk") or {}).get(
                "position_size_pct", 10.0
            ),
            use_quant_sizing=req.quant_sizing,
        )

        engine = BacktestEngine(req.strategy_config, bt_config)

        # 최적화할 파라미터 범위
        param_ranges = {
            "stop_loss_pct": [1.0, 1.5, 2.0, 2.5],
            "take_profit_pct": [4.0, 5.0, 6.0, 7.0, 8.0],
            "position_size_pct": [5.0, 7.0, 10.0, 12.0],
        }
        if req.quant_sizing or (req.strategy_config.get("risk") or {}).get(
            "quant_sizing_enabled"
        ):
            param_ranges["quant_sizing_enabled"] = [False, True]
            param_ranges["risk_per_trade_pct"] = [0.4, 0.8, 1.2]
            param_ranges["dynamic_sl_tp_enabled"] = [False, True]

        optimization_result = engine.optimize_parameters(df, param_ranges)

        return optimization_result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if connector is not None:
            await connector.close()


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(
    req: BacktestRequest,
    user: User = Depends(get_current_user),
):
    connector = None
    try:
        connector = ExchangeConnector(exchange_id=req.exchange, is_paper=True)
        symbol = req.strategy_config.get("symbol", "BTC/USDT")
        timeframe = req.strategy_config.get("timeframe", "1h")

        df = await connector.fetch_ohlcv(symbol, timeframe, limit=1500)

        if req.start_date:
            df = df[df.index >= pd.Timestamp(req.start_date)]
        if req.end_date:
            df = df[df.index <= pd.Timestamp(req.end_date)]

        if len(df) < 60:
            raise HTTPException(
                status_code=400,
                detail="Not enough data for backtest (need 60+ candles)",
            )

        bt_config = BacktestConfig(
            initial_capital=req.initial_capital,
            fee_rate=req.fee_rate,
            position_size_pct=(req.strategy_config.get("risk") or {}).get(
                "position_size_pct", 10.0
            ),
            monte_carlo_runs=req.monte_carlo_runs if req.monte_carlo else 100,
            use_quant_sizing=req.quant_sizing,
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

        # 몬테카를로 시뮬레이션 (선택적)
        monte_carlo_results = None
        if req.monte_carlo:
            monte_carlo_results = engine.run_monte_carlo(df)

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
            monte_carlo_results=monte_carlo_results,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if connector is not None:
            await connector.close()
