"""RAG 청크 (ADR 0013). 상품 DB와 데모 약관을 잘라 임베딩과 함께 저장한다"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base

EMBED_DIM = 768  # gemini-embedding-2를 768차원으로 줄여 저장 (ADR 0013)


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    chunk_id: Mapped[str] = mapped_column(String(100), primary_key=True)  # 예: card-terms#7, product:account:3
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # 문서 파일 이름 또는 product
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # 문서 > 제7조(제목)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # 바뀐 청크만 다시 임베딩
    tokens: Mapped[list] = mapped_column(JSON, nullable=False)  # Kiwi 내용어 (BM25용, 색인 때 한 번)
    embedding_model: Mapped[str] = mapped_column(String(50), nullable=False)  # 모델이 바뀌면 전부 다시 (벡터 호환 안 됨)
    # shortcut: SQLite 테스트는 JSON에 담고 파이썬으로 거리 계산, 운영은 pgvector
    embedding: Mapped[list] = mapped_column(Vector(EMBED_DIM).with_variant(JSON(), "sqlite"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
