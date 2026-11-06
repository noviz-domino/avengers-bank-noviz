"""RAG 검색 평가: 정답 세트(golden.jsonl)로 Hit@1·Hit@5·MRR을 검색 방식별로 잰다 (ADR 0013).

실행 (Gemini 무료 한도를 씀: 질문 수만큼 임베딩 1번씩, 방식끼리는 재사용):
    uv run python -m avengers_bank.domains.rag.evaluate
먼저 DB에 색인이 있어야 한다: POST /system/rag/reindex
"""

import asyncio
import json
from pathlib import Path

from avengers_bank.domains.rag.ai import AI, gemini
from avengers_bank.domains.rag.service import rag_service

GOLDEN = Path(__file__).parent / "golden.jsonl"
MODES = ("hybrid", "vector", "bm25")


def load_golden() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]


def score(ranked: list[list[str]], expected: list[list[str]]) -> dict[str, float]:
    """질문마다 검색 결과(순서대로)와 정답 id 목록. 정답 중 하나라도 맞으면 맞힌 것"""
    first = [next((r + 1 for r, i in enumerate(got) if i in want), None) for got, want in zip(ranked, expected)]
    n = len(first)
    return {
        "hit@1": sum(f == 1 for f in first) / n,
        "hit@5": sum(f is not None and f <= 5 for f in first) / n,
        "mrr": sum(1 / f for f in first if f) / n,
    }


class CachedEmbed:
    """같은 질문을 여러 방식으로 검색할 때 임베딩을 한 번만 부른다 (무료 한도 절약)"""

    def __init__(self, ai: AI):
        self.ai, self.embedding_model, self.cache = ai, ai.embedding_model, {}

    async def embed(self, texts, *, query, titles=None):
        key = (tuple(texts), query)
        if key not in self.cache:
            self.cache[key] = await self.ai.embed(texts, query=query, titles=titles)
        return self.cache[key]


async def evaluate(db, ai: AI, modes=MODES) -> dict[str, dict[str, float]]:
    golden, cached = load_golden(), CachedEmbed(ai)
    result = {}
    for mode in modes:
        ranked = [[h.chunk_id for h in await rag_service.search(db, cached, g["q"], 5, mode)] for g in golden]
        result[mode] = score(ranked, [g["expected"] for g in golden])
    return result


async def main() -> None:
    from avengers_bank.core.database import SessionLocal

    ai = gemini()
    if ai is None:
        raise SystemExit("GEMINI_API_KEY가 없습니다. .env에 넣고 다시 실행하세요.")
    async with SessionLocal() as db:
        result = await evaluate(db, ai)
    print(f"질문 {len(load_golden())}개, 임베딩 {ai.embedding_model}")
    print(f"{'방식':<8}{'Hit@1':>8}{'Hit@5':>8}{'MRR':>8}")
    for mode, m in result.items():
        print(f"{mode:<8}{m['hit@1']:>8.3f}{m['hit@5']:>8.3f}{m['mrr']:>8.3f}")


if __name__ == "__main__":
    asyncio.run(main())
