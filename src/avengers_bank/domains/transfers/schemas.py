from pydantic import BaseModel, Field


class TransferCreate(BaseModel):
    """POST /transfers — 이체 요청. 바로 보내지 않고 승인 대기를 만든다 (ADR 0004)"""

    from_account_id: int
    to_account_num: str = Field(min_length=1, max_length=20)
    amount: int = Field(gt=0, le=10_000_000_000)
    memo: str | None = Field(default=None, min_length=1, max_length=100)
    # 요청한 쪽(웹·Agent·MCP)이 만든다. 같은 키로 다시 오면 새로 만들지 않고 처음 것을 돌려준다
    idempotency_key: str = Field(min_length=8, max_length=100)
