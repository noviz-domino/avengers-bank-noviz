"""카드번호 형식 (ADR 0009): 9410 T PP NNNNNNNN C (16자리)

- 9410: 발급사 번호(BIN). 9는 어느 업종에도 배정되지 않은 번호라 데모용으로 쓴다
- T: 종류 (1 신용, 2 체크)
- PP: 카드 상품 코드 (card_products.product_code)
- NNNNNNNN: 일련번호
- C: 검증 숫자 (Luhn). 실제 카드처럼 한 자리 오타를 잡는다
"""

BIN = "9410"
TYPE_CODES = {"CREDIT": "1", "DEBIT": "2"}


def luhn_digit(body: str) -> str:
    """body 뒤에 붙일 검증 숫자. 오른쪽부터 두 칸마다 두 배 해서 9를 빼고 모두 더한다"""
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:  # 검증 숫자가 붙으면 이 자리가 오른쪽에서 두 번째가 된다
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return str((10 - total % 10) % 10)


def is_valid(card_num: str) -> bool:
    return len(card_num) == 16 and card_num.isdigit() and luhn_digit(card_num[:-1]) == card_num[-1]


def prefix(card_type: str, product_code: int) -> str:
    return f"{BIN}{TYPE_CODES[card_type]}{product_code:02d}"


def make_card_num(card_type: str, product_code: int, serial: int) -> str:
    if not 1 <= product_code <= 99:
        raise ValueError(f"상품 코드는 1~99여야 합니다: {product_code}")
    if not 1 <= serial <= 99_999_999:
        raise ValueError(f"일련번호는 1~99999999여야 합니다: {serial}")
    body = f"{prefix(card_type, product_code)}{serial:08d}"
    return body + luhn_digit(body)


def mask(card_num: str) -> str:
    """앞 6자리와 뒤 4자리만 보여 준다: 9410-12**-****-0018"""
    return f"{card_num[:4]}-{card_num[4:6]}**-****-{card_num[12:]}"
