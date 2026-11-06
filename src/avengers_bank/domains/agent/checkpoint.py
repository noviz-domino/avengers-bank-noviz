"""대화 저장 (ADR 0006: PostgreSQL 체크포인터). 서버를 다시 켜도 대화가 남는다.

DB가 PostgreSQL이 아니거나(테스트의 SQLite) lifespan 밖에서는 메모리에 둔다: 그때는 서버를 다시 켜면 대화가 사라진다.
체크포인터 테이블(checkpoint*)은 LangGraph가 만들고 관리해서 alembic 대상이 아니다 (alembic/env.py에서 제외).
"""

from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.engine import make_url

from avengers_bank.core.config import get_settings

saver: BaseCheckpointSaver = InMemorySaver()


@asynccontextmanager
async def postgres_saver():
    """앱 lifespan에서 연다. 연결 풀을 써서 연결 하나가 끊겨도 다음 요청은 새 연결로 (PR #21 리뷰)"""
    global saver
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        yield
        return
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    conninfo = url.set(drivername="postgresql").render_as_string(hide_password=False)  # psycopg는 +드라이버를 모른다
    # LangGraph 문서의 연결 설정: 자동 커밋, prepared statement 끔(풀에서 연결을 돌려 쓰므로), dict 행
    kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    async with AsyncConnectionPool(conninfo, kwargs=kwargs, max_size=5, open=False) as pool:
        pg = AsyncPostgresSaver(pool)
        await pg.setup()  # 테이블이 없으면 만든다 (여러 번 불러도 안전)
        previous, saver = saver, pg
        try:
            yield
        finally:
            saver = previous
