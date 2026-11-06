"""RAG 문서를 청크로 자른다 (ADR 0013, 지난 RAG 레포의 구조형 청킹).

- 데모 약관(docs/*.md): 조항 1개 = 청크 1개. 1,200자가 넘으면 ①② 항 경계에서만 나누고 조 제목을 반복한다.
- 상품 DB: 상품 1개 = 청크 1개. id는 DB id가 아니라 종류·상품 코드라서 seed를 다시 넣어도 같다.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from avengers_bank.core.clock import today_kst
from avengers_bank.domains.cards.models import CardProduct
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.products.repository import on_sale

DOCS = Path(__file__).parent / "docs"
MAX_CHARS = 1200
ARTICLE = re.compile(r"^## (제(\d+)조)\((.+?)\)\s*$", re.M)
PARAGRAPH = re.compile(r"^(?=[①-⑳])", re.M)  # ①② 항이 시작하는 줄
KINDS = {"CHECKING": "입출금 통장", "DEPOSIT": "정기예금", "SAVINGS": "적금", "DEBIT": "체크카드", "CREDIT": "신용카드"}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    title: str
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.title}\n{self.content}".encode()).hexdigest()


def split_long(body: str) -> list[str]:
    """MAX_CHARS 이하면 그대로. 넘으면 ①② 항 경계에서 차례로 묶는다 (항 하나가 길면 그 항은 혼자)"""
    if len(body) <= MAX_CHARS:
        return [body]
    pieces, current = [], ""
    for para in (p.strip() for p in PARAGRAPH.split(body) if p.strip()):
        if current and len(current) + len(para) + 1 > MAX_CHARS:
            pieces.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    return pieces + [current] if current else pieces


def chunk_doc(path: Path) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    doc_title = text.splitlines()[0].removeprefix("# ").strip()
    parts = ARTICLE.split(text)  # [머리말, 제1조, 1, 목적, 본문, 제2조, ...]
    chunks = []
    for i in range(1, len(parts), 4):
        article, number, name, body = parts[i], parts[i + 1], parts[i + 2], parts[i + 3].strip()
        head = f"{article}({name})"
        pieces = split_long(body)
        for j, piece in enumerate(pieces, start=1):
            suffix = f"-{j}" if len(pieces) > 1 else ""
            chunks.append(Chunk(f"{path.stem}#{number}{suffix}", path.name, f"{doc_title} > {head}", f"{head}\n{piece}"))
    return chunks


def doc_chunks() -> list[Chunk]:
    return [c for path in sorted(DOCS.glob("*.md")) for c in chunk_doc(path)]


def account_product_text(p: AccountProduct) -> str:
    lines = [f"{p.name} ({KINDS[p.type]})", p.description, f"기본 금리 연 {p.base_rate}%"]
    if p.max_preferential_rate:
        lines.append(f"우대금리 최대 연 {p.max_preferential_rate}%p")
    if p.min_term_months or p.max_term_months:
        lines.append(f"가입 기간 {p.min_term_months or 1}~{p.max_term_months or '제한 없음'}개월")
    if p.min_amount or p.max_amount:
        low = f"{p.min_amount:,}원" if p.min_amount else "제한 없음"
        high = f"{p.max_amount:,}원" if p.max_amount else "제한 없음"
        lines.append(f"가입 금액 {low} ~ {high}")
    if p.min_age:
        lines.append(f"가입 나이 만 {p.min_age}세 이상")
    if p.conditions:
        lines.append(f"가입 조건: {p.conditions}")
    if p.sale_start or p.sale_end:
        lines.append(f"판매 기간 {p.sale_start or ''} ~ {p.sale_end or ''} (특판)")
    lines += [f"우대금리 조건: {r.description} (+{r.rate}%p)" for r in p.preferential_rates]
    return "\n".join(lines)


async def product_chunks(db: AsyncSession) -> list[Chunk]:
    """판매 중인 계좌·카드 상품 (상품 API와 같은 기준: 특판 기간 포함). 대출은 기능이 아직 없어서 넣지 않는다.
    shortcut: 특판이 끝난 날 색인을 다시 만들어야 빠진다. 대금 출금처럼 매일 /system으로 부르면 된다"""
    accounts = await db.scalars(
        select(AccountProduct).options(selectinload(AccountProduct.preferential_rates))
        .where(*on_sale(today_kst()), AccountProduct.type != "LOAN")
        .order_by(AccountProduct.type, AccountProduct.product_code)
    )
    cards = await db.scalars(select(CardProduct).where(CardProduct.is_active.is_(True))
                             .order_by(CardProduct.type, CardProduct.product_code))
    chunks = [
        Chunk(f"product:{p.type.lower()}:{p.product_code}", "product", f"상품 > {p.name}", account_product_text(p))
        for p in accounts
    ]
    chunks += [
        Chunk(f"product:{p.type.lower()}:{p.product_code}", "product", f"상품 > {p.name}",
              f"{p.name} ({KINDS[p.type]})\n연회비 {p.annual_fee:,}원\n혜택: {p.benefits}")
        for p in cards
    ]
    return chunks
