"""이체 요청: 검사하고 승인 대기만 만든다. 실제 이동은 승인 후 실행 함수(accounts/money.py)가 한다."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.exceptions import BadRequestException, ConflictException
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.money import TransferRejected, check_transfer, check_transfer_amount, today_transfer_out
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.budget.calc import impact_text
from avengers_bank.domains.budget.service import preview
from avengers_bank.domains.transfers import clearing
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
            sent_today = await today_transfer_out(db, data.from_account_id)
            try:
                if data.to_bank is None:
                    dst = await db.scalar(select(Account).where(Account.account_num == data.to_account_num))
                    internal = check_transfer(src, dst, data.amount, sent_today)
                    receiver = await db.get(User, dst.user_id)
                    to_whom = label(dst) if internal else f"{receiver.name}님({dst.account_num})"
                    payload = {"to_account_id": dst.account_id}
                else:
                    clearing.check_source(src, user_id)
                    if data.amount > 100_000_000:
                        raise TransferRejected("LIMIT_EXCEEDED", "타행 이체는 1회 1억 원까지 가능합니다.")
                    check_transfer_amount(src, data.amount, sent_today)
                    holder_name = await clearing.recipient(data.to_bank, data.to_account_num)
                    sender = await db.get(User, user_id)
                    to_whom = f"{holder_name}님(은행 {data.to_bank}, {data.to_account_num})"
                    payload = {
                        "to_bank": data.to_bank, "holder_name": holder_name,
                        "from_account": src.account_num, "sender_name": sender.name,
                    }
            except TransferRejected as e:
                raise BadRequestException(message=e.message, code=e.code) from None

            payload = {
                "from_account_id": src.account_id, "to_account_num": data.to_account_num,
                "amount": data.amount, "memo": data.memo, **payload,
            }
            # 승인 화면 문장은 서버가 payload로 만든다 (규칙 5)
            summary = f"{label(src)}에서 {to_whom}에게 {data.amount:,}원 보내기"
            # 예산 미리 계산 (ADR 0007·0024): 넘으면 같은 승인 화면에서 사유를 받는다. 실행 때 잠금 안에서 다시 검사.
            # 409로 막지 않는다: 이체는 원래 승인 화면이 확인 단계라 PIN 한 번으로 이체와 예산 확인을 같이 받는다
            # shortcut: 타행 이체는 실행 함수(clearing.stage_transfer)가 예산 재검사를 하지 않아 미리 계산도 붙이지 않는다.
            # 타행 이체에 예산 가드를 넣을 때 stage_transfer의 재검사와 함께 추가한다.
            if data.to_bank is None and not internal and (found := await preview(db, user_id)):
                profile, budget = found
                check = {"free_before": budget.free_to_spend, "amount": data.amount,
                         "over": data.amount > budget.free_to_spend}
                if check["over"]:
                    check["impact"] = impact_text(budget, data.amount, profile.goal_name)
                    summary += "\n" + check["impact"]
                payload["budget_check"] = check
            action = PendingAction(
                user_id=user_id, action_type="TRANSFER" if data.to_bank is None else clearing.ACTION_TYPE,
                requested_by=requested_by,
                idempotency_key=data.idempotency_key, expires_at=datetime.now(UTC) + APPROVAL_TTL,
                payload=payload, summary=summary,
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
        action_type = "TRANSFER" if data.to_bank is None else clearing.ACTION_TYPE
        same = (existing.action_type == action_type and p["from_account_id"] == data.from_account_id
                and p["to_account_num"] == data.to_account_num and p["amount"] == data.amount
                and p.get("memo") == data.memo and p.get("to_bank") == data.to_bank)
        if not same:
            raise ConflictException(
                message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED"
            )
        return existing


transfer_service = TransferService()
