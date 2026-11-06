"""Gemini 연결 (ADR 0013). 테스트는 get_ai를 가짜로 바꿔 끼워서 Gemini를 부르지 않는다"""

from functools import lru_cache
from typing import Protocol, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from avengers_bank.core.config import get_settings
from avengers_bank.core.exceptions import ApiException
from avengers_bank.domains.rag.models import EMBED_DIM

T = TypeVar("T", bound=BaseModel)
BATCH = 100


class AI(Protocol):
    embedding_model: str

    async def embed(self, texts: list[str], *, query: bool, titles: list[str] | None = None) -> list[list[float]]: ...

    async def generate_json(self, prompt: str, schema: type[T]) -> T: ...


def unavailable(message: str, code: str) -> ApiException:
    return ApiException(status_code=503, code=code, message=message)


class GeminiAI:
    def __init__(self, api_key: str, model: str, embedding_model: str):
        self.client = genai.Client(api_key=api_key)
        self.model, self.embedding_model = model, embedding_model

    async def embed(self, texts: list[str], *, query: bool, titles: list[str] | None = None) -> list[list[float]]:
        # gemini-embedding-2는 task_type이 없어서 질문·문서를 정해진 접두어로 구분한다 (임베딩 문서 권장 형식)
        if query:
            texts = [f"task: search result | query: {t}" for t in texts]
        else:
            texts = [f"title: {title or 'none'} | text: {t}" for t, title in zip(texts, titles or [None] * len(texts))]
        vectors = []
        try:
            for i in range(0, len(texts), BATCH):
                res = await self.client.aio.models.embed_content(
                    model=self.embedding_model, contents=texts[i:i + BATCH],
                    config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
                )
                vectors += [e.values for e in res.embeddings]
        except errors.APIError as e:
            raise unavailable(f"임베딩 서비스를 쓸 수 없습니다 ({e.code}).", "AI_UNAVAILABLE") from None
        return vectors

    async def generate_json(self, prompt: str, schema: type[T]) -> T:
        try:
            res = await self.client.aio.models.generate_content(
                model=self.model, contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0, response_mime_type="application/json", response_schema=schema
                ),
            )
        except errors.APIError as e:
            raise unavailable(f"답변 서비스를 쓸 수 없습니다 ({e.code}).", "AI_UNAVAILABLE") from None
        return schema.model_validate_json(res.text)


@lru_cache
def gemini() -> GeminiAI | None:
    s = get_settings()
    if s.gemini_api_key is None:
        return None
    return GeminiAI(s.gemini_api_key.get_secret_value(), s.gemini_model, s.gemini_embedding_model)


def get_ai() -> AI:
    """FastAPI 의존성. 키가 없으면 503 (RAG만 꺼지고 나머지 은행 기능은 그대로)"""
    ai = gemini()
    if ai is None:
        raise unavailable("AI 기능이 꺼져 있습니다(GEMINI_API_KEY 없음).", "AI_DISABLED")
    return ai
