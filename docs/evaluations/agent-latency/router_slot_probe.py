"""라우터 칸 채우기 시험 (ADR 0036): 까다로운 질문 9개에서 담당·빠른 길·검색 기간·업종을 모델별로 비교한다.

    docker compose cp docs/evaluations/agent-latency/router_slot_probe.py app:/tmp/
    docker compose exec app python /tmp/router_slot_probe.py gemini-3.5-flash-lite minimal
(Windows Git Bash는 앞에 MSYS_NO_PATHCONV=1)
"""
import asyncio, json, sys, time
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from avengers_bank.core.clock import today_kst
from avengers_bank.core.config import get_settings
from avengers_bank.domains.agent.graph import ROUTER, Plan

QS = ["이번 달 식비 얼마 썼어?", "지난달 편의점에서 얼마 썼어?", "어제 카페에서 쓴 돈", "이번 달 교통비 합계",
      "생활비 통장 잔액만 알려줘", "30만 원 써도 돼?", "카드 대금 못 내면 어떻게 돼?", "11월 1일부터 10일까지 들어온 돈", "이번 주 술값 얼마야?"]

async def main(model, thinking):
    s = get_settings()
    llm = ChatGoogleGenerativeAI(model=model, google_api_key=s.gemini_api_key.get_secret_value(), temperature=0, reasoning_effort=thinking)
    system = SystemMessage(f"{ROUTER}\n오늘은 {today_kst().isoformat()}(한국)이다.")
    for q in QS:
        t = time.perf_counter()
        p = await llm.with_structured_output(Plan).ainvoke([system, HumanMessage(q)])
        d = {k: v for k, v in p.model_dump().items() if v not in (None, [], "")}
        print(f"{time.perf_counter()-t:4.1f}s {q} -> {json.dumps(d, ensure_ascii=False)}")
        await asyncio.sleep(4)

asyncio.run(main(sys.argv[1], sys.argv[2]))
