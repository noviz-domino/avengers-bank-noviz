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
from avengers_bank.domains.budget.calc import Budget, still_confirmed
from avengers_bank.domains.budget.service import lock_cycle
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
    src: Account | None, dst: Account | None, amount: int, sent_today: int, opening_deposit: bool = False
) -> bool:
    """이체해도 되는지 검사하고, 내 계좌끼리 이동이면 True. 안 되면 TransferRejected."""
    if src is None or src.status != "ACTIVE":
        raise TransferRejected("ACCOUNT_NOT_FOUND", "보내는 계좌를 찾을 수 없습니다.")
    if src.account_type != "CHECKING":
        raise TransferRejected("ACCOUNT_CANNOT_SEND", "입출금 계좌에서만 보낼 수 있습니다.")
    if dst is None or dst.status != "ACTIVE":
        raise TransferRejected("RECEIVER_NOT_FOUND", "받는 계좌를 찾을 수 없습니다.")
    if dst.account_id == src.account_id:
        raise TransferRejected("SAME_ACCOUNT", "같은 계좌로는 보낼 수 없습니다.")
    internal = src.user_id == dst.user_id
    # 남에게는 입출금 계좌로만. 내 적금에는 납입할 수 있다. 예금은 가입 때 한 번만 넣는다
    receivable = dst.account_type == "CHECKING" or (internal and dst.account_type == "SAVINGS")
    if not (receivable or (opening_deposit and internal and dst.account_type == "DEPOSIT")):
        raise TransferRejected("ACCOUNT_CANNOT_RECEIVE", "이 계좌로는 보낼 수 없습니다.")
    if amount > src.balance:
        raise TransferRejected("INSUFFICIENT_BALANCE", "잔액이 부족합니다.")
    if not internal:  # 이체 한도는 다른 사람에게 보낼 때만
        if amount > src.per_transfer_limit:
            raise TransferRejected("PER_TRANSFER_LIMIT_EXCEEDED", f"1회 이체 한도({src.per_transfer_limit:,}원)를 넘습니다.")
        if sent_today + amount > src.daily_transfer_limit:
            left = max(src.daily_transfer_limit - sent_today, 0)
            raise TransferRejected("DAILY_LIMIT_EXCEEDED", f"오늘 더 보낼 수 있는 금액은 {left:,}원입니다.")
    return internal


def check_budget_confirmed(budget: Budget, amount: int, budget_check: dict | None, emergency: bool = False) -> None:
    """예산 가드의 실행 때 재검사 (ADR 0007 "예산을 넘는 승인 건" 3). 승인 때 본 자유 사용 가능액(free_before)보다
    나빠졌으면 BUDGET_CHANGED. 미리 계산이 없던 요청(그사이 신청함)은 지금 숫자 안에 들어와야 통과.
    "긴급"으로 확인한 건은 다시 막지 않고 기록만 남긴다 (budget.md 결제 검사)"""
    free_at_confirm = budget_check["free_before"] if budget_check else amount
    if not emergency and not still_confirmed(budget.free_to_spend, amount, free_at_confirm):
        raise TransferRejected(
            "BUDGET_CHANGED",
            f"확인한 뒤 예산 상황이 나빠졌습니다(지금 자유 사용 가능액 {budget.free_to_spend:,}원). 바뀐 숫자를 보고 다시 요청해 주세요.",
        )


async def execute_transfer(
    db: AsyncSession, *, owner_user_id: int, from_account_id: int, to_account_id: int, amount: int,
    action_id: uuid.UUID | None, memo: str | None, opening_deposit: bool = False,
    budget_check: dict | None = None, emergency: bool = False,
) -> uuid.UUID:
    """호출한 쪽의 트랜잭션 안에서 실행한다. 잔액 변경 + 장부 두 줄 + (호출한 쪽의) 승인 상태 변경이 함께 커밋된다.
    budget_check: 요청 때 저장한 예산 미리 계산 (pending_actions.payload), emergency: 승인 때 "긴급" 선택"""
    # 잠금 순서: 예산 주기 행 → 계좌 id 오름차순 (ERD 규칙 5). 주기는 남에게 보낼 때(지출)만 잠근다.
    # 계좌 주인은 바뀌지 않아서 잠그기 전에 읽어도 된다. 내 계좌끼리(예금 가입 등)는 계좌를 먼저 잠근 호출도 있어서 잠그지 않는다
    receiver = await db.scalar(select(Account.user_id).where(Account.account_id == to_account_id))
    budget = await lock_cycle(db, owner_user_id) if receiver != owner_user_id else None
    accounts = {
        a.account_id: a for a in await db.scalars(
            select(Account).where(Account.account_id.in_({from_account_id, to_account_id}))
            .order_by(Account.account_id).with_for_update()
            # 같은 세션에 예전에 읽은 계좌가 있어도 잠근 뒤의 최신 값으로 덮어쓴다 (잔액 유실 방지)
            .execution_options(populate_existing=True)
        )
    }
    src, dst = accounts.get(from_account_id), accounts.get(to_account_id)
    if src is not None and src.user_id != owner_user_id:  # 실행 직전 소유권 재검사 (승인·실행 규칙 3)
        src = None
    internal = check_transfer(src, dst, amount, await today_transfer_out(db, from_account_id), opening_deposit)
    # 가드 목록 (ADR 0007): 예산 가드. 내 계좌끼리는 지출이 아니라 검사하지 않는다
    if budget is not None and not internal:
        check_budget_confirmed(budget[1], amount, budget_check, emergency)

    names = dict((await db.execute(
        select(User.user_id, User.name).where(User.user_id.in_({src.user_id, dst.user_id}))
    )).all())
    src.balance -= amount
    dst.balance += amount
    transfer_id = uuid.uuid4()
    out_type, in_type = ("INTERNAL_OUT", "INTERNAL_IN") if internal else ("TRANSFER_OUT", "TRANSFER_IN")
    db.add_all([
        AccountTransaction(
            account_id=src.account_id, action_id=action_id, transfer_id=transfer_id, tx_type=out_type,
            amount=-amount, balance_after=src.balance, counterparty_name=names[dst.user_id],
            counterparty_account=dst.account_num, memo=memo, category=classify(out_type, memo, names[dst.user_id]),
        ),
        AccountTransaction(
            account_id=dst.account_id, action_id=action_id, transfer_id=transfer_id, tx_type=in_type,
            amount=amount, balance_after=dst.balance, counterparty_name=names[src.user_id],
            counterparty_account=src.account_num, memo=memo, category=classify(in_type, memo, names[src.user_id]),
        ),
    ])
    await db.flush()
    return transfer_id


async def execute_card_ledger(
    db: AsyncSession, *, owner_user_id: int, account_id: int, tx_type: str, amount: int,
    merchant_name: str, category: str,
) -> AccountTransaction:
    """체크카드 결제(CARD_PAYMENT, amount −)와 취소 환불(REFUND, +)을 결제 계좌 장부에 쓴다 (ADR 0010).
    호출한 쪽 트랜잭션 안에서, 카드 행을 잠근 뒤에 부른다 (잠금 순서: 카드 → 계좌)"""
    account = await db.scalar(
        select(Account).where(Account.account_id == account_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    # 환불도 ACTIVE 계좌로만. 결제 계좌가 해지됐으면 취소는 환불 대기가 되고 상담원이 다른 계좌로 보낸다 (ADR 0012)
    if account is None or account.user_id != owner_user_id or account.status != "ACTIVE":
        raise TransferRejected("ACCOUNT_NOT_FOUND", "결제 계좌를 쓸 수 없습니다.")
    if account.balance + amount < 0:
        raise TransferRejected("INSUFFICIENT_BALANCE", "잔액이 부족합니다.")
    # 예산 가드(체크카드 결제)는 부르는 쪽(cards/service.py pay)이 카드 → 예산 주기 순서로 잠근 뒤 이 함수 전에 한다.
    # 신용카드는 이 함수를 지나지 않아서 같은 자리에서 검사해야 하기 때문 (ADR 0022)
    account.balance += amount
    tx = AccountTransaction(
        account_id=account.account_id, tx_type=tx_type, amount=amount, balance_after=account.balance,
        counterparty_name=merchant_name[:50], category=category,
    )
    db.add(tx)
    await db.flush()
    return tx
