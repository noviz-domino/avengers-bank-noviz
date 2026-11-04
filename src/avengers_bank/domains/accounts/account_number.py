"""계좌번호 형식: 110-TPP-NNNNNN

- 110: 은행 코드 (AvengersBank 고정)
- T: 계좌 종류 (1 입출금, 2 예금, 3 적금, 4 대출 예약)
- PP: 상품 번호 (account_products.product_id, 01~99)
- NNNNNN: 일련번호 (000001~999999)

종류 코드가 테이블마다 달라서 세 계좌 테이블 사이에서는 번호가 겹칠 수 없다.
"""

BANK_CODE = "110"
TYPE_CODES = {"checking": "1", "deposit": "2", "savings": "3"}
ACCOUNT_NUM_PATTERN = r"^\d{3}-\d{3}-\d{6}$"


def make_account_num(account_type: str, product_no: int, serial: int) -> str:
    if not 1 <= product_no <= 99:
        raise ValueError(f"상품 번호는 1~99여야 합니다: {product_no}")
    if not 1 <= serial <= 999_999:
        raise ValueError(f"일련번호는 1~999999여야 합니다: {serial}")
    return f"{BANK_CODE}-{TYPE_CODES[account_type]}{product_no:02d}-{serial:06d}"


def account_type_of(account_num: str) -> str | None:
    """계좌번호만 보고 어느 테이블(checking/deposit/savings)인지 알려준다."""
    if len(account_num) != 14 or not account_num.startswith(f"{BANK_CODE}-"):
        return None
    code = account_num[4]
    return next((t for t, c in TYPE_CODES.items() if c == code), None)


def check_constraint_sql(account_type: str) -> str:
    # LIKE의 _는 아무 글자 하나: PostgreSQL과 테스트용 SQLite에서 똑같이 동작한다
    return f"account_num LIKE '{BANK_CODE}-{TYPE_CODES[account_type]}__-______'"
