from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate)
    await _seed_demo_user()


def _migrate(conn):
    """create_all이 누락한 컬럼을 ALTER TABLE로 추가 (SQLite용 수동 마이그레이션)"""
    from sqlalchemy import text, inspect

    inspector = inspect(conn)

    # auto_bot_trades 신규 컬럼 (선물 지원 추가 시 기존 DB에 없음)
    _add_columns_if_missing(conn, inspector, "auto_bot_trades", [
        ("market_type",       "VARCHAR(8)  NOT NULL DEFAULT 'spot'"),
        ("side",              "VARCHAR(8)  NOT NULL DEFAULT 'long'"),
        ("leverage",          "INTEGER     NOT NULL DEFAULT 1"),
        ("margin_mode",       "VARCHAR(16) NOT NULL DEFAULT 'cross'"),
        ("liquidation_price", "FLOAT"),
        ("funding_paid",      "FLOAT       NOT NULL DEFAULT 0.0"),
    ])


def _add_columns_if_missing(conn, inspector, table: str, columns: list[tuple[str, str]]):
    from sqlalchemy import text

    tables = inspector.get_table_names()
    if table not in tables:
        return  # create_all이 처리

    existing = {col["name"] for col in inspector.get_columns(table)}
    for col_name, col_def in columns:
        if col_name not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


async def _seed_demo_user():
    from sqlalchemy import select, or_
    from ..models.user import User
    from .security import hash_password

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(or_(User.email == "demo@coai.test", User.username == "demo"))
        )
        user = result.scalar_one_or_none()
        if user is None:
            session.add(User(
                email="demo@coai.test",
                username="demo",
                hashed_password=hash_password("demo1234!"),
            ))
        else:
            user.email = "demo@coai.test"
            user.username = "demo"
            user.hashed_password = hash_password("demo1234!")
        await session.commit()
