from pydantic import BaseModel, Field, model_validator


class TransferCreate(BaseModel):
    """POST /transfers — 이체 요청. 바로 보내지 않고 승인 대기를 만든다 (ADR 0004)"""

    from_account_id: int
    to_account_num: str = Field(min_length=1, max_length=50)
    to_bank: str | None = Field(default=None, pattern=r"^[0-9]{3}$")
    amount: int = Field(gt=0, le=10_000_000_000)
    memo: str | None = Field(default=None, min_length=1, max_length=100)
    # 요청한 쪽(웹·Agent·MCP)이 만든다. 같은 키로 다시 오면 새로 만들지 않고 처음 것을 돌려준다
    idempotency_key: str = Field(min_length=8, max_length=100)

    @model_validator(mode="after")
    def local_account_length(self):
        if self.to_bank is None and len(self.to_account_num) > 20:
            raise ValueError("우리 은행 계좌번호는 20자 이하여야 합니다.")
        return self
