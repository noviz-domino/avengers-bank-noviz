# alembic/env.py
import asyncio
import selectors
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from avengers_bank.core.config import get_settings
from avengers_bank.core.database import Base
from avengers_bank.domains.accounts.models import Account, AccountTerms, AccountTransaction  # noqa: F401
from avengers_bank.domains.approvals.models import PendingAction  # noqa: F401
from avengers_bank.domains.audit.models import AuditLog  # noqa: F401
from avengers_bank.domains.budget.models import BudgetCycle, BudgetDecision, BudgetProfile, FixedExpense  # noqa: F401
from avengers_bank.domains.cards.models import Card, CardProduct, CardTransaction  # noqa: F401
from avengers_bank.domains.rag.models import RagChunk  # noqa: F401
from avengers_bank.domains.products.models import AccountProduct, ProductPreferentialRate  # noqa: F401
from avengers_bank.domains.users.models import RefreshToken, User  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
if config.config_file_name and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """LangGraph 체크포인터 테이블(checkpoint*)은 LangGraph가 만들고 관리한다 (ADR 0015). alembic check가 지우라고 하지 않게"""
    return not (type_ == "table" and reflected and name.startswith("checkpoint"))


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"}, include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    if sys.platform == "win32":
        asyncio.run(
            run_async_migrations(),
            loop_factory=lambda: asyncio.SelectorEventLoop(
                selectors.SelectSelector()
            ),
        )
    else:
        asyncio.run(run_async_migrations())
