# 5. 거래내역 검색과 카테고리

> **모든 계좌의 거래는 장부 하나(`account_transactions`)에 있어서, 검색은 쿼리 하나다. 기록할 때 규칙으로 카테고리를 붙이고, 사용자가 고칠 수 있다. 검색 결과에는 조건 전체의 합계가 같이 와서 "지난달 식비 얼마?"에 바로 답할 수 있다.**

결정 원문: [ADR 0003 장부 하나](../decisions/0003-db-redesign.md), [scope.md 5번](../planning/scope.md)

## 코드 위치

| 기능 | API | 코드 |
|---|---|---|
| 검색 (내 모든 계좌) | `GET /transactions?…` | `accounts/router.py` `tx_router`, `accounts/service.py` `search_transactions`, `accounts/repository.py` `_filtered` |
| 카테고리·메모 고치기 | `PATCH /transactions/{tx_id}` | `accounts/service.py` `update_transaction` |
| 카테고리 규칙 | (장부에 기록할 때) | `accounts/categories.py` `classify` |
| 한 계좌의 최근 거래 | `GET /accounts/{id}/transactions` | (3. 상품·계좌) |

## 검색 조건

| 조건 | 예 | 어떻게 |
|---|---|---|
| 계좌 | `account_id=1` | 없으면 내 모든 계좌. 남의 계좌면 404 |
| 기간 | `from_date=2026-11-01&to_date=2026-11-30` | **한국 날짜** 00:00을 UTC로 바꿔 비교 |
| 금액 | `min_amount=10000&max_amount=50000` | 부호와 상관없이 **크기**로 (`abs(amount)`) |
| 키워드 | `keyword=편의` | 메모·상대방 이름에 포함, 대소문자 무시. `%`·`_`는 글자 그대로 |
| 방향 | `direction=OUT` | 들어온 돈(`IN`, amount > 0) / 나간 돈(`OUT`) |
| 카테고리 | `category=식사` | 고정 목록 중 하나 (없는 값은 422) |
| 쪽 | `limit=20&before=123` | 최근부터. 다음 쪽은 응답의 `next_before` |

```json
{ "transactions": [ … ], "total_in": 8750000, "total_out": 650000, "next_before": 41 }
```
`total_in`·`total_out`은 **이번 쪽이 아니라 조건 전체**의 합계입니다.

## 내 거래만 보이게

```python
conds = [Account.user_id == user_id]          # 항상 들어가는 첫 조건
select(AccountTransaction).join(Account, ...).where(*conds)
```
장부에는 사용자 칸이 없어서 계좌와 이어서(join) "그 계좌의 주인이 나"인 거래만 봅니다. 남의 `account_id`를 넣으면 결과가 비는 대신 **404**를 줍니다(계좌 조회와 같은 정책, ADR 0008).

## 카테고리는 어떻게 정해지나

```
① 거래 종류만 보고 정해지는 것    INTERNAL_* → 저축·내 계좌, DEPOSIT·TRANSFER_IN → 수입 …
② 나가는 돈은 메모·상대방 이름의 낱말   "회식" → 외식·술자리, "점심" → 식사, "월세" → 주거·통신 …
③ 없으면                           TRANSFER_OUT → 이체, 그 밖 → 기타
```
- 규칙은 **위에서부터** 먼저 맞는 것입니다. "회식"이 "식사"보다 위인 이유는 budget.md의 "회식은 필수 생활비에 섞이지 않게" 때문입니다.
- 사용자가 `PATCH`로 고칠 수 있고, 금액·상대방은 못 고칩니다(장부는 돈의 기록이라).
- 지금은 코드의 고정 목록입니다. 예산 기능에서 카테고리마다 "필수인가"를 사용자가 정해야 해서, 그때 `categories` 테이블로 옮깁니다(shortcut 주석).

## 면접 예상 질문

**Q. 계좌 종류가 여러 개인데 검색이 어떻게 쿼리 하나인가요?**
A. 거래내역을 계좌 종류마다 나누지 않고 장부 하나에 부호 있는 금액으로 쌓았기 때문입니다(ADR 0003). 팀 뼈대처럼 테이블이 3개였다면 3번 조회해서 합쳐야 하고, 합계·정렬·쪽 나누기도 따로 해야 했습니다.

**Q. 합계를 왜 같이 주나요? 클라이언트가 더하면 되잖아요.**
A. 클라이언트는 이번 쪽(20개)만 받아서, 전체 합계를 알려면 모든 쪽을 다 받아야 합니다. 서버에서 같은 조건으로 `SUM`을 한 번 더 하면 "지난달 식비 얼마?" 같은 질문에 Agent가 숫자를 계산하지 않고 바로 답할 수 있습니다. "계산은 코드, 설명은 AI" 원칙과도 맞습니다.

**Q. 날짜 검색에서 시간대는 어떻게 처리했나요?**
A. 사용자가 말하는 "11월 1일"은 한국 날짜입니다. 서버(컨테이너)와 DB 저장은 UTC라서, 한국 날짜 00:00을 UTC로 바꿔서 비교합니다. 그대로 비교하면 한국 시간 0~9시 거래가 전날로 잡힙니다. `test_date_range_uses_korean_date`가 "어제 한국 시간 23:30" 거래로 확인합니다.

**Q. 키워드 검색에서 SQL 인젝션이나 와일드카드 문제는요?**
A. SQLAlchemy가 값을 바인딩해서 인젝션은 생기지 않고, `icontains(..., autoescape=True)`로 `%`·`_`를 글자 그대로 검색합니다. "100%"로 검색해도 모든 거래가 나오지 않습니다(`test_filters`).

**Q. 쪽 나누기를 왜 offset이 아니라 `before`(마지막 tx_id)로 하나요?**
A. offset은 앞에 새 거래가 생기면 같은 거래가 두 번 보이거나 빠집니다. "이 id보다 작은 것"으로 넘기면 새 거래가 생겨도 이어서 볼 수 있고, 뒤쪽 쪽에서도 느려지지 않습니다.
