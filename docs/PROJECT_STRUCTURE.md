# 프로젝트 구조

FastAPI + SQLAlchemy(async) + Alembic. 업무별로 **도메인 폴더**를 나누고, 각 도메인 안은 같은 5개 파일로 구성합니다.

## 전체 트리

```
avengers-bank/
├── .env.example            # 환경변수 예시 → .env로 복사해서 사용 (.env는 커밋 금지)
├── pyproject.toml          # 의존성 (uv)
├── uv.lock
├── alembic.ini
├── alembic/                # DB 마이그레이션
│   ├── env.py              # 모든 models.py를 import해서 테이블 정보를 모음
│   └── versions/           # 마이그레이션 파일이 쌓이는 곳
├── CLAUDE.md               # Claude Code 작업 규칙 (변경 시 문서화)
├── Dockerfile, compose.yaml # Docker 실행 (app + PostgreSQL)
├── .github/workflows/ci.yml # CI: PR과 main push마다 pytest + PostgreSQL 마이그레이션 검사
├── docs/                   # 문서 목차: docs/README.md
│   └── decisions/          # 설계 결정 기록(ADR): 왜 바꿨는지
├── tests/                  # pytest (SQLite로 실행, DB 서버 불필요)
│   ├── conftest.py
│   ├── test_users.py           # 회원가입, 로그인, 로그인 잠금
│   ├── test_products.py        # 상품 목록·상세, 특판 기간, seed
│   ├── test_refresh_tokens.py  # 토큰 교체, 재사용 감지, 만료, 기기별 로그아웃
│   ├── test_accounts.py        # 계좌 개설·가입 조건·적용 금리, 메인 화면 총자산, 남의 계좌 404, 거래내역
│   ├── test_account_close.py   # 계좌 해지 규칙(잔액·연결 카드·안 낸 대금), 해지 뒤 환불 대기와 상담원 환불
│   ├── test_agent.py           # 감독관·담당(가짜 LLM, 도구는 진짜 MCP→REST), 승인 대기 AGENT, 맥락·대화방 분리, 핑퐁 제한, 503
│   ├── test_mcp.py             # 도구 목록(승인·결제·system 없음), 승인 대기만, 남의 것은 오류, HTTP /mcp Bearer 전달, 토큰 파일 교체
│   ├── test_rag.py             # 청킹·RRF·평가 지표, 바뀐 것만 임베딩, 정답 세트 청크 존재, 인용 검사 (가짜 AI, Gemini 안 부름)
│   ├── test_transfers.py       # 이체 승인 흐름, 두 번 승인, 멱등키, PIN 잠금, 승인 전 잔액 변화, 한도
│   ├── test_deposits.py        # 예금 개설 승인, 실패 때 빈 계좌가 남지 않음, 특판 종료, 예금 추가 입금 불가
│   ├── test_transaction_search.py  # 검색 조건·합계·한국 날짜·쪽, 남의 거래 404, 카테고리 규칙·수정
│   ├── test_cards.py           # 카드번호·Luhn, 발급, 결제 계좌 규칙, 정지·분실·해제(PIN), 남의 카드 404
│   ├── test_card_payments.py   # 카드 결제·재전송·한도·취소 환불·신용 안 갚은 금액·남의 카드 404
│   ├── test_card_bills.py      # 신용 대금 출금·다시 불러도 한 번·결제일 당일분 제외·연체·청구 후 취소·서버 키
│   ├── test_account_number.py  # 계좌번호 규칙, CHECK 제약, 마이그레이션과 모델의 CHECK 일치
│   └── test_alembic_env.py     # 모든 models.py가 alembic/env.py에 import됐는지
└── src/avengers_bank/
    ├── main.py             # 앱 생성, CORS, 예외 핸들러, 라우터 등록
    ├── seed.py             # 데모 상품 데이터 (python -m avengers_bank.seed)
    ├── core/               # 모든 도메인이 같이 쓰는 공용 코드
    │   ├── config.py       # .env 읽기
    │   ├── database.py     # DB 연결, Base, get_db
    │   ├── security.py     # 비밀번호 해시, JWT
    │   ├── dependencies.py # get_current_user (로그인 사용자 확인)
    │   ├── exceptions.py   # BadRequest/Unauthorized/Forbidden/NotFound/Conflict
    │   ├── exception_handlers.py
    │   └── responses.py    # SuccessResponse, ErrorResponse 형식
    └── domains/
        ├── users/          # 회원가입, 로그인, 내 정보          ✅ 구현됨
        ├── products/       # 계좌·대출 상품 조회, 우대금리       ✅ 목록·상세, 가입 조건·적용 금리(eligibility.py)
        ├── accounts/       # 계좌·예적금 조건·장부              ✅ 개설·조회, 거래 검색, 카테고리(categories.py), 계좌번호 규칙, **돈 실행 지점(money.py)**
        ├── approvals/      # 승인 대기 작업, PIN 승인·거절        ✅
        ├── audit/          # 감사 기록(로그인·PIN 실패 등)         ✅ 기록만
        ├── transfers/      # 이체 요청 (테이블 없음)             ✅ 승인 대기 생성
        ├── cards/          # 카드 상품·카드·사용내역, 번호 규칙(card_number.py) ✅ 발급·정지·해제·결제·취소·대금 출금(/system)
        ├── agent/          # AI 상담: 감독관 + 계좌·카드·상품 Agent(graph.py), 채팅 API, 체크포인터 ✅
        ├── mcp_server/     # MCP 도구 16개(REST를 사용자 토큰으로), HTTP /mcp + 로컬 stdio(login, 토큰 파일) ✅
        └── rag/            # 상품·약관 RAG: 데모 약관(docs/*.md), 청킹, Gemini 연결(ai.py), 하이브리드 검색, 평가(golden.jsonl) ✅
```

## 도메인 안의 5개 파일

```
요청 → router → service → repository → DB
              (schemas, models는 옆에서 사용)
```

| 파일 | 역할 | 비유 |
|---|---|---|
| `router.py` | URL을 받아서 service를 호출하고 응답을 감쌈 | 창구 직원: 접수만 |
| `service.py` | 규칙 검사, 처리 순서, 트랜잭션 | 팀장: "잔액 충분해? 한도 넘었어?" |
| `repository.py` | DB 조회·저장만 | 금고 담당 |
| `models.py` | DB 테이블 정의 (SQLAlchemy) | 장부 양식 |
| `schemas.py` | 요청·응답 데이터 모양 (Pydantic) | 신청서 양식 |

`users` 도메인이 완성된 예시입니다. 새 기능은 이 도메인을 보고 같은 방식으로 작성합니다.

## 도메인끼리 의존하는 방향

```
users ◀── accounts ◀── transfers
  ▲          ▲
  └──────── cards        (체크카드 결제 → 연결 계좌 출금)
products ◀── accounts, cards   (개설·발급 시 상품 종류 검증)
users ◀── approvals ◀── transfers   (이체는 승인 대기를 만들고, 승인되면 실행)
```

- 다른 도메인의 데이터가 필요하면 **service에서 상대 도메인의 repository**를 호출합니다. 다른 도메인의 router는 호출하지 않습니다.
- 돈이 움직이는 처리(이체, 납입, 카드 결제)는 **실행 함수 하나**를 지나고, `async with db.begin():` 블록 하나 안에서 잔액 변경과 장부 기록을 모두 끝냅니다([ADR 0007](decisions/0007-money-execution-and-budget-guard.md)).

## ERD 테이블 → 코드 위치

| ERD 테이블 | 모델 클래스 | 파일 |
|---|---|---|
| `users`, `refresh_tokens` | `User`, `RefreshToken` | `domains/users/models.py` |
| `account_products`, `product_preferential_rates` | `AccountProduct`, `ProductPreferentialRate` | `domains/products/models.py` |
| `accounts`, `account_terms`, `account_transactions` | `Account`, `AccountTerms`, `AccountTransaction` | `domains/accounts/models.py` |
| `pending_actions` | `PendingAction` | `domains/approvals/models.py` |
| `audit_logs` | `AuditLog` | `domains/audit/models.py` |
| `card_products`, `cards`, `card_transactions` | `CardProduct`, `Card`, `CardTransaction` | `domains/cards/models.py` |

> 팀 뼈대의 계좌 3종·거래내역 3종·카드 5개 모델은 [ADR 0003](decisions/0003-db-redesign.md)에 따라 지웠습니다. CHECK 제약용 `in_sql()`은 `core/database.py`에 있고, 마이그레이션에는 결과 문자열을 그대로 적습니다.

## 역할 분담 예시

도메인 폴더 단위로 나누면 서로 같은 파일을 고칠 일이 적습니다.

| 담당 | 폴더 |
|---|---|
| A | `products`, `users`(PATCH 추가) |
| B | `accounts` |
| C | `transfers` (`accounts` repository 사용) |
| D | `cards` (`accounts` repository 사용) |

`core/`와 `main.py`는 공용이므로 수정하기 전에 팀에 공유합니다.
