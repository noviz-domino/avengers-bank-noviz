# 상품 목록·상세 데모

시안: `docs/design-drafts/15-products-option-1-selected.png`.

레포 루트에서 Git Bash로 실행:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory frontend
```

`http://127.0.0.1:8765/products.html`로 접속한다. 직접 상세 진입은
`products.html#product/stark`이며, 전체 / 입출금 / 예금 / 적금 분류와
상세 → 목록 복귀, 브라우저 뒤로·앞으로 가기를 제공한다.

- `products-data.mjs`: seed의 입출금·예금·적금 5개를 옮긴 데모 데이터. 대출·카드는 범위 밖.
- `products.mjs`: 목록·상세 렌더링과 상품 내부 이동.
- `products.css`: `.products-app` 범위 안에서만 적용되는 상품 스타일.
- `products.html`: 공통 메뉴 연결 전 독립 확인용 진입점. 기존 앱 파일은 수정하지 않는다.

상품 조건은 `src/avengers_bank/seed.py`, 가입 시 급여이체 우대 제외 기준은
`domains/accounts`와 `domains/rag/docs/deposit-terms.md`를 따른다.
최고금리는 모든 우대 충족 시 수치이며, 상세에 가입 시 적용 가능한 최고금리를 따로 표시한다.
특판은 한국 날짜 기준 판매 기간 안에서만 목록·상세에 노출한다.
계좌 개설·가입·잔액 변경·API 호출은 실행하지 않는다.

통합 단계: 공통 메뉴·라우터에서 상품 진입을 연결하고, 상품 전용 컨테이너에
`products-app` 클래스를 붙여 `mountProducts(root)`를 호출한다.
현재 hash 경로는 `#products`, `#product/<id>`이며 분류는 화면을 벗어나기 전까지 유지한다.
이탈 시 반환된 정리 함수를 호출해 리스너를 해제한다. 공통 앱의 hash 변경 리스너와
라우트 허용 목록도 통합 단계에서 조정해야 한다. 상품의 방패 마크는 공통 로고에 맞춰 둔 사본이다.

검증:

```bash
node --test frontend/demo.test.mjs frontend/products.test.mjs
```
