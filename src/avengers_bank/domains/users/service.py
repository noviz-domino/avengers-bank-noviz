from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from avengers_bank.core.exceptions import ConflictException, LockedException, UnauthorizedException
from avengers_bank.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from avengers_bank.domains.users.models import User
from avengers_bank.domains.users.repository import user_repository
from avengers_bank.domains.users.schemas import UserCreate, UserLogin

# 로그인 잠금 (ADR 0005). 잠긴 동안은 비밀번호가 맞아도 거절한다
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_DURATION = timedelta(minutes=15)


def is_locked(locked_until: datetime | None, now: datetime) -> bool:
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:  # SQLite는 시간대를 버리고 돌려준다. 저장한 값은 UTC
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > now


def login_locked() -> LockedException:
    return LockedException(
        message=f"로그인을 {LOGIN_MAX_FAILS}회 실패해서 잠겼습니다. 잠시 후 다시 시도해 주세요.",
        code="LOGIN_LOCKED",
    )


class UserService:
    async def signup(self, db: AsyncSession, data: UserCreate) -> User:
        hashed_password = await run_in_threadpool(hash_password, data.password)

        async with db.begin():
            if await user_repository.find_by_login_id(db, data.login_id) is not None:
                raise ConflictException(
                    code="LOGIN_ID_ALREADY_EXISTS",
                    message="이미 사용 중인 아이디입니다.",
                )
            user = User(
                login_id=data.login_id,
                hashed_password=hashed_password,
                name=data.name,
                nick_name=data.nick_name,
                phone=data.phone,
                birth_date=data.birth_date,
                marketing_agreed=data.marketing_agreed,
            )
            await user_repository.save(db, user)
            await db.refresh(user)

        return user

    async def login(self, db: AsyncSession, data: UserLogin) -> str:
        # 실패 횟수는 실패해도 저장해야 해서, 예외는 트랜잭션이 커밋된 뒤에 던진다
        async with db.begin():
            user = await user_repository.find_by_login_id(db, data.login_id, for_update=True)
            if user is None:
                raise UnauthorizedException(
                    message="아이디 또는 비밀번호가 올바르지 않습니다.", code="INVALID_CREDENTIALS"
                )
            now = datetime.now(UTC)
            if is_locked(user.login_locked_until, now):
                raise login_locked()

            ok = await run_in_threadpool(verify_password, data.password, user.hashed_password)
            if ok:
                user.login_fail_count = 0
                user.login_locked_until = None
            else:
                user.login_fail_count += 1
                if user.login_fail_count >= LOGIN_MAX_FAILS:
                    user.login_fail_count = 0
                    user.login_locked_until = now + LOGIN_LOCK_DURATION
            # 잠금 시간이 지난 옛 값이 남아 있을 수 있어서 시각으로 판단
            user_id, locked_now = user.user_id, is_locked(user.login_locked_until, now)

        if not ok:
            if locked_now:
                raise login_locked()
            raise UnauthorizedException(
                message="아이디 또는 비밀번호가 올바르지 않습니다.", code="INVALID_CREDENTIALS"
            )
        return create_access_token(user_id)

    async def get_current_user(self, db: AsyncSession, token: str) -> User:
        user_id = decode_access_token(token)
        user = await user_repository.find_by_id(db, user_id)
        if user is None:
            raise UnauthorizedException(
                message="유효하지 않거나 만료된 토큰입니다.", code="INVALID_TOKEN"
            )
        return user

    # TODO: PATCH /users/me — 이름, 닉네임, 전화번호 수정


user_service = UserService()
