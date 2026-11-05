import importlib.util
import inspect
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.exc import IntegrityError

from avengers_bank.core.database import Base, SessionLocal
from avengers_bank.domains.accounts.account_number import account_type_of, make_account_num
from avengers_bank.domains.accounts.models import Account, AccountTransaction
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.users.models import User

pytestmark = pytest.mark.anyio

VERSIONS = Path(__file__).parent.parent / "alembic" / "versions"
# CHECK를 만드는 마이그레이션. 새로 만들면 여기에 추가한다
CHECK_MIGRATIONS = ["c3d9e1a47b20", "d81f4b6c2e90", "f2b8d4e6a913", "b6e1f3a8c442"]


def load_migration(revision: str):
    path = next(VERSIONS.glob(f"{revision}_*.py"))
    spec = importlib.util.spec_from_file_location(revision, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model_checks() -> dict[str, str]:
    return {
        c.name: str(c.sqltext)
        for t in Base.metadata.tables.values() for c in t.constraints
        if isinstance(c, CheckConstraint)
    }


def test_make_account_num():
    assert make_account_num("CHECKING", 1, 1) == "110-101-000001"
    assert make_account_num("SAVINGS", 12, 345) == "110-312-000345"
    for bad in [("CHECKING", 100, 1), ("CHECKING", 1, 0), ("checking", 1, 1), ("LOAN", 1, 1)]:
        with pytest.raises(ValueError):
            make_account_num(*bad)


def test_account_type_of():
    assert account_type_of("110-101-000001") == "CHECKING"
    assert account_type_of("110-201-000001") == "DEPOSIT"
    assert account_type_of("110-301-000001") == "SAVINGS"
    for bad in ["110-901-000001", "999-101-000001", "110-101-1", "110-1ab-cdefgh", "110-1234567890"]:
        assert account_type_of(bad) is None, bad


def test_migration_checks_match_models():
    # alembic check는 CHECK 변경을 감지하지 못한다. 모델의 CHECK를 바꾸면 이 테스트가 깨지니,
    # 새 마이그레이션에 CHECKS를 적고 아래 revision을 그 파일로 바꾼다.
    in_migrations = {}
    for revision in CHECK_MIGRATIONS:
        in_migrations |= load_migration(revision).CHECKS
    in_migrations["ck_account_products_product_code"] = load_migration("ac577183c7ec").PRODUCT_CODE_CHECK
    assert in_migrations == model_checks()


def test_migration_creates_every_check():
    # CHECKS에 적어 놓고 upgrade()에서 빠뜨려도 위 테스트·alembic check·SQLite 테스트는 모두 통과한다
    for revision in CHECK_MIGRATIONS:
        migration = load_migration(revision)
        source = inspect.getsource(migration.upgrade)
        created = lambda n: any(  # noqa: E731
            p in source for p in (f"check('{n}')", f"create_check_constraint('{n}'", f"name='{n}'")
        )
        missing = [n for n in migration.CHECKS if not created(n)]
        assert not missing, (revision, missing)


async def seed(db) -> None:
    db.add_all([
        User(login_id="ironman", hashed_password="x", name="토니", phone="010", birth_date=date(1990, 1, 1)),
        AccountProduct(type="CHECKING", product_code=1, name="통장", description="x", base_rate=0),
        AccountProduct(type="DEPOSIT", product_code=1, name="예금", description="x", base_rate=3),
    ])
    await db.commit()


def checking(num: str, **kw) -> Account:
    return Account(
        user_id=1, product_id=1, account_type="CHECKING", account_num=num,
        per_transfer_limit=1_000_000, daily_transfer_limit=5_000_000, **kw,
    )


@pytest.mark.parametrize("bad", [
    {"account_num": "110-201-000002"},                            # 예금 번호를 입출금 계좌에
    {"account_num": "110-101-000002", "balance": -1},             # 잔액 음수
    {"account_num": "110-101-000002", "per_transfer_limit": None},  # 입출금인데 한도 없음
    {"account_num": "110-101-000002", "per_transfer_limit": 0},     # 한도 0
    {"account_num": "110-101-000002", "daily_transfer_limit": 1},   # 1일 한도 < 1회 한도
    {"account_num": "110-101-000002", "status": "DELETED"},
])
async def test_account_checks_reject(client, bad):
    async with SessionLocal() as db:
        await seed(db)
        db.add(checking("110-101-000001"))
        await db.commit()

        num = bad.pop("account_num")
        account = checking(num)
        for key, value in bad.items():
            setattr(account, key, value)
        db.add(account)
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_deposit_account_has_no_transfer_limit(client):
    async with SessionLocal() as db:
        await seed(db)
        db.add(Account(user_id=1, product_id=2, account_type="DEPOSIT", account_num="110-201-000001"))
        await db.commit()

        db.add(Account(
            user_id=1, product_id=2, account_type="DEPOSIT", account_num="110-201-000002",
            per_transfer_limit=1, daily_transfer_limit=1,
        ))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_transaction_checks_reject(client):
    async with SessionLocal() as db:
        await seed(db)
        db.add(checking("110-101-000001"))
        await db.commit()

        db.add(AccountTransaction(account_id=1, tx_type="DEPOSIT", amount=1000, balance_after=1000))
        await db.commit()

        for bad in [
            {"tx_type": "GIFT", "amount": 1, "balance_after": 1},
            {"tx_type": "DEPOSIT", "amount": 0, "balance_after": 1},
            {"tx_type": "WITHDRAW", "amount": 1000, "balance_after": 2000},  # 나가는 거래인데 +
            {"tx_type": "DEPOSIT", "amount": -1000, "balance_after": 0},     # 들어오는 거래인데 -
            {"tx_type": "WITHDRAW", "amount": -2000, "balance_after": -1000},
        ]:
            db.add(AccountTransaction(account_id=1, **bad))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()


async def test_product_code_unique_within_type(client):
    def product(type_, code):
        return AccountProduct(type=type_, product_code=code, name="상품", description="x", base_rate=0)

    async with SessionLocal() as db:
        db.add_all([product("CHECKING", 1), product("DEPOSIT", 1), product("LOAN", 1)])  # 종류가 다르면 같은 코드 가능
        await db.commit()

        for bad in [product("CHECKING", 1), product("SAVINGS", 100), product("CARD", 1)]:
            db.add(bad)
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
