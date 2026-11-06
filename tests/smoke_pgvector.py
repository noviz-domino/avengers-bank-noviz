"""CI의 PostgreSQL에서 pgvector 경로를 한 번 실제로 돌린다 (pytest는 SQLite라 이 경로를 못 지난다, PR #19 리뷰).

    uv run alembic upgrade head && uv run python tests/smoke_pgvector.py
"""

import asyncio

from sqlalchemy import delete

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.rag.models import EMBED_DIM, RagChunk
from avengers_bank.domains.rag.service import vector_rank


def axis(i: int) -> list[float]:
    v = [0.0] * EMBED_DIM
    v[i] = 1.0
    return v


async def main() -> None:
    async with SessionLocal() as db:
        async with db.begin():
            db.add_all([
                RagChunk(chunk_id=f"smoke#{i}", source="smoke", title="smoke", content="x", content_hash="x",
                         tokens=[], embedding_model="smoke", embedding=axis(i))
                for i in (0, 1)
            ])
        async with db.begin():
            ranked = await vector_rank(db, axis(1), 2)
            await db.execute(delete(RagChunk).where(RagChunk.source == "smoke"))
    assert db.get_bind().dialect.name == "postgresql", "PostgreSQL에서 돌려야 의미가 있다"
    assert ranked == ["smoke#1", "smoke#0"], ranked
    print("pgvector 코사인 검색 OK")


if __name__ == "__main__":
    asyncio.run(main())
