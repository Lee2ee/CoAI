"""
전략 실행 엔진.
- JSON config으로 구동 (하드코딩 전략 없음)
- 진입/청산 조건 평가
- 리스크 관리 (손절/익절) 연동
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..exchange.connector import ExchangeConnector, PaperBroker
from ..indicator.engine import evaluate_conditions
from ..risk.manager import RiskManager
from ...models.strategy import Strategy
from ...models.order import Order, OrderStatus
from ...models.trade import Trade
from ...models.position import Position

logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    단일 전략 실행기.
    각 전략은 독립된 StrategyEngine 인스턴스를 가짐.
    """

    def __init__(self, strategy: Strategy, connector: ExchangeConnector, paper_broker: Optional[PaperBroker] = None):
        self.strategy = strategy
        self.connector = connector
        self.paper_broker = paper_broker
        self.config = strategy.config
        self.risk = RiskManager(self.config.get("risk", {}))
        self._running = False
        self._position: Optional[dict] = None  # 현재 포지션 상태

    async def tick(self, db: AsyncSession):
        """1틱 실행 - 스케줄러가 주기적으로 호출"""
        try:
            symbol = self.config["symbol"]
            timeframe = self.config.get("timeframe", "1h")
            df = await self.connector.fetch_ohlcv(symbol, timeframe, limit=200)

            if df.empty or len(df) < 50:
                return

            ticker = await self.connector.fetch_ticker(symbol)
            current_price = ticker["last"]

            # 포지션이 없으면 진입 조건 확인
            if self._position is None:
                entry_conditions = self.config.get("entry_conditions", [])
                if evaluate_conditions(df, entry_conditions):
                    await self._open_position(db, symbol, current_price, df)

            # 포지션이 있으면 청산 조건 + 리스크 확인
            else:
                exit_reason = self._check_exit(current_price)
                if exit_reason:
                    await self._close_position(db, symbol, current_price, exit_reason)
                else:
                    exit_conditions = self.config.get("exit_conditions", [])
                    if evaluate_conditions(df, exit_conditions):
                        await self._close_position(db, symbol, current_price, "signal")

                # 미실현 손익 업데이트
                self._update_unrealized_pnl(current_price)

        except Exception as e:
            logger.error(f"Strategy {self.strategy.id} tick error: {e}", exc_info=True)

    def _check_exit(self, current_price: float) -> Optional[str]:
        """손절/익절 체크"""
        if self._position is None:
            return None
        return self.risk.check_exit(
            entry_price=self._position["entry_price"],
            current_price=current_price,
            direction=self._position["direction"],
        )

    def _update_unrealized_pnl(self, current_price: float):
        if self._position is None:
            return
        entry = self._position["entry_price"]
        amount = self._position["amount"]
        if self._position["direction"] == "long":
            pnl = (current_price - entry) * amount
            pnl_pct = (current_price - entry) / entry * 100
        else:
            pnl = (entry - current_price) * amount
            pnl_pct = (entry - current_price) / entry * 100
        self._position["unrealized_pnl"] = pnl
        self._position["unrealized_pnl_pct"] = pnl_pct

    async def _open_position(self, db: AsyncSession, symbol: str, price: float, df):
        risk_config = self.config.get("risk", {})
        position_size_pct = risk_config.get("position_size_pct", 5.0)

        if self.strategy.is_paper and self.paper_broker:
            balance = self.paper_broker.get_balance()
            usdt = balance.get("USDT", 0)
            amount = (usdt * position_size_pct / 100) / price
            try:
                order = self.paper_broker.execute_market_order(symbol, "buy", amount, price)
            except ValueError as e:
                logger.warning(f"Paper order failed: {e}")
                return
        else:
            # 실거래: 실제 주문
            logger.info(f"[LIVE] Opening position {symbol} @ {price}")
            order = await self.connector.create_market_order(symbol, "buy", amount)
            amount = order["filled"]
            price = order["price"]

        sl_price, tp_price = self.risk.calc_levels(price, "long")

        self._position = {
            "symbol": symbol,
            "direction": "long",
            "entry_price": price,
            "amount": amount,
            "stop_loss_price": sl_price,
            "take_profit_price": tp_price,
            "entry_at": datetime.utcnow(),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
        }

        # DB 기록
        db_order = Order(
            strategy_id=self.strategy.id,
            exchange_order_id=order.get("id"),
            symbol=symbol,
            side="buy",
            order_type="market",
            status=OrderStatus.CLOSED,
            amount=amount,
            price=price,
            filled_amount=amount,
            avg_fill_price=price,
            fee=order.get("fee", 0),
            is_paper=self.strategy.is_paper,
            meta={"trigger": "entry_signal"},
        )
        db.add(db_order)
        await db.flush()
        logger.info(f"[Strategy {self.strategy.id}] Opened {symbol} @ {price:.4f}, amount={amount:.6f}")

    async def _close_position(self, db: AsyncSession, symbol: str, price: float, reason: str):
        if self._position is None:
            return

        amount = self._position["amount"]
        entry_price = self._position["entry_price"]
        entry_at = self._position["entry_at"]

        if self.strategy.is_paper and self.paper_broker:
            try:
                order = self.paper_broker.execute_market_order(symbol, "sell", amount, price)
            except ValueError as e:
                logger.warning(f"Paper close failed: {e}")
                return
            fee_total = order.get("fee", 0)
        else:
            order = await self.connector.create_market_order(symbol, "sell", amount)
            price = order["price"]
            fee_total = order.get("fee", 0)

        pnl = (price - entry_price) * amount - fee_total
        pnl_pct = (price - entry_price) / entry_price * 100

        trade = Trade(
            strategy_id=self.strategy.id,
            symbol=symbol,
            direction="long",
            entry_price=entry_price,
            exit_price=price,
            amount=amount,
            fee_total=fee_total,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason,
            is_paper=self.strategy.is_paper,
            entry_at=entry_at,
        )
        db.add(trade)
        await db.flush()

        self._position = None
        logger.info(
            f"[Strategy {self.strategy.id}] Closed {symbol} @ {price:.4f}, "
            f"PnL={pnl:.4f} ({pnl_pct:.2f}%), reason={reason}"
        )

    def get_state(self) -> dict:
        return {
            "strategy_id": self.strategy.id,
            "name": self.strategy.name,
            "running": self._running,
            "position": self._position,
        }
