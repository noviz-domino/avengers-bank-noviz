"""AI 상담 측정 (ADR 0016): 라우팅 정확도, LLM 호출 수, 응답 시간(p50·p95)을 실제 Gemini로 잰다.

질문은 읽기만 하는 것만(routing.jsonl): 이체·분실 신고처럼 데이터를 바꾸는 질문은 반복 측정하지 않는다.
서버(docker compose)가 떠 있어야 하고, 데모 계정으로 로그인해 도구를 부른다. Gemini 호출: 질문마다 2~6번.

    docker compose exec app python -m avengers_bank.domains.agent.evaluate [--label before] [--pause 6]
"""

import argparse
import asyncio
import json
import math
import time
import uuid
from pathlib import Path

import httpx

from avengers_bank.domains.agent.llm import gemini_chat
from avengers_bank.domains.agent.service import agent_service
from avengers_bank.domains.agent.tracing import CallCounter
from avengers_bank.seed import DEMO_LOGIN_ID, DEMO_PASSWORD

ROUTING = Path(__file__).parent / "routing.jsonl"


def load_routing() -> list[dict]:
    return [json.loads(line) for line in ROUTING.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], p: float) -> float:
    """가장 가까운 순위 방식 (질문 수가 적어서 보간하지 않는다)"""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["error"] is None]
    times = [r["seconds"] for r in ok]
    return {
        "questions": len(rows), "errors": len(rows) - len(ok),
        "routing_accuracy": sum(r["routed"] in r["expected"] for r in ok) / len(rows),
        "llm_calls_avg": sum(r["calls"] for r in ok) / max(len(ok), 1),
        "p50": percentile(times, 50) if times else None, "p95": percentile(times, 95) if times else None,
    }


async def run(token: str, user_id: int, pause: float) -> list[dict]:
    llm, rows = gemini_chat(), []
    if llm is None:
        raise SystemExit("GEMINI_API_KEY가 없습니다.")
    for item in load_routing():
        counter = CallCounter()
        started, routed, error = time.perf_counter(), None, None
        try:
            res = await agent_service.chat(llm, user_id, token, str(uuid.uuid4()), item["q"], callbacks=[counter])
            routed = res.routed
        except Exception as e:  # 측정은 계속한다
            error = type(e).__name__
        rows.append({"q": item["q"], "expected": item["expected"], "routed": routed, "error": error,
                     "calls": counter.calls, "seconds": round(time.perf_counter() - started, 1)})
        print(f"{rows[-1]['seconds']:>6}s  calls={counter.calls}  {routed}  {'OK' if routed in item['expected'] else 'X'}  {item['q']}")
        await asyncio.sleep(pause)  # 무료 티어 분당 호출 한도
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    parser.add_argument("--pause", type=float, default=6.0)
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    login = httpx.post(f"{args.api}/users/login", json={"login_id": DEMO_LOGIN_ID, "password": DEMO_PASSWORD})
    if login.is_error:
        raise SystemExit(f"데모 계정 로그인 실패({login.status_code}). 서버를 띄우고 seed가 들어갔는지 확인하세요.")
    token = login.json()["data"]["access_token"]
    me = httpx.get(f"{args.api}/users/me", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    rows = asyncio.run(run(token, me["user_id"], args.pause))
    print(json.dumps({"label": args.label, **summarize(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
