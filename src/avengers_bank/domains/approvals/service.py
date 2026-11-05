"""승인 대기 작업의 승인·거절·실행 (ADR 0004, docs/ERD.md 승인·실행 규칙)"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.exceptions import BadRequestException, ConflictException, NotFoundException
from avengers_bank.domains.accounts.money import TransferRejected, execute_transfer
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.users.service import user_service


async def run_transfer(db: AsyncSession, action: PendingAction) -> None:
    p = action.payload
    await execute_transfer(
        db, owner_user_id=action.user_id, from_account_id=p["from_account_id"], to_account_id=p["to_account_id"],
        amount=p["amount"], action_id=action.action_id, memo=p.get("memo"),
    )


# action_type → 실행 함수. 새 승인 대상(예금 개설, 카드 해제 등)은 여기에 추가한다
EXECUTORS = {"TRANSFER": run_transfer}


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)  # SQLite는 시간대를 버리고 돌려준다


def not_found() -> NotFoundException:
    return NotFoundException(message="승인 요청을 찾을 수 없습니다.", code="ACTION_NOT_FOUND")


class ApprovalService:
    async def get(self, db: AsyncSession, user_id: int, action_id: uuid.UUID) -> PendingAction:
        action = await approval_repository.find(db, action_id)
        if action is None or action.user_id != user_id:
            raise not_found()
        return action

    async def list_pending(self, db: AsyncSession, user_id: int) -> list[PendingAction]:
        return await approval_repository.find_pending(db, user_id, datetime.now(UTC))

    async def approve(
        self, db: AsyncSession, user_id: int, action_id: uuid.UUID, pin: str, ip: str | None = None
    ) -> PendingAction:
        # 남의 작업(404)이나 이미 처리·만료된 작업(409)이면 PIN을 묻기 전에 알린다: PIN 실패로 세지 않게
        action = await self.get(db, user_id, action_id)
        if action.status != "PENDING" or as_utc(action.expires_at) <= datetime.now(UTC):
            await self._explain_not_claimable(db, user_id, action_id, datetime.now(UTC))
        await db.rollback()
        await user_service.verify_pin(db, user_id, pin, ip=ip, target=str(action_id))

        failure: TransferRejected | None = None
        async with db.begin():
            now = datetime.now(UTC)
            action = await approval_repository.claim(db, action_id, user_id, now, "APPROVED")
            if action is None:
                await self._explain_not_claimable(db, user_id, action_id, now)
            try:
                await EXECUTORS[action.action_type](db, action)
                action.status, action.executed_at = "EXECUTED", now
            except TransferRejected as e:
                # 실행 직전 재검사에서 막힘 (규칙 3). 돈은 움직이지 않고 실패만 남긴다
                failure = e
                action.status, action.failure_reason = "FAILED", f"{e.code}: {e.message}"
        if failure is not None:  # 실패 상태가 커밋된 뒤에 알린다
            raise BadRequestException(message=failure.message, code=failure.code)
        return action

    async def reject(self, db: AsyncSession, user_id: int, action_id: uuid.UUID) -> PendingAction:
        """거절은 안전한 쪽이라 PIN이 필요 없다"""
        async with db.begin():
            now = datetime.now(UTC)
            action = await approval_repository.claim(db, action_id, user_id, now, "REJECTED")
            if action is None:
                await self._explain_not_claimable(db, user_id, action_id, now)
        return action

    async def _explain_not_claimable(self, db: AsyncSession, user_id: int, action_id: uuid.UUID, now: datetime):
        action = await approval_repository.find(db, action_id)
        if action is None or action.user_id != user_id:
            raise not_found()
        if action.status == "PENDING" and as_utc(action.expires_at) <= now:
            raise ConflictException(message="승인 시간이 지났습니다. 다시 요청해 주세요.", code="ACTION_EXPIRED")
        raise ConflictException(message="이미 처리된 요청입니다.", code="ACTION_NOT_PENDING")


approval_service = ApprovalService()
