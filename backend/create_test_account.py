"""테스트 계정 생성 스크립트"""
import asyncio
from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_password
from app.models.user import User
from sqlalchemy import select

TEST_EMAIL = "demo@example.com"
TEST_PASSWORD = "demo1234!"
TEST_USERNAME = "demo"


async def main():
    await init_db()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == TEST_EMAIL))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[OK] 테스트 계정이 이미 존재합니다. (id={existing.id})")
        else:
            user = User(
                email=TEST_EMAIL,
                username=TEST_USERNAME,
                hashed_password=hash_password(TEST_PASSWORD),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"[OK] 테스트 계정 생성 완료 (id={user.id})")

    print()
    print("=== 테스트 로그인 정보 ===")
    print(f"  이메일:   {TEST_EMAIL}")
    print(f"  비밀번호: {TEST_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
