"""
거래소 연결 추상화 레이어 - ccxt 기반.

is_paper = True  → 주문을 PaperBroker로 가상 처리 (시세는 실제 거래소 공개 API)
is_paper = False → 실제 API 키로 실거래소 주문

sandbox 모드는 사용하지 않음:
  - Binance Testnet은 별도 계정/키 필요, 국내에서 차단되는 경우가 많음
  - 모의거래는 PaperBroker가 담당하므로 공개 API만 사용하면 충분
"""
import ccxt.async_support as ccxt
import pandas as pd
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
from typing import Optional
import asyncio


EXCHANGE_CLASSES = {
    "upbit": ccxt.upbit,
    # 확장 시 여기에 추가: "binance": ccxt.binance, etc.
}

# 거래소별 스팟 수수료율 (매수·매도 동일 적용)
# 출처: 각 거래소 공식 수수료 정책 기준 (2025년)
EXCHANGE_FEES: dict[str, float] = {
    "upbit":   0.0005,   # 0.05%  — KRW 마켓 단일 수수료 (maker = taker)
    "binance": 0.001,    # 0.10%  — 기본 (BNB 할인 미적용)
    "bybit":   0.001,    # 0.10%  — 스팟 기본 (VIP0 taker 기준)
    "bithumb": 0.0025,   # 0.25%  — KRW 마켓 기본 수수료
    "coinone": 0.002,    # 0.20%  — KRW 마켓 taker 기준
}

TIMEFRAME_MAP = {
    "1m":  60_000,
    "3m":  180_000,
    "5m":  300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h":  3_600_000,
    "4h":  14_400_000,
    "1d":  86_400_000,
    "1w":  604_800_000,
    "1M":  2_592_000_000,
}

# 요청 타임아웃 (ms)
REQUEST_TIMEOUT = 10_000


class ExchangeConnector:
    def __init__(
        self,
        exchange_id: str,
        api_key: str = "",
        api_secret: str = "",
        is_paper: bool = True,
    ):
        cls = EXCHANGE_CLASSES.get(exchange_id)
        if cls is None:
            raise ValueError(f"지원하지 않는 거래소: {exchange_id}")

        self.is_paper = is_paper
        self.exchange_id = exchange_id

        self._exchange = cls({
            "apiKey": api_key,
            "secret": api_secret,
            "options": {"defaultType": "spot"},
            "enableRateLimit": True,
            "timeout": REQUEST_TIMEOUT,
            # sandbox 미사용: 시세는 항상 실거래소 공개 API 사용
        })

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 500
    ) -> pd.DataFrame:
        MAX_PER_REQUEST = 200  # 업비트 단일 요청 최대 200개

        if limit <= MAX_PER_REQUEST:
            raw = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        else:
            # 역방향 페이지네이션: 최신 봉부터 가져온 뒤 oldest_ts 기준으로 이전 구간 채움
            # 순방향(since→) 방식은 Upbit의 to 파라미터 변환 시 배치 경계 불일치로 갭 발생
            tf_ms = TIMEFRAME_MAP.get(timeframe, 3_600_000)

            raw: list = []
            while len(raw) < limit:
                remaining = min(MAX_PER_REQUEST, limit - len(raw))
                if not raw:
                    batch = await self._exchange.fetch_ohlcv(
                        symbol, timeframe, limit=remaining
                    )
                else:
                    oldest_ts = raw[0][0]
                    batch = await self._exchange.fetch_ohlcv(
                        symbol, timeframe,
                        since=oldest_ts - remaining * tf_ms,
                        limit=remaining,
                    )
                if not batch:
                    break
                raw = batch + raw  # 오래된 봉을 앞에 붙임
                # 중복 제거 및 시간순 정렬
                seen: set = set()
                deduped = []
                for c in raw:
                    if c[0] not in seen:
                        seen.add(c[0])
                        deduped.append(c)
                raw = sorted(deduped, key=lambda x: x[0])
                if len(batch) < remaining:
                    break
                await asyncio.sleep(0.3)  # 업비트 레이트 리밋 대응

            # limit개로 자르기 (가장 최신 봉 기준)
            raw = raw[-limit:]

        if not raw:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df.astype(float)

    async def fetch_ticker(self, symbol: str) -> dict:
        return await self._exchange.fetch_ticker(symbol)

    async def fetch_balance(self) -> dict:
        if self.is_paper:
            raise RuntimeError("모의거래 잔고는 PaperBroker를 사용하세요.")
        return await self._exchange.fetch_balance()

    async def create_market_order(
        self, symbol: str, side: str, amount: float
    ) -> dict:
        if self.is_paper:
            raise RuntimeError("모의거래 주문은 PaperBroker를 사용하세요.")
        return await self._exchange.create_market_order(symbol, side, amount)

    async def create_limit_order(
        self, symbol: str, side: str, amount: float, price: float
    ) -> dict:
        if self.is_paper:
            raise RuntimeError("모의거래 주문은 PaperBroker를 사용하세요.")
        return await self._exchange.create_limit_order(symbol, side, amount, price)

    async def fetch_order(self, order_id: str, symbol: str) -> dict:
        return await self._exchange.fetch_order(order_id, symbol)

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        return await self._exchange.cancel_order(order_id, symbol)

    async def close(self):
        await self._exchange.close()


class PaperBroker:
    """
    모의 거래 브로커.
    실제 거래소 시세 데이터를 기반으로 주문을 가상 체결.
    """

    def __init__(self, initial_balance: float = 10_000.0, fee_rate: float = EXCHANGE_FEES["upbit"]):
        self.balance = {"USDT": initial_balance}
        self.fee_rate = fee_rate
        self.orders: list[dict] = []
        self._order_id = 0

    def _next_id(self) -> str:
        self._order_id += 1
        return f"PAPER-{self._order_id:06d}"

    def execute_market_order(
        self, symbol: str, side: str, amount: float, current_price: float
    ) -> dict:
        quote = symbol.split("/")[1] if "/" in symbol else "USDT"
        base = symbol.split("/")[0]
        fee = amount * current_price * self.fee_rate
        cost = amount * current_price + fee

        if side == "buy":
            if self.balance.get(quote, 0) < cost:
                raise ValueError(f"{quote} 잔고 부족: {cost:.4f} 필요")
            self.balance[quote] = self.balance.get(quote, 0) - cost
            self.balance[base] = self.balance.get(base, 0) + amount
        elif side == "sell":
            if self.balance.get(base, 0) < amount:
                raise ValueError(f"{base} 잔고 부족: {amount:.6f} 필요")
            self.balance[base] = self.balance.get(base, 0) - amount
            self.balance[quote] = (
                self.balance.get(quote, 0) + amount * current_price - fee
            )

        order = {
            "id": self._next_id(),
            "symbol": symbol,
            "side": side,
            "type": "market",
            "amount": amount,
            "price": current_price,
            "filled": amount,
            "fee": fee,
            "status": "closed",
            "timestamp": datetime.now(KST).isoformat(),
        }
        self.orders.append(order)
        return order

    def get_balance(self) -> dict:
        return dict(self.balance)

    def get_total_value_usdt(self, prices: dict[str, float]) -> float:
        total = self.balance.get("USDT", 0)
        for asset, amount in self.balance.items():
            if asset == "USDT":
                continue
            total += amount * prices.get(f"{asset}/USDT", 0)
        return total
