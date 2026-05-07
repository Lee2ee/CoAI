from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "CoAI Trading System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./coai.db"

    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    DEFAULT_EXCHANGE: str = "upbit"
    PAPER_TRADING_DEFAULT: bool = True

    # Risk limits
    MAX_POSITION_SIZE_PCT: float = 10.0
    MAX_DAILY_LOSS_PCT: float = 5.0

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    # AI 자동 전략 생성
    # 프로바이더: "ollama" (무료 로컬) | "groq" (무료 API) | "anthropic" (유료)
    AI_PROVIDER: str = "ollama"

    # Ollama (완전 무료, 로컬 실행 - https://ollama.com)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"      # ollama pull llama3.2

    # Groq (무료 API 티어 - https://console.groq.com)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Anthropic (유료)
    ANTHROPIC_API_KEY: str = ""

    # Gemini
    GEMINI_API_KEY: str = ""

    # Binance Futures
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET: str = ""
    BINANCE_FUTURES_TESTNET: bool = True   # 기본 테스트넷, 실거래 시 False

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
