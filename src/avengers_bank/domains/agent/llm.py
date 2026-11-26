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


@lru_cache
def router_chat() -> BaseChatModel | None:
    """라우터 전용 모델 (ADR 0036). 키가 없으면 None이고 라우터는 담당과 같은 모델(테스트의 가짜 모델)을 쓴다"""
    s = get_settings()
    if s.gemini_api_key is None:
        return None
    return ChatGoogleGenerativeAI(
        model=s.gemini_router_model, google_api_key=s.gemini_api_key.get_secret_value(),
        temperature=0, timeout=30, max_retries=2, reasoning_effort=s.gemini_router_thinking,
    )


def router_for(llm: BaseChatModel) -> BaseChatModel:
    """실제 Gemini로 돌 때만 라우터 전용 모델을 쓴다. 테스트의 가짜 모델은 라우터도 그대로"""
    return (router_chat() or llm) if llm is gemini_chat() else llm


def get_llm() -> BaseChatModel:
    llm = gemini_chat()
    if llm is None:
        raise unavailable("AI 기능이 꺼져 있습니다(GEMINI_API_KEY 없음).", "AI_DISABLED")
    return llm
