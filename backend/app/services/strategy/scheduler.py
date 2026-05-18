"""
전략 스케줄러 - 활성화된 전략들을 주기적으로 실행.
"""
import asyncio
import logging
from typing import Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..exchange.connector import ExchangeConnector, PaperBroker
from .engine import StrategyEngine
from ...core.database import AsyncSessionLocal
from ...models.strategy import Strategy
from sqlalchemy import select

logger = logging.getLogger(__name__)

TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300,
    "15m": 900, "30m": 1800, "1h": 3600,
    "4h": 14400, "1d": 86400,
}


class StrategyScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._engines: dict[int, StrategyEngine] = {}
        self._brokers: dict[int, PaperBroker] = {}
        self._connectors: dict[int, ExchangeConnector] = {}

    def start(self):
        self._scheduler.add_job(
            self._sync_active_strategies,
            IntervalTrigger(seconds=60),
            id="sync_strategies",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("Strategy scheduler started")

    async def activate_strategy(self, strategy: Strategy, api_key: str = "", api_secret: str = ""):
        if strategy.id in self._engines:
            return

        connector = ExchangeConnector(
            exchange_id=strategy.config.get("exchange", "upbit"),
            api_key=api_key,
            api_secret=api_secret,
            is_paper=strategy.is_paper,
        )

        broker = PaperBroker() if strategy.is_paper else None

        engine = StrategyEngine(strategy, connector, broker)
        self._engines[strategy.id] = engine
        self._connectors[strategy.id] = connector
        if broker:
            self._brokers[strategy.id] = broker

        timeframe = strategy.config.get("timeframe", "1h")
        tf_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
        # 체크 주기: 타임프레임의 1/4 (최소 60초, 최대 900초)
        # 예) 1h → 900초(15분), 4h → 900초(15분), 15m → 225초(4분)
        interval = max(60, min(tf_seconds // 4, 900))

        from datetime import datetime as _dt
        self._scheduler.add_job(
            self._run_tick,
            IntervalTrigger(seconds=interval),
            args=[strategy.id],
            id=f"strategy_{strategy.id}",
            replace_existing=True,
            next_run_time=_dt.now(),   # 활성화 즉시 첫 실행
        )
        logger.info(f"Strategy {strategy.id} activated, interval={interval}s (tf={timeframe})")

    async def deactivate_strategy(self, strategy_id: int):
        if strategy_id in self._engines:
            connector = self._connectors.pop(strategy_id, None)
            if connector:
                await connector.close()
            del self._engines[strategy_id]
            self._brokers.pop(strategy_id, None)

        job_id = f"strategy_{strategy_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
        logger.info(f"Strategy {strategy_id} deactivated")

    async def _run_tick(self, strategy_id: int):
        engine = self._engines.get(strategy_id)
        if not engine:
            return
        async with AsyncSessionLocal() as db:
            await engine.tick(db)
            await db.commit()

    async def _sync_active_strategies(self):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.is_active == True)
            )
            active_ids = {s.id for s in result.scalars()}

        to_remove = [sid for sid in list(self._engines.keys()) if sid not in active_ids]
        for sid in to_remove:
            await self.deactivate_strategy(sid)

    def get_all_states(self) -> list[dict[str, Any]]:
        return [e.get_state() for e in self._engines.values()]

    def stop(self):
        self._scheduler.shutdown()


_scheduler_instance: StrategyScheduler | None = None


def get_scheduler() -> StrategyScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = StrategyScheduler()
    return _scheduler_instance
