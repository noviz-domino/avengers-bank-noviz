import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from avengers_bank.core.exceptions import ConflictException, LockedException, UnauthorizedException
from avengers_bank.core.config import get_settings
from avengers_bank.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from avengers_bank.domains.users.models import RefreshToken, User
from avengers_bank.domains.users.repository import refresh_token_repository, user_repository
from avengers_bank.domains.users.schemas import TokenResponse, UserCreate, UserLogin

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

    async def login(self, db: AsyncSession, data: UserLogin) -> TokenResponse:
        # 비밀번호 확인(Argon2, 느림)은 행을 잠그지 않고 하고, 실패 횟수는 UPDATE 한 문장으로 올린다.
        # 동시에 여러 번 틀려도 횟수가 덮어써지지 않고, 연결을 오래 붙잡지 않는다.
        async with db.begin():
            user = await user_repository.find_by_login_id(db, data.login_id)
            if user is None:
                raise UnauthorizedException(
                    message="아이디 또는 비밀번호가 올바르지 않습니다.", code="INVALID_CREDENTIALS"
                )
            now = datetime.now(UTC)
            if is_locked(user.login_locked_until, now):
                raise login_locked()
            user_id, hashed_password = user.user_id, user.hashed_password

        ok = await run_in_threadpool(verify_password, data.password, hashed_password)

        async with db.begin():
            if ok:
                await user_repository.reset_login_failures(db, user_id)
                # 로그인마다 새 family: 기기별로 따로 로그아웃·도난 대응
                refresh = await self._issue_refresh(db, user_id, uuid.uuid4(), data.device_name, now)
                return TokenResponse(access_token=create_access_token(user_id), refresh_token=refresh)
            locked_until = await user_repository.add_login_failure(
                db, user_id, LOGIN_MAX_FAILS, now + LOGIN_LOCK_DURATION
            )

        # 예외는 실패 횟수가 커밋된 뒤에 던진다
        if is_locked(locked_until, now):
            raise login_locked()
        raise UnauthorizedException(
            message="아이디 또는 비밀번호가 올바르지 않습니다.", code="INVALID_CREDENTIALS"
        )

    async def refresh(self, db: AsyncSession, raw_token: str) -> TokenResponse:
        """refresh token을 새 것으로 바꾼다. 이미 바꾼 토큰이 다시 오면 그 기기의 토큰을 모두 폐기한다."""
        token_hash, now = hash_refresh_token(raw_token), datetime.now(UTC)
        async with db.begin():
            old = await refresh_token_repository.revoke_if_active(db, token_hash, now)
            if old is None:
                known = await refresh_token_repository.find_by_hash(db, token_hash)
                reused = known is not None and known.revoked_at is not None
                if reused:  # 도난으로 본다: 공격자와 사용자 중 누가 먼저 썼는지 알 수 없어서 둘 다 끊는다
                    await refresh_token_repository.revoke_family(db, known.family_id, now)
            else:
                user_id = old.user_id
                new_raw = await self._issue_refresh(db, user_id, old.family_id, old.device_name, now, replaces=old)

        if old is None:  # 폐기는 커밋된 뒤에 예외를 던진다
            if reused:
                raise UnauthorizedException(
                    message="이미 사용된 로그인 정보입니다. 보안을 위해 다시 로그인해 주세요.",
                    code="REFRESH_TOKEN_REUSED",
                )
            raise UnauthorizedException(
                message="로그인 정보가 만료되었습니다. 다시 로그인해 주세요.", code="INVALID_REFRESH_TOKEN"
            )
        return TokenResponse(access_token=create_access_token(user_id), refresh_token=new_raw)

    async def logout(self, db: AsyncSession, raw_token: str) -> None:
        """이 기기(같은 family)의 refresh token을 모두 폐기한다. 없는 토큰이어도 성공으로 본다."""
        async with db.begin():
            token = await refresh_token_repository.find_by_hash(db, hash_refresh_token(raw_token))
            if token is not None:
                await refresh_token_repository.revoke_family(db, token.family_id, datetime.now(UTC))

    async def _issue_refresh(
        self, db: AsyncSession, user_id: int, family_id: uuid.UUID, device_name: str | None,
        now: datetime, replaces: RefreshToken | None = None,
    ) -> str:
        raw = new_refresh_token()
        token = await refresh_token_repository.save(db, RefreshToken(
            user_id=user_id, token_hash=hash_refresh_token(raw), family_id=family_id,
            device_name=device_name, expires_at=now + timedelta(days=get_settings().refresh_expire_days),
        ))
        if replaces is not None:
            replaces.replaced_by = token.token_id
        return raw

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
