class CardService:
    # TODO: 카드 기능 PR (docs/ERD.md "예정", ADR 0003·0007)
    #   - 발급: 상품 종류 검증, 결제 계좌가 본인 입출금 계좌인지 확인
    #   - 결제: 실행 함수(ADR 0007)를 거쳐 예산 가드 → 체크카드는 장부(CARD_PAYMENT) 기록
    #   - 누적 사용액은 저장하지 않고 card_transactions 합계로 계산
    #   - 정지는 바로, 해제는 승인 대기
    pass


card_service = CardService()
