"""빠른 길 (ADR 0034): 라우터가 단순 조회라고 표시한 요청은 담당 Agent의 LLM 호출 없이 도구를 바로 부르고 코드가 답을 쓴다.

담당 Agent는 "어떤 도구를 쓸지" 한 번, "결과로 답 쓰기" 한 번, 최소 LLM 두 번이 든다(한 번에 3~4초). 잔액·카드 목록·
남은 예산처럼 도구 하나로 끝나는 조회는 답 모양이 정해져 있어서 코드가 쓰는 편이 빠르고 숫자도 틀리지 않는다.
약관 질문은 RAG(ask_bank_docs)가 근거와 함께 답을 이미 쓰므로 그 답을 그대로 낸다.
도구가 실패하면 None을 돌려주고 원래 담당 Agent가 처리한다.
"""

import json
from datetime import UTC, date, datetime
from typing import Literal

from langchain_core.tools import BaseTool

from avengers_bank.core.clock import KST, today_kst

QuickKind = Literal["balance", "search", "cards", "budget", "docs"]
# 담당별로 쓸 수 있는 빠른 길과 도구 (한 담당에 여러 길)
LANES: dict[str, dict[QuickKind, str]] = {
    "account": {"balance": "get_my_accounts", "search": "search_transactions"},
    "card": {"cards": "get_my_cards"}, "budget": {"budget": "get_budget"}, "product": {"docs": "ask_bank_docs"},
}
CARD_STATUS = {"ACTIVE": "사용 중", "SUSPENDED": "일시정지", "LOST": "분실 신고"}


def won(amount: int) -> str:
    return f"{amount:,}원"


def data_of(raw) -> dict:
    """MCP 도구 결과(JSON 글자 또는 내용 조각 목록)에서 REST 응답의 data"""
    if isinstance(raw, list):
        raw = "".join(part.get("text", "") if isinstance(part, dict) else getattr(part, "text", str(part)) for part in raw)
    return json.loads(raw)["data"]


def balance_text(data: dict) -> str:
    rows = [f"- {a['nickname'] or a['product_name']}({a['account_num']}): {won(a['balance'])}" for a in data["accounts"]]
    return "\n".join([f"총자산은 {won(data['total_balance'])}이에요.", *rows]) if rows else "아직 계좌가 없어요."


def cards_text(cards: list[dict]) -> str:
    if not cards:
        return "아직 카드가 없어요."
    rows = [f"- {c['nickname'] or c['product_name']}({c['masked_card_num']}): {CARD_STATUS.get(c['status'], c['status'])}" for c in cards]
    return "\n".join([f"카드는 {len(cards)}장이에요.", *rows])


def budget_text(b: dict) -> str:
    if not b.get("enrolled"):
        return "예산을 아직 신청하지 않았어요. 앱의 예산 화면에서 신청할 수 있어요."

    def left(amount: int) -> str:
        return won(amount) if amount >= 0 else f"{won(-amount)} 모자라요"
    days = b["cycle"]["days_left"]
    daily = (f"- 남은 {days}일 동안 하루에 {won(b['daily_allowance'])}까지 쓸 수 있어요." if b["free_to_spend"] > 0
             else f"- 목표 저축을 지키려면 남은 {days}일 동안 더 쓸 수 있는 돈이 없어요.")
    return "\n".join([
        "이번 주기에 더 쓸 수 있는 돈이에요.",
        f"- 생활비만 보면 {left(b['free_before_saving'])}",
        f"- 목표 저축까지 지키면 {left(b['free_to_spend'])}",
        daily,
    ])


def docs_text(r: dict) -> str:
    titles = list(dict.fromkeys(c["title"] for c in r.get("citations", [])))
    return r["answer"] + (f"\n\n근거: {', '.join(titles)}" if titles else "")


SHOWN = 5  # 검색 답에 보여 줄 최근 거래 수


def day_label(d: date) -> str:
    return f"{d.month}월 {d.day}일"


def kst_day(iso: str) -> date:
    """거래 시각(UTC 저장)을 한국 날짜로. 밤 늦은 거래가 전날로 보이지 않게"""
    at = datetime.fromisoformat(iso)
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(KST).date()


def search_args(search: dict, today: date) -> dict | None:
    """라우터가 채운 검색 조건을 검사한다. 기간이 없거나 날짜가 이상하면 None (담당 Agent가 처리, ADR 0035)"""
    try:
        start, end = date.fromisoformat(search["from_date"]), date.fromisoformat(search["to_date"])
    except (KeyError, TypeError, ValueError):
        return None
    if start > end or end > today:
        return None
    return {"from_date": start, "to_date": end, "categories": list(dict.fromkeys(search.get("categories") or []))[:3],
            "keyword": search.get("keyword") or None, "direction": search.get("direction")}


async def spending(tool: BaseTool, search: dict, today: date) -> str | None:
    """지출·수입 검색: 업종마다 한 번씩 부르고 서버가 계산한 합계(total_in·total_out)만 더한다. 모델은 계산하지 않는다"""
    args = search_args(search, today)
    if args is None:
        return None
    base = {"from_date": args["from_date"].isoformat(), "to_date": args["to_date"].isoformat(),
            "keyword": args["keyword"], "direction": args["direction"], "limit": SHOWN}
    results = [data_of(await tool.ainvoke({k: v for k, v in {**base, "category": c}.items() if v is not None}))
               for c in args["categories"] or [None]]
    total_in, total_out = sum(r["total_in"] for r in results), sum(r["total_out"] for r in results)
    what = "·".join(args["categories"]) or (f"'{args['keyword']}'" if args["keyword"] else "")
    head = f"{day_label(args['from_date'])}~{day_label(args['to_date'])}" + (f" {what}" if what else "")
    lines = []
    if args["direction"] != "IN":
        lines.append(f"{head} 쓴 돈은 {won(total_out)}이에요.")
    if args["direction"] != "OUT":
        lines.append(f"{head} 들어온 돈은 {won(total_in)}이에요." if args["direction"] == "IN" else f"들어온 돈은 {won(total_in)}이에요.")
    txs = sorted((t for r in results for t in r["transactions"]), key=lambda t: t["created_at"], reverse=True)
    for t in txs[:SHOWN]:
        name = t["counterparty_name"] or t["memo"] or t["category"] or "거래"
        sign = "+" if t["amount"] > 0 else "−"
        lines.append(f"- {day_label(kst_day(t['created_at']))} {name} {sign}{won(abs(t['amount']))}")
    if len(txs) > SHOWN or any(r["next_before"] for r in results):
        lines.append(f"(최근 {SHOWN}건만 보여요. 합계는 기간 전체예요.)")
    elif not txs:
        lines.append("이 기간에 해당하는 거래가 없어요.")
    return "\n".join(lines)


async def run_lane(kind: QuickKind, tool: BaseTool, question: str | None, search: dict | None = None) -> str | None:
    """빠른 길 하나를 실행해 답 글을 돌려준다. 도구가 실패하거나 조건이 이상하면 None (담당 Agent가 대신 처리)"""
    try:
        if kind == "search":
            return await spending(tool, search or {}, today_kst())
        raw = await tool.ainvoke({"question": question} if kind == "docs" else {})
        data = data_of(raw)
    except Exception:  # ToolError(서버 오류 코드), 형식 문제: 원래 길로
        return None
    return {"balance": balance_text, "cards": cards_text, "budget": budget_text, "docs": docs_text}[kind](data)
