# API 엔드포인트

- 실행 중인 서버에서는 `http://127.0.0.1:8000/docs`(Swagger)에서 직접 호출해 볼 수 있습니다.
- 🔒 표시가 있는 API는 `Authorization: Bearer <access_token>` 헤더가 필요합니다.
- 상태: ✅ 구현됨 / 📝 TODO (router 파일에 주석으로 자리만 잡아 둠)

## 공통 응답 형식

성공:
```json
{ "data": { ... }, "message": "회원가입이 완료되었습니다." }
```

실패:
```json
{ "error": { "code": "INSUFFICIENT_BALANCE", "message": "잔액이 부족합니다.", "details": [] } }
```

| HTTP | 언제 | 예외 클래스 (`core/exceptions.py`) |
|---|---|---|
| 400 | 잔액 부족, 한도 초과 등 처리 불가 | `BadRequestException` |
| 401 | 로그인 안 함, 토큰 만료 | `UnauthorizedException` |
| 403 | 권한이 없는 작업 (남의 계좌·카드는 403이 아니라 **404**: 있다는 것을 알려 주지 않으려고) | `ForbiddenException` |
| 404 | 계좌·카드·상품 없음 | `NotFoundException` |
| 409 | 아이디·계좌번호 중복 | `ConflictException` |
| 423 | 로그인 5회 실패로 잠김 | `LockedException` |
| 422 | 입력값 형식 오류 (FastAPI 자동) | — |

`code`는 `ACCOUNT_NOT_FOUND`, `DAILY_LIMIT_EXCEEDED`처럼 **대문자 스네이크 케이스**로 구체적으로 적습니다.

---

## users: 회원 (`domains/users`)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | POST | `/users/signup` | | 회원가입 (생년월일 필수, 마케팅 동의 선택) |
| ✅ | POST | `/users/login` | | 로그인, access token(15분) + refresh token(14일) 발급. 5회 실패하면 15분 잠금 |
| ✅ | POST | `/users/token/refresh` | | refresh token을 새 것으로 바꾸고 access token 재발급. 이미 바꾼 토큰이 다시 오면 그 기기 전체 폐기 |
| ✅ | POST | `/users/logout` | | 이 기기의 refresh token 폐기 (없는 토큰이어도 성공) |
| ✅ | GET | `/users/me` | 🔒 | 내 정보 조회 |
| 📝 | PATCH | `/users/me` | 🔒 | 이름, 닉네임, 전화번호 수정 |

<details>
<summary>요청·응답 예시</summary>

`POST /users/signup`
```json
{ "login_id": "ironman", "password": "password1234", "name": "토니 스타크", "nick_name": null, "phone": "010-1234-5678", "birth_date": "1990-05-29", "marketing_agreed": true }
```
→ `201`
```json
{ "data": { "user_id": 1, "login_id": "ironman", "name": "토니 스타크", "nick_name": null, "phone": "010-1234-5678", "birth_date": "1990-05-29", "marketing_agreed": true, "created_at": "2026-11-04T10:00:00Z" }, "message": "회원가입이 완료되었습니다." }
```

`POST /users/login`
```json
{ "login_id": "ironman", "password": "password1234", "device_name": "아이폰" }
```
→ `200`
```json
{ "data": { "access_token": "eyJhbGciOi...", "refresh_token": "q3Zx...", "token_type": "bearer" }, "message": null }
```
실패: `401 INVALID_CREDENTIALS`(1~4번째), `423 LOGIN_LOCKED`(5번째부터 15분 동안, 비밀번호가 맞아도)

`POST /users/token/refresh`, `POST /users/logout`
```json
{ "refresh_token": "q3Zx..." }
```
→ refresh는 로그인과 같은 모양(새 refresh token). 실패: `401 INVALID_REFRESH_TOKEN`(만료·없음), `401 REFRESH_TOKEN_REUSED`(이미 바꾼 토큰, 그 기기의 토큰 모두 폐기)
</details>

## products: 상품 (`domains/products`)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/products/accounts?type=` | | **판매 중인** 계좌·대출 상품 목록 (`type` = CHECKING·DEPOSIT·SAVINGS·LOAN, 생략하면 전체) |
| ✅ | GET | `/products/accounts/{product_id}` | | 상품 상세: 설명, 가입 조건, 우대금리 조건. 판매 중이 아니면 `404 PRODUCT_NOT_FOUND` |
| 📝 | GET | `/products/cards?type=` | | 카드 상품 목록 (카드 기능 PR에서 `card_products`와 함께) |

<details>
<summary>응답 예시</summary>

`GET /products/accounts/4` → `200`
```json
{ "data": {
  "product_id": 4, "type": "SAVINGS", "name": "스타크 자유적금",
  "base_rate": "3.50", "max_preferential_rate": "1.00",
  "min_term_months": 12, "max_term_months": 24, "min_amount": 10000, "max_amount": 1000000,
  "min_age": null, "sale_start": null, "sale_end": null,
  "description": "매달 정한 금액을 넣어 목돈을 만드는 적금입니다. …",
  "conditions": "월 1만 원부터 100만 원까지, 12~24개월.",
  "preferential_rates": [
    { "code": "SALARY_TRANSFER", "description": "이 은행 입출금 계좌로 급여를 받으면", "rate": "0.50" },
    { "code": "MARKETING_AGREED", "description": "마케팅 정보 수신에 동의하면", "rate": "0.20" },
    { "code": "FIRST_PRODUCT", "description": "이 은행에서 처음 가입하는 예·적금이면", "rate": "0.30" }
  ]
}, "message": null }
```
금리는 소수점이 정확해야 해서 문자열로 보냅니다. "판매 중"은 한국 날짜로 판단합니다(서버 시간대가 UTC여도 자정에 바뀜). 적금·예금의 `min_amount`·`max_amount`는 적금은 월 납입금, 예금은 맡기는 금액입니다.
</details>

## accounts: 계좌 (`domains/accounts`)

계좌는 `accounts` 한 테이블이라 종류별 경로를 두지 않습니다([ADR 0003](decisions/0003-db-redesign.md)). 모두 🔒이고, **남의 계좌는 `404 ACCOUNT_NOT_FOUND`**입니다.

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/accounts` | 🔒 | 해지하지 않은 내 계좌(잔액 많은 순) + 총자산. 메인 화면은 앞의 3개 ([screens.md](planning/screens.md)) |
| ✅ | POST | `/accounts` | 🔒 | 입출금·적금 개설 (종류는 상품이 정함). 가입 조건 검사, 적금은 적용 금리 확정 |
| ✅ | GET | `/accounts/{account_id}` | 🔒 | 계좌 상세 (적금·예금은 금리·만기 포함) |
| ✅ | GET | `/accounts/{account_id}/transactions?limit=&before=` | 🔒 | 거래내역, 최근부터. 다음 쪽은 받은 마지막 `tx_id`를 `before`로 |
| ✅ | PATCH | `/accounts/{account_id}` | 🔒 | 별칭 변경 (`null`이면 지움) |
| 📝 | | 예금 개설 | 🔒 | 맡길 돈을 입출금 계좌에서 옮겨야 해서 이체·승인 PR에서 |
| 📝 | | 이체 한도 변경, 해지 | 🔒 | 한도를 올리는 것은 보안을 약하게 해서 승인 PR에서. 해지는 잔액 0일 때만 |

<details>
<summary>요청·응답 예시</summary>

`POST /accounts` (적금)
```json
{ "product_id": 4, "nickname": "휴대폰 모으기", "term_months": 12, "monthly_payment": 100000, "payment_day": 25 }
```
→ `201`
```json
{ "data": {
  "account_id": 3, "account_type": "SAVINGS", "account_num": "110-301-000001", "product_name": "스타크 자유적금",
  "nickname": "휴대폰 모으기", "balance": 0, "status": "ACTIVE", "opened_at": "...",
  "per_transfer_limit": null, "daily_transfer_limit": null,
  "terms": { "applied_rate": "4.00", "rate_detail": [{"code": "MARKETING_AGREED", "rate": "0.20"}, {"code": "FIRST_PRODUCT", "rate": "0.30"}],
             "maturity_date": "2027-11-05", "monthly_payment": 100000, "payment_day": 25 }
}, "message": "계좌가 개설되었습니다." }
```
- 입출금 계좌는 이체 한도 기본값 1회 100만 원, 1일 500만 원으로 열립니다.
- 적금의 적용 금리 = 기본금리 + min(충족한 우대 합계, 우대 상한). 마케팅 동의와 첫 예·적금 우대는 개설 때 확인하고, **급여이체 우대는 개설 때 알 수 없어서 넣지 않습니다**. 상한에 걸리면 `rate_detail` 끝에 `{"code": "PREFERENTIAL_CAP", "rate": "-0.20"}`처럼 깎인 만큼이 붙어서, 기본금리 + `rate_detail` 합계 = 적용 금리입니다([ADR 0008](decisions/0008-account-opening-policy.md)).
- 만기일은 오늘(한국 날짜) + 기간. 그 달에 같은 날이 없으면 말일입니다.
- 실패: `400 AGE_NOT_ELIGIBLE`, `400 TERM_OUT_OF_RANGE`, `400 AMOUNT_OUT_OF_RANGE`, `400 DEPOSIT_NEEDS_TRANSFER`(예금), `400 PRODUCT_NOT_OPENABLE`(대출), `404 PRODUCT_NOT_FOUND`(판매 중 아님), `409 ACCOUNT_NUM_CONFLICT`(같은 상품을 동시에 개설, 다시 시도)

`GET /accounts` → `200`
```json
{ "data": {
  "total_balance": 8100000,
  "accounts": [
    { "account_id": 3, "account_type": "DEPOSIT", "account_num": "110-201-000001", "product_name": "히어로 정기예금", "nickname": null, "balance": 5000000, "status": "ACTIVE", "opened_at": "..." },
    { "account_id": 1, "account_type": "CHECKING", "account_num": "110-101-000001", "product_name": "어벤져스 입출금통장", "nickname": "생활비", "balance": 2350000, "status": "ACTIVE", "opened_at": "..." }
  ]
}, "message": null }
```
</details>

## transfers: 돈 이동 (`domains/transfers`)

이체는 바로 실행하지 않고 **승인 대기 작업(`pending_actions`)을 만든 뒤 PIN 승인으로 실행**합니다([ADR 0004](decisions/0004-agent-integration.md), [ADR 0007](decisions/0007-money-execution-and-budget-guard.md)). 경로는 이체 PR에서 확정합니다.

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| 📝 | POST | `/transfers` | 🔒 | 이체 요청 → 승인 대기 생성 (잔액·1회·1일 한도·예산 미리 계산) |
| 📝 | POST | `/approvals/{action_id}/approve` | 🔒 | 승인 (`action_id` + PIN만 받음). Agent·MCP 도구에는 없음 |

실패 예시(예정): `400 INSUFFICIENT_BALANCE`, `400 PER_TRANSFER_LIMIT_EXCEEDED`, `400 DAILY_LIMIT_EXCEEDED`, `404 ACCOUNT_NOT_FOUND`(없거나 남의 계좌)

## cards: 카드 (`domains/cards`)

카드 테이블(`card_products`, `cards`, `card_transactions`)은 카드 기능 PR에서 새로 만듭니다([ERD](ERD.md) "예정"). 팀 뼈대의 신용·체크 분리 경로(`/cards/{type}/...`)는 쓰지 않고, 그 PR에서 경로를 정합니다.

---

## 새 API를 추가하는 순서

1. `schemas.py`: 요청·응답 모양 정의
2. `repository.py`: 필요한 DB 조회·저장 메서드
3. `service.py`: 규칙 검사와 처리 (돈이 움직이면 `async with db.begin():`)
4. `router.py`: 경로 연결, `SuccessResponse[...]`로 감싸서 반환
5. `tests/`에 테스트 추가
6. 이 문서의 상태를 📝 → ✅로 변경
