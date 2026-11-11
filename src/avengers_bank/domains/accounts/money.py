"""돈 실행 지점 (ADR 0007). 계좌 잔액과 장부는 여기서만 바꾼다.

요청 단계(이체 요청 만들기)와 실행 단계(승인 후)가 같은 검사(check_transfer)를 쓴다.
실행 단계는 행을 잠근 뒤 다시 검사해서, 요청과 승인 사이에 바뀐 상황(다른 출금 등)을 반영한다.
"""

import uuid
from datetime import UTC, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import KST, today_kst
from avengers_bank.domains.accounts.categories import classify
from avengers_bank.domains.accounts.models import Account, AccountTransaction
from avengers_bank.domains.interbank.models import InterbankReceipt
from avengers_bank.domains.users.models import User


class TransferRejected(Exception):
    """이체를 할 수 없는 이유. 요청 단계에서는 400으로, 실행 단계에서는 승인 대기 FAILED로 바뀐다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


async def today_transfer_out(db: AsyncSession, account_id: int) -> int:
    """오늘(한국 날짜) 다른 사람에게 보낸 합계. 1일 한도는 TRANSFER_OUT만 센다 (ERD 규칙 12)"""
    # UTC로 바꿔서 넘긴다: SQLite는 시간대를 버리고 저장해서, KST 그대로 넘기면 9시간 어긋난다
    since = datetime.combine(today_kst(), time(0), KST).astimezone(UTC)
    total = await db.scalar(
        select(func.coalesce(func.sum(AccountTransaction.amount), 0)).where(
            AccountTransaction.account_id == account_id,
            AccountTransaction.tx_type == "TRANSFER_OUT",
            AccountTransaction.created_at >= since,
        )
    )
    return -total


def check_transfer(
    src: Account | None,
    dst: Account | None,
    amount: int,
    sent_today: int,
    opening_deposit: bool = False,
) -> bool:
    """이체해도 되는지 검사하고, 내 계좌끼리 이동이면 True. 안 되면 TransferRejected."""
    if src is None or src.status != "ACTIVE":
        raise TransferRejected("ACCOUNT_NOT_FOUND", "보내는 계좌를 찾을 수 없습니다.")
    if src.account_type != "CHECKING":
        raise TransferRejected(
            "ACCOUNT_CANNOT_SEND", "입출금 계좌에서만 보낼 수 있습니다."
        )
    if dst is None or dst.status != "ACTIVE":
        raise TransferRejected("RECEIVER_NOT_FOUND", "받는 계좌를 찾을 수 없습니다.")
    if dst.account_id == src.account_id:
        raise TransferRejected("SAME_ACCOUNT", "같은 계좌로는 보낼 수 없습니다.")
    internal = src.user_id == dst.user_id
    # 남에게는 입출금 계좌로만. 내 적금에는 납입할 수 있다. 예금은 가입 때 한 번만 넣는다
    receivable = dst.account_type == "CHECKING" or (
        internal and dst.account_type == "SAVINGS"
    )
    if not (
        receivable or (opening_deposit and internal and dst.account_type == "DEPOSIT")
    ):
        raise TransferRejected(
            "ACCOUNT_CANNOT_RECEIVE", "이 계좌로는 보낼 수 없습니다."
        )
    if amount > src.balance:
        raise TransferRejected("INSUFFICIENT_BALANCE", "잔액이 부족합니다.")
    if not internal:  # 이체 한도는 다른 사람에게 보낼 때만
        if amount > src.per_transfer_limit:
            raise TransferRejected(
                "PER_TRANSFER_LIMIT_EXCEEDED",
                f"1회 이체 한도({src.per_transfer_limit:,}원)를 넘습니다.",
            )
        if sent_today + amount > src.daily_transfer_limit:
            left = max(src.daily_transfer_limit - sent_today, 0)
            raise TransferRejected(
                "DAILY_LIMIT_EXCEEDED", f"오늘 더 보낼 수 있는 금액은 {left:,}원입니다."
            )
    return internal


async def execute_transfer(
    db: AsyncSession,
    *,
    owner_user_id: int,
    from_account_id: int,
    to_account_id: int,
    amount: int,
    action_id: uuid.UUID | None,
    memo: str | None,
    opening_deposit: bool = False,
) -> uuid.UUID:
    """호출한 쪽의 트랜잭션 안에서 실행한다. 잔액 변경 + 장부 두 줄 + (호출한 쪽의) 승인 상태 변경이 함께 커밋된다."""
    # 잠금 순서: 계좌 id 오름차순 (ERD 규칙 5). 예산 기능이 생기면 그 앞에 예산 주기 행을 잠근다
    accounts = {
        a.account_id: a
        for a in await db.scalars(
            select(Account)
            .where(Account.account_id.in_({from_account_id, to_account_id}))
            .order_by(Account.account_id)
            .with_for_update()
            # 같은 세션에 예전에 읽은 계좌가 있어도 잠근 뒤의 최신 값으로 덮어쓴다 (잔액 유실 방지)
            .execution_options(populate_existing=True)
        )
    }
    src, dst = accounts.get(from_account_id), accounts.get(to_account_id)
    if (
        src is not None and src.user_id != owner_user_id
    ):  # 실행 직전 소유권 재검사 (승인·실행 규칙 3)
        src = None
    internal = check_transfer(
        src, dst, amount, await today_transfer_out(db, from_account_id), opening_deposit
    )
    # 가드 목록 (ADR 0007): 예산 가드는 예산 기능 PR에서 여기에 들어간다

    names = dict(
        (
            await db.execute(
                select(User.user_id, User.name).where(
                    User.user_id.in_({src.user_id, dst.user_id})
                )
            )
        ).all()
    )
    src.balance -= amount
    dst.balance += amount
    transfer_id = uuid.uuid4()
    out_type, in_type = (
        ("INTERNAL_OUT", "INTERNAL_IN") if internal else ("TRANSFER_OUT", "TRANSFER_IN")
    )
    db.add_all(
        [
            AccountTransaction(
                account_id=src.account_id,
                action_id=action_id,
                transfer_id=transfer_id,
                tx_type=out_type,
                amount=-amount,
                balance_after=src.balance,
                counterparty_name=names[dst.user_id],
                counterparty_account=dst.account_num,
                memo=memo,
                category=classify(out_type, memo, names[dst.user_id]),
            ),
            AccountTransaction(
                account_id=dst.account_id,
                action_id=action_id,
                transfer_id=transfer_id,
                tx_type=in_type,
                amount=amount,
                balance_after=dst.balance,
                counterparty_name=names[src.user_id],
                counterparty_account=src.account_num,
                memo=memo,
                category=classify(in_type, memo, names[src.user_id]),
            ),
        ]
    )
    await db.flush()
    return transfer_id


async def execute_card_ledger(
    db: AsyncSession,
    *,
    owner_user_id: int,
    account_id: int,
    tx_type: str,
    amount: int,
    merchant_name: str,
    category: str,
) -> AccountTransaction:
    """체크카드 결제(CARD_PAYMENT, amount −)와 취소 환불(REFUND, +)을 결제 계좌 장부에 쓴다 (ADR 0010).
    호출한 쪽 트랜잭션 안에서, 카드 행을 잠근 뒤에 부른다 (잠금 순서: 카드 → 계좌)"""
    account = await db.scalar(
        select(Account)
        .where(Account.account_id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # 환불도 ACTIVE 계좌로만. 결제 계좌가 해지됐으면 취소는 환불 대기가 되고 상담원이 다른 계좌로 보낸다 (ADR 0012)
    if (
        account is None
        or account.user_id != owner_user_id
        or account.status != "ACTIVE"
    ):
        raise TransferRejected("ACCOUNT_NOT_FOUND", "결제 계좌를 쓸 수 없습니다.")
    if account.balance + amount < 0:
        raise TransferRejected("INSUFFICIENT_BALANCE", "잔액이 부족합니다.")
    # 가드 목록 (ADR 0007): 예산 가드는 예산 기능 PR에서 여기에도 들어간다 (결제만)
    account.balance += amount
    tx = AccountTransaction(
        account_id=account.account_id,
        tx_type=tx_type,
        amount=amount,
        balance_after=account.balance,
        counterparty_name=merchant_name[:50],
        category=category,
    )
    db.add(tx)
    await db.flush()
    return tx


async def execute_interbank_receive(
    db: AsyncSession,
    *,
    transfer_id: uuid.UUID,
    to_account: str,
    amount: int,
    from_bank: str,
    from_account: str,
    sender_name: str,
    memo: str = "",
) -> tuple[AccountTransaction | None, bool]:
    """
    ClearingHub 외부 입금 실행.

    반환값:
        (거래내역, 신규 입금 여부)

    주의:
        호출자가 db.begin() 트랜잭션을 관리해야 한다.
        허브 서명과 요청 데이터 검증이 끝난 뒤 호출한다.
    """

    # 1. 같은 이체 ID가 이미 처리되었는지 확인
    existing = await db.get(InterbankReceipt, transfer_id)

    if existing is not None:
        # 동일 ID를 다른 계좌나 금액에 재사용하는 경우 차단
        if (
            existing.amount != amount
            or existing.sender_bank_code != from_bank
            or existing.sender_account != from_account
        ):
            raise ValueError("동일한 이체 ID의 거래 내용이 다릅니다.")

        # 이미 완료된 거래이므로 잔액을 다시 변경하지 않음
        return None, False

    # 2. 입금 계좌 조회 및 잠금
    account = await db.scalar(
        select(Account)
        .where(Account.account_num == to_account)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    # 3. 계좌 상태 및 금액 검증
    if account is None:
        raise TransferRejected(
            "ACCOUNT_NOT_FOUND",
            "받는 계좌가 없습니다.",
        )

    if account.status != "ACTIVE":
        raise TransferRejected(
            "ACCOUNT_INACTIVE",
            "입금할 수 없는 계좌입니다.",
        )

    if account.account_type != "CHECKING":
        raise TransferRejected(
            "ACCOUNT_INACTIVE",
            "입출금 계좌만 외부 입금을 받을 수 있습니다.",
        )

    if type(amount) is not int or amount <= 0:
        raise TransferRejected(
            "AMOUNT_INVALID",
            "입금 금액이 올바르지 않습니다.",
        )

    # 4. 중복 방지 기록을 먼저 DB에 등록
    receipt = InterbankReceipt(
        transfer_id=transfer_id,
        account_id=account.account_id,
        amount=amount,
        sender_bank_code=from_bank,
        sender_account=from_account,
    )

    db.add(receipt)

    # PRIMARY KEY 중복 충돌을 이 시점에서 검사
    await db.flush()

    # 5. 실제 계좌 잔액 증가
    account.balance += amount

    # 6. 기존 장부에 외부 입금 내역 생성
    transaction = AccountTransaction(
        account_id=account.account_id,
        transfer_id=transfer_id,
        tx_type="TRANSFER_IN",
        amount=amount,
        balance_after=account.balance,
        counterparty_name=sender_name[:50],
        counterparty_account=from_account[:30],
        memo=memo[:100],
        category=classify("TRANSFER_IN", memo, sender_name),
    )

    db.add(transaction)

    # 7. DB에 변경 내용 전송
    # 아직 commit은 하지 않음
    await db.flush()

    return transaction, True
