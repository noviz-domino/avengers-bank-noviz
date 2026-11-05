"""계좌번호 형식: 110-TPP-NNNNNN (결정 이유: docs/decisions/0001, 0003)

- 110: 은행 코드 (AvengersBank 고정)
- T: 계좌 종류 (1 입출금, 2 예금, 3 적금, 4 대출 예약)
- PP: 상품 코드 (account_products.product_code, 종류 안에서 01~99)
- NNNNNN: 일련번호 (000001~999999)

계좌는 accounts 테이블 하나에 있고, 종류 코드가 account_type과 맞는지 DB CHECK가 확인한다.
"""

import re

BANK_CODE = "110"
TYPE_CODES = {"CHECKING": "1", "DEPOSIT": "2", "SAVINGS": "3"}
ACCOUNT_NUM_PATTERN = rf"^{BANK_CODE}-([{''.join(TYPE_CODES.values())}])\d{{2}}-\d{{6}}$"


def make_account_num(account_type: str, product_code: int, serial: int) -> str:
    if account_type not in TYPE_CODES:
        raise ValueError(f"알 수 없는 계좌 종류입니다: {account_type}")
    if not 1 <= product_code <= 99:
        raise ValueError(f"상품 코드는 1~99여야 합니다: {product_code}")
    if not 1 <= serial <= 999_999:
        raise ValueError(f"일련번호는 1~999999여야 합니다: {serial}")
    return f"{BANK_CODE}-{TYPE_CODES[account_type]}{product_code:02d}-{serial:06d}"


def account_type_of(account_num: str) -> str | None:
    """계좌번호만 보고 계좌 종류(CHECKING/DEPOSIT/SAVINGS)를 알려준다. 형식이 틀리면 None."""
    match = re.fullmatch(ACCOUNT_NUM_PATTERN, account_num)
    if match is None:
        return None
    return next(t for t, c in TYPE_CODES.items() if c == match.group(1))


def account_num_check_sql() -> str:
    # LIKE의 _는 아무 글자 하나: PostgreSQL과 테스트용 SQLite에서 똑같이 동작한다.
    # 그래서 DB는 종류 코드와 길이만 강제하고, 숫자인지는 make_account_num이 보장한다.
    return " OR ".join(
        f"(account_type = '{t}' AND account_num LIKE '{BANK_CODE}-{c}__-______')"
        for t, c in TYPE_CODES.items()
    )
