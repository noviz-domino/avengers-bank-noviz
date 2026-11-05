from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PastDate


class UserCreate(BaseModel):
    login_id: str = Field(min_length=4, max_length=50)
    password: str = Field(min_length=8, max_length=128, repr=False)
    name: str = Field(min_length=1, max_length=50)
    nick_name: str | None = Field(default=None, max_length=50)
    phone: str = Field(min_length=9, max_length=20)
    birth_date: PastDate  # 상품 가입 나이 조건 검사 (ADR 0003)
    marketing_agreed: bool = False  # 우대금리 조건


class UserLogin(BaseModel):
    login_id: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128, repr=False)


class UserResponse(BaseModel):
    user_id: int
    login_id: str
    name: str
    nick_name: str | None
    phone: str
    birth_date: date | None
    marketing_agreed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
