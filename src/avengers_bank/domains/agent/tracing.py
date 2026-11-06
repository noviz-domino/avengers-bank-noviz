"""Agent 실행 추적 (ADR 0006·0016: Langfuse 무료 클라우드). 키가 없으면 꺼진다. 테스트는 항상 끈다.

Langfuse로 나가는 것: 대화 내용, 감독관·담당 Agent의 LLM 입출력, 도구 결과(데모 데이터). 사용자는 `user-{id}`로만.
"""

from functools import lru_cache

from langchain_core.callbacks import BaseCallbackHandler

from avengers_bank.core.config import get_settings


@lru_cache
def langfuse_client():
    s = get_settings()
    if s.langfuse_public_key is None or s.langfuse_secret_key is None:
        return None
    from langfuse import Langfuse

    return Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key.get_secret_value(),
                    base_url=s.langfuse_base_url)


def handlers() -> list[BaseCallbackHandler]:
    client = langfuse_client()
    if client is None:
        return []
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler(public_key=get_settings().langfuse_public_key)]


def metadata(user_id: int, session_id: str) -> dict:
    """Langfuse가 알아보는 metadata 키: 사용자·대화방별로 묶어 본다"""
    return {"langfuse_user_id": f"user-{user_id}", "langfuse_session_id": session_id, "langfuse_tags": ["chat"]}


def flush() -> None:
    """앱이 꺼질 때 남은 추적을 보낸다"""
    if (client := langfuse_client()) is not None:
        client.flush()


class CallCounter(BaseCallbackHandler):
    """LLM 호출 수를 센다 (측정 명령용, ADR 0016)"""

    def __init__(self):
        self.calls = 0

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.calls += 1
