"""
시장 데이터 API - 차트용 OHLCV + 지표값 반환.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Query, HTTPException
from ..services.exchange.connector import ExchangeConnector
from ..services.indicator.engine import get_indicator_values

router = APIRouter(prefix="/market", tags=["market"])
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


async def _make_connector(exchange: str) -> ExchangeConnector:
    return ExchangeConnector(exchange_id=exchange, is_paper=True)


def _exchange_error(exchange: str, e: Exception) -> HTTPException:
    msg = str(e).split("\n")[0][:200]
    if "ExchangeNotAvailable" in type(e).__name__ or "NetworkError" in type(e).__name__:
        detail = f"{exchange} 거래소에 연결할 수 없습니다. 네트워크 또는 방화벽을 확인하세요. ({msg})"
    elif "RequestTimeout" in type(e).__name__:
        detail = f"{exchange} 요청 타임아웃. 잠시 후 다시 시도하세요."
    else:
        detail = f"거래소 오류: {msg}"
    logger.error(f"market API error ({exchange}): {msg}")
    return HTTPException(status_code=502, detail=detail)


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = Query("BTC/KRW"),
    timeframe: str = Query("1h"),
    limit: int = Query(500, ge=50, le=1500),
    exchange: str = Query("upbit"),
):
    connector = await _make_connector(exchange)
    try:
        df = await asyncio.wait_for(
            connector.fetch_ohlcv(symbol, timeframe, limit=limit),
            timeout=REQUEST_TIMEOUT,
        )
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": [
                {
                    # ts.value = nanoseconds since UTC epoch → always UTC seconds
                    "time": int(ts.value // 1_000_000_000),
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
                for ts, row in df.iterrows()
            ],
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"{exchange} 요청 타임아웃")
    except Exception as e:
        raise _exchange_error(exchange, e)
    finally:
        await connector.close()


@router.get("/indicators")
async def get_indicators(
    symbol: str = Query("BTC/KRW"),
    timeframe: str = Query("1h"),
    limit: int = Query(500),
    exchange: str = Query("upbit"),
    indicators: str = Query("[]"),
):
    try:
        indicator_configs = json.loads(indicators)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="indicators 파라미터가 올바른 JSON 배열이 아닙니다.")

    connector = await _make_connector(exchange)
    try:
        df = await asyncio.wait_for(
            connector.fetch_ohlcv(symbol, timeframe, limit=limit),
            timeout=REQUEST_TIMEOUT,
        )
        values = get_indicator_values(df, indicator_configs)
        return {"symbol": symbol, "indicators": values}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"{exchange} 요청 타임아웃")
    except Exception as e:
        raise _exchange_error(exchange, e)
    finally:
        await connector.close()


@router.get("/ticker")
async def get_ticker(
    symbol: str = Query("BTC/KRW"),
    exchange: str = Query("upbit"),
):
    connector = await _make_connector(exchange)
    try:
        ticker = await asyncio.wait_for(
            connector.fetch_ticker(symbol),
            timeout=REQUEST_TIMEOUT,
        )
        return {
            "symbol": symbol,
            "last": ticker["last"],
            "bid": ticker["bid"],
            "ask": ticker["ask"],
            "change_pct": ticker.get("percentage") or 0,
            "volume": ticker.get("quoteVolume") or 0,
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"{exchange} 요청 타임아웃")
    except Exception as e:
        raise _exchange_error(exchange, e)
    finally:
        await connector.close()


@router.get("/markets")
async def get_markets(exchange: str = Query("upbit")):
    """거래소 전체 종목 목록 반환 (KRW 마켓)"""
    connector = await _make_connector(exchange)
    try:
        markets = await asyncio.wait_for(
            connector._exchange.load_markets(),
            timeout=REQUEST_TIMEOUT,
        )
        await connector.close()
    except Exception as e:
        await connector.close()
        raise _exchange_error(exchange, e)

    symbols = sorted([
        symbol for symbol in markets.keys()
        if symbol.endswith("/KRW") and markets[symbol].get("active", True)
    ])
    return {"exchange": exchange, "symbols": symbols}


@router.get("/exchanges")
async def get_supported_exchanges():
    return {
        "exchanges": [
            {"id": "upbit", "name": "Upbit", "note": "국내 최대 원화 거래소"},
            # 확장 시 여기에 추가
        ]
    }
