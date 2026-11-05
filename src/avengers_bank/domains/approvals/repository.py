import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.domains.approvals.models import PendingAction


class ApprovalRepository:
    async def save(self, db: AsyncSession, action: PendingAction) -> PendingAction:
        db.add(action)
        await db.flush()
        return action

    async def find(self, db: AsyncSession, action_id: uuid.UUID) -> PendingAction | None:
        return await db.get(PendingAction, action_id)

    async def find_by_key(self, db: AsyncSession, user_id: int, key: str) -> PendingAction | None:
        return await db.scalar(select(PendingAction).where(
            PendingAction.user_id == user_id, PendingAction.idempotency_key == key
        ))

    async def find_pending(self, db: AsyncSession, user_id: int, now: datetime) -> list[PendingAction]:
        return list(await db.scalars(
            select(PendingAction)
            .where(PendingAction.user_id == user_id, PendingAction.status == "PENDING", PendingAction.expires_at > now)
            .order_by(PendingAction.created_at.desc())
        ))

    async def claim(
        self, db: AsyncSession, action_id: uuid.UUID, user_id: int, now: datetime, to_status: str
    ) -> PendingAction | None:
        """PENDING이고 만료 전인 내 작업만 to_status로 바꾼다. 한 문장이라 두 번 승인해도 한 번만 통과 (규칙 2)"""
        values = {"status": to_status}
        if to_status == "APPROVED":
            values |= {"approved_at": now, "approval_method": "PIN"}
        return await db.scalar(
            update(PendingAction)
            .where(
                PendingAction.action_id == action_id, PendingAction.user_id == user_id,
                PendingAction.status == "PENDING", PendingAction.expires_at > now,
            )
            .values(values)
            .returning(PendingAction)
        )


approval_repository = ApprovalRepository()
