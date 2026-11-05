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
| 403 | 남의 계좌·카드에 접근 | `ForbiddenException` |
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
| ✅ | POST | `/users/login` | | 로그인, JWT 발급. 5회 실패하면 15분 잠금 |
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
{ "login_id": "ironman", "password": "password1234" }
```
→ `200`
```json
{ "data": { "access_token": "eyJhbGciOi...", "token_type": "bearer" }, "message": null }
```
실패: `401 INVALID_CREDENTIALS`(1~4번째), `423 LOGIN_LOCKED`(5번째부터 15분 동안, 비밀번호가 맞아도)
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

계좌는 `accounts` 한 테이블이라 종류별 경로를 두지 않습니다([ADR 0003](decisions/0003-db-redesign.md)). 팀 뼈대의 `/accounts/{type}/{id}`는 아래로 바뀝니다.

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| 📝 | GET | `/accounts` | 🔒 | 내 계좌 전체 + 총자산 (메인 화면: [screens.md](planning/screens.md)) |
| 📝 | POST | `/accounts` | 🔒 | 계좌 개설 (`account_type`, `product_id`, 예·적금은 기간·금액) |
| 📝 | GET | `/accounts/{account_id}` | 🔒 | 계좌 상세 (예·적금은 금리·만기 포함) |
| 📝 | GET | `/accounts/{account_id}/transactions` | 🔒 | 거래내역 |
| 📝 | PATCH | `/accounts/{account_id}` | 🔒 | 별칭, 이체 한도(입출금만) 변경 |

<details>
<summary>응답 예시 (초안)</summary>

`GET /accounts` → `200`
```json
{ "data": {
  "total_balance": 10800000,
  "accounts": [
    { "account_id": 2, "account_type": "DEPOSIT", "account_num": "110-201-000001", "balance": 10000000, "nickname": null, "status": "ACTIVE", "opened_at": "..." },
    { "account_id": 1, "account_type": "CHECKING", "account_num": "110-101-000001", "balance": 500000, "nickname": "생활비", "status": "ACTIVE", "opened_at": "..." }
  ]
}, "message": null }
```
계좌 한 줄의 모양은 `domains/accounts/schemas.py`의 `AccountSummaryResponse`입니다.
</details>

## transfers: 돈 이동 (`domains/transfers`)

이체는 바로 실행하지 않고 **승인 대기 작업(`pending_actions`)을 만든 뒤 PIN 승인으로 실행**합니다([ADR 0004](decisions/0004-agent-integration.md), [ADR 0007](decisions/0007-money-execution-and-budget-guard.md)). 경로는 이체 PR에서 확정합니다.

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| 📝 | POST | `/transfers` | 🔒 | 이체 요청 → 승인 대기 생성 (잔액·1회·1일 한도·예산 미리 계산) |
| 📝 | POST | `/approvals/{action_id}/approve` | 🔒 | 승인 (`action_id` + PIN만 받음). Agent·MCP 도구에는 없음 |

실패 예시(예정): `400 INSUFFICIENT_BALANCE`, `400 PER_TRANSFER_LIMIT_EXCEEDED`, `400 DAILY_LIMIT_EXCEEDED`, `403 ACCOUNT_FORBIDDEN`, `404 ACCOUNT_NOT_FOUND`

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
