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
- `products.html`: 공통 앱과 별개로 유지하는 독립 확인용 진입점.

상품 조건은 `src/avengers_bank/seed.py`, 가입 시 급여이체 우대 제외 기준은
`domains/accounts`와 `domains/rag/docs/deposit-terms.md`를 따른다.
최고금리는 모든 우대 충족 시 수치이며, 상세에 가입 시 적용 가능한 최고금리를 따로 표시한다.
특판은 한국 날짜 기준 판매 기간 안에서만 목록·상세에 노출한다.
계좌 개설·가입·잔액 변경·API 호출은 실행하지 않는다.

공통 앱은 `#products`, `#product/<id>`를 로그인 이후 허용한다.
`products-app` 컨테이너에 `renderProducts(route, kind, undefined, true)`를 렌더링하며
공통 라우터 하나가 해시 이동을 처리한다. 분류는 목록·상세·다른 메뉴를 오가도 유지하고
로그아웃·새로고침하면 초기화한다. 독립 페이지는 기존 `mountProducts(root)`와
반환된 리스너 정리 함수를 사용한다. 상품의 방패 마크는 공통 로고에 맞춰 둔 사본이다.
원본은 `product-screen`의 미커밋 상품 파일 6개이며 원본 작업 트리는 수정하지 않았다.

검증:

```bash
node --test frontend/demo.test.mjs frontend/products.test.mjs
```
