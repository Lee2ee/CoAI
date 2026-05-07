"""
AI 자동 전략 생성 - 멀티 프로바이더 지원.
설정은 ai_settings.json (ai_config API)에서 동적으로 읽어옴.
- ollama:    완전 무료, 로컬 실행
- groq:      무료 API 티어
- anthropic: Claude (유료)
- openai:    ChatGPT (유료)
- gemini:    Google Gemini (무료 Flash 포함)
"""
import json
import asyncio
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.user import User
from ..models.strategy import Strategy
from ..services.exchange.connector import ExchangeConnector
from ..services.indicator.engine import compute_indicator
from .deps import get_current_user
from .ai_config import get_user_ai_config

router = APIRouter(prefix="/auto-strategy", tags=["auto-strategy"])
logger = logging.getLogger(__name__)


# ─── LLM 호출 (ai_settings.json 기반) ─────────────────────────────────────

async def _call_llm(system: str, user_msg: str, cfg: dict) -> str:
    provider = cfg.get("provider", "ollama")

    if provider == "ollama":
        return await _call_ollama(system, user_msg, cfg)
    elif provider == "groq":
        return await _call_groq(system, user_msg, cfg)
    elif provider == "anthropic":
        return await _call_anthropic(system, user_msg, cfg)
    elif provider == "openai":
        return await _call_openai(system, user_msg, cfg)
    elif provider == "gemini":
        return await _call_gemini(system, user_msg, cfg)
    else:
        raise HTTPException(status_code=400, detail=f"알 수 없는 AI 프로바이더: {provider}")


async def _call_ollama(system: str, user_msg: str, cfg: dict) -> str:
    base = cfg.get("ollama_url", "http://localhost:11434")
    model = cfg.get("model", "llama3.2")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            res = await client.post(f"{base}/api/chat", json=payload)
            res.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Ollama 서버에 연결할 수 없습니다 ({base}). Ollama가 실행 중인지 확인하세요.",
            )
    return res.json()["message"]["content"]


async def _call_groq(system: str, user_msg: str, cfg: dict) -> str:
    api_key = cfg.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Groq API 키가 설정되지 않았습니다. 설정 메뉴에서 입력해주세요.")
    payload = {
        "model": cfg.get("model", "llama-3.3-70b-versatile"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Groq API 오류: {res.text[:200]}")
    return res.json()["choices"][0]["message"]["content"]


async def _call_anthropic(system: str, user_msg: str, cfg: dict) -> str:
    api_key = cfg.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Claude API 키가 설정되지 않았습니다. 설정 메뉴에서 입력해주세요.")
    payload = {
        "model": cfg.get("model", "claude-sonnet-4-6"),
        "max_tokens": 1500,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Claude API 오류: {res.text[:200]}")
    return res.json()["content"][0]["text"]


async def _call_openai(system: str, user_msg: str, cfg: dict) -> str:
    api_key = cfg.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="OpenAI API 키가 설정되지 않았습니다. 설정 메뉴에서 입력해주세요.")
    payload = {
        "model": cfg.get("model", "gpt-4o"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OpenAI API 오류: {res.text[:200]}")
    return res.json()["choices"][0]["message"]["content"]


async def _call_gemini(system: str, user_msg: str, cfg: dict) -> str:
    api_key = cfg.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Gemini API 키가 설정되지 않았습니다. 설정 메뉴에서 입력해주세요.")
    model = cfg.get("model", "gemini-2.0-flash")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user_msg}"}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json=payload,
        )
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Gemini API 오류: {res.text[:200]}")
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]


# ─── 시장 분석 ──────────────────────────────────────────────────────────────

def _build_market_summary(df, symbol: str, timeframe: str) -> str:
    close = df["close"]
    current_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    change_pct = (current_price - prev_price) / prev_price * 100

    lines = [
        f"Symbol: {symbol}, Timeframe: {timeframe}",
        f"Current price: {current_price:,.0f} KRW (change: {change_pct:+.2f}%)",
        f"24h High: {float(df['high'].tail(24).max()):,.0f}, Low: {float(df['low'].tail(24).min()):,.0f}",
        "",
        "=== Technical Indicators ===",
    ]

    try:
        rsi = compute_indicator(df, "RSI", {"length": 14})
        lines.append(f"RSI(14): {float(rsi.iloc[-1]):.2f}")
    except Exception:
        pass

    try:
        ema20 = compute_indicator(df, "EMA", {"length": 20})
        ema50 = compute_indicator(df, "EMA", {"length": 50})
        lines.append(f"EMA20: {float(ema20.iloc[-1]):,.0f}, EMA50: {float(ema50.iloc[-1]):,.0f}")
        lines.append(f"Price vs EMA20: {(current_price/float(ema20.iloc[-1])-1)*100:+.2f}%")
        lines.append(f"EMA20 vs EMA50: {(float(ema20.iloc[-1])/float(ema50.iloc[-1])-1)*100:+.2f}%")
    except Exception:
        pass

    try:
        macd = compute_indicator(df, "MACD", {"fast": 12, "slow": 26, "signal": 9})
        cols = macd.columns.tolist()
        lines.append(
            f"MACD: {float(macd[cols[0]].iloc[-1]):.2f}, "
            f"Signal: {float(macd[cols[2]].iloc[-1]):.2f}, "
            f"Histogram: {float(macd[cols[1]].iloc[-1]):.2f}"
        )
    except Exception:
        pass

    try:
        bb = compute_indicator(df, "BB", {"length": 20, "std": 2.0})
        cols = bb.columns.tolist()
        bbl = float(bb[cols[0]].iloc[-1])
        bbu = float(bb[cols[2]].iloc[-1])
        bb_pct = (current_price - bbl) / (bbu - bbl) * 100 if (bbu - bbl) > 0 else 50
        lines.append(f"Bollinger Band position: {bb_pct:.1f}% (0=lower, 100=upper)")
    except Exception:
        pass

    try:
        stoch = compute_indicator(df, "STOCH", {"k": 14, "d": 3, "smooth_k": 3})
        cols = stoch.columns.tolist()
        lines.append(f"Stochastic K: {float(stoch[cols[0]].iloc[-1]):.2f}, D: {float(stoch[cols[1]].iloc[-1]):.2f}")
    except Exception:
        pass

    try:
        avg_vol = float(df["volume"].tail(20).mean())
        cur_vol = float(df["volume"].iloc[-1])
        lines.append(f"Volume vs 20-avg: {(cur_vol/avg_vol-1)*100:+.1f}%")
    except Exception:
        pass

    lines.append("\nRecent 10 closes: " + ", ".join(f"{float(v):,.0f}" for v in df["close"].tail(10).tolist()))
    return "\n".join(lines)


# ─── 프롬프트 ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert quantitative trading strategy designer.
Analyze market data and return ONLY a valid JSON object with this exact structure (no markdown, no explanation):

{
  "symbol": "{{SYMBOL}}",
  "timeframe": "{{TIMEFRAME}}",
  "exchange": "upbit",
  "entry_conditions": [
    {"id": "e1", "indicator": "RSI", "params": {"length": 14}, "operator": "<", "value": 35},
    {"id": "e2", "indicator": "EMA_CROSS", "params": {"fast": 9, "slow": 21}, "operator": "cross_above"}
  ],
  "exit_conditions": [
    {"id": "x1", "indicator": "RSI", "params": {"length": 14}, "operator": ">", "value": 65}
  ],
  "risk": {
    "stop_loss_pct": 2.0,
    "take_profit_pct": 5.0,
    "position_size_pct": 5.0,
    "trailing_stop": false
  }
}

Rules:
- Indicators: RSI, EMA, SMA, MACD, BB, STOCH, ATR, EMA_CROSS
- Operators: <, >, <=, >=, ==, cross_above, cross_below
- EMA_CROSS: no "value" field needed
- MACD value=0 means crossing zero line
- 2-4 entry conditions, 1-3 exit conditions
- stop_loss_pct: 1.5-4.0, take_profit_pct: 2x-4x stop loss
- Be conservative with risk"""


# 지원 심볼 목록 (scanner.py SCAN_SYMBOLS와 동일하게 유지)
SUPPORTED_SYMBOLS = [
    "BTC/KRW", "ETH/KRW", "XRP/KRW", "SOL/KRW", "DOGE/KRW",
    "ADA/KRW", "AVAX/KRW", "LINK/KRW", "DOT/KRW", "ATOM/KRW",
    "MATIC/KRW", "LTC/KRW", "BCH/KRW", "ETC/KRW", "TRX/KRW",
    "NEAR/KRW", "APT/KRW", "OP/KRW", "SUI/KRW", "SEI/KRW",
    "SAND/KRW", "MANA/KRW", "ALGO/KRW", "HBAR/KRW", "VET/KRW",
]


# ─── API 엔드포인트 ─────────────────────────────────────────────────────────

class AutoStrategyRequest(BaseModel):
    symbol: str = "BTC/KRW"
    timeframe: str = "1h"
    exchange: str = "upbit"
    strategy_name: str = ""


@router.get("/provider")
async def get_provider(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 AI 프로바이더 설정 반환"""
    cfg = await get_user_ai_config(user.id, db)
    provider = cfg.get("provider", "ollama")
    needs_key = provider != "ollama"
    return {
        "provider": provider,
        "model": cfg.get("model", ""),
        "ready": not needs_key or bool(cfg.get("api_key", "")),
    }


@router.get("/symbols")
async def get_symbols(user: User = Depends(get_current_user)):
    """AI 전략 생성 지원 심볼 목록"""
    return {"symbols": SUPPORTED_SYMBOLS}


@router.post("/generate")
async def generate_strategy(
    req: AutoStrategyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 심볼 정규화 및 검증
    symbol = req.symbol.upper().strip()
    if "/" not in symbol:
        symbol = f"{symbol}/KRW"
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 심볼입니다: {symbol}. 지원 목록: {', '.join(SUPPORTED_SYMBOLS[:5])} 등"
        )

    # 시장 데이터 수집
    connector = ExchangeConnector(exchange_id=req.exchange, is_paper=True)
    try:
        df = await asyncio.wait_for(
            connector.fetch_ohlcv(symbol, req.timeframe, limit=200),
            timeout=20,
        )
        await connector.close()
    except asyncio.TimeoutError:
        await connector.close()
        raise HTTPException(status_code=504, detail="시장 데이터 조회 타임아웃")
    except Exception as e:
        await connector.close()
        raise HTTPException(status_code=502, detail=f"시장 데이터 조회 실패: {e}")

    if df is None or len(df) < 50:
        raise HTTPException(status_code=502, detail=f"{symbol} 데이터가 부족합니다. 다른 타임프레임을 시도해보세요.")

    market_summary = _build_market_summary(df, symbol, req.timeframe)

    # 사용자별 AI 설정 로드
    ai_cfg = await get_user_ai_config(user.id, db)

    # 심볼을 프롬프트에 직접 주입
    system_prompt = SYSTEM_PROMPT.replace("{{SYMBOL}}", symbol).replace("{{TIMEFRAME}}", req.timeframe)
    user_prompt = (
        f"Analyze the following market data and generate an optimal trading strategy.\n\n"
        f"{market_summary}\n\n"
        f"Generate a complete strategy JSON for {symbol} {req.timeframe}. "
        f"The symbol field MUST be exactly \"{symbol}\". Return ONLY the JSON object."
    )

    # AI 호출
    raw_text = await _call_llm(system_prompt, user_prompt, ai_cfg)

    # JSON 파싱
    try:
        text = raw_text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("JSON not found")
        config = json.loads(text[start:end])
    except Exception as e:
        logger.error(f"JSON parse error: {e}\nRaw: {raw_text[:500]}")
        raise HTTPException(status_code=502, detail="AI 응답 파싱 실패. 다시 시도해주세요.")

    # 필수 필드 검증
    for field in ["entry_conditions", "exit_conditions", "risk"]:
        if field not in config:
            raise HTTPException(
                status_code=502,
                detail=f"AI가 올바른 형식을 반환하지 않았습니다 (missing: {field}). 다시 시도해주세요."
            )

    # 심볼/타임프레임/거래소를 요청값으로 강제 덮어씀 (AI가 잘못 반환해도 안전)
    config["symbol"] = symbol
    config["timeframe"] = req.timeframe
    config["exchange"] = req.exchange

    # 전략 저장
    name = req.strategy_name or f"AI전략 {symbol} {req.timeframe}"
    strategy = Strategy(
        user_id=user.id,
        name=name,
        description=f"AI 자동 생성 ({ai_cfg.get('provider','ollama')} / {symbol} {req.timeframe})",
        config=config,
        is_paper=True,
        is_active=False,
    )
    db.add(strategy)
    await db.flush()

    return {
        "strategy_id": strategy.id,
        "name": strategy.name,
        "config": config,
        "market_summary": market_summary,
    }
