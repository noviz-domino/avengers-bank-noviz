from datetime import datetime

from pydantic import BaseModel, ConfigDict

# TODO: 개설 요청 스키마 — AccountCreate (account_type, product_id, 예·적금은 기간·금액)
# TODO: 상세 응답 스키마 — 계좌 상세(예·적금은 account_terms 포함), 거래내역 Response
# TODO: 수정 요청 스키마 — 별칭, 이체 한도(입출금만)


class AccountSummaryResponse(BaseModel):
    """GET /accounts — 계좌 목록 한 줄"""

    account_id: int
    account_type: str  # CHECKING / DEPOSIT / SAVINGS
    account_num: str
    balance: int
    nickname: str | None
    status: str
    opened_at: datetime

    model_config = ConfigDict(from_attributes=True)
