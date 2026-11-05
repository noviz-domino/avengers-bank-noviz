from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.domains.audit.models import AuditLog


class AuditRepository:
    async def record(
        self, db: AsyncSession, *, user_id: int | None, actor: str, action: str,
        target: str | None = None, detail: dict | None = None, ip: str | None = None,
    ) -> None:
        """호출한 쪽의 트랜잭션에 같이 들어간다. 실패 횟수와 기록이 함께 커밋된다."""
        db.add(AuditLog(user_id=user_id, actor=actor, action=action, target=target, detail=detail, ip=ip))


audit_repository = AuditRepository()
