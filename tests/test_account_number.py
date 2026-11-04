import pytest
from sqlalchemy.exc import IntegrityError

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.account_number import account_type_of, make_account_num
from avengers_bank.domains.accounts.models import CheckingAccount
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.users.models import User

pytestmark = pytest.mark.anyio


def test_make_account_num():
    assert make_account_num("checking", 1, 1) == "110-101-000001"
    assert make_account_num("savings", 12, 345) == "110-312-000345"
    with pytest.raises(ValueError):
        make_account_num("checking", 100, 1)
    with pytest.raises(ValueError):
        make_account_num("checking", 1, 0)


def test_account_type_of():
    assert account_type_of("110-101-000001") == "checking"
    assert account_type_of("110-201-000001") == "deposit"
    assert account_type_of("110-301-000001") == "savings"
    assert account_type_of("110-901-000001") is None
    assert account_type_of("999-101-000001") is None
    assert account_type_of("110-101-1") is None


async def test_check_constraint_rejects_wrong_type_code(client):
    async with SessionLocal() as db:
        db.add_all([
            User(login_id="ironman", hashed_password="x", name="토니", phone="010"),
            AccountProduct(type="CHECKING", name="통장", description="x", interest_rate=0),
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
