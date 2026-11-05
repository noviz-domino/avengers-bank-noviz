from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from avengers_bank.core.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.db_echo)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def in_sql(column: str, values: tuple[str, ...]) -> str:
    """CHECK 제약용 `column IN ('A', 'B')` 문장. 마이그레이션에는 결과 문자열을 그대로 적는다."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db:
        yield db
