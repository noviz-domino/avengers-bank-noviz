from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from avengers_bank.core.database import engine
from avengers_bank.core.exception_handlers import register_exception_handlers
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.accounts.router import router as account_router
from avengers_bank.domains.agent import tracing
from avengers_bank.domains.agent.checkpoint import postgres_saver
from avengers_bank.domains.agent.router import router as chat_router
from avengers_bank.domains.accounts.router import tx_router as transaction_router
from avengers_bank.domains.approvals.router import router as approval_router
from avengers_bank.domains.cards.router import products_router as card_product_router
from avengers_bank.domains.cards.router import router as card_router
from avengers_bank.domains.cards.router import system_router as card_system_router
from avengers_bank.domains.mcp_server.server import mcp
from avengers_bank.domains.rag.router import router as rag_router
from avengers_bank.domains.rag.router import system_router as rag_system_router
from avengers_bank.domains.products.router import router as product_router
from avengers_bank.domains.transfers.router import router as transfer_router
from avengers_bank.domains.users.router import router as user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # /mcp 요청을 받는 동안 MCP 세션 관리자가 돌고, 대화는 PostgreSQL 체크포인터에 남는다
        async with mcp.session_manager.run(), postgres_saver():
            yield
    finally:
        tracing.flush()  # 남은 Langfuse 추적을 보내고 끈다
        await engine.dispose()


mcp_app = mcp.streamable_http_app()  # session_manager는 이걸 만들 때 생긴다 (lifespan보다 먼저)
app = FastAPI(title="AvengersBank", lifespan=lifespan, responses=error_responses(500))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
register_exception_handlers(app)
app.include_router(user_router)
app.include_router(product_router)
app.include_router(account_router)
app.include_router(transaction_router)
app.include_router(transfer_router)
app.include_router(approval_router)
app.include_router(card_router)
app.include_router(card_product_router)
app.include_router(card_system_router)
app.include_router(rag_router)
app.include_router(rag_system_router)
app.include_router(chat_router)


@app.get("/", response_model=SuccessResponse[dict[str, str]])
async def get_root():
    return SuccessResponse[dict[str, str]](data={"Hello": "AvengersBank"})
# MCP(ADR 0014): Authorization 헤더의 사용자 토큰으로 위 REST API를 부르는 도구들.
# mount 대신 경로 하나로 붙인다: mount는 /mcp를 /mcp/로 307 리다이렉트해서 따라가지 않는 클라이언트가 실패한다
app.add_route("/mcp", mcp_app)
