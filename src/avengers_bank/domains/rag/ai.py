"""Gemini 연결 (ADR 0013). 테스트는 get_ai를 가짜로 바꿔 끼워서 Gemini를 부르지 않는다"""

from functools import lru_cache
from typing import Protocol, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from avengers_bank.core.config import get_settings
from avengers_bank.core.exceptions import ApiException
from avengers_bank.domains.rag.models import EMBED_DIM

T = TypeVar("T", bound=BaseModel)
BATCH = 100
TIMEOUT_MS = 30_000
# 임베딩 입력 형식(접두어)이나 차원을 바꾸면 올린다: 저장된 벡터와 호환되지 않아 전부 다시 임베딩해야 함
EMBED_FORMAT = "v1"


class AI(Protocol):
    embedding_model: str  # 저장·비교용 이름 (모델 + 차원 + 입력 형식)

    async def embed(self, texts: list[str], *, query: bool, titles: list[str] | None = None) -> list[list[float]]: ...

    async def generate_json(self, prompt: str, schema: type[T]) -> T: ...


def unavailable(message: str, code: str = "AI_UNAVAILABLE") -> ApiException:
    return ApiException(status_code=503, code=code, message=message)


class GeminiAI:
    def __init__(self, api_key: str, model: str, embedding_model: str, thinking: str = "low"):
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        self.model, self.model_name, self.thinking = model, embedding_model, thinking
        self.embedding_model = f"{embedding_model}/{EMBED_DIM}/{EMBED_FORMAT}"

    async def embed(self, texts: list[str], *, query: bool, titles: list[str] | None = None) -> list[list[float]]:
        # gemini-embedding-2는 task_type이 없어서 질문·문서를 정해진 접두어로 구분한다 (임베딩 문서 권장 형식)
        if query:
            texts = [f"task: search result | query: {t}" for t in texts]
        else:
            texts = [f"title: {title or 'none'} | text: {t}" for t, title in zip(texts, titles or [None] * len(texts))]
        vectors = []
        try:
            for i in range(0, len(texts), BATCH):
                # 문자열 목록을 그대로 넘기면 SDK가 gemini-embedding-2에서 Content 하나로 합쳐 벡터가 1개만 온다.
                # 텍스트마다 Content로 감싸야 텍스트마다 벡터가 하나씩 온다 (PR #19 리뷰)
                contents = [types.Content(parts=[types.Part(text=t)]) for t in texts[i:i + BATCH]]
                res = await self.client.aio.models.embed_content(
                    model=self.model_name, contents=contents,
                    config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
                )
                vectors += [e.values for e in res.embeddings or []]
        except (errors.APIError, httpx.HTTPError) as e:
            raise unavailable(f"임베딩 서비스를 쓸 수 없습니다 ({type(e).__name__}).") from None
        if len(vectors) != len(texts):  # 개수가 어긋나면 zip이 조용히 잘라 엉뚱한 청크에 벡터가 붙는다
            raise unavailable(f"임베딩 개수가 맞지 않습니다 ({len(vectors)}/{len(texts)}).")
        return vectors

    async def generate_json(self, prompt: str, schema: type[T]) -> T:
        try:
            res = await self.client.aio.models.generate_content(
                model=self.model, contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0, response_mime_type="application/json", response_schema=schema,
                    thinking_config=types.ThinkingConfig(thinking_level=self.thinking),  # Agent와 같은 수준 (ADR 0016)
                ),
            )
            return schema.model_validate_json(res.text or "")
        except (errors.APIError, httpx.HTTPError) as e:
            raise unavailable(f"답변 서비스를 쓸 수 없습니다 ({type(e).__name__}).") from None
        except ValidationError:  # 빈 응답(안전 필터 등)이나 형식이 어긋난 JSON
            raise unavailable("답변 형식이 올바르지 않습니다. 다시 시도해 주세요.", "AI_BAD_RESPONSE") from None


@lru_cache
def gemini() -> GeminiAI | None:
    s = get_settings()
    if s.gemini_api_key is None:
        return None
    return GeminiAI(s.gemini_api_key.get_secret_value(), s.gemini_model, s.gemini_embedding_model, s.gemini_thinking)


def get_ai() -> AI:
    """FastAPI 의존성. 키가 없으면 503 (RAG만 꺼지고 나머지 은행 기능은 그대로)"""
    ai = gemini()
    if ai is None:
        raise unavailable("AI 기능이 꺼져 있습니다(GEMINI_API_KEY 없음).", "AI_DISABLED")
    return ai
