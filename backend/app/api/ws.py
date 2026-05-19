"""
WebSocket 엔드포인트 - 실시간 시세 + 전략 상태 전송.

오류 처리:
- 거래소 요청 실패 시 지수 백오프 (최대 60초 대기)
- 연결 끊김 시 에러 상태를 클라이언트에 전달 후 재시도
- 로그는 처음 실패 시에만 출력 (같은 오류 반복 제거)
"""
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from ..services.exchange.connector import ExchangeConnector
from ..services.strategy.scheduler import get_scheduler

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

# 백오프 설정
BACKOFF_MIN = 3      # 초기 대기 (초)
BACKOFF_MAX = 60     # 최대 대기 (초)
BACKOFF_MULT = 2     # 배수
TICK_INTERVAL = 3    # 정상 시 폴링 간격 (초)


@router.websocket("/ws/ticker")
async def ws_ticker(
    websocket: WebSocket,
    symbol: str = Query("BTC/KRW"),
    exchange: str = Query("upbit"),
):
    await websocket.accept()
    connector = ExchangeConnector(exchange_id=exchange, is_paper=True)

    backoff = BACKOFF_MIN
    last_error: str = ""

    try:
        while True:
            try:
                ticker = await asyncio.wait_for(
                    connector.fetch_ticker(symbol),
                    timeout=10,
                )
                await websocket.send_json({
                    "type": "ticker",
                    "symbol": symbol,
                    "last": ticker["last"],
                    "bid": ticker["bid"],
                    "ask": ticker["ask"],
                    "change_pct": ticker.get("percentage") or 0,
                    "volume": ticker.get("quoteVolume") or 0,
                })
                # 성공 시 백오프 리셋
                backoff = BACKOFF_MIN
                last_error = ""
                await asyncio.sleep(TICK_INTERVAL)

            except WebSocketDisconnect:
                raise

            except asyncio.TimeoutError:
                err = f"{exchange} 요청 타임아웃"
                if err != last_error:
                    logger.warning(f"WS ticker timeout: {symbol}@{exchange}")
                    last_error = err
                await websocket.send_json({"type": "error", "message": err, "backoff": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULT, BACKOFF_MAX)

            except Exception as e:
                err = str(e).split("\n")[0][:120]  # 첫 줄만
                if err != last_error:
                    logger.warning(f"WS ticker error ({exchange}/{symbol}): {err}")
                    last_error = err
                await websocket.send_json({"type": "error", "message": err, "backoff": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULT, BACKOFF_MAX)

    except WebSocketDisconnect:
        pass
    finally:
        await connector.close()


@router.websocket("/ws/tickers")
async def ws_tickers(
    websocket: WebSocket,
    symbols: str = Query("BTC/KRW"),
    exchange: str = Query("upbit"),
):
    """여러 심볼을 한 커넥션으로 폴링. symbols=BTC/KRW,ETH/KRW,... 형식."""
    await websocket.accept()
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    connector = ExchangeConnector(exchange_id=exchange, is_paper=True)

    try:
        while True:
            tasks = [
                asyncio.wait_for(connector.fetch_ticker(sym), timeout=10)
                for sym in symbol_list
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, result in zip(symbol_list, results):
                if isinstance(result, Exception):
                    continue
                await websocket.send_json({
                    "type": "ticker",
                    "symbol": sym,
                    "last": result["last"],
                    "bid": result.get("bid", 0),
                    "ask": result.get("ask", 0),
                    "change_pct": result.get("percentage") or 0,
                    "volume": result.get("quoteVolume") or 0,
                })
            await asyncio.sleep(TICK_INTERVAL)

    except WebSocketDisconnect:
        pass
    finally:
        await connector.close()


@router.websocket("/ws/strategies")
async def ws_strategies(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            states = get_scheduler().get_all_states()
            await websocket.send_json({"type": "strategies", "data": states})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
