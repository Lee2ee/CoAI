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
    await _seed_demo_user()


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
