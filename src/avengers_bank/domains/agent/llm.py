"""Agent가 쓰는 채팅 모델 (ADR 0013: gemini-3.8-flash). 테스트는 get_llm을 가짜로 바꿔 끼운다"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from avengers_bank.core.config import get_settings
from avengers_bank.domains.rag.ai import unavailable


@lru_cache
def gemini_chat() -> BaseChatModel | None:
    s = get_settings()
    if s.gemini_api_key is None:
        return None
    return ChatGoogleGenerativeAI(
        model=s.gemini_model, google_api_key=s.gemini_api_key.get_secret_value(),
        temperature=0, timeout=60, max_retries=2, reasoning_effort=s.gemini_thinking,
    )


def get_llm() -> BaseChatModel:
    llm = gemini_chat()
    if llm is None:
        raise unavailable("AI 기능이 꺼져 있습니다(GEMINI_API_KEY 없음).", "AI_DISABLED")
    return llm
