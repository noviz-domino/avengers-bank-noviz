"""거래 카테고리: 장부에 기록할 때 규칙으로 정하고, 사용자가 고칠 수 있다 (예산 분석의 재료, scope.md 5번)

shortcut: 카테고리는 지금 코드의 고정 목록이다. 예산 기능 PR에서 categories 테이블(필수 여부 등)로 옮긴다.
"""

CATEGORIES = (
    "식사", "카페·간식", "외식·술자리", "교통", "쇼핑", "의료", "주거·통신", "여가",
    "이체", "저축·내 계좌", "수입", "대출", "카드 대금", "기타",
)

# 거래 종류만 보고 정해지는 것
BY_TX_TYPE = {
    "INTERNAL_IN": "저축·내 계좌", "INTERNAL_OUT": "저축·내 계좌",
    "GOAL_SAVING_IN": "저축·내 계좌", "GOAL_SAVING_OUT": "저축·내 계좌",
    "DEPOSIT": "수입", "TRANSFER_IN": "수입", "INTEREST": "수입", "REFUND": "수입",
    "LOAN_DISBURSE": "대출", "LOAN_REPAY": "대출", "CARD_BILL": "카드 대금",
}

# 나가는 돈은 메모·상대방 이름의 낱말로 고른다. 위에서부터 먼저 맞는 것
KEYWORDS = [
    # "술"만 쓰면 수술비·미술학원도 걸려서 낱말 전체로 적는다
    (("외식", "회식", "술자리", "술집", "주점", "호프", "포차"), "외식·술자리"),
    (("카페", "커피", "스타벅스", "간식", "편의점"), "카페·간식"),
    (("점심", "저녁", "아침", "식사", "밥", "식당"), "식사"),
    (("버스", "지하철", "택시", "교통", "주유"), "교통"),
    (("병원", "약국", "의원", "치과", "수술"), "의료"),
    (("월세", "관리비", "통신", "전기", "가스", "수도"), "주거·통신"),
    (("영화", "공연", "게임", "여행"), "여가"),
    (("쇼핑", "마트", "옷"), "쇼핑"),
]


def classify(tx_type: str, memo: str | None, counterparty_name: str | None = None) -> str:
    if tx_type in BY_TX_TYPE:
        return BY_TX_TYPE[tx_type]
    text = f"{memo or ''} {counterparty_name or ''}"
    for words, category in KEYWORDS:
        if any(w in text for w in words):
            return category
    return "이체" if tx_type == "TRANSFER_OUT" else "기타"
