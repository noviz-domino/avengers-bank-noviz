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
| ✅ | POST | `/users/signup` | | 회원가입 (생년월일 필수, 마케팅 동의 선택). 이름은 한글·영문과 띄어쓰기만, 30자까지 (승인 화면에 받는 사람 이름으로 들어가서 숫자·기호로 금액처럼 꾸미지 못하게) |
| ✅ | POST | `/users/login` | | 로그인, access token(15분) + refresh token(14일) 발급. 5회 실패하면 15분 잠금 |
| ✅ | POST | `/users/token/refresh` | | refresh token을 새 것으로 바꾸고 access token 재발급. 이미 바꾼 토큰이 다시 오면 그 기기 전체 폐기 |
| ✅ | POST | `/users/logout` | | 이 기기의 refresh token 폐기 (없는 토큰이어도 성공) |
| ✅ | GET | `/users/me` | 🔒 | 내 정보 조회 (`has_pin`: 거래 PIN 설정 여부) |
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
| ✅ | GET | `/products/cards?type=` | | 카드 상품 목록 (아래 cards 절) |

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
| ✅ | POST | `/accounts/deposits` | 🔒 | **예금 개설 신청** → `202` 승인 대기. PIN 승인 때 계좌 생성 + 맡길 돈 이동이 한 트랜잭션 |
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
- 실패: `400 AGE_NOT_ELIGIBLE`, `400 TERM_OUT_OF_RANGE`, `400 AMOUNT_OUT_OF_RANGE`, `400 DEPOSIT_NEEDS_TRANSFER`(예금은 `/accounts/deposits`로), `400 PRODUCT_NOT_OPENABLE`(대출), `404 PRODUCT_NOT_FOUND`(판매 중 아님), `409 ACCOUNT_NUM_CONFLICT`(같은 상품을 동시에 개설, 다시 시도)

`POST /accounts/deposits` (예금)
```json
{ "product_id": 2, "from_account_id": 1, "amount": 2000000, "term_months": 12, "nickname": "목돈", "idempotency_key": "web-7c2d…" }
```
→ `202` 승인 대기 (`action_type: OPEN_DEPOSIT`, summary: "생활비(110-101-000001)에서 2,000,000원을 히어로 정기예금 12개월에 맡기기"). `POST /approvals/{action_id}/approve`(PIN) → 예금 계좌가 열리고 2,000,000원이 옮겨지며, 응답(`ActionResponse`)의 `result.account_id`에 새 계좌 id가 들어갑니다.
- 예금 금액은 상품의 `min_amount`~`max_amount`, 출금 계좌는 내 입출금 계좌. 승인 때 상품 판매·가입 조건·잔액을 **다시** 확인하고, 안 되면 계좌를 만들지 않고 `FAILED`(계좌번호 충돌 `ACCOUNT_NUM_CONFLICT`도 같음)
- 승인 뒤 같은 멱등키로 다시 보내면 `200`으로 처음 요청(상태 `EXECUTED`)을 돌려줍니다
- 예금 계좌에는 나중에 이체로 돈을 더 넣을 수 없습니다(`ACCOUNT_CANNOT_RECEIVE`)

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

## transactions: 거래내역 검색 (`domains/accounts`)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/transactions` | 🔒 | 내 모든 계좌의 거래 검색 + 조건 전체 합계 |
| ✅ | PATCH | `/transactions/{tx_id}` | 🔒 | 카테고리·메모 고치기 (보낸 칸만, 금액·상대방은 못 고침) |

<details>
<summary>요청·응답 예시</summary>

`GET /transactions?from_date=2026-11-01&to_date=2026-11-30&direction=OUT&category=식사&limit=20`
→ `200`
```json
{ "data": {
  "transactions": [ { "tx_id": 4, "account_id": 1, "tx_type": "CARD_PAYMENT", "amount": -12000, "balance_after": 2350000,
                      "counterparty_name": null, "counterparty_account": null, "memo": "점심", "category": "식사", "created_at": "…" } ],
  "total_in": 0, "total_out": 12000, "next_before": null
}, "message": null }
```
| 조건 | 뜻 |
|---|---|
| `account_id` | 없으면 내 모든 계좌. 남의 계좌는 `404 ACCOUNT_NOT_FOUND` |
| `from_date`, `to_date` | **한국 날짜** (양 끝 포함) |
| `min_amount`, `max_amount` | 금액의 크기(부호 무시) |
| `keyword` | 메모·상대방 이름에 포함 (대소문자 무시, `%`·`_`는 글자 그대로) |
| `direction` | `IN` / `OUT` |
| `category` | 식사, 카페·간식, 외식·술자리, 교통, 쇼핑, 의료, 주거·통신, 여가, 이체, 저축·내 계좌, 수입, 대출, 카드 대금, 기타 |
| `limit`, `before` | 최근부터. 다음 쪽은 응답의 `next_before`를 `before`로 |

- `total_in`, `total_out`은 이번 쪽이 아니라 **조건 전체**의 합계(`total_out`은 양수)
- 실패: `422`(기간·금액 범위가 거꾸로, 없는 카테고리, **모르는 조건 이름**(오타), PATCH에 금액 등 고칠 수 없는 칸, 카테고리를 `null`로), `404 TRANSACTION_NOT_FOUND`(없거나 남의 거래)
- `next_before`는 다음 쪽이 정말 있을 때만 값이 있습니다
</details>

## transfers: 돈 이동 (`domains/transfers`)

이체는 바로 실행하지 않고 **승인 대기 작업(`pending_actions`)을 만든 뒤 PIN 승인으로 실행**합니다([ADR 0004](decisions/0004-agent-integration.md), [ADR 0007](decisions/0007-money-execution-and-budget-guard.md)). **웹에서 시작해도** 같습니다.

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | POST | `/transfers` | 🔒 | 이체 요청 → `202` 승인 대기. 같은 `idempotency_key`로 다시 오면 `200`으로 처음 것을 돌려줌 |

- 보내는 계좌: 내 **입출금** 계좌만. 받는 계좌: 다른 사람의 **입출금** 계좌, 또는 **내 적금**(납입)
- 요청 때 잔액·1회 한도·1일 한도(오늘 한국 날짜, `TRANSFER_OUT`만)를 미리 검사하고, **승인 때 같은 검사를 잠금 안에서 다시** 합니다
- 내 계좌끼리 이동은 `INTERNAL_OUT/IN`으로 기록하고 이체 한도를 적용하지 않습니다

<details>
<summary>요청·응답 예시</summary>

```json
{ "from_account_id": 1, "to_account_num": "110-101-000002", "amount": 50000, "memo": "밥값", "idempotency_key": "web-4b1e0c9a" }
```
→ `202`
```json
{ "data": { "action_id": "1f0c…", "action_type": "TRANSFER", "status": "PENDING", "requested_by": "WEB",
  "summary": "생활비(110-101-000001)에서 피터님(110-101-000002)에게 50,000원 보내기",
  "expires_at": "…(10분 뒤)", "created_at": "…", "executed_at": null, "failure_reason": null },
  "message": "승인 화면에서 PIN을 입력하면 보내집니다." }
```
실패: `400 INSUFFICIENT_BALANCE`, `400 PER_TRANSFER_LIMIT_EXCEEDED`, `400 DAILY_LIMIT_EXCEEDED`, `400 ACCOUNT_NOT_FOUND`(보내는 계좌가 없거나 남의 것), `400 RECEIVER_NOT_FOUND`, `400 ACCOUNT_CANNOT_SEND`(입출금 아님), `400 ACCOUNT_CANNOT_RECEIVE`, `400 SAME_ACCOUNT`, `409 IDEMPOTENCY_KEY_REUSED`(같은 키, 다른 내용. 메모도 비교), `409 DUPLICATE_REQUEST`(같은 키가 동시에 옴)
</details>

## approvals: 승인 (`domains/approvals`)

사람이 **은행 화면에서만** 씁니다. Agent·MCP 도구에는 넣지 않습니다([ADR 0004](decisions/0004-agent-integration.md)).

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/approvals` | 🔒 | 승인을 기다리는 내 요청 (만료 전) |
| ✅ | GET | `/approvals/{action_id}` | 🔒 | 승인 화면: 서버가 만든 `summary`, 상태, 실패 이유 |
| ✅ | POST | `/approvals/{action_id}/approve` | 🔒 | **PIN만** 받아 승인 → 실행. 같은 트랜잭션에서 실행 직전 재검사 |
| ✅ | POST | `/approvals/{action_id}/reject` | 🔒 | 거절 (안전한 쪽이라 PIN 없음) |
| ✅ | PUT | `/users/me/pin` | 🔒 | 거래 PIN 6자리 설정·변경. **비밀번호를 다시 받음**(토큰만으로는 못 바꿈) |

실패: `400 PIN_NOT_SET`, `400 INVALID_PIN`(남은 횟수 안내), `423 PIN_LOCKED`(5회, 15분. 로그인은 안 잠김), `409 ACTION_EXPIRED`(10분), `409 ACTION_NOT_PENDING`(이미 처리. 이 둘은 **PIN을 확인하기 전에** 알려서 PIN 실패로 세지 않음), `404 ACTION_NOT_FOUND`(없거나 남의 것), 실행 때 재검사 실패는 그 이유(예: `400 INSUFFICIENT_BALANCE`)로 답하고 요청은 `FAILED`로 남습니다.

## cards: 카드 (`domains/cards`)

카드번호는 응답에 **가린 번호**(`masked_card_num`, 앞 6자리·뒤 4자리)만 나갑니다. 남의 카드는 `404 CARD_NOT_FOUND`. 결정 이유: [ADR 0009](decisions/0009-card-policy.md)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/products/cards?type=` | | 판매 중인 카드 상품 (CREDIT·DEBIT) |
| ✅ | POST | `/cards` | 🔒 | 발급 (`product_id`, `linked_account_id`=내 입출금 계좌, 신용은 `payment_day` 1~28, 기본 14) |
| ✅ | GET | `/cards`, `/cards/{card_id}` | 🔒 | 내 카드 목록·상세 |
| ✅ | POST | `/cards/{card_id}/suspend` | 🔒 | 정지(`reason: SUSPENDED`) 또는 분실 신고(`LOST`). **바로** 적용. 분실은 되돌릴 수 없음 |
| ✅ | POST | `/cards/{card_id}/unsuspend` | 🔒 | 정지 해제 요청 → `202` 승인 대기(`UNSUSPEND_CARD`). PIN 승인 때 상태를 다시 보고 풂 |
| ✅ | POST | `/cards/{card_id}/payments` | 🔒 | **가맹점 결제 흉내**(`merchant_name`, `amount`, `idempotency_key`). PIN 없이 바로 `201`. 체크는 결제 계좌에서 출금, 신용은 사용 기록(`UNBILLED`). 같은 요청 번호면 처음 결과 `200`. Agent 도구에 없음 ([ADR 0010](decisions/0010-card-payments.md)) |
| ✅ | GET | `/cards/{card_id}/transactions` | 🔒 | 사용내역 (최근 순) |
| ✅ | POST | `/cards/{card_id}/transactions/{card_tx_id}/cancel` | 🔒 | 전액 취소. 체크는 결제 계좌로 환불(`REFUND`), 신용은 기록만 취소. 정지·분실 카드도 됨 |
| ✅ | GET | `/cards/{card_id}/limits` | 🔒 | `daily_limit`·`daily_used`(오늘, 취소 제외), 신용은 `credit_limit`·`credit_used`(안 갚은 금액) |


- 기본 한도: 체크 1일 100만, 신용 1일 100만·신용 한도(안 갚은 금액) 300만. 카드 응답의 `monthly_limit`은 `credit_limit`으로 바뀜
- 발급·정지 실패: `400 ACCOUNT_NOT_FOUND`(결제 계좌가 내 입출금 계좌가 아님), `404 CARD_PRODUCT_NOT_FOUND`, `409 CARD_LOST`, `409 CARD_NOT_SUSPENDED`, `409 CARD_NUM_CONFLICT`(동시 발급, 다시 시도)
- 결제 실패: `409 CARD_NOT_ACTIVE`(정지·분실), `400 CARD_DAILY_LIMIT_EXCEEDED`, `400 CREDIT_LIMIT_EXCEEDED`, `400 INSUFFICIENT_BALANCE`, `400 ACCOUNT_NOT_FOUND`(결제 계좌를 쓸 수 없음), `409 IDEMPOTENCY_KEY_REUSED`
- 결제 실패(신용): `409 CARD_OVERDUE` (대금을 못 낸 사용분이 있음, [ADR 0011](decisions/0011-card-bills.md))
- 취소: 안 낸 것(`UNBILLED`·`BILLED`)은 기록만, 낸 것(체크카드, `PAID`)은 결제 계좌로 환불. 실패: `404 CARD_TX_NOT_FOUND`, `409 CARD_TX_ALREADY_CANCELED`

## system: 시스템 작업 (`domains/cards`의 `system_router`)

사용자 토큰이 아니라 **서버 키**(`X-System-Key` 헤더 = `.env`의 `SYSTEM_API_KEY`)로만 부릅니다. 키를 설정하지 않으면 `403 SYSTEM_API_DISABLED`, 틀리면 `403 SYSTEM_KEY_INVALID`. 결정 이유: [ADR 0011](decisions/0011-card-bills.md)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | POST | `/system/card-bills/run?run_date=` | 🔑 | 신용카드 대금 출금. 날짜를 비우면 오늘(한국), 오늘 이후는 거절. 결제일이면 전날까지 쓴 것을 묶어 전액 출금(`CARD_BILL`), 못 내면 연체로 남기고 다음 실행 때 다시. 같은 날짜로 다시 불러도 한 번만 |

```json
{ "success": true, "data": { "run_date": "2030-01-14", "paid_cards": 3, "overdue_cards": 1, "failed_cards": 0, "total_paid": 450000 } }
```
- 실패: `400 RUN_DATE_IN_FUTURE`(오늘 이후 날짜), `403 SYSTEM_API_DISABLED`, `403 SYSTEM_KEY_INVALID`. 카드 하나가 예상 못 한 오류로 실패하면 그 카드만 되돌리고 `failed_cards`에 셈

---

## 새 API를 추가하는 순서

1. `schemas.py`: 요청·응답 모양 정의
2. `repository.py`: 필요한 DB 조회·저장 메서드
3. `service.py`: 규칙 검사와 처리 (돈이 움직이면 `async with db.begin():`)
4. `router.py`: 경로 연결, `SuccessResponse[...]`로 감싸서 반환
5. `tests/`에 테스트 추가
6. 이 문서의 상태를 📝 → ✅로 변경
