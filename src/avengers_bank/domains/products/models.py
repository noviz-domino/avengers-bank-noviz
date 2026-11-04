from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base


class AccountProduct(Base):
    __tablename__ = "account_products"
    __table_args__ = (
        UniqueConstraint("type", "product_code", name="uq_account_products_type_product_code"),
        CheckConstraint("product_code BETWEEN 1 AND 99", name="ck_account_products_product_code"),
    )

    product_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # CHECKING / DEPOSIT / SAVINGS
    # 계좌번호 가운데 PP 자리 (docs/decisions/0001). 종류 안에서만 고유, product_id와 별개
    product_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 연 금리(%)


class CardProduct(Base):
    __tablename__ = "card_products"

    product_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # CREDIT / DEBIT
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
