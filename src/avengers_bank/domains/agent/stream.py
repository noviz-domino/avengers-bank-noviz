"""채팅 스트리밍 (ADR 0018): LangGraph 실행 이벤트를 화면용 SSE 이벤트로 바꾼다.

전체 시간은 그대로지만, 사용자는 처음부터 진행 상태를 보고 답은 만들어지는 대로 본다.
    status  진행 상태 (담당 고르기 → 담당 시작 → 도구 실행)
    token   담당 AI가 쓰는 답의 글자 조각. 복합 요청은 담당별로 차례로 (agent로 구분)
    done    끝: session_id, 최종 답(reply), 일한 담당
    error   중간에 실패 (HTTP 상태는 이미 200이라 이벤트로 알린다)
라우터의 계획(JSON)과 담당의 "어떤 도구를 쓸지" 결정은 사용자에게 보낼 글이 아니라서 token으로 내보내지 않는다.
도구 호출 전의 "확인해 볼게요" 같은 서문은 token으로 나갈 수 있고 done.reply에서는 빠진다.
화면은 token을 미리보기로 표시하고, done을 받으면 표시한 텍스트를 done.reply로 바꿔 끼운다.
인사처럼 라우터가 혼자 답하면 token 없이 done.reply로만 답이 온다.
"""

import json

from langgraph.types import Command

from avengers_bank.domains.agent.graph import TOOLS

AGENT_LABELS = {"account": "계좌 담당이 확인하고 있어요", "card": "카드 담당이 확인하고 있어요",
                "product": "상품·약관 담당이 찾아보고 있어요", "budget": "예산 담당이 확인하고 있어요"}
TOOL_LABELS = {
    "get_my_accounts": "계좌를 조회하고 있어요", "get_account": "계좌를 조회하고 있어요",
    "search_transactions": "거래내역을 찾고 있어요", "request_transfer": "이체 요청을 만들고 있어요",
    "open_account": "계좌를 개설하고 있어요", "request_deposit": "예금 신청을 만들고 있어요",
    "close_account": "계좌를 해지하고 있어요", "get_my_cards": "카드를 조회하고 있어요",
    "issue_card": "카드를 발급하고 있어요", "search_card_transactions": "카드 사용내역을 찾고 있어요",
    "get_card_limit": "카드 한도를 조회하고 있어요", "suspend_card": "카드를 정지하고 있어요",
    "request_unsuspend_card": "정지 해제 요청을 만들고 있어요", "search_products": "상품을 찾고 있어요",
    "get_product_detail": "상품 정보를 보고 있어요", "ask_bank_docs": "약관에서 근거를 찾고 있어요",
    "get_budget": "예산을 확인하고 있어요", "check_budget": "예산에 주는 영향을 보고 있어요",
}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content or [])


class EventTranslator:
    """astream_events(v2) 이벤트 하나를 받아 보낼 SSE 문자열들을 돌려준다"""

    def __init__(self):
        self.agent: str | None = None  # 지금 일하는 담당
        self.streamed: set[str] = set()  # 글자를 이미 흘려보낸 LLM 실행 (끝날 때 또 보내지 않게)
        self.answered: list[str] = []  # 답 글자를 보낸 담당 순서 (담당이 바뀌면 줄을 띄운다)

    def __call__(self, ev: dict) -> list[str]:
        kind, name = ev["event"], ev.get("name")
        node = (ev.get("metadata") or {}).get("langgraph_node")
        if kind == "on_chain_end" and name == "router" and node == "router":
            out = ev["data"].get("output")
            update = out.update if isinstance(out, Command) and isinstance(out.update, dict) else {}
            agents = [*update.get("routed", []), *update.get("plan", [])]
            if not agents:
                return []
            names = [AGENT_LABELS[a].split()[0] for a in agents]
            label = f"{names[0]} 담당에게 보낼게요" if len(names) == 1 else " → ".join(names) + " 순서로 확인할게요"
            return [sse("status", {"stage": "routed", "agents": agents, "label": label})]
        if kind == "on_chain_start" and name in TOOLS and node == name and self.agent != name:
            self.agent = name  # 바깥 노드와 안쪽 Agent 그래프가 같은 이름이라 한 번만
            return [sse("status", {"stage": "agent", "agent": name, "label": AGENT_LABELS[name]})]
        if kind == "on_tool_start":
            return [sse("status", {"stage": "tool", "agent": self.agent, "tool": name,
                                   "label": TOOL_LABELS.get(name, "처리하고 있어요")})]
        if self.agent is None or node == "router":
            return []
        if kind == "on_chat_model_stream":
            chunk = ev["data"]["chunk"]
            piece = text_of(chunk.content)
            if piece and not getattr(chunk, "tool_call_chunks", None):
                self.streamed.add(ev["run_id"])
                return [self.token(piece)]
        if kind == "on_chat_model_end" and ev["run_id"] not in self.streamed:
            out = ev["data"].get("output")  # 글자 단위로 못 주는 모델은 끝날 때 한 번에
            piece = text_of(getattr(out, "content", ""))
            if piece and not getattr(out, "tool_calls", None):
                return [self.token(piece)]
        return []

    def token(self, piece: str) -> str:
        """복합 요청에서 다음 담당의 첫 글자 앞에는 빈 줄 (done의 전체 답과 같은 모양)"""
        if self.answered and self.answered[-1] != self.agent:
            piece = "\n\n" + piece
        if not self.answered or self.answered[-1] != self.agent:
            self.answered.append(self.agent)
        return sse("token", {"agent": self.agent, "text": piece})
