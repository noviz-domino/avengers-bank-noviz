class TransferService:
    # 이 도메인은 테이블이 없다. 계좌와 장부는 accounts.repository를 통해 읽고 쓴다.
    #
    # TODO: request_transfer — 바로 실행하지 않고 pending_actions만 만든다 (ADR 0004)
    #       요청 때 예산을 미리 계산해서 payload.budget_check에 저장 (ADR 0007)
    # TODO: 승인 후 실행은 실행 함수 하나(ADR 0007)에서:
    #       예산 주기 행 → 계좌 행(id 오름차순) 잠금 → 예산 가드 → 잔액·1회·1일 한도
    #       → 장부 두 줄(TRANSFER_OUT −, TRANSFER_IN +, 같은 transfer_id) + 잔액 변경
    pass


transfer_service = TransferService()
