"""AvengersBank MCP 서버 (ADR 0004·0006·0014). 도구는 모두 REST API를 사용자 토큰으로 부르는 얇은 어댑터다.

넣지 않는 것: 승인·PIN API(사람만 승인), 카드 결제(가맹점 시뮬레이터, ADR 0010), /system/*(서버 키).
돈이 움직이는 도구는 승인 대기만 만든다. 실제 실행은 사용자가 승인 화면에서 PIN을 넣어야 한다.
"""

import uuid
from datetime import date
from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from avengers_bank.domains.accounts.schemas import Category
from avengers_bank.domains.mcp_server.api import call

INSTRUCTIONS = """어벤져스은행 고객의 계좌·카드·상품 업무를 돕는 도구입니다.
- 이체·예금 개설·카드 정지 해제는 승인 대기만 만듭니다. 사용자에게 "은행 앱 승인 화면에서 PIN을 입력해 주세요"라고 안내하세요.
- PIN이나 비밀번호를 사용자에게 묻지 마세요. 승인은 도구로 할 수 없습니다.
- 금액·계좌·카드가 모호하면 실행하지 말고 되물으세요.
- 상품·약관 규칙 질문은 ask_bank_docs로 근거와 함께 답하세요."""

mcp = FastMCP(
    "avengers-bank", instructions=INSTRUCTIONS,
    stateless_http=True, json_response=True, streamable_http_path="/",
    # 모든 도구가 Bearer 토큰을 요구해서, 쿠키 없는 요청을 막는 DNS rebinding 보호는 끈다 (컨테이너 Host 헤더 허용)
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
REQUEST = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)  # 승인 대기만
CHANGE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)  # PIN 없이 바로 바뀜


def new_key() -> str:
    """요청 번호. 도구 호출마다 새로: 같은 요청이 두 번 와도 승인 대기가 하나 더 생길 뿐 PIN 없이는 돈이 안 움직인다"""
    return f"mcp-{uuid.uuid4()}"


# ── 계좌 ─────────────────────────────────────────────

@mcp.tool(annotations=READ)
async def get_my_accounts(ctx: Context) -> dict:
    """내 계좌 목록(해지한 계좌 제외)과 잔액, 총자산."""
    return await call(ctx, "GET", "/accounts")


@mcp.tool(annotations=READ)
async def get_account(ctx: Context, account_id: int) -> dict:
    """계좌 하나의 상세: 이체 한도, 예·적금 조건(금리·만기)."""
    return await call(ctx, "GET", f"/accounts/{account_id}")


@mcp.tool(annotations=READ)
async def search_transactions(
    ctx: Context,
    account_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    keyword: Annotated[str | None, Field(description="메모·상대방 이름에서 찾을 낱말")] = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    direction: Literal["IN", "OUT"] | None = None,
    category: Category | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict:
    """거래내역 검색(내 모든 계좌 또는 한 계좌). 날짜는 한국 날짜. 조건 전체의 들어온 돈·나간 돈 합계도 준다."""
    return await call(ctx, "GET", "/transactions", params={
        "account_id": account_id, "from_date": from_date and from_date.isoformat(),
        "to_date": to_date and to_date.isoformat(), "keyword": keyword, "min_amount": min_amount,
        "max_amount": max_amount, "direction": direction, "category": category, "limit": limit,
    })


@mcp.tool(annotations=REQUEST)
async def request_transfer(
    ctx: Context,
    from_account_id: int,
    to_account_num: Annotated[str, Field(description="받는 계좌번호, 예: 110-101-000001")],
    amount: Annotated[int, Field(gt=0, description="원 단위 정수")],
    memo: str | None = None,
) -> dict:
    """이체 요청. 돈을 바로 보내지 않고 승인 대기를 만든다. 사용자가 10분 안에 승인 화면에서 PIN으로 승인해야 실행된다."""
    return await call(ctx, "POST", "/transfers", body={
        "from_account_id": from_account_id, "to_account_num": to_account_num, "amount": amount,
        "memo": memo, "idempotency_key": new_key(),
    })


@mcp.tool(annotations=CHANGE)
async def open_account(
    ctx: Context,
    product_id: int,
    nickname: str | None = None,
    term_months: Annotated[int | None, Field(description="적금만: 가입 기간(개월)")] = None,
    monthly_payment: Annotated[int | None, Field(description="적금만: 월 납입액(원)")] = None,
    payment_day: Annotated[int | None, Field(ge=1, le=28, description="적금만: 납입일 1~28")] = None,
) -> dict:
    """입출금 통장·적금 개설(바로 만들어짐). 정기예금은 request_deposit을 쓴다. 상품은 search_products로 찾는다."""
    return await call(ctx, "POST", "/accounts", body={
        "product_id": product_id, "nickname": nickname, "term_months": term_months,
        "monthly_payment": monthly_payment, "payment_day": payment_day,
    })


@mcp.tool(annotations=REQUEST)
async def request_deposit(
    ctx: Context, product_id: int, from_account_id: int,
    amount: Annotated[int, Field(gt=0)], term_months: int, nickname: str | None = None,
) -> dict:
    """정기예금 개설 신청. 맡길 돈을 입출금 계좌에서 옮겨야 해서 승인 대기를 만든다(PIN 승인 후 개설)."""
    return await call(ctx, "POST", "/accounts/deposits", body={
        "product_id": product_id, "from_account_id": from_account_id, "amount": amount,
        "term_months": term_months, "nickname": nickname, "idempotency_key": new_key(),
    })


@mcp.tool(annotations=CHANGE)
async def close_account(ctx: Context, account_id: int) -> dict:
    """입출금 계좌 해지(바로). 잔액 0이고, 그 계좌를 쓰는 카드·안 낸 카드 대금이 없을 때만 된다. 남은 돈은 먼저 이체한다."""
    return await call(ctx, "POST", f"/accounts/{account_id}/close")


# ── 카드 ─────────────────────────────────────────────

@mcp.tool(annotations=READ)
async def get_my_cards(ctx: Context) -> dict:
    """내 카드 목록. 카드번호는 가린 번호만 나온다."""
    return await call(ctx, "GET", "/cards")


@mcp.tool(annotations=CHANGE)
async def issue_card(
    ctx: Context, product_id: int,
    linked_account_id: Annotated[int, Field(description="결제 계좌: 내 입출금 계좌")],
    nickname: str | None = None,
    payment_day: Annotated[int | None, Field(ge=1, le=28, description="신용카드만: 대금 결제일, 없으면 14일")] = None,
) -> dict:
    """카드 발급(바로). 카드 상품은 search_products(kind="CARD")로 찾는다."""
    return await call(ctx, "POST", "/cards", body={
        "product_id": product_id, "linked_account_id": linked_account_id, "nickname": nickname,
        "payment_day": payment_day,
    })


@mcp.tool(annotations=READ)
async def search_card_transactions(ctx: Context, card_id: int) -> dict:
    """카드 사용내역(최근 순). 신용카드는 청구 상태(UNBILLED·BILLED·PAID)도 나온다."""
    return await call(ctx, "GET", f"/cards/{card_id}/transactions")


@mcp.tool(annotations=READ)
async def get_card_limit(ctx: Context, card_id: int) -> dict:
    """카드 한도와 쓴 금액: 오늘 쓴 금액, 신용카드는 안 갚은 금액."""
    return await call(ctx, "GET", f"/cards/{card_id}/limits")


@mcp.tool(annotations=CHANGE)
async def suspend_card(
    ctx: Context, card_id: int,
    lost: Annotated[bool, Field(description="분실 신고면 true. 분실 카드는 다시 쓸 수 없다")] = False,
) -> dict:
    """카드 정지 또는 분실 신고(PIN 없이 바로). 안전해지는 쪽이라 바로 적용된다."""
    return await call(ctx, "POST", f"/cards/{card_id}/suspend", body={"reason": "LOST" if lost else "SUSPENDED"})


@mcp.tool(annotations=REQUEST)
async def request_unsuspend_card(ctx: Context, card_id: int) -> dict:
    """정지한 카드 다시 쓰기 요청. 승인 대기를 만들고, 사용자가 PIN으로 승인하면 풀린다. 분실 카드는 안 된다."""
    return await call(ctx, "POST", f"/cards/{card_id}/unsuspend", body={"idempotency_key": new_key()})


# ── 상품 ─────────────────────────────────────────────

@mcp.tool(annotations=READ)
async def search_products(
    ctx: Context,
    kind: Literal["CHECKING", "DEPOSIT", "SAVINGS", "CARD"] | None = None,
) -> dict:
    """판매 중인 상품 목록(금리·가입 조건 요약). kind를 비우면 계좌 상품과 카드 상품 모두."""
    if kind == "CARD":
        return await call(ctx, "GET", "/products/cards")
    accounts = await call(ctx, "GET", "/products/accounts", params={"type": kind})
    accounts["data"] = [p for p in accounts["data"] if p["type"] != "LOAN"]  # 대출은 기능이 아직 없음
    if kind is not None:
        return accounts
    cards = await call(ctx, "GET", "/products/cards")
    return {"message": None, "data": {"accounts": accounts["data"], "cards": cards["data"]}}


@mcp.tool(annotations=READ)
async def get_product_detail(ctx: Context, product_id: int) -> dict:
    """계좌 상품 상세: 가입 조건, 우대금리 조건."""
    return await call(ctx, "GET", f"/products/accounts/{product_id}")


@mcp.tool(annotations=READ)
async def ask_bank_docs(ctx: Context, question: Annotated[str, Field(min_length=1, max_length=500)]) -> dict:
    """상품·약관 규칙 질문에 근거(인용)와 함께 답한다(RAG). 내 잔액·내 거래 같은 내 데이터 질문에는 쓰지 않는다."""
    return await call(ctx, "POST", "/rag/ask", body={"question": question})
