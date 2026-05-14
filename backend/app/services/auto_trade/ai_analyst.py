"""
자동매매봇 AI 분석 모듈 (TODO 1~4 구현).

무료 AI (Ollama/Groq) 최적화:
- 프롬프트 최소화 (< 400 토큰)
- 결과 캐싱으로 API 호출 절약
- 타임아웃 + 폴백 (AI 실패 시 봇 정상 동작 보장)

호출 빈도 관리:
- 진입 확인: 종목당 10분 캐시
- 시장 국면: 15분 캐시
- 손절 분석: 연속 손절 3회마다 1회
- 청산 보조: 수익 중 포지션, 종목당 5분 캐시
"""
import asyncio
import json
import logging
import time
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_FILE = Path(__file__).parent.parent.parent.parent / "ai_settings.json"

# ── 인메모리 캐시 ─────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, dict]] = {}

CACHE_TTL: dict[str, int] = {
    "entry":  600,   # 10분
    "regime": 900,   # 15분
    "exit":   300,   # 5분
}

# ── 런타임 설정 (DB에서 주입, 파일보다 우선) ──────────────────────────────
_runtime_cfg: dict | None = None


def set_config(cfg: dict) -> None:
    """
    AI 설정을 런타임 메모리에 주입.
    설정 저장 시 즉시 호출 → 재시작 없이 모든 프로바이더 즉시 적용.
    """
    global _runtime_cfg
    _runtime_cfg = {
        "provider":   cfg.get("provider", "ollama"),
        "model":      cfg.get("model", "llama3.2"),
        "api_key":    cfg.get("api_key", ""),
        "ollama_url": cfg.get("ollama_url", "http://localhost:11434"),
    }
    # 프로바이더/모델이 바뀌면 LLM 응답 캐시도 초기화
    _cache.clear()
    logger.info(f"AI 설정 갱신: provider={_runtime_cfg['provider']} model={_runtime_cfg['model']}")


def _load_cfg() -> dict:
    # 1순위: 런타임 주입값 (DB에서 저장 시 갱신됨)
    if _runtime_cfg is not None:
        return _runtime_cfg
    # 2순위: 파일 (이전 방식 호환 / 서버 첫 시작)
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"provider": "ollama", "model": "llama3.2", "api_key": "", "ollama_url": "http://localhost:11434"}


def is_ai_available() -> bool:
    """AI 사용 가능 여부 확인 (키 설정 여부)"""
    cfg = _load_cfg()
    provider = cfg.get("provider", "ollama")
    if provider == "ollama":
        return True  # 로컬은 항상 시도 가능
    return bool(cfg.get("api_key", ""))


def _get_cache(key: str, ttl: int) -> dict | None:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None


def _set_cache(key: str, val: dict):
    _cache[key] = (time.time(), val)


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 블록 추출"""
    text = text.strip()
    # 마크다운 코드블록 제거
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            if "{" in part:
                text = part.lstrip("json").strip()
                break
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("JSON not found in response")
    return json.loads(text[start:end])


# ── LLM 호출 ─────────────────────────────────────────────────────────────

async def _call(prompt: str, max_tokens: int = 120, timeout: float = 25.0) -> str:
    cfg = _load_cfg()
    provider = cfg.get("provider", "ollama")
    try:
        if provider == "ollama":
            return await asyncio.wait_for(_ollama(prompt, cfg, max_tokens), timeout=timeout)
        elif provider in ("groq", "openai"):
            return await asyncio.wait_for(_openai_compat(prompt, cfg, max_tokens), timeout=timeout)
        elif provider == "anthropic":
            return await asyncio.wait_for(_anthropic(prompt, cfg, max_tokens), timeout=timeout)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    except asyncio.TimeoutError:
        raise TimeoutError(f"AI 응답 타임아웃 ({timeout}s)")


async def _ollama(prompt: str, cfg: dict, max_tokens: int) -> str:
    base = cfg.get("ollama_url", "http://localhost:11434")
    payload = {
        "model": cfg.get("model", "llama3.2"),
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(f"{base}/api/chat", json=payload)
        res.raise_for_status()
    return res.json()["message"]["content"]


async def _openai_compat(prompt: str, cfg: dict, max_tokens: int) -> str:
    """Groq / OpenAI 호환 엔드포인트"""
    provider = cfg.get("provider", "groq")
    api_key = cfg.get("api_key", "")
    if not api_key:
        raise ValueError("API 키 없음")
    url = (
        "https://api.groq.com/openai/v1/chat/completions"
        if provider == "groq"
        else "https://api.openai.com/v1/chat/completions"
    )
    payload = {
        "model": cfg.get("model", "llama-3.3-70b-versatile"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(url, json=payload, headers={"Authorization": f"Bearer {api_key}"})
        if res.status_code == 429:
            raise ValueError("Groq 요청 한도 초과")
        res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"]


async def _anthropic(prompt: str, cfg: dict, max_tokens: int) -> str:
    api_key = cfg.get("api_key", "")
    if not api_key:
        raise ValueError("API 키 없음")
    payload = {
        "model": cfg.get("model", "claude-haiku-4-5-20251001"),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        res.raise_for_status()
    return res.json()["content"][0]["text"]



# ══════════════════════════════════════════════════════════════════════════
# TODO 1: AI 진입 확인
# ══════════════════════════════════════════════════════════════════════════

async def check_entry(
    symbol: str,
    score: int,
    strategy_type: str,
    signals: list[str],
    rsi: float,
) -> dict:
    """
    진입 여부 AI 검증.

    Returns:
        {
          "enter": bool,
          "confidence": int (50~95),
          "size_multiplier": float (1.0/1.1/1.2),
          "reason": str
        }
    실패 시 폴백: enter=True, confidence=70 (봇 정상 진행)
    """
    cache_key = f"entry:{symbol}:{score}:{strategy_type}"
    cached = _get_cache(cache_key, CACHE_TTL["entry"])
    if cached:
        logger.debug(f"AI 진입 캐시 사용: {symbol}")
        return cached

    signals_str = ", ".join(signals[:3]) if signals else "none"
    prompt = (
        f"Crypto entry decision. Reply ONLY with JSON. reason must be in Korean.\n"
        f"Symbol:{symbol} Score:{score}/100 Strategy:{strategy_type} "
        f"RSI:{rsi:.0f} Signals:{signals_str}\n"
        f'Should we enter now? {{"enter":true/false,"confidence":50-95,"reason":"한국어 1문장"}}'
    )

    try:
        raw = await _call(prompt, max_tokens=80)
        data = _parse_json(raw)
        confidence = max(50, min(95, int(data.get("confidence", 70))))
        result = {
            "enter":           bool(data.get("enter", True)),
            "confidence":      confidence,
            "size_multiplier": 1.2 if confidence >= 90 else (1.1 if confidence >= 80 else 1.0),
            "reason":          str(data.get("reason", "")),
        }
        _set_cache(cache_key, result)
        logger.info(
            f"AI 진입 확인 {symbol}: enter={result['enter']} "
            f"confidence={confidence} reason={result['reason']}"
        )
        return result
    except Exception as e:
        logger.warning(f"AI 진입 확인 실패 ({symbol}): {e}")
        return {"enter": True, "confidence": 70, "size_multiplier": 1.0, "reason": "AI 분석 실패 - 기본값"}


# ══════════════════════════════════════════════════════════════════════════
# 포지션별 매매 스타일 선택
# ══════════════════════════════════════════════════════════════════════════

async def choose_position_style(
    symbol: str,
    strategy_type: str,
    rsi: float,
    score: int,
    signals: list[str],
    global_style: str = "short",
) -> dict:
    """
    종목 특성에 맞는 최적 매매 스타일 AI 선택.
    - oversold_bounce / 낮은 RSI → mid / long (반등 대기)
    - macd_momentum / 거래량 급증 → scalping / short (빠른 모멘텀)
    - golden_cross → mid (추세 전환 추종)

    Returns: {"style": "scalping|short|mid|long", "reason": "한국어"}
    폴백: global_style 그대로 유지
    캐시: 10분 (진입 캐시와 동일 TTL)
    """
    cache_key = f"pstyle:{symbol}:{strategy_type}:{int(rsi)}"
    cached = _get_cache(cache_key, CACHE_TTL["entry"])
    if cached:
        return cached

    signals_str = ", ".join(signals[:3]) if signals else "none"
    prompt = (
        f"Pick best trading style for this crypto position. Reply ONLY JSON. reason in Korean.\n"
        f"Symbol:{symbol} Strategy:{strategy_type} RSI:{rsi:.0f} Score:{score} Signals:{signals_str}\n"
        f"Styles: scalping=tight SL/TP fast exit, short=hours, mid=days trend, long=patient oversold\n"
        f"Hints: oversold_bounce→mid/long, macd_momentum→scalping/short, "
        f"golden_cross→mid, volume_breakout→short, RSI<30→mid/long, RSI>50→scalping/short\n"
        f'{{"style":"scalping/short/mid/long","reason":"한국어 1문장"}}'
    )

    try:
        raw = await _call(prompt, max_tokens=60)
        data = _parse_json(raw)
        style = data.get("style", global_style)
        if style not in ("scalping", "short", "mid", "long"):
            style = global_style
        result = {"style": style, "reason": str(data.get("reason", ""))}
        _set_cache(cache_key, result)
        logger.info(f"AI 포지션 스타일 {symbol}: {style} ({result['reason']})")
        return result
    except Exception as e:
        logger.warning(f"AI 스타일 선택 실패 ({symbol}): {e}")
        return {"style": global_style, "reason": "AI 미응답 - 글로벌 스타일 사용"}


# ══════════════════════════════════════════════════════════════════════════
# TODO 2: 시장 국면 감지
# ══════════════════════════════════════════════════════════════════════════

async def detect_regime(
    btc_closes: list[float],
    btc_rsi: float,
    btc_volume_ratio: float,
) -> dict:
    """
    BTC 데이터로 시장 국면 감지 (15분 캐시).

    Returns:
        {
          "regime": "trending" | "ranging" | "volatile",
          "style":  "scalping" | "short" | "mid" | "long",
          "min_score_delta": int (-10 ~ +10),
          "reason": str
        }
    """
    if len(btc_closes) < 10:
        return {"regime": "ranging", "style": "short", "min_score_delta": 0, "reason": "데이터 부족"}

    # 가격 1% 단위로 캐시 키 생성 (너무 자주 바뀌지 않도록)
    price_bucket = int(btc_closes[-1] / (btc_closes[-1] * 0.01)) if btc_closes[-1] > 0 else 0
    cache_key = f"regime:{price_bucket}"
    cached = _get_cache(cache_key, CACHE_TTL["regime"])
    if cached:
        logger.debug("AI 국면 캐시 사용")
        return cached

    recent = btc_closes[-10:]
    change_20 = (btc_closes[-1] - btc_closes[-20]) / btc_closes[-20] * 100 if len(btc_closes) >= 20 else 0
    closes_str = " ".join(f"{p:.0f}" for p in recent)

    prompt = (
        f"Crypto market regime. Reply ONLY with JSON. reason must be in Korean.\n"
        f"BTC closes(10): {closes_str}\n"
        f"20-candle change:{change_20:+.1f}% RSI:{btc_rsi:.0f} VolRatio:{btc_volume_ratio:.1f}x\n"
        f"Trending=strong directional, Ranging=sideways, Volatile=choppy\n"
        f'Styles: scalping=fast, short=1h, mid=4h, long=1d\n'
        f'{{"regime":"trending/ranging/volatile","style":"scalping/short/mid/long",'
        f'"min_score_delta":-10to10,"reason":"한국어 1문장"}}'
    )

    try:
        raw = await _call(prompt, max_tokens=100)
        data = _parse_json(raw)
        result = {
            "regime":          str(data.get("regime", "ranging")),
            "style":           str(data.get("style", "short")),
            "min_score_delta": max(-10, min(10, int(data.get("min_score_delta", 0)))),
            "reason":          str(data.get("reason", "")),
        }
        # 유효성 검증
        if result["regime"] not in ("trending", "ranging", "volatile"):
            result["regime"] = "ranging"
        if result["style"] not in ("scalping", "short", "mid", "long"):
            result["style"] = "short"
        _set_cache(cache_key, result)
        logger.info(
            f"AI 시장 국면: {result['regime']} → 추천 스타일={result['style']} "
            f"점수조정={result['min_score_delta']:+d} ({result['reason']})"
        )
        return result
    except Exception as e:
        logger.warning(f"AI 국면 감지 실패: {e}")
        return {"regime": "ranging", "style": "short", "min_score_delta": 0, "reason": "AI 분석 실패"}


# ══════════════════════════════════════════════════════════════════════════
# TODO 3: 손절 후 자기 분석
# ══════════════════════════════════════════════════════════════════════════

async def analyze_losses(
    recent_trades: list[dict],
    current_settings: dict,
) -> dict:
    """
    연속 손절 원인 분석 → 파라미터 조정 제안.

    Returns:
        {
          "issue": str,
          "sl_pct_delta":    float (0 ~ 2.0),
          "min_score_delta": int   (0 ~ 10),
          "reason": str
        }
    """
    if not recent_trades:
        return {"issue": "NO_DATA", "sl_pct_delta": 0, "min_score_delta": 0, "reason": "데이터 없음"}

    trades_str = " | ".join(
        f"{t['symbol']} pnl={t['pnl_pct']:+.1f}% st={t.get('strategy_type','?')}"
        for t in recent_trades[:5]
    )
    prompt = (
        f"Analyze losing crypto trades. Reply ONLY with JSON. reason must be in Korean.\n"
        f"Losses: {trades_str}\n"
        f"Current: SL={current_settings.get('stop_loss_pct')}% "
        f"min_score={current_settings.get('min_score')}\n"
        f"Issues: SL_TOO_TIGHT, WRONG_STRATEGY, BAD_TIMING, MARKET_CONDITION\n"
        f'{{"issue":"TYPE","sl_pct_delta":0-2.0,"min_score_delta":0-10,"reason":"한국어 1문장"}}'
    )

    try:
        raw = await _call(prompt, max_tokens=100)
        data = _parse_json(raw)
        result = {
            "issue":           str(data.get("issue", "MARKET_CONDITION")),
            "sl_pct_delta":    max(0.0, min(2.0, float(data.get("sl_pct_delta", 0.5)))),
            "min_score_delta": max(0,   min(10,  int(data.get("min_score_delta", 5)))),
            "reason":          str(data.get("reason", "")),
        }
        logger.info(
            f"AI 손절 분석: issue={result['issue']} "
            f"SL+{result['sl_pct_delta']}% score+{result['min_score_delta']} ({result['reason']})"
        )
        return result
    except Exception as e:
        logger.warning(f"AI 손절 분석 실패: {e}")
        return {"issue": "MARKET_CONDITION", "sl_pct_delta": 0.5, "min_score_delta": 5, "reason": "AI 분석 실패"}


# ══════════════════════════════════════════════════════════════════════════
# TODO 4: 청산 타이밍 AI 보조
# ══════════════════════════════════════════════════════════════════════════

async def check_exit(
    symbol: str,
    pnl_pct: float,
    strategy_type: str,
    signals: list[str],
    sl_gap_pct: float,
    sl_pct: float = 2.5,
    tp_pct: float = 6.0,
) -> dict:
    """
    이익 중인 포지션의 청산 타이밍 판단 (5분 캐시).

    sl_gap_pct: 현재가와 SL 사이 거리 (%)
    sl_pct: 손절 설정값 (%)
    tp_pct: 익절 설정값 (%)

    Returns:
        {
          "action": "hold" | "tighten_sl" | "close_now",
          "reason": str
        }
    """
    cache_key = f"exit:{symbol}:{int(pnl_pct * 10)}"
    cached = _get_cache(cache_key, CACHE_TTL["exit"])
    if cached:
        return cached

    signals_str = ", ".join(signals[:3]) if signals else "none"
    tp_progress = round(pnl_pct / tp_pct * 100) if tp_pct > 0 else 0
    prompt = (
        f"Crypto exit decision. Reply ONLY with JSON. reason must be in Korean.\n"
        f"Symbol:{symbol} PnL:{pnl_pct:+.1f}% Strategy:{strategy_type} "
        f"SL:{sl_pct:.1f}% TP:{tp_pct:.1f}% TP_progress:{tp_progress}% "
        f"SL_gap:{sl_gap_pct:.1f}% Signals:{signals_str}\n"
        f"R:R context: if closed now, win={pnl_pct:.1f}% vs potential loss={sl_pct:.1f}%.\n"
        f"Prefer hold unless strong reversal signal. "
        f"Actions: hold=keep position, tighten_sl=raise stop loss, close_now=exit immediately\n"
        f'{{"action":"hold/tighten_sl/close_now","reason":"한국어 1문장"}}'
    )

    try:
        raw = await _call(prompt, max_tokens=80)
        data = _parse_json(raw)
        action = str(data.get("action", "hold"))
        if action not in ("hold", "tighten_sl", "close_now"):
            action = "hold"
        result = {"action": action, "reason": str(data.get("reason", ""))}
        _set_cache(cache_key, result)
        if action != "hold":
            logger.info(f"AI 청산 보조 {symbol}: {action} ({result['reason']})")
        return result
    except Exception as e:
        logger.warning(f"AI 청산 보조 실패 ({symbol}): {e}")
        return {"action": "hold", "reason": "AI 분석 실패"}
