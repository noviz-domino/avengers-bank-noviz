from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PastDate


class UserCreate(BaseModel):
    login_id: str = Field(min_length=4, max_length=50)
    password: str = Field(min_length=8, max_length=128, repr=False)
    # 승인 화면 문장에 받는 사람 이름으로 들어간다. 숫자·기호로 금액처럼 보이게 꾸미지 못하게 글자만 받는다
    name: str = Field(min_length=1, max_length=30, pattern=r"^[가-힣a-zA-Z]+( [가-힣a-zA-Z]+)*$")
    nick_name: str | None = Field(default=None, max_length=50)
    phone: str = Field(min_length=9, max_length=20)
    birth_date: PastDate  # 상품 가입 나이 조건 검사 (ADR 0003)
    marketing_agreed: bool = False  # 우대금리 조건


class UserLogin(BaseModel):
    login_id: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128, repr=False)
    device_name: str | None = Field(default=None, max_length=100)  # 기기 이름. 로그인 기기 목록 기능을 만들면 보여줌


class PinSet(BaseModel):
    """거래 PIN 설정·변경. 비밀번호를 다시 받는다 (토큰만으로는 PIN을 바꿀 수 없게)"""

    password: str = Field(min_length=1, max_length=128, repr=False)
    pin: str = Field(pattern=r"^\d{6}$", repr=False)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=200, repr=False)


class UserResponse(BaseModel):
    user_id: int
    login_id: str
    name: str
    nick_name: str | None
    phone: str
    birth_date: date | None
    marketing_agreed: bool
    has_pin: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
