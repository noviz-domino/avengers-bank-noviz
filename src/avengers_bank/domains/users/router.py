from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.dependencies import get_current_user
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.users.schemas import (
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from avengers_bank.domains.users.service import user_service

router = APIRouter(prefix="/users", tags=["users"], responses=error_responses(422))


@router.post(
    "/signup",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(409),
)
async def signup(data: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    user = await user_service.signup(db, data)
    return SuccessResponse[UserResponse](data=user, message="회원가입이 완료되었습니다.")


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
    responses=error_responses(401, 423),
)
async def login(
    data: UserLogin, db: Annotated[AsyncSession, Depends(get_db)], response: Response
):
    tokens = await user_service.login(db, data)
    no_store(response)
    return SuccessResponse[TokenResponse](data=tokens)


@router.post(
    "/token/refresh",
    response_model=SuccessResponse[TokenResponse],
    responses=error_responses(401),
)
async def refresh_token(
    data: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)], response: Response
):
    tokens = await user_service.refresh(db, data.refresh_token)
    no_store(response)
    return SuccessResponse[TokenResponse](data=tokens)


@router.post("/logout", response_model=SuccessResponse[None])
async def logout(data: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    await user_service.logout(db, data.refresh_token)
    return SuccessResponse[None](data=None, message="로그아웃되었습니다.")


def no_store(response: Response) -> None:
    # 토큰이 담긴 응답은 브라우저·프록시가 저장하지 않게
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.get(
    "/me", response_model=SuccessResponse[UserResponse], responses=error_responses(401)
)
async def get_me(current_user: Annotated[UserResponse, Depends(get_current_user)]):
    return SuccessResponse[UserResponse](data=current_user)


# TODO: PATCH /users/me — 내 정보 수정
