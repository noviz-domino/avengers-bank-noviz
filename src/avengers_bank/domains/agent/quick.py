"""빠른 길 (ADR 0034): 라우터가 단순 조회라고 표시한 요청은 담당 Agent의 LLM 호출 없이 도구를 바로 부르고 코드가 답을 쓴다.

담당 Agent는 "어떤 도구를 쓸지" 한 번, "결과로 답 쓰기" 한 번, 최소 LLM 두 번이 든다(한 번에 3~4초). 잔액·카드 목록·
남은 예산처럼 도구 하나로 끝나는 조회는 답 모양이 정해져 있어서 코드가 쓰는 편이 빠르고 숫자도 틀리지 않는다.
약관 질문은 RAG(ask_bank_docs)가 근거와 함께 답을 이미 쓰므로 그 답을 그대로 낸다.
도구가 실패하면 None을 돌려주고 원래 담당 Agent가 처리한다.

이름 선택지 (ADR 0037): 사람은 "체크카드", "생활비 통장"처럼 이름으로 말하고 도구는 번호(card_id·account_id)를 받는다.
담당 Agent는 번호를 찾으려고 목록 도구를 먼저 불러서 LLM이 한 번 더 들었다. 라우터 앞에서 코드가 내 계좌·카드 목록을
불러 이름표를 라우터의 선택지로 주고, 라우터가 고른 이름표를 코드가 번호로 바꾼다. 없는 계좌·카드는 고를 수 없다.
"""

import asyncio
import json
import re
from datetime import UTC, date, datetime
from typing import Literal

from langchain_core.tools import BaseTool

from avengers_bank.core.clock import KST, today_kst

QuickKind = Literal["balance", "search", "account_detail", "cards", "card_limit", "card_txs", "budget", "docs"]
# 담당별로 쓸 수 있는 빠른 길과 도구 (한 담당에 여러 길)
LANES: dict[str, dict[QuickKind, str]] = {
    "account": {"balance": "get_my_accounts", "search": "search_transactions", "account_detail": "get_account"},
    "card": {"cards": "get_my_cards", "card_limit": "get_card_limit", "card_txs": "search_card_transactions"},
    "budget": {"budget": "get_budget"}, "product": {"docs": "ask_bank_docs"},
}
CARD_STATUS = {"ACTIVE": "사용 중", "SUSPENDED": "일시정지", "LOST": "분실 신고"}
# "30만 원", "300,000원", "5천 원", "삼만원". 금액이 있는 예산 질문은 요약이 아니라 check_budget이 필요하다
AMOUNT = re.compile(r"\d[\d,]*\s*(?:원|만|천)|[일이삼사오육칠팔구십백천만]+\s*원")


def lane_allowed(kind: str, said: str) -> bool:
    """라우터의 빠른 길 표시를 코드가 한 번 더 거른다 (ADR 0037). 가벼운 라우터는 temperature를 무시해서 같은 질문도
    가끔 다르게 표시한다(측정: "30만 원짜리 사도 돼?"를 8번 중 4번 남은 예산 빠른 길로). 틀린 표시가 틀린 답이 되는 길만 막는다"""
    return not (kind == "budget" and AMOUNT.search(said))


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


# ── 이름 선택지 (ADR 0037) ─────────────────────────────

def account_label(a: dict) -> str:
    return f"{a['nickname'] or a['product_name']} ({a['account_num']})"


def last4(c: dict) -> str:
    return f"•••• {c['masked_card_num'][-4:]}"


def card_label(c: dict) -> str:
    return f"{c['nickname'] or c['product_name']} {last4(c)} ({CARD_STATUS.get(c['status'], c['status'])})"


async def load_targets(by_name: dict[str, BaseTool]) -> dict:
    """라우터 앞에서 내 계좌·카드 목록을 코드가 부른다(LLM 없음, REST 수십 ms). 실패하면 빈 목록이고 라우터는 선택지 없이 돈다"""
    async def one(tool: str, pick) -> list[dict]:
        try:
            return pick(data_of(await by_name[tool].ainvoke({})))
        except Exception:
            return []
    accounts, cards = await asyncio.gather(one("get_my_accounts", lambda d: d["accounts"]), one("get_my_cards", lambda d: d))
    return {"accounts": accounts, "cards": cards}


def resolve(targets: dict, account: str | None, card: str | None) -> dict:
    """라우터가 고른 이름표를 실제 계좌·카드로. 이름표가 겹치거나 없으면 고르지 않은 것으로 본다"""
    def pick(items: list[dict], label, chosen: str | None) -> dict | None:
        found = [i for i in items if label(i) == chosen]
        return found[0] if chosen and len(found) == 1 else None
    return {"account": pick(targets["accounts"], account_label, account), "card": pick(targets["cards"], card_label, card),
            "cards": targets["cards"]}


async def card_limits(tool: BaseTool, target: dict) -> str | None:
    """카드 한도: 고른 카드 하나, 안 골랐으면 사용 중인 카드 전부. 남은 금액은 서버 숫자를 코드가 뺀다"""
    cards = [target["card"]] if target.get("card") else [c for c in target.get("cards", []) if c["status"] == "ACTIVE"]
    if not cards:
        return None
    lines = []
    for c in cards:
        lim = data_of(await tool.ainvoke({"card_id": c["card_id"]}))
        line = (f"- {c['nickname'] or c['product_name']}({last4(c)}): 하루 한도 {won(lim['daily_limit'])} 중 오늘 "
                f"{won(lim['daily_used'])}을 써서 {won(lim['daily_limit'] - lim['daily_used'])} 남았어요.")
        if lim.get("credit_limit") is not None:
            line += f" 신용 한도는 {won(lim['credit_limit'])} 중 {won(lim['credit_limit'] - (lim['credit_used'] or 0))} 남았어요."
        if c["status"] != "ACTIVE":
            line += f" 지금 {CARD_STATUS.get(c['status'], c['status'])} 상태라 결제할 수 없어요."
        lines.append(line)
    return "\n".join(lines)


async def card_txs(tool: BaseTool, target: dict) -> str | None:
    """카드 최근 사용내역: 고른 카드 하나, 안 골랐으면 내 카드 전부를 합쳐 최근 순"""
    cards = [target["card"]] if target.get("card") else target.get("cards", [])
    if not cards:
        return None
    rows = [(c, t) for c in cards for t in data_of(await tool.ainvoke({"card_id": c["card_id"]}))]
    rows.sort(key=lambda r: (r[1]["approved_at"], r[1]["card_tx_id"]), reverse=True)  # 같은 시각이면 나중 거래 먼저
    head = f"{target['card']['nickname'] or target['card']['product_name']}({last4(target['card'])})" if target.get("card") else "카드"
    if not rows:
        return f"{head} 최근 사용내역이 없어요."
    lines = [f"{head} 최근 사용내역이에요."]
    for c, t in rows[:SHOWN]:
        canceled = " (취소)" if t["status"] == "CANCELED" else ""
        where = "" if target.get("card") else f" · {last4(c)}"
        lines.append(f"- {day_label(kst_day(t['approved_at']))} {t['merchant_name']} {won(t['amount'])}{canceled}{where}")
    if len(rows) > SHOWN:
        lines.append(f"(최근 {SHOWN}건만 보여요. 기간이나 가맹점을 말씀하시면 더 찾아 드려요.)")
    return "\n".join(lines)


async def account_detail(tool: BaseTool, target: dict) -> str | None:
    """계좌 상세: 라우터가 계좌를 분명히 골랐을 때만 (안 골랐으면 담당 Agent가 되묻는다)"""
    if not target.get("account"):
        return None
    a = data_of(await tool.ainvoke({"account_id": target["account"]["account_id"]}))

    def limit(v) -> str:
        return "제한 없음" if v is None else won(v)
    lines = [f"{a['nickname'] or a['product_name']}({a['account_num']}) · {a['product_name']}", f"- 잔액 {won(a['balance'])}"]
    if a["account_type"] == "CHECKING":
        lines.append(f"- 이체 한도: 1회 {limit(a['per_transfer_limit'])}, 하루 {limit(a['daily_transfer_limit'])}")
    if t := a.get("terms"):
        lines.append(f"- 적용 금리 연 {t['applied_rate']}%, 만기일 {t['maturity_date']}")
        if t.get("monthly_payment"):
            lines.append(f"- 매월 {t['payment_day']}일에 {won(t['monthly_payment'])} 납입")
    return "\n".join(lines)


async def run_lane(kind: QuickKind, tool: BaseTool, question: str | None, search: dict | None = None,
                   target: dict | None = None) -> str | None:
    """빠른 길 하나를 실행해 답 글을 돌려준다. 도구가 실패하거나 조건이 이상하면 None (담당 Agent가 대신 처리)"""
    try:
        if kind == "search":
            return await spending(tool, search or {}, today_kst())
        if kind in ("card_limit", "card_txs", "account_detail"):
            return await {"card_limit": card_limits, "card_txs": card_txs, "account_detail": account_detail}[kind](tool, target or {})
        raw = await tool.ainvoke({"question": question} if kind == "docs" else {})
        data = data_of(raw)
    except Exception:  # ToolError(서버 오류 코드), 형식 문제: 원래 길로
        return None
    return {"balance": balance_text, "cards": cards_text, "budget": budget_text, "docs": docs_text}[kind](data)
