# 3. 상품·계좌

> **계좌는 종류와 상관없이 `accounts` 테이블 하나에 있고, 예·적금에만 있는 조건(금리·만기)은 `account_terms`로 뺐다. 가입 조건과 적용 금리는 코드가 계산하고, 계좌번호 규칙과 잔액 규칙은 DB가 CHECK로 막는다.**

결정 원문: [ADR 0001 계좌번호](../decisions/0001-account-number-format.md), [ADR 0003 DB 재설계](../decisions/0003-db-redesign.md), [ADR 0008 계좌 개설 정책](../decisions/0008-account-opening-policy.md)

## 코드 위치

| 기능 | API | 코드 |
|---|---|---|
| 판매 중인 상품 목록·상세 | `GET /products/accounts`, `/{id}` | `products/service.py`, `products/repository.py` `on_sale` |
| 가입 조건·적용 금리 | (개설할 때) | `products/eligibility.py` |
| 계좌 개설 (입출금·적금) | `POST /accounts` | `accounts/service.py` `open_account` → `create_account` |
| 예금 개설 (승인 필요) | `POST /accounts/deposits` | `accounts/service.py` `request_deposit`, 승인 뒤 `run_open_deposit` |
| 메인 화면 (총자산 + 잔액 많은 순) | `GET /accounts` | `accounts/service.py` `list_my_accounts` |
| 상세·거래내역·별칭 | `GET /accounts/{id}`, `/transactions`, `PATCH` | `accounts/service.py` |
| 계좌번호 | — | `accounts/account_number.py` |
| 데모 데이터 | `python -m avengers_bank.seed` | `seed.py` |

## 왜 계좌 테이블이 하나인가

팀 뼈대는 입출금·예금·적금이 테이블 3개, 거래내역도 3개였습니다. 그러면 "내 계좌 전체", "계좌번호로 찾기", "지난달 지출"이 모두 3번씩 조회해야 하고, Agent 도구도 종류마다 갈라집니다.

```
accounts (모든 계좌)                 account_terms (예·적금만, 1:1)
├ account_type  CHECKING/DEPOSIT/SAVINGS ├ applied_rate  가입 때 확정 금리
├ account_num   110-TPP-NNNNNN          ├ rate_detail   적용된 우대 내역
├ balance       0 이상 (CHECK)          ├ maturity_date 만기일
└ 이체 한도     입출금만 (CHECK)         └ monthly_payment, payment_day (적금)
```

종류마다 다른 칸 때문에 생기는 실수는 DB가 막습니다:
- 입출금 계좌는 이체 한도가 **반드시 있고**, 예·적금은 **반드시 없음**
- 계좌번호의 종류 코드(110-**1**01-…)가 `account_type`과 맞아야 함
- 잔액, 거래 후 잔액은 0 이상

## 계좌 개설 흐름

```
POST /accounts {product_id, term_months, monthly_payment}
  ① 판매 중인 상품인가 (is_active + 특판 기간, 한국 날짜)        → 404 PRODUCT_NOT_FOUND
  ② 예금이면 거절 → POST /accounts/deposits로 (맡길 돈이 움직여서 승인 필요)  → 400 DEPOSIT_NEEDS_TRANSFER
  ③ 가입 조건: 나이(만 나이), 기간, 금액                          → 400 AGE_NOT_ELIGIBLE …
  ④ 계좌번호: 같은 상품 안에서 가장 큰 번호 + 1                   → 동시에 겹치면 409
  ⑤ 적금이면 적용 금리 계산해서 account_terms에 스냅샷
```

### 예금은 왜 따로인가

입출금·적금은 열 때 돈이 움직이지 않아서 바로 엽니다. 예금은 **맡길 돈을 입출금 계좌에서 옮겨야** 해서, 이체와 똑같이 승인 대기 → PIN → 실행으로 엽니다([4. 돈이 움직이는 흐름](04-money-flow.md)). 계좌를 만드는 부분(`create_account`)은 두 경로가 같은 함수를 씁니다.

### 적용 금리

```
적용 금리 = 기본금리 + min(충족한 우대 합계, 우대 상한)
예) 스타크 자유적금: 3.50 + 마케팅 동의 0.20 + 첫 예·적금 0.30 = 4.00
```
- **급여이체 우대는 넣지 않습니다.** 가입하는 순간에는 급여를 받을지 알 수 없어서입니다.
- 상한에 걸리면 `rate_detail`에 깎인 만큼(`PREFERENTIAL_CAP: -0.20`)을 남겨서, **기본금리 + 기록 합계 = 적용 금리**가 항상 맞습니다. 나중에 "왜 이 금리냐"를 기록만으로 설명할 수 있습니다.

## 남의 계좌는 404

```python
if found is None or found[0].user_id != user_id:
    raise not_found()   # 403이 아니라 404
```
403("있지만 당신 것이 아님")을 주면 계좌 id를 바꿔 가며 다른 사람 계좌가 있는지 알아낼 수 있습니다. 없는 계좌와 같은 응답을 줘서 그것도 막습니다.

## 면접 예상 질문

**Q. 계좌를 한 테이블에 합치면 NULL 칸이 많아지지 않나요?**
A. 그래서 다른 칸이 많은 예·적금 조건은 1:1 테이블로 뺐습니다. `accounts`에 남은 종류별 칸은 이체 한도 2개뿐이고, "입출금이면 있음, 아니면 없음"을 CHECK로 강제합니다. 공통 기능(조회·이체·장부)은 한 곳에서, 다른 부분만 분리하는 방식입니다.

**Q. 금리를 왜 계좌에 저장하나요? 상품에서 읽으면 되잖아요.**
A. 상품 금리는 나중에 바뀌지만, 이미 가입한 계좌는 가입 당시 금리로 계약된 것입니다. 그래서 가입할 때 확정한 금리와 어떤 우대가 적용됐는지를 스냅샷으로 남깁니다.

**Q. 특판 기간을 어떻게 판단하나요?**
A. 판매 중 조건(`is_active` + 기간)을 한 함수에 두고 목록·상세·개설이 같이 씁니다. 날짜는 서버 시간대(컨테이너는 UTC)가 아니라 **한국 날짜**로 판단합니다. UTC로 보면 한국 시간 0~9시에는 하루가 어긋나서 끝난 특판에 가입할 수 있었습니다(PR #7 리뷰).

**Q. 예금 승인 때 잔액이 부족하면 빈 예금 계좌가 남지 않나요?**
A. 그걸 막으려고 순서를 정했습니다. 실행기는 **출금 계좌를 먼저 잠그고 잔액을 확인한 뒤에** 예금 계좌를 만듭니다. 계좌를 먼저 만들고 이체가 실패하면, 승인 대기는 `FAILED`로 커밋되면서 같은 트랜잭션의 빈 계좌도 함께 커밋되기 때문입니다. 잠근 동안은 잔액이 바뀌지 않아서 뒤의 이체는 통과합니다. `test_failed_approval_leaves_no_empty_account`가 확인하고, 순서를 바꾸면 이 테스트가 실패합니다.

**Q. 계좌번호 일련번호를 어떻게 만드나요? 동시에 만들면요?**
A. 같은 상품 접두어 안에서 가장 큰 번호 + 1입니다. 동시에 열어 번호가 겹치면 DB의 unique 제약이 막고 409로 다시 시도하게 합니다. 자주 겹치면 DB 시퀀스로 바꾸면 되고, 코드에 그 한계를 주석으로 남겼습니다(ADR 0008).
