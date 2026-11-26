"""라우터 흔들림 시험 (ADR 0037): 같은 질문을 여러 번 물어 담당·빠른 길 표시가 바뀌는지 센다.
gemini-3.5-flash-lite는 temperature를 무시해서 같은 질문에도 다르게 고를 수 있다. 평가(evaluate.py)는 질문당 한 번이라 이걸 못 본다.

    docker compose cp docs/evaluations/agent-latency/router_repeat_probe.py app:/tmp/
    docker compose exec app python /tmp/router_repeat_probe.py 3
(Windows Git Bash는 앞에 MSYS_NO_PATHCONV=1)
"""
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

import avengers_bank.domains.agent as agent_pkg
from avengers_bank.core.clock import today_kst
from avengers_bank.domains.agent.graph import ROUTER, Plan
from avengers_bank.domains.agent.llm import router_chat


async def main(n: int) -> None:
    llm = router_chat().with_structured_output(Plan)
    system = SystemMessage(f"{ROUTER}\n오늘은 {today_kst().isoformat()}(한국)이다.")
    questions = [json.loads(line)["q"] for line in (Path(agent_pkg.__file__).parent / "routing.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    questions += ["30만 원짜리 사도 돼?", "5만 원 써도 돼?", "생활비 통장 잔액만 알려줘"]
    shaky = 0
    for q in questions:
        seen = Counter()
        for _ in range(n):
            p = await llm.ainvoke([system, HumanMessage(q)])
            seen[f"{'+'.join(p.agents) or '-'} / quick={'+'.join(p.quick) or '-'}"] += 1
            await asyncio.sleep(1)
        shaky += len(seen) > 1
        print(("흔들림 " if len(seen) > 1 else "같음   ") + q + "  " + json.dumps(dict(seen), ensure_ascii=False))
    print(f"질문 {len(questions)}개 중 {shaky}개가 {n}번 안에서 다르게 표시됨")


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
