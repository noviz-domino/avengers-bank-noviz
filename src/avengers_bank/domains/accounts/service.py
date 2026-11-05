class AccountService:
    # TODO: open_account — 상품 종류 검증, 계좌번호 발급은 여기 한 곳에서만 (make_account_num)
    #       예·적금이면 account_terms도 같은 트랜잭션에서 저장
    # TODO: get_my_accounts — 메인 화면용 총자산과 잔액 상위 3개 (docs/planning/screens.md)
    # TODO: get_account / get_transactions — 본인 계좌가 아니면 ForbiddenException
    # TODO: update_account — 별칭, 이체 한도 변경
    # TODO: close_account — 잔액 0일 때만 (ADR 0006)
    pass


account_service = AccountService()
