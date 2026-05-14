"""
거래소 연결 추상화 레이어 - ccxt 기반.

is_paper = True  → 주문을 PaperBroker로 가상 처리 (시세는 실제 거래소 공개 API)
is_paper = False → 실제 API 키로 실거래소 주문

sandbox 모드는 사용하지 않음:
  - Binance Testnet은 별도 계정/키 필요, 국내에서 차단되는 경우가 많음
  - 모의거래는 PaperBroker가 담당하므로 공개 API만 사용하면 충분
"""
import ccxt.async_support as ccxt
import aiohttp
import pandas as pd
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
from typing import Optional
import asyncio


EXCHANGE_CLASSES = {
    "upbit":   ccxt.upbit,
    "binance": ccxt.binance,
    "bybit":   ccxt.bybit,
}

# 거래소별 단일 요청 최대 캔들 수
MAX_PER_REQUEST_BY_EXCHANGE: dict[str, int] = {
    "upbit":   200,
    "binance": 1000,
    "bybit":   200,
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
        # 업비트는 Windows에서 aiohttp ThreadedResolver 필요 (비동기 DNS 문제)
        # 다른 거래소는 기본 세션 사용
        if exchange_id == "upbit":
            _connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
            self._exchange.session = aiohttp.ClientSession(connector=_connector)

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 500
    ) -> pd.DataFrame:
        MAX_PER_REQUEST = MAX_PER_REQUEST_BY_EXCHANGE.get(self.exchange_id, 200)

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
    슬리피지(bid/ask spread 근사)를 적용해 실거래와 유사한 환경을 시뮬레이션.
    """

    # 매수: ask ≈ last * (1 + spread), 매도: bid ≈ last * (1 - spread)
    SLIPPAGE_RATE = 0.001   # 0.1% — 업비트 소형 코인 평균 spread 근사

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
        # 슬리피지 적용: 매수는 ask(+0.1%), 매도는 bid(-0.1%)
        if side == "buy":
            fill_price = current_price * (1 + self.SLIPPAGE_RATE)
        else:
            fill_price = current_price * (1 - self.SLIPPAGE_RATE)
        fee = amount * fill_price * self.fee_rate
        cost = amount * fill_price + fee

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
                self.balance.get(quote, 0) + amount * fill_price - fee
            )

        order = {
            "id": self._next_id(),
            "symbol": symbol,
            "side": side,
            "type": "market",
            "amount": amount,
            "price": fill_price,
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


# ── 선물 수수료율 ─────────────────────────────────────────────────────────────
FUTURES_FEE_RATE = 0.0004   # 0.04% per side (Binance Futures taker 기본)


class BinanceFuturesConnector:
    """
    Binance USDT-M 선물 전용 커넥터.
    testnet=True 이면 Binance Futures Testnet 사용.
    is_paper=True 이면 FuturesPaperBroker 만 사용 (API 키 불필요).
    """

    def __init__(self, api_key: str = "", secret: str = "", testnet: bool = False):
        self._exchange = ccxt.binance({
            "apiKey":  api_key,
            "secret":  secret,
            "options": {"defaultType": "future"},
            "enableRateLimit": True,
            "timeout": REQUEST_TIMEOUT,
        })
        if testnet:
            self._exchange.set_sandbox_mode(True)
        self.testnet = testnet

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """심볼별 레버리지 설정. leverage: 1~125 (기본 5)."""
        await self._exchange.set_leverage(leverage, symbol)

    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        """mode: 'cross' | 'isolated'. 이미 설정된 경우 오류 무시."""
        try:
            await self._exchange.set_margin_mode(mode, symbol)
        except Exception:
            pass

    async def open_long(self, symbol: str, usdt_amount: float, leverage: int) -> dict:
        """USDT 기준 롱 진입. quantity = usdt_amount * leverage / mark_price."""
        mark_price = await self.get_mark_price(symbol)
        qty = round((usdt_amount * leverage) / mark_price, 3)
        return await self._exchange.create_market_buy_order(symbol, qty)

    async def open_short(self, symbol: str, usdt_amount: float, leverage: int) -> dict:
        """USDT 기준 숏 진입."""
        mark_price = await self.get_mark_price(symbol)
        qty = round((usdt_amount * leverage) / mark_price, 3)
        return await self._exchange.create_market_sell_order(
            symbol, qty, {"reduceOnly": False}
        )

    async def close_position(self, symbol: str, side: str, qty: float) -> dict:
        """side: 'long' | 'short'. reduceOnly=True 로 포지션만 청산."""
        if side == "long":
            return await self._exchange.create_market_sell_order(
                symbol, qty, {"reduceOnly": True}
            )
        return await self._exchange.create_market_buy_order(
            symbol, qty, {"reduceOnly": True}
        )

    async def get_mark_price(self, symbol: str) -> float:
        ticker = await self._exchange.fetch_ticker(symbol)
        return ticker.get("markPrice") or ticker["last"]

    async def get_liquidation_price(self, symbol: str) -> Optional[float]:
        try:
            positions = await self._exchange.fetch_positions([symbol])
            for p in positions:
                if p["symbol"] == symbol and (p.get("contracts") or 0) > 0:
                    return p.get("liquidationPrice")
        except Exception:
            pass
        return None

    async def get_funding_rate(self, symbol: str) -> float:
        """현재 펀딩비. 양수=롱이 숏에게 지불, 음수=숏이 롱에게 지불."""
        try:
            info = await self._exchange.fetch_funding_rate(symbol)
            return info.get("fundingRate", 0.0)
        except Exception:
            return 0.0

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> pd.DataFrame:
        bars = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df.astype(float)

    async def fetch_ticker(self, symbol: str) -> dict:
        return await self._exchange.fetch_ticker(symbol)

    async def get_balance(self) -> dict:
        """{'total': float, 'free': float, 'used': float} — USDT 기준."""
        bal = await self._exchange.fetch_balance()
        usdt = bal.get("USDT", {})
        return {
            "total": usdt.get("total", 0.0),
            "free":  usdt.get("free",  0.0),
            "used":  usdt.get("used",  0.0),
        }

    async def close(self):
        await self._exchange.close()


class FuturesPaperBroker:
    """
    선물 모의 거래 브로커.
    USDT 증거금 방식 (Isolated Margin 근사). 롱/숏 양방향 지원.
    슬리피지(bid/ask spread 근사)를 적용해 실거래와 유사한 환경을 시뮬레이션.
    """

    SLIPPAGE_RATE = 0.0005  # 0.05% — 선물은 현물보다 spread 좁음

    def __init__(self, initial_balance: float = 1_000.0):
        self.usdt_balance: float = initial_balance
        self.positions: dict[str, dict] = {}   # symbol → position dict
        self.fee_rate: float = FUTURES_FEE_RATE
        self._order_id = 0

    def _next_id(self) -> str:
        self._order_id += 1
        return f"FPAPER-{self._order_id:06d}"

    def open_position(
        self,
        symbol: str,
        side: str,          # 'long' | 'short'
        usdt_amount: float, # 투입 증거금 (USDT)
        leverage: int,
        price: float,
    ) -> dict:
        # 슬리피지: 롱 진입은 ask(+), 숏 진입은 bid(-)
        fill_price = price * (1 + self.SLIPPAGE_RATE) if side == "long" else price * (1 - self.SLIPPAGE_RATE)
        price = fill_price
        contracts = (usdt_amount * leverage) / price
        fee = contracts * price * self.fee_rate
        required = usdt_amount + fee

        if self.usdt_balance < required:
            raise ValueError(
                f"USDT 잔고 부족: {required:.4f} 필요, 현재 {self.usdt_balance:.4f}"
            )
        self.usdt_balance -= required

        # 청산가 근사 (Isolated Margin, MMR=0.5%)
        mmr = 0.005
        liq_price = (
            price * (1 - 1 / leverage + mmr) if side == "long"
            else price * (1 + 1 / leverage - mmr)
        )

        self.positions[symbol] = {
            "side":              side,
            "entry_price":       price,
            "contracts":         contracts,
            "leverage":          leverage,
            "initial_margin":    usdt_amount,
            "liquidation_price": liq_price,
            "unrealized_pnl":    0.0,
            "entry_fee":         fee,
            "funding_paid":      0.0,
        }
        return {
            "id":        self._next_id(),
            "symbol":    symbol,
            "side":      side,
            "price":     price,
            "contracts": contracts,
            "fee":       fee,
            "status":    "closed",
        }

    def close_position(self, symbol: str, price: float) -> dict:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            raise ValueError(f"포지션 없음: {symbol}")

        contracts = pos["contracts"]
        entry     = pos["entry_price"]
        side      = pos["side"]
        # 슬리피지: 롱 청산은 bid(-), 숏 청산은 ask(+)
        price = price * (1 - self.SLIPPAGE_RATE) if side == "long" else price * (1 + self.SLIPPAGE_RATE)
        exit_fee  = contracts * price * self.fee_rate

        raw_pnl = (
            (price - entry) * contracts if side == "long"
            else (entry - price) * contracts
        )
        pnl = raw_pnl - pos["entry_fee"] - exit_fee - pos["funding_paid"]
        self.usdt_balance += pos["initial_margin"] + pnl

        return {
            "id":        self._next_id(),
            "symbol":    symbol,
            "side":      side,
            "price":     price,
            "contracts": contracts,
            "pnl":       round(pnl, 6),
            "fee":       exit_fee,
            "status":    "closed",
        }

    def update_unrealized_pnl(self, symbol: str, mark_price: float):
        pos = self.positions.get(symbol)
        if pos is None:
            return
        entry     = pos["entry_price"]
        contracts = pos["contracts"]
        pos["unrealized_pnl"] = (
            (mark_price - entry) * contracts if pos["side"] == "long"
            else (entry - mark_price) * contracts
        )

    def apply_funding(self, symbol: str, funding_rate: float):
        """펀딩비 부과. 롱은 양수 펀딩비 지불, 숏은 음수 펀딩비 지불."""
        pos = self.positions.get(symbol)
        if pos is None:
            return
        notional = pos["contracts"] * pos["entry_price"]
        # 롱: funding_rate > 0 이면 비용, 숏: funding_rate < 0 이면 비용
        if pos["side"] == "long":
            cost = notional * funding_rate
        else:
            cost = notional * (-funding_rate)
        if cost > 0:
            pos["funding_paid"] += cost
            self.usdt_balance = max(0.0, self.usdt_balance - cost)

    def get_balance(self) -> dict:
        return {"USDT": self.usdt_balance}
