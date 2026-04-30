import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .core.database import init_db
from .api import auth, strategies, backtest, market, trades, ws, exchange_accounts, auto_strategy, auto_bot, ai_config
from .services.strategy.scheduler import get_scheduler

settings = get_settings()

# ── 로그 레벨 설정 (노이즈 제거) ────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    get_scheduler().start()
    yield
    get_scheduler().stop()


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
