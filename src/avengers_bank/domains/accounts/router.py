from fastapi import APIRouter

from avengers_bank.core.responses import error_responses

router = APIRouter(prefix="/accounts", tags=["accounts"], responses=error_responses(422))

# 계좌가 한 테이블이라 종류별 경로를 두지 않는다 (ADR 0003)
# TODO: GET   /accounts                          내 계좌 전체 + 총자산
# TODO: POST  /accounts                          계좌 개설 (account_type으로 구분)
# TODO: GET   /accounts/{account_id}             계좌 상세 (예·적금은 조건 포함)
# TODO: GET   /accounts/{account_id}/transactions  거래내역
# TODO: PATCH /accounts/{account_id}             별칭, 이체 한도(입출금만) 변경
