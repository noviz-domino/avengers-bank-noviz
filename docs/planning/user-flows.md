# 주요 이용 흐름

FigJam "주요 이용 흐름 (초안)"을 옮겼습니다. 마름모는 판단, **빨간 상자는 실패 상황**입니다. 실패 상황은 README의 "직접 선정한 실패 상황의 동작 확인"에 그대로 씁니다.

> 흐름 안의 테이블 이름(`users`, `accounts`, `transactions` 등)은 FigJam DB 초안 기준입니다. 현재 ERD와의 대응은 [맨 아래 표](#테이블-이름-대응)를 보세요.

## ① 회원가입 · 로그인

```mermaid
flowchart LR
    A([시작]) --> B["회원가입 정보 입력<br/>(아이디·비밀번호·이름·휴대폰)"]
    B --> C{아이디 중복 아님?}
    C -- 예 --> D["가입 완료<br/>(users 저장)"]
    C -- 아니오 --> CF["중복 안내 후<br/>다시 입력"]:::fail
    D --> E[로그인 입력]
    E --> F{"아이디·비밀번호<br/>일치?"}
    F -- 예 --> G([메인 화면])
    F -- 아니오 --> FF["실패 안내<br/>(5회 실패 시 잠금)"]:::fail
    classDef fail fill:#FFCDC2,stroke:#FF7556,color:#1E1E1E
```

## ② 상품 조회 · 계좌 개설

```mermaid
flowchart LR
    A([로그인 상태]) --> B["예·적금 상품 목록<br/>(금리·기간·조건)"]
    B --> C[상품 선택·비교]
    C --> D{가입 조건 충족?}
    D -- 예 --> E["금액·기간·<br/>출금 계좌 입력"]
    D -- 아니오 --> DF["가입 불가<br/>사유 안내"]:::fail
    E --> F{"출금 계좌<br/>잔액 충분?"}
    F -- 예 --> G["계좌 생성 + 출금 기록<br/>(accounts, transactions)"]
    F -- 아니오 --> FF[잔액 부족 안내]:::fail
    G --> H([개설 완료])
    classDef fail fill:#FFCDC2,stroke:#FF7556,color:#1E1E1E
```

## ③ 계좌 이체

```mermaid
flowchart LR
    A([출금 계좌 선택]) --> B["받는 계좌·금액 입력<br/>(최근 보낸 사람 선택)"]
    B --> C{받는 계좌 존재?}
    C -- 예 --> D{이체 한도 이내?}
    C -- 아니오 --> CF[계좌 없음 안내]:::fail
    D -- 예 --> E{잔액 충분?}
    D -- 아니오 --> DF[한도 초과 안내]:::fail
    E -- 예 --> F["이체 확인<br/>(비밀번호 재확인)"]
    E -- 아니오 --> EF[잔액 부족 안내]:::fail
    F --> G["잔액 반영 + 거래내역 2건<br/>(보낸 쪽·받는 쪽)"]
    G --> H([이체 완료 + 알림])
    classDef fail fill:#FFCDC2,stroke:#FF7556,color:#1E1E1E
```

## ④ 카드 결제

```mermaid
flowchart LR
    A([카드 결제 요청]) --> B{카드 정상 상태?}
    B -- 예 --> C{이용 한도 이내?}
    B -- 아니오 --> BF["정지·분실 카드<br/>거절"]:::fail
    C -- 예 --> D{"연결 계좌<br/>잔액 충분?"}
    C -- 아니오 --> CF[한도 초과 거절]:::fail
    D -- 예 --> E["결제 승인<br/>(card_payments, 잔액 차감)"]
    D -- 아니오 --> DF[잔액 부족 거절]:::fail
    E --> F([결제 알림])
    classDef fail fill:#FFCDC2,stroke:#FF7556,color:#1E1E1E
```

## ⑤ 대출 신청 · 실행

```mermaid
flowchart LR
    A([대출 상품 조회]) --> B["한도 조회<br/>(소득·신용점수)"]
    B --> C["대출 신청<br/>(금액·기간·상환 방식)"]
    C --> D{심사 통과?}
    D -- 예 --> E["대출 실행<br/>(계좌로 입금)"]
    D -- 아니오 --> DF[거절 사유 안내]:::fail
    E --> F["상환 일정 생성<br/>(loan_schedules)"]
    F --> G([정기 상환])
    classDef fail fill:#FFCDC2,stroke:#FF7556,color:#1E1E1E
```

## ⑥ 자연어 요청 (AI · RAG)

```mermaid
flowchart LR
    A(["자연어 입력<br/>#quot;엄마한테 5만원 보내줘#quot;"]) --> B["의도 분류<br/>(이체·조회·상품 질문 등)"]
    B --> C{"필요한 정보<br/>충분?"}
    C -- 예 --> D{"상품·약관<br/>질문인가?"}
    C -- 아니오 --> CF["추가 질문<br/>#quot;어느 계좌에서 보낼까요?#quot;"]:::ask
    D -- 예 --> E["RAG 검색 후 답변<br/>(약관·FAQ·상품 설명)"]
    D -- 아니오 --> DN["기능 실행 또는<br/>화면 링크 제공"]
    E --> F(["대화 기록 저장<br/>(맥락 유지)"])
    DN --> F
    classDef ask fill:#FFECBD,stroke:#FFC943,color:#1E1E1E
```

"추가 질문"은 실패가 아니라 되묻기라서 노란색입니다. 사용자가 답하면 다시 의도 분류부터 판단합니다.

## 실패 상황 모음

README의 "실패 상황 동작 확인"에 쓸 후보입니다. 구현하면서 실제 응답(`error.code`)을 채웁니다.

| 흐름 | 실패 상황 | 예상 응답 |
|---|---|---|
| ① | 이미 있는 아이디로 가입 | `409 LOGIN_ID_ALREADY_EXISTS` ✅ 구현됨 |
| ① | 아이디·비밀번호 불일치 | `401 INVALID_CREDENTIALS` ✅ 구현됨 |
| ① | 5회 연속 실패 후 로그인 | 미정 |
| ② | 가입 조건 불충족 | 미정 |
| ② | 출금 계좌 잔액 부족 | `400 INSUFFICIENT_BALANCE` (예정) |
| ③ | 없는 계좌로 이체 | `404 ACCOUNT_NOT_FOUND` (예정) |
| ③ | 1회·1일 한도 초과 | `400 PER_TRANSFER_LIMIT_EXCEEDED`, `400 DAILY_LIMIT_EXCEEDED` (예정) |
| ③ | 남의 계좌에서 출금 | `403 ACCOUNT_FORBIDDEN` (예정) |
| ④ | 정지·분실 카드 결제 | 미정 |
| ④ | 카드 한도 초과, 연결 계좌 잔액 부족 | 미정 |
| ⑤ | 대출 심사 거절 | 미정 |
| ⑥ | 정보가 부족한 자연어 요청 | 추가 질문으로 응답 |

예정 코드는 `docs/API_ENDPOINTS.md`에 적힌 값입니다.

## 테이블 이름 대응

| 흐름에 적힌 이름 (FigJam 초안) | 현재 ERD (`docs/ERD.md`) |
|---|---|
| `users` | `users` |
| `accounts` | `checking_accounts`, `deposit_accounts`, `savings_accounts` |
| `transactions` | `checking_account_histories`, `deposit_account_histories`, `savings_account_histories` |
| `card_payments` | `credit_card_histories`, `debit_card_histories` |
| `loan_schedules` | 없음 (대출 테이블 미정) |
