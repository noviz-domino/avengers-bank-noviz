from fastapi import APIRouter

from avengers_bank.core.responses import error_responses

router = APIRouter(prefix="/cards", tags=["cards"], responses=error_responses(422))

# TODO: 카드 기능 PR (경로 초안: docs/API_ENDPOINTS.md)
