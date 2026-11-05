"""이체 요청: 검사하고 승인 대기만 만든다. 실제 이동은 승인 후 실행 함수(accounts/money.py)가 한다."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.exceptions import BadRequestException, ConflictException
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.money import TransferRejected, check_transfer, today_transfer_out
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.transfers.schemas import TransferCreate
from avengers_bank.domains.users.models import User

APPROVAL_TTL = timedelta(minutes=10)


def label(account: Account) -> str:
    return f"{account.nickname or '내 계좌'}({account.account_num})"


class TransferService:
    async def request_transfer(
        self, db: AsyncSession, user_id: int, data: TransferCreate, requested_by: str = "WEB"
    ) -> tuple[PendingAction, bool]:
        """(승인 대기, 새로 만들었는지). 같은 멱등키로 다시 오면 처음 것을 돌려준다 (ERD 규칙 6)"""
        async with db.begin():
            existing = await approval_repository.find_by_key(db, user_id, data.idempotency_key)
            if existing is not None:
                return self._same_request(existing, data), False

            src = await db.get(Account, data.from_account_id)
            if src is not None and src.user_id != user_id:
                src = None  # 남의 계좌는 없는 것과 같다 (ADR 0008)
            dst = await db.scalar(select(Account).where(Account.account_num == data.to_account_num))
            try:
                internal = check_transfer(src, dst, data.amount, await today_transfer_out(db, data.from_account_id))
            except TransferRejected as e:
                raise BadRequestException(message=e.message, code=e.code) from None

            receiver = await db.get(User, dst.user_id)
            to_whom = label(dst) if internal else f"{receiver.name}님({dst.account_num})"
            action = PendingAction(
                user_id=user_id, action_type="TRANSFER", requested_by=requested_by,
                idempotency_key=data.idempotency_key, expires_at=datetime.now(UTC) + APPROVAL_TTL,
                payload={
                    "from_account_id": src.account_id, "to_account_id": dst.account_id,
                    "to_account_num": dst.account_num, "amount": data.amount, "memo": data.memo,
                },
                # 승인 화면 문장은 서버가 payload로 만든다 (규칙 5)
                summary=f"{label(src)}에서 {to_whom}에게 {data.amount:,}원 보내기",
            )
            try:
                await approval_repository.save(db, action)
            except IntegrityError as e:
                if "idempotency_key" not in str(e.orig):  # 같은 키가 동시에 온 경우만 409, 다른 위반은 버그
                    raise
                raise ConflictException(message="같은 요청을 처리하고 있습니다.", code="DUPLICATE_REQUEST") from None
            return action, True

    def _same_request(self, existing: PendingAction, data: TransferCreate) -> PendingAction:
        p = existing.payload
        same = (existing.action_type == "TRANSFER" and p["from_account_id"] == data.from_account_id
                and p["to_account_num"] == data.to_account_num and p["amount"] == data.amount
                and p.get("memo") == data.memo)
        if not same:
            raise ConflictException(
                message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED"
            )
        return existing


transfer_service = TransferService()
