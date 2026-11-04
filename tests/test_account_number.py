import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.exc import IntegrityError

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.account_number import (
    TYPE_CODES,
    account_type_of,
    check_constraint_sql,
    make_account_num,
)
from avengers_bank.domains.accounts.models import CheckingAccount
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.users.models import User

pytestmark = pytest.mark.anyio

VERSIONS = Path(__file__).parent.parent / "alembic" / "versions"


def load_migration(revision: str):
    path = next(VERSIONS.glob(f"{revision}_*.py"))
    spec = importlib.util.spec_from_file_location(revision, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_sql(model, name: str) -> str:
    return next(
        str(c.sqltext) for c in model.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == name
    )


def test_make_account_num():
    assert make_account_num("checking", 1, 1) == "110-101-000001"
    assert make_account_num("savings", 12, 345) == "110-312-000345"
    for bad in [("checking", 100, 1), ("checking", 1, 0), ("CHECKING", 1, 1), ("loan", 1, 1)]:
        with pytest.raises(ValueError):
            make_account_num(*bad)


def test_account_type_of():
    assert account_type_of("110-101-000001") == "checking"
    assert account_type_of("110-201-000001") == "deposit"
    assert account_type_of("110-301-000001") == "savings"
    for bad in ["110-901-000001", "999-101-000001", "110-101-1", "110-1ab-cdefgh", "110-1234567890"]:
        assert account_type_of(bad) is None, bad


def test_migration_checks_match_models():
    # alembic check는 CHECK 변경을 감지하지 못한다. 규칙을 바꾸면 이 테스트가 깨지니,
    # 새 마이그레이션을 만들고 아래에서 보는 revision을 그 파일로 바꾼다.
    accounts = load_migration("b46530c30681")
    assert accounts.CHECKS == {f"{t}_accounts": check_constraint_sql(t) for t in TYPE_CODES}

    products = load_migration("ac577183c7ec")
    assert products.PRODUCT_CODE_CHECK == check_sql(AccountProduct, "ck_account_products_product_code")


async def test_check_constraint_rejects_wrong_type_code(client):
    async with SessionLocal() as db:
        db.add_all([
            User(login_id="ironman", hashed_password="x", name="토니", phone="010"),
            AccountProduct(type="CHECKING", product_code=1, name="통장", description="x", interest_rate=0),
        ])
        await db.commit()

        def account(num):
            return CheckingAccount(
                user_id=1, product_id=1, account_num=num,
                per_transfer_limit=1, daily_transfer_limit=1,
            )

        db.add(account("110-101-000001"))
        await db.commit()

        db.add(account("110-201-000002"))  # 예금 번호를 입출금 테이블에
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_product_code_unique_within_type(client):
    def product(type_, code):
        return AccountProduct(type=type_, product_code=code, name="상품", description="x", interest_rate=0)

    async with SessionLocal() as db:
        db.add_all([product("CHECKING", 1), product("DEPOSIT", 1)])  # 종류가 다르면 같은 코드 가능
        await db.commit()

        db.add(product("CHECKING", 1))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        db.add(product("SAVINGS", 100))  # 1~99 밖
        with pytest.raises(IntegrityError):
            await db.commit()
