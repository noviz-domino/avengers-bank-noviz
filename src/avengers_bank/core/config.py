import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(min_length=1)
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_expire_minutes: int = Field(default=15, gt=0)  # access token은 짧게 (ADR 0005)
    refresh_expire_days: int = Field(default=14, gt=0)  # 쓸 때마다 새로 발급되고 기간도 다시 시작
    db_echo: bool = False
    # 대금 출금 같은 시스템 작업 API의 키 (ADR 0011). 없으면 그 API는 꺼진다
    system_api_key: SecretStr | None = Field(default=None, min_length=32)
    clearing_hub_url: str = "https://clearing-hub.ai-agent-develop.cloud"
    clearing_bank_code: str | None = Field(default=None, pattern=r"^[0-9]{3}$")
    clearing_api_key: SecretStr | None = None
    clearing_private_key: SecretStr | None = None
    clearing_hub_public_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9+/]{43}=$")
    # RAG·Agent (ADR 0013). 키가 없으면 RAG API는 503. 무료 티어 키만, GitHub Secrets에 넣지 않는다
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    # Gemini 3의 생각 수준. 낮을수록 빠르다. low가 p50 15→8초 (ADR 0016 측정). minimal은 3.8 Flash가 지원하지 않음
    gemini_thinking: Literal["low", "medium", "high"] = "low"
    # 서버 전체 AI 호출 하루 한도(한국 날짜 기준, 채팅 1번 = 3). 공개 서버에서 계정을 여러 개 만들어도 비용이 묶이게 (ADR 0026)
    ai_daily_limit: int = Field(default=100, gt=0)
    kakao_local_api_key: SecretStr | None = None
    # Agent 실행 추적 (ADR 0016). 키가 없으면 꺼진다
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        env_ignore_empty=True,  # .env.example처럼 `KEY=`로 비워 두면 "없음" (PR #17 리뷰)
        hide_input_in_errors=True,
    )

    @field_validator("clearing_private_key")
    @classmethod
    def clearing_key_format(cls, key: SecretStr | None) -> SecretStr | None:
        if key and not re.fullmatch(r"[A-Za-z0-9+/]{43}=", key.get_secret_value()):
            raise ValueError("ClearingHub 개인키는 raw Ed25519 32바이트의 표준 base64여야 합니다.")
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
