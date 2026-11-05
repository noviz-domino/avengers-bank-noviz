from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base


class AccountProduct(Base):
    """계좌·대출 상품. 대출도 type = LOAN으로 여기에 둔다 (ADR 0003)"""

    __tablename__ = "account_products"
    __table_args__ = (
        UniqueConstraint("type", "product_code", name="uq_account_products_type_product_code"),
        CheckConstraint("product_code BETWEEN 1 AND 99", name="ck_account_products_product_code"),
        CheckConstraint(
            "type IN ('CHECKING', 'DEPOSIT', 'SAVINGS', 'LOAN')", name="ck_account_products_type"
        ),
    )

    product_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 계좌번호 가운데 PP 자리 (docs/decisions/0001). 종류 안에서만 고유, product_id와 별개
    product_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)  # RAG 문서로도 사용
    base_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 기본 연 금리(%)
    max_preferential_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=0, server_default="0", nullable=False
    )  # 우대금리 상한(%p)
    min_term_months: Mapped[int | None] = mapped_column(SmallInteger)
    max_term_months: Mapped[int | None] = mapped_column(SmallInteger)
    min_amount: Mapped[int | None] = mapped_column(BigInteger)
    max_amount: Mapped[int | None] = mapped_column(BigInteger)  # 대출은 한도 상한
    min_age: Mapped[int | None] = mapped_column(SmallInteger)
    conditions: Mapped[str | None] = mapped_column(Text)  # 가입 조건 설명
    sale_start: Mapped[date | None] = mapped_column(Date)  # 특판 기간
    sale_end: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
