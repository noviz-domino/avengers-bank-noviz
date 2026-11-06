from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(min_length=1)
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_expire_minutes: int = Field(default=15, gt=0)  # access token은 짧게 (ADR 0005)
    refresh_expire_days: int = Field(default=14, gt=0)  # 쓸 때마다 새로 발급되고 기간도 다시 시작
    db_echo: bool = False
    # 대금 출금 같은 시스템 작업 API의 키 (ADR 0011). 없으면 그 API는 꺼진다
    system_api_key: SecretStr | None = Field(default=None, min_length=32)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        env_ignore_empty=True,  # .env.example처럼 `KEY=`로 비워 두면 "없음" (PR #17 리뷰)
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
