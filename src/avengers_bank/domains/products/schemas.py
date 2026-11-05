from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountProductResponse(BaseModel):
    product_id: int
    type: str
    name: str
    description: str
    base_rate: Decimal
    max_preferential_rate: Decimal

    model_config = ConfigDict(from_attributes=True)


# TODO: 카드 상품 응답은 카드 기능 PR에서 card_products와 함께
