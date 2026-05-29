import logging
import sys
import os

# Windows 터미널 한글 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .core.database import init_db, AsyncSessionLocal
from .api import auth, strategies, backtest, market, trades, ws, exchange_accounts, auto_strategy, auto_bot, ai_config
from .services.auto_trade.bot import get_auto_bot
from .services.strategy.scheduler import get_scheduler

settings = get_settings()

# ── 로그 설정 ────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    os.system("")   # Windows ANSI 활성화


class _ColorFormatter(logging.Formatter):
    _C = {
        logging.DEBUG:    "\033[90m",   # 회색
        logging.INFO:     "\033[36m",   # 청록
        logging.WARNING:  "\033[33m",   # 노랑
        logging.ERROR:    "\033[31m",   # 빨강
        logging.CRITICAL: "\033[35m",   # 자홍
    }
    _TRADE = "\033[32;1m"   # 초록 굵게 — 진입/청산 이벤트
    _R = "\033[0m"

    def format(self, record):
        msg = record.getMessage()
        trade_event = record.levelno == logging.INFO and (
            ("진입" in msg or "청산" in msg or "피라미딩" in msg)
            and "차단" not in msg and "실패" not in msg
        )
        c = self._TRADE if trade_event else self._C.get(record.levelno, "")
        rec = logging.makeLogRecord(record.__dict__)
        rec.levelname = f"{c}{record.levelname:<8}{self._R}"
        rec.msg = f"{c}{record.msg}{self._R}"
        rec.args = record.args
        return super().format(rec)


class _BotFilter(logging.Filter):
    """
    봇/AI 로거(app.services.auto_trade, app.api.auto_bot)의 INFO를 선별 출력.
    나머지 로거의 INFO는 그대로 통과.
    WARNING 이상은 모두 통과.
    """
    _BOT_PREFIXES = ("app.services.auto_trade", "app.api.auto_bot", "app.api.ai_config")

    # INFO 통과 키워드 — 거래·상태 변화 이벤트
    _SHOW = (
        "진입", "청산", "피라미딩", "수동",          # 거래 이벤트
        "started", "stopped", "paused", "resumed", "full_stop",  # 봇 상태
        "국면", "MDD",                               # AI·리스크
        "AI 손절", "AI 청산 보조",                   # AI 결정
        "AI 설정 갱신",                              # 설정 변경
    )

    # INFO 억제 키워드 — 노이즈
    _HIDE = (
        "WS:", "구독 갱신", "연결 완료", "연결 종료",
        "잔고 변경", "설정 변경 적용",
        "DB전략 신호", "AI 포지션 스타일", "AI 진입 확인",
        "AI 국면 캐시", "동적 종목 발굴",
        "AutoBot 트레일링", "AutoBot: 전략 교체", "AutoBot: 신호 약화",
        "AutoBot: AI SL 상향",
    )

    def filter(self, record):
        if record.levelno >= logging.WARNING:
            return True
        is_bot = any(record.name.startswith(p) for p in self._BOT_PREFIXES)
        if not is_bot:
            return True
        msg = record.getMessage()
        if any(h in msg for h in self._HIDE):
            return False
        return any(s in msg for s in self._SHOW)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_ColorFormatter(
    fmt="%(asctime)s  %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
))
_handler.addFilter(_BotFilter())
logging.root.setLevel(logging.INFO)
logging.root.handlers = [_handler]

for _noisy in (
    "apscheduler", "apscheduler.executors", "apscheduler.scheduler",
    "ccxt", "ccxt.base.exchange",
    "httpx", "httpcore",
    "aiohttp", "aiohttp.access",
    "asyncio",
    "uvicorn.access",
    "sqlalchemy.engine", "sqlalchemy.pool",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


async def _load_ai_config_from_db():
    """서버 시작 시 DB에서 AI 설정을 로드해 런타임 메모리에 주입"""
    from sqlalchemy import select
    from .models.user_ai_config import UserAIConfig
    from .services.auto_trade import ai_analyst
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserAIConfig).limit(1))
            cfg = result.scalar_one_or_none()
            if cfg:
                ai_analyst.set_config({
                    "provider":   cfg.provider,
                    "model":      cfg.model,
                    "api_key":    cfg.api_key or "",
                    "ollama_url": cfg.ollama_url or "http://localhost:11434",
                })
    except Exception as e:
        logging.getLogger(__name__).warning(f"AI 설정 DB 로드 실패 (ai_settings.json 폴백): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _load_ai_config_from_db()
    get_scheduler().start()
    try:
        yield
    finally:
        await get_auto_bot().shutdown()
        await get_scheduler().stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(trades.router, prefix="/api/v1")
app.include_router(exchange_accounts.router, prefix="/api/v1")
app.include_router(auto_strategy.router, prefix="/api/v1")
app.include_router(auto_bot.router, prefix="/api/v1")
app.include_router(ai_config.router, prefix="/api/v1")
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
