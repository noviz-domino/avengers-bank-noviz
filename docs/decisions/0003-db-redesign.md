# 0003. DB 재설계: 계좌·거래·카드 통합과 승인 대기 중심 구조

- 상태: 채택 (핵심 6개 테이블 구현: 마이그레이션 `c3d9e1a47b20`)
- 날짜: 2026-11-04
- 관련 PR: #4
- 새 ERD: [docs/ERD.md](../ERD.md)

## 결정

1. **계좌는 `accounts` 한 테이블**에 `account_type`(입출금·예금·적금)으로 구분한다. 예·적금에만 있는 조건(확정 금리, 만기일, 월 납입금)은 1:1 테이블 `account_terms`로 뺀다.
2. **거래는 `account_transactions` 하나의 장부**에 쌓는다. 금액은 부호로 방향을 나타내고(+ 들어옴, − 나감), 거래 후 잔액·상대방·메모·카테고리·거래 종류를 모두 둔다. 이체 두 줄은 `transfer_id`로 묶는다.
3. **카드는 `cards` + `card_transactions`** 두 테이블로 체크·신용을 함께 담는다. 누적 사용액은 저장하지 않고 계산한다.
4. **사람(또는 Agent)이 시작한 출금·이체·대출 실행·예산 초과 결제는 `pending_actions`를 거친다.** 사람이 승인해야 실행된다. 예산 안 결제, 시스템 입금, 카드 정지는 바로 실행한다(목록: [ERD](../ERD.md) "승인이 필요한 것과 바로 실행하는 것", ADR 0004).
5. **ERD에는 지금 구현하는 테이블만 그린다.** 첫 구현은 6개(`users`, `account_products`, `accounts`, `account_terms`, `account_transactions`, `pending_actions`)이고, 나머지는 ERD의 "예정" 표에 두었다가 그 기능의 PR에서 추가한다. 최종 25개(핵심 6 + 예정 19, 2차인 `passkeys`와 나중인 `notifications` 포함).
6. **다른 테이블이 이미 하는 일은 테이블로 만들지 않는다** (아래 "만들지 않는 테이블").

## 배경

- 이 프로젝트의 목표는 **은행 웹 + 은행 웹에서 하는 모든 일을 Agent로 할 수 있는 슈퍼앱**이다 ([scope.md](../planning/scope.md)).
- Agent는 화면마다 API를 따로 쓰는 게 아니라 **도구 몇 개로 모든 기능을 다룬다.** 그래서 DB가 일관된 모양이어야 도구가 단순해진다.
- 팀 뼈대 ERD는 계좌 3개, 거래내역 3개, 카드 2개, 카드 사용내역 2개로 나뉘어 있고, 컬럼 이름도 테이블마다 다르다(`change_amount`, `deposit_amount`, `used_amount`).
- 거래내역에 잔액·메모·카테고리·상대방 이름이 없어서 기획의 검색·지출 통계·예산 관리를 만들 수 없었다.
- **지금이 바꾸기 가장 싼 시점**이다. users 말고는 구현된 기능과 데이터가 없다.

## 검토한 대안

### 계좌 테이블

| 대안 | 장점 | 단점 | 결과 |
|---|---|---|---|
| 종류별 3개 테이블 (팀 원안) | 종류마다 컬럼이 딱 맞음 | 조회·이체·거래내역·분석을 3벌씩. 계좌번호 찾기 3번. Agent 도구가 종류마다 갈라짐 | 버림 |
| 한 테이블에 모든 컬럼 (NULL 많음) | 조인 없음 | 예·적금 전용 칸이 입출금 행에서 모두 NULL. 규칙이 CHECK로 복잡해짐 | 버림 |
| **한 테이블 + 예·적금 조건만 1:1 테이블** | 공통 기능은 한 곳. 다른 부분만 분리 | 예·적금 상세를 볼 때 조인 1번 | **채택** |

이체 한도는 입출금 계좌에만 있지만 칸이 둘뿐이라 `accounts`에 두고, CHECK로 "입출금이면 NOT NULL, 아니면 NULL"을 강제한다.

### 거래내역

| 대안 | 결과 |
|---|---|
| 계좌 종류별 거래내역 3개 (팀 원안) | 위와 같은 이유로 버림 |
| 이체를 별도 `transfers` 테이블 + 장부 | 이체 정보가 두 곳에 나뉨. 장부 두 줄을 `transfer_id`로 묶으면 충분해서 버림 |
| **하나의 장부, 부호 있는 금액, `transfer_id`** | **채택**. "지난달 지출"이 쿼리 하나 |

### 카드 누적 사용액

| 대안 | 결과 |
|---|---|
| `accumulated_amount`를 저장하고 결제마다 증가 (팀 원안) | 결제 취소·환불 때 같이 고쳐야 하고 어긋나기 쉬움. 버림 |
| **사용내역 합계로 계산** | **채택**. 한도 검사 때 이번 달 합계를 구함. 데이터가 커지면 그때 캐시 |

### 대출 상품

| 대안 | 결과 |
|---|---|
| `loan_products` 별도 테이블 | 금리·기간·금액·조건 칸이 계좌 상품과 같아서 중복 |
| **`account_products`에 `type = LOAN`** | **채택**. 대출 전용 칸은 `income_multiplier` 하나 |

대출 자체(`loans`)는 계좌가 아니라 별도 테이블이다. 잔액이 음수인 계좌로 다루면 "잔액 0 이상" 규칙이 깨지기 때문이다. 대출번호는 ADR 0001에서 예약한 종류 코드 `4`를 쓴다.

### 승인 대기를 어디에 저장하나

| 대안 | 결과 |
|---|---|
| LangGraph 메모리(체크포인터)에만 (이전 포트폴리오 방식) | 서버가 재시작되면 사라지고, 웹·MCP 등 다른 입구와 공유되지 않음. 버림 |
| **DB의 `pending_actions`** | **채택**. 어느 입구에서 요청해도 같은 승인 화면, 같은 규칙. 실행 상태가 남아서 같은 승인이 두 번 실행되지 않음 |

### 만들지 않는 테이블

설계 초안(약 30개)을 검토하면서 뺐다. 포트폴리오 기준으로 **핵심(돈 처리·승인·Agent 안전장치·예산)은 단단하게, 세세한 것은 줄인다.**

| 테이블 | 결과 | 이유 |
|---|---|---|
| `idempotency_keys` | 뺌 | 승인이 필요한 돈 이동은 `pending_actions`를 거치고, 거기 `(user_id, idempotency_key)` unique가 같은 일을 함. 바로 실행하는 카드 결제는 카드 기능 PR에서 `card_transactions`에 같은 방식으로 둔다 |
| `rag_documents` | 뺌 | 출처·제목은 `rag_chunks.metadata`로 충분 |
| `chat_sessions` | 뺌 | `chat_messages.session_id`로 대화 목록을 묶을 수 있고, 대화 맥락은 LangGraph가 저장 |
| `verification_codes` | 뺌 | 휴대폰 본인확인을 범위에서 뺌 (ADR 0005) |
| `account_rate_adjustments` | `account_terms.rate_detail`(JSON)로 합침 | 우대 내역은 가입 때 한 번 정해지는 스냅샷이고, 우대별 집계는 범위에 없음 |
| `passkeys`, `notifications` | 나중에 | 범위 안이지만 그 기능을 만들 때 추가 |

### 첫 구현을 6개로 시작하는 이유

| 대안 | 결과 |
|---|---|
| 설계한 테이블을 한 번에 다 만들기 | 코드에는 쓰지 않는 빈 테이블이 오래 남고, ERD와 코드가 어긋남 |
| **기능을 만들 때마다 그 PR에서 테이블 추가** | **채택**. 앞에서 정한 "코드와 문서는 같은 PR에서" 규칙과 맞음. 전체 방향은 이 ADR과 ERD "예정" 표가 잡아 줌 |

## 결과

**좋아지는 점**
- 조회·이체·거래내역·검색·분석이 **계좌 종류와 상관없이 한 번씩만** 구현된다.
- Agent 도구가 단순해진다: `get_my_accounts`, `search_transactions` 하나로 모든 계좌를 다룬다.
- 예산 관리의 "돈의 종류"를 장부의 `tx_type`으로 바로 구분할 수 있다.
- 승인이 필요한 돈 이동은 `pending_actions`를 거치고 장부 줄에 `action_id`가 남아서, 승인·실행·실패를 따라갈 수 있다.

**감수할 점**
- **팀 뼈대 ERD와 크게 달라진다.** 매일 아침 공유 때 이 문서로 차이를 설명한다(아래 "팀 뼈대와의 차이").
- 테이블은 첫 구현 6개에서 시작해 최종 25개가 된다(팀 뼈대 13개). 한 번에 다 만들지 않고 **구현 순서대로 마이그레이션을 나눠** 추가한다.
- 예·적금 상세를 볼 때 `account_terms` 조인이 필요하다.
- `rag_chunks`(pgvector)는 SQLite 테스트에서 만들 수 없다. PostgreSQL CI 검사로 확인한다.

**ADR 0001과의 관계**
- 계좌 테이블이 하나가 되어 "테이블 사이 계좌번호 중복" 문제는 사라진다.
- 하지만 **종류 코드가 든 번호 형식은 유지**한다. 사람이 읽기 좋고, Agent가 번호만 보고 종류를 안다.
- 계좌별 CHECK 3개는 `accounts` 하나의 CHECK로 바뀐다: `(account_type = 'CHECKING' AND account_num LIKE '110-1__-______') OR …`
- ADR 0001의 상태는 "일부 변경 (→ 0003)"으로 바꾼다.

**마이그레이션 방법**
- 아직 데이터가 없는 테이블(계좌·거래·카드)은 **새 마이그레이션에서 지우고 새로 만든다.** 기존 마이그레이션 파일은 고치지 않는다.
- PK는 지금처럼 `int`로 둔다. 타입 변경 마이그레이션이 필요 없고 SQLite 테스트에서도 자동 증가한다.
- `users`에는 컬럼을 추가한다(기존 회원가입 기능 유지). 기존 행이 있는 DB에서도 실패하지 않게 `birth_date`는 NULL 허용, `marketing_agreed`는 `server_default=false`, 실패 횟수는 `server_default=0`으로 넣는다. 회원가입 API에 생년월일·마케팅 동의 입력이 생긴다.
- `account_products`: `interest_rate` → `base_rate`로 바꾸고 우대 상한·기간·금액·나이·특판 칸을 추가한다. `product_code`(ADR 0001)는 그대로.
- `card_products`와 카드 테이블은 **첫 구현 마이그레이션에서 지운다.** 같은 PR에서 `domains/cards/models.py`의 옛 모델, `alembic/env.py`·`tests/conftest.py`의 import, 서비스 주석의 옛 모델 이름도 지운다(남기면 autogenerate가 다시 만든다). 카드 기능 PR에서 새 구조로 다시 만든다.
- `tests/test_account_number.py`의 `test_migration_checks_match_models`는 지금 b46530c30681을 직접 읽는다. 새 CHECK를 넣는 마이그레이션으로 바꾼다.
- 구현 순서대로 나눈다: ① 핵심 6개(회원 확장과 로그인·PIN 잠금 컬럼, 상품, 계좌, 장부, 승인 대기) → ② 보안 보강(`refresh_tokens`, `audit_logs`) → ③ 카드 → ④ 대출 → ⑤ 예산 → ⑥ Agent·RAG. [scope.md](../planning/scope.md) "구현 순서"와 같다.

**함께 바뀌는 문서 (구현 PR에서)**
- `docs/API_ENDPOINTS.md`: `/accounts/{type}/{id}` → `/accounts/{id}`처럼 종류별 경로가 하나로 합쳐짐. 회원가입 요청에 생년월일·마케팅 동의 추가
- `docs/PROJECT_STRUCTURE.md`: `domains/` 아래에 `loans`, `budget`, `agent`, `auth` 등 추가

**팀 뼈대와의 차이**

| 팀 뼈대 | 이 레포 |
|---|---|
| `checking_accounts`, `deposit_accounts`, `savings_accounts` | `accounts` + `account_terms` |
| `*_account_histories` 3개 | `account_transactions` 하나 |
| `credit_cards`, `debit_cards` | `cards` |
| `*_card_histories` 2개 | `card_transactions` |
| `accumulated_amount` | 계산으로 대체 |
| (없음) | 승인 대기(첫 구현), 이후 대출, 예산, 감사 기록, 대화, RAG, refresh token 테이블 (ERD "예정") |
