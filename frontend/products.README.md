# 상품 목록·상세·가입

시안: `docs/design-drafts/15-products-option-1-selected.png`.

공통 앱이 `#products`, `#product/<product_id>`에서 `mountProducts(root, route)`를 호출합니다. 해시가 바뀌면 앱이 다시 마운트하며, 선택한 분류는 모듈 변수에 두어 목록·상세를 오가도 유지합니다(새로고침하면 초기화). 스타일은 `products.css`(`.products-app` 범위).

실제 API로 동작합니다.

| 기능 | API |
|---|---|
| 목록(분류는 화면에서 거름, 대출 제외) | `GET /products/accounts` |
| 상세(조건·우대금리·특판 기간) | `GET /products/accounts/{id}`, 판매 중이 아니면 `404 PRODUCT_NOT_FOUND` → "상품을 찾을 수 없어요" |
| 입출금·적금 가입 | `POST /accounts` (적금: `term_months`, `monthly_payment`, `payment_day`) |
| 예금 가입 | `POST /accounts/deposits` → `202` → `openApproval(action_id)` (PIN) |

- 금리는 서버가 문자열이라 0.01% 단위 정수로 더합니다. "가입 시 적용 가능한 최고 금리"는 급여이체 우대를 빼고 우대 상한까지만 더합니다.
- 입력 검사는 서버가 정본입니다. 화면은 `min`/`max` 힌트를 주고 서버 오류 문구(나이·기간·금액 조건, 잔액 부족 등)를 그대로 보여 줍니다. 성공하면 홈으로 가는 링크를 줍니다.
- 로딩·오류(다시 시도) 상태가 있고 서버 문자열은 모두 이스케이프합니다.
- 데모 데이터(`products-data.mjs`)와 독립 페이지(`products.html`)는 없앴습니다.

## 검증

```bash
node --test frontend/*.test.mjs
```

수동 확인(서버 실행 중, 로그인 후): 분류별 목록 → 상세(없는 id 포함) → 적금·입출금 가입, 조건 위반 오류 문구, 예금 승인. 320px에서 가로 넘침을 확인합니다.
