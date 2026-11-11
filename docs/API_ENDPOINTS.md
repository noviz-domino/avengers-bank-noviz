# API 엔드포인트

- 실행 중인 서버에서는 `http://127.0.0.1:8000/docs`(Swagger)에서 직접 호출해 볼 수 있습니다.
- 🔒 표시가 있는 API는 `Authorization: Bearer <access_token>` 헤더가 필요합니다.
- 상태: ✅ 구현됨 / 📝 TODO (router 파일에 주석으로 자리만 잡아 둠)

## 공통 응답 형식

예산 관리: [ADR 0024](decisions/0024-budget-guard.md). 모바일 앱의 예산 화면에서 신청·조회·변경·해지한다. AI는 조회 도구만 사용한다.

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/budget` | 🔒 | 수입·월급날·고정 지출·하루 생활비·목표로 신청 (201) |
| GET | `/budget` | 🔒 | 이번 주기 계산 내역. 미신청은 `200 {data: {enrolled: false}}` |
| GET | `/budget/check?amount=300000` | 🔒 | 지출 영향 조회. amount 양의 정수, category 선택. 미신청 404 |
| PATCH | `/budget` | 🔒 | 강화는 200 계산 내역. 완화는 202 `BUDGET_UPDATE` 승인 대기, PIN 후 반영. 수입·생활비·고정 지출·목표·항상 통과 업종 변경 |
| DELETE | `/budget` | 🔒 | 해지 승인 대기 (202, 기존 대기는 200). 기존 승인 API의 PIN 필요 |

예산 초과 카드 결제는 `409 BUDGET_CONFIRMATION_REQUIRED`의 `error.data`로 `action_id`, `free_to_spend`, `after`, `shortage`, `impact`를 준다. 승인 조회에는 `needs_budget_reason`, `budget_impact`가 추가되며, 승인 요청은 기존 `pin` 외에 `reason`(초과 시 필수), `emergency`(기본 false)를 받는다.

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
| ✅ | GET | `/products/benefits` | 🔒 | 은행 혜택 카탈로그(`catalogue`)와 내가 저장한 100크레딧 구성(`saved`). 저장한 구성이 지금 카탈로그와 맞지 않으면 빈 구성 + `needs_review: true` ([ADR 0023](decisions/0023-card-protection-and-benefits.md)) |
| ✅ | PUT | `/products/benefits` | 🔒 | 혜택 구성 저장(`offer_ids`, 6개까지). **미리보기**이고 실제 결제 금액에는 적용 안 함. 실패: `400 UNKNOWN_BENEFIT`(카탈로그에 없는 혜택), `400 BENEFIT_CONSTRAINT`(100크레딧 초과 또는 같은 업종 둘) |

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
| ✅ | POST | `/accounts/{account_id}/close` | 🔒 | **입출금 계좌 해지**, 잔액 0일 때만 바로. 쓸 수 있는 연결 카드·안 낸 카드 대금이 있으면 막음 ([ADR 0012](decisions/0012-account-close.md)). 실패: `400 ACCOUNT_CANNOT_CLOSE`(예·적금), `409 ACCOUNT_NOT_ACTIVE`, `409 BALANCE_REMAINING`, `409 LINKED_CARD_EXISTS`, `409 CARD_UNPAID` |
| 📝 | | 이체 한도 변경 | 🔒 | 한도를 올리는 것은 보안을 약하게 해서 승인 PR에서 |

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
    { "account_id": 1, "account_type": "CHECKING", "account_num": "110-101-000001", "product_name": "캡아메리카 입출금통장", "nickname": "생활비", "balance": 2350000, "status": "ACTIVE", "opened_at": "..." }
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
| ✅ | GET | `/transfers/banks` | 🔒 | ClearingHub에 참가한 다른 은행 목록 |

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

타행 이체는 `POST /transfers`에 허브가 배정한 3자리 `to_bank`를 추가합니다. 서버가 수취인 이름을 조회해 PIN 승인 요약에 넣습니다. 승인 직후 `APPROVED`와 `result.clearing_status: PENDING`을 반환하며, `GET /approvals/{action_id}`에서 `COMPLETED` 또는 `FAILED`를 확인합니다. 타행 설정이 비어 있으면 `503 CLEARING_DISABLED`입니다.

| 메서드 | 허브 콜백 | 역할 |
|---|---|---|
| POST | `/interbank/inquiry` | 활성 입출금 계좌 수취인 확인 |
| POST | `/interbank/receive` | 검증된 타행 입금 한 번 기록 |
| GET | `/interbank/receive/{transfer_id}` | 이미 반영된 입금 확인 |

콜백은 [ClearingHub 규격](https://github.com/jjh7757/clearing-hub/blob/main/docs/SPEC.md)의 4절 Ed25519 서명과 JSON 응답을 사용합니다.

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
| ✅ | POST | `/cards/{card_id}/payments` | 🔒 | **가맹점 결제 흉내**(`merchant_name`, `amount`, `idempotency_key`). PIN 없이 바로 `201`. 체크는 결제 계좌에서 출금, 신용은 사용 기록(`UNBILLED`). 같은 요청 번호면 처음 결과 `200`. Agent 도구에 없음 ([ADR 0010](decisions/0010-card-payments.md)). 결제 보호를 켠 사용자는 `409 MERCHANT_CHANNEL_REQUIRED` (가맹점 경로 `POST /system/card-payments/{card_id}`만) |
| ✅ | GET | `/cards/{card_id}/transactions?payment_date=` | 🔒 | 사용내역 (최근 순). `payment_date`(한국 날짜)를 주면 그날 승인된 거래만 |
| ✅ | GET | `/cards/protection` | 🔒 | 내 결제 보호 설정: `location_check`, `active_from`·`active_until`(한국 시간 `HH:MM`). 위치 좌표는 돌려주지 않음 ([ADR 0023](decisions/0023-card-protection-and-benefits.md)) |
| ✅ | PUT | `/cards/protection` | 🔒 | 보호 설정 변경, **거래 PIN 필요**(`pin`). 활동 시작·종료는 둘 다 주거나 둘 다 비움, 같으면 `422`. 위치 확인을 끄면 저장한 위치를 지움. 실패: `400 INVALID_PIN`, `400 PIN_NOT_SET`, `423 PIN_LOCKED` |
| ✅ | PUT | `/cards/protection/location` | 🔒 | 스마트폰 위치 갱신(`latitude`, `longitude`, `accuracy_m`, `observed_at`). 최근 한 건만, 소수 둘째 자리로 반올림해 저장. 실패: `400 STALE_PHONE_LOCATION`(15분보다 오래됐거나 미래 시각), `409 LOCATION_CHECK_DISABLED`(위치 확인을 안 켬) |
| ✅ | PUT | `/cards/protection/activity` | 🔒 | 은행 화면 활동 시각을 서버 시간으로 기록(1분에 한 번까지). 활동시간을 정한 사용자만 저장 |
| ✅ | POST | `/cards/{card_id}/transactions/{card_tx_id}/cancel` | 🔒 | 전액 취소. 체크는 결제 계좌로 환불(`REFUND`), 신용은 기록만 취소. 정지·분실 카드도 됨 |
| ✅ | GET | `/cards/{card_id}/limits` | 🔒 | `daily_limit`·`daily_used`(오늘, 취소 제외), 신용은 `credit_limit`·`credit_used`(안 갚은 금액) |


- 기본 한도: 체크 1일 100만, 신용 1일 100만·신용 한도(안 갚은 금액) 300만. 카드 응답의 `monthly_limit`은 `credit_limit`으로 바뀜
- 발급·정지 실패: `400 ACCOUNT_NOT_FOUND`(결제 계좌가 내 입출금 계좌가 아님), `404 CARD_PRODUCT_NOT_FOUND`, `409 CARD_LOST`, `409 CARD_NOT_SUSPENDED`, `409 CARD_NUM_CONFLICT`(동시 발급, 다시 시도)
- 결제 실패: `409 CARD_NOT_ACTIVE`(정지·분실), `400 CARD_DAILY_LIMIT_EXCEEDED`, `400 CREDIT_LIMIT_EXCEEDED`, `400 INSUFFICIENT_BALANCE`, `400 ACCOUNT_NOT_FOUND`(결제 계좌를 쓸 수 없음), `409 IDEMPOTENCY_KEY_REUSED`
- 결제 실패(신용): `409 CARD_OVERDUE` (대금을 못 낸 사용분이 있음, [ADR 0011](decisions/0011-card-bills.md))
- 취소: 안 낸 것(`UNBILLED`·`BILLED`)은 기록만, 낸 것(체크카드, `PAID`)은 결제 계좌로 환불. 결제 계좌가 해지됐으면 **환불 대기**(`refund_pending: true`)로 두고 상담원이 다른 계좌로 보냄([ADR 0012](decisions/0012-account-close.md)). 실패: `404 CARD_TX_NOT_FOUND`, `409 CARD_TX_ALREADY_CANCELED`

## chat: AI 상담 (`domains/agent`)

자연어로 은행 업무를 합니다. 라우터가 계좌·카드·상품 담당을 고르고, 담당은 MCP 도구(아래 절)로 REST를 부릅니다. 결정 이유: [ADR 0015](decisions/0015-agent-chat.md), 코드 설명: [가이드 12](guides/12-agent.md)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | POST | `/chat` | 🔒 | `message`(1000자까지), `session_id`(UUID, 없으면 새 대화) → `session_id`, `reply`, `routed`(일한 담당). 이체 등은 승인 대기까지, PIN은 승인 화면에서 |
| ✅ | POST | `/chat/stream` | 🔒 | 같은 요청을 **SSE**로: `status`(진행 상태) → `token`(답 글자, `agent`로 담당 구분) → `done`(전체 답) / `error`. 처리 중인 대화방이면 스트림 대신 `409` ([ADR 0018](decisions/0018-chat-stream-router.md)) |
| ✅ | GET | `/chat/{session_id}` | 🔒 | 내 대화 기록(사람 말과 AI 답). 남의 대화방이면 빈 목록 |
| ✅ | POST | `/chat/transfer-check` | 🔒 | **송금 전 요청 점검** (읽기 전용). `/chat`과 같은 요청, 별도 대화방. 받은 문자·계좌를 내 최근 180일 송금 기록과 비교(`compare_previous_transfers`), 계좌번호는 끝 4자리만. `routed: ["transfer_check"]`. 이체 도구가 없고 Langfuse로 보내지 않음 |
| ✅ | POST | `/chat/benefits` | 🔒 | **혜택 상담** (읽기 전용). `mode`: `bundle`(최근 3개월 소비로 100크레딧 구성 추천) / `nearby`(식당 → 카페 → 돌아오는 코스). 응답에 AI 답과 함께 도구가 계산한 `recommendation` 또는 `plan` 원본 ([ADR 0023](decisions/0023-card-protection-and-benefits.md)) |

- 실패: `503 AI_DISABLED`(Gemini 키 없음), `503 AI_UNAVAILABLE`(LLM 실패·90초 초과), `409 CHAT_BUSY`(같은 대화방의 앞 메시지를 처리 중), `429 AI_RATE_LIMITED`(RAG와 같은 한도 1분 10, 채팅 한 번은 3으로 셈)
- Agent가 만든 승인 대기는 `requested_by = AGENT`
- `/chat/benefits` 요청: `demo`(예시 데이터), `nearby`는 `budget_won`(1,000~500,000)·`available_minutes`(1~240) 필수. 실제 검색(`demo: false`)은 `location`과 식사·카페 예상 가격(`meal_price_won`, `cafe_price_won`)도 필수, 위치는 실제 `nearby`에서만 받음(아니면 `422`). `allow_channel_coupon`(채널 추가가 필요한 쿠폰 포함), `preview_bundle`(저장한 혜택 구성으로 할인 미리보기). AI가 정한 예산·시간은 요청 값을 넘지 못함
- `/chat/benefits` 실패: 위 공통 실패 + `503 PLACE_SEARCH_DISABLED`(`KAKAO_LOCAL_API_KEY` 없음, 시연 모드는 됨), `503 PLACE_SEARCH_UNAVAILABLE`(카카오 응답 실패), `503 COUPONS_UNAVAILABLE`(쿠폰 파일 오류)

```json
{ "success": true, "data": { "session_id": "6f1c…", "reply": "피터님 계좌로 50,000원 이체를 요청했어요. 은행 앱 승인 화면에서 PIN을 입력해 주세요.", "routed": ["account"] } }
```

스트리밍 예 (`POST /chat/stream`, "카드 한도랑 내 잔액 알려줘"):

```text
event: status
data: {"stage": "routing", "label": "담당을 고르고 있어요"}

event: status
data: {"stage": "routed", "agents": ["card", "account"], "label": "카드 → 계좌 순서로 확인할게요"}

event: status
data: {"stage": "agent", "agent": "card", "label": "카드 담당이 확인하고 있어요"}

event: status
data: {"stage": "tool", "agent": "card", "tool": "get_card_limit", "label": "카드 한도를 조회하고 있어요"}

event: token
data: {"agent": "card", "text": "일일 한도는 1,000,000원입니다."}

event: token
data: {"agent": "account", "text": "\n\n보유하신 계좌의 잔액 안내입니다."}

event: done
data: {"session_id": "…", "reply": "일일 한도는 1,000,000원입니다.\n\n보유하신 계좌의 잔액 안내입니다.", "routed": ["card", "account"]}
```

- 도구 호출 전의 “확인해 볼게요” 같은 서문은 `token`으로 나갈 수 있고 `done.reply`에서는 빠진다. 화면은 `token`을 미리보기로 표시하고, `done`을 받으면 표시한 텍스트를 `done.reply`로 바꿔 끼운다.
- 인사처럼 라우터가 혼자 답하면 `token` 없이 `done.reply`로만 답이 온다.

## mcp: AI 도구 (`domains/mcp_server`)

MCP(Model Context Protocol) 서버. 도구 18개가 아래 REST API를 사용자 토큰으로 부릅니다. 결정 이유: [ADR 0014](decisions/0014-mcp-server.md), 코드 설명: [가이드 11](guides/11-mcp.md)

| 상태 | 입구 | 인증 | 설명 |
|---|---|---|---|
| ✅ | `POST /mcp` (streamable HTTP, JSON 응답) | `Authorization: Bearer <access token>` | 우리 Agent용. 헤더의 토큰을 그대로 REST에 넘김 |
| ✅ | `python -m avengers_bank.domains.mcp_server` (stdio) | refresh token 파일 (`login` 명령) | Claude Desktop·Claude Code용 |

- 도구: 계좌 `get_my_accounts` `get_account` `search_transactions` `request_transfer` `open_account` `request_deposit` `close_account` / 카드 `get_my_cards` `issue_card` `search_card_transactions` `get_card_limit` `suspend_card` `request_unsuspend_card` / 상품 `search_products` `get_product_detail` `ask_bank_docs` / 예산(읽기만) `get_budget`(`GET /budget`) `check_budget`(`GET /budget/check`, `amount`>0·`category` 선택)
- 없는 것: 승인·PIN, 카드 결제, `/system/*`, 대출, 예산 신청·변경·해제(`POST`·`PATCH`·`DELETE /budget`: 신청은 사용자가 표를 보고 확정, 약하게 바꾸기·해제는 PIN이라 예산 화면에서 사람이)
- 실패하면 REST의 오류를 `코드: 메시지`로 돌려줍니다(예: `CARD_NOT_FOUND: 카드를 찾을 수 없습니다.`).

### 요청한 곳 (`X-Requested-By`)

승인 대기를 만드는 API(`POST /transfers`, `POST /accounts/deposits`, `POST /cards/{id}/unsuspend`)는 `X-Requested-By: WEB | AGENT | MCP` 헤더를 받아 `requested_by`에 남깁니다(없으면 `WEB`). `SYSTEM`은 헤더로 보낼 수 없고, 가맹점 결제가 보호 규칙에 걸렸을 때 서버가 직접 씁니다. 승인 화면이 "AI가 만든 요청"이라고 보여 주는 **정보용**이고, 보안은 PIN 승인이 맡습니다.

## rag: 상품·약관 질문 (`domains/rag`)

상품 DB와 데모 약관을 근거로 답합니다. Gemini 키(`GEMINI_API_KEY`)가 없으면 `503 AI_DISABLED`, Gemini가 실패하면(한도 초과·시간 초과 등) `503 AI_UNAVAILABLE`, 답이 형식에 안 맞으면 `503 AI_BAD_RESPONSE`. 사용자당 1분에 10번(검색·답변 합쳐), 넘으면 `429 AI_RATE_LIMITED`. 결정 이유: [ADR 0013](decisions/0013-agent-rag-plan.md), 코드 설명: [가이드 10](guides/10-rag.md)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/rag/search?q=&k=5` | 🔒 | 근거 검색 (벡터 + Kiwi BM25, RRF). `chunk_id`, `title`, `content`, `score` |
| ✅ | POST | `/rag/ask` | 🔒 | `question`(500자까지) → `action`(`answer`·`clarify`·`abstain`), `answer`, `citations`(검색된 근거 안에서만) |

```json
{ "success": true, "data": { "action": "answer", "answer": "결제일에 잔액이 모자라면 출금하지 않고 연체로 남고, 그동안 그 신용카드로 결제할 수 없습니다.",
  "citations": [ { "chunk_id": "card-terms#8", "title": "캡아메리카뱅크 카드 이용약관 > 제8조(연체)" } ] } }
```

## system: 시스템 작업 (`domains/cards`, `domains/rag`의 `system_router`)

사용자 토큰이 아니라 **서버 키**(`X-System-Key` 헤더 = `.env`의 `SYSTEM_API_KEY`)로만 부릅니다. 키를 설정하지 않으면 `403 SYSTEM_API_DISABLED`, 틀리면 `403 SYSTEM_KEY_INVALID`. 결정 이유: [ADR 0011](decisions/0011-card-bills.md)

| 상태 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| ✅ | POST | `/system/card-payments/{card_id}` | 🔑 | **가맹점 결제 시뮬레이터**: `/cards/{id}/payments`의 본문 + `channel`(`IN_PERSON`·`ONLINE`), 오프라인만 `terminal_location`. 보호 규칙을 통과하면 `201` 결제, 걸리면 **`202` 승인 대기**(`CARD_PAYMENT`, `requested_by = SYSTEM`, 아직 결제 안 함). 같은 요청 번호로 재전송: 대기 중이면 같은 대기 `202`, 결제됐으면 `200`. 실패: `404 CARD_NOT_FOUND`, `409 CARD_PAYMENT_NOT_APPROVABLE`(거절·만료·실패한 대기), `409 IDEMPOTENCY_KEY_REUSED` + 결제 실패 코드 ([ADR 0023](decisions/0023-card-protection-and-benefits.md)) |
| ✅ | GET | `/system/card-refunds` | 🔑 | 상담원용: 환불 대기 목록 (결제 계좌를 쓸 수 없어 못 돌려준 결제 취소). 카드 주인 `user_id`, 원래 결제 계좌 `linked_account_id` 포함 |
| ✅ | POST | `/system/card-refunds/{card_tx_id}` | 🔑 | 상담원용: 고객 확인 후 `to_account_id`(카드 주인의 입출금 계좌)로 환불. 실패: `400 ACCOUNT_NOT_FOUND`, `404 CARD_TX_NOT_FOUND`, `409 REFUND_NOT_PENDING` |
| ✅ | POST | `/system/rag/reindex` | 🔑 | RAG 색인 갱신: 데모 약관과 판매 중인 상품(특판 기간 포함)을 다시 자르고, 본문 해시나 임베딩 모델·차원·입력 형식이 바뀐 청크만 임베딩. 상품을 바꾸거나 특판이 끝나면 부른다(매일 부르면 됨). 동시에 두 번 오면 차례로 처리. `total`, `embedded`, `deleted` |
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
