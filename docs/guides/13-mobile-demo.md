# 13. 모바일 은행 데모

> **로그인, 계좌 확인, 직접 이체와 상담 이체를 동일한 시연 데이터로 체험합니다. PIN 승인 뒤에 잔액과 거래내역이 함께 바뀝니다.**

| 하는 일 | 코드 |
|---|---|
| 홈·계좌·이체·상담 화면 이동 | `frontend/app.mjs`의 `go`, `render` |
| 상담 응답과 누락 정보 확인 | `frontend/demo.mjs`의 `replyTo` |
| 이체 확인과 승인 | `frontend/demo.mjs`의 `transferError`, `approveTransfer` |
| 카드 화면·상태 | `frontend/cards.mjs`의 `mountCards`, `cards-demo.mjs` |
| 상품 목록·상세·금리 | `frontend/products.mjs`의 `renderProducts`, `products-data.mjs` |
| 실제 브라우저 통합 검증 | `frontend/integration.browser.mjs`의 `verifyIntegration` |

## 사용 흐름

직접 이체는 수취 계좌 → 금액 → 확인으로 이동합니다. 상담에서 “토니에게 5만 원 보내줘”라고 하면 출금 계좌를 묻습니다. “생활비 통장”이라고 답한 뒤 **이체 내용 확인**을 누르면 같은 확인 화면으로 들어갑니다. 시연용 PIN을 등록하지 않았다면 등록 화면을 먼저 표시합니다.

## 핵심 코드

```javascript
const error = approveTransfer(demo, transfer, data.get("pin"));
form.reset();
if (error) return formError(form, error);
step("done");
```

확인 버튼만으로 잔액을 바꾸지 않습니다. 승인 함수가 PIN과 이체 조건을 검사한 뒤 한 번에 잔액과 거래내역을 갱신합니다. 금액 초안은 직접 입력하거나 상담에서 받은 값이므로 승인 시에도 같은 조건을 확인합니다.

## 카드·상품 통합과 검증

공통 라우터는 `#cards`, `#products`, `#product/<id>`를 로그인 이후 허용합니다. 상품은 `renderProducts`로 공통 라우터에서 렌더링해 독립 페이지의 해시 리스너와 충돌하지 않게 했습니다. 상품 분류는 앱 상태에 보관합니다. 카드는 전용 컨테이너에 마운트하고 화면 교체 전에 반환된 정리 함수를 호출합니다. 카드 상태 배열은 앱에 보관해 메뉴 왕복 후에도 정지·분실 상태가 유지됩니다. 보기 방식과 선택 카드는 재진입 시 초기화합니다. 로그아웃은 계좌·카드·상품 상태를 모두 초기화합니다.

`cards.html`·`products.html`은 독립 확인용으로 유지합니다. 통합 화면에서는 `embedded` 옵션으로 중복 데모 표시를 숨기고 공통 메뉴를 표시합니다. 새 패키지나 서버 변경은 없습니다.

검증: 정적 서버로 앱을 연 뒤 브라우저 개발자 도구에서 아래를 실행합니다. 데모 상태를 초기화하며 로그인 보호·메뉴·카드 확인 대화상자·상태 유지·상품 필터·뒤로/앞으로·없는 상품·계좌 별칭·직접/상담 이체·로그아웃 초기화를 확인합니다. 모바일 320·390·480px에서 반복합니다.

```javascript
await (await import('/integration.browser.mjs')).verifyIntegration()
```

## 면접 예상 질문

**Q. 상담에서 바로 이체하지 않은 이유는요?**

상담은 누락 정보를 물어본 뒤 초안을 만들어 줍니다. 사람이 받는 계좌와 금액을 보고 별도 화면에서 PIN을 입력합니다. 데모도 기존 백엔드의 상담과 거래 승인 경계를 화면 흐름으로 보여줍니다.
