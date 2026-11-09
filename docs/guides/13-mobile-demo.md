# 13. 모바일 은행 데모

> **로그인, 계좌 확인, 직접 이체와 상담 이체를 동일한 시연 데이터로 체험합니다. PIN 승인 뒤에 잔액과 거래내역이 함께 바뀝니다.**

| 하는 일 | 코드 |
|---|---|
| 홈·계좌·이체·상담 화면 이동 | `frontend/app.mjs`의 `go`, `render` |
| 상담 응답과 누락 정보 확인 | `frontend/demo.mjs`의 `replyTo` |
| 이체 확인과 승인 | `frontend/demo.mjs`의 `transferError`, `approveTransfer` |
| 카드 화면·상태 | `frontend/cards.mjs`의 `mountCards` (실제 API) |
| 상품 목록·상세·가입 | `frontend/products.mjs`의 `mountProducts` (실제 API) |
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

## 카드·상품: 실제 API 연결

> **카드와 상품 화면은 데모 데이터 없이 서버 API로 동작합니다. 정지·분실은 바로, 정지 해제와 예금 개설은 서버가 만든 승인 요청을 PIN으로 승인해야 반영됩니다.**

| 하는 일 | 코드 |
|---|---|
| 카드 목록·상세·사용내역·한도 | `frontend/cards.mjs`의 `loadAll`, `loadCard` (`GET /cards`, `/cards/{id}`, `/transactions`, `/limits`) |
| 카드 발급 | `cards.mjs`의 `submitIssue` (`GET /products/cards`, `GET /accounts`, `POST /cards`) |
| 정지·분실·정지 해제 | `cards.mjs`의 `changeStatus` (`POST /cards/{id}/suspend`, `/unsuspend` → `openApproval`) |
| 상품 목록·상세·금리 | `frontend/products.mjs`의 `listView`, `detailView`, `openingRate` |
| 가입 | `products.mjs`의 `submit` (입출금·적금 `POST /accounts`, 예금 `POST /accounts/deposits` → `openApproval`) |

요청 흐름: 화면 진입 → `api()`로 목록 조회(로딩 표시) → 카드는 선택할 때마다 상세·내역·한도를 다시 조회 → 쓰기 요청 → 성공 메시지 또는 서버 오류 문구 표시. 정지 해제는 `202`로 받은 `action_id`를 공통 승인 창(`openApproval`)에 넘기고, 서버 실행이 끝난 뒤에만 "해제했어요"를 보여 줍니다.

```javascript
const { data } = await api(`/cards/${card.card_id}/unsuspend`, { method: "POST", body: { idempotency_key: idempotencyKey() } });
const result = await openApproval(data.action_id);
notice = result.status === "EXECUTED" ? "정지를 해제했어요." : ...;
```

왜 이렇게 했나:
- 정지는 안전한 쪽이라 바로 적용하고(확인 대화상자만), 푸는 것은 PIN으로 승인합니다. 분실은 되돌릴 수 없어 대화상자에 그대로 적습니다.
- 금리는 서버가 문자열(`"3.50"`)로 줍니다. 화면은 0.01% 단위 정수로 바꿔 더하고(`hundredths`) 부동소수점 오차를 피합니다. 개설 시 적용 금리는 급여이체 우대를 빼고 우대 상한까지만 더합니다(서버 정책과 같음).
- 입력 검사는 서버가 정본입니다. 화면은 `min`/`max` 힌트만 주고, 서버의 오류 문구(`AMOUNT_OUT_OF_RANGE` 등)를 그대로 보여 줍니다. 서버가 준 모든 문자열은 이스케이프합니다.
- 월 이용금액은 한국 날짜 기준 이달의 `APPROVED` 건만 합산합니다. 할인 집계는 서버에 없어 만들지 않았습니다.
- 데모 데이터(`cards-demo.mjs`, `products-data.mjs`)와 독립 페이지(`cards.html`, `products.html`)는 지웠습니다.

검증: `node --test frontend/*.test.mjs`(순수 로직), 브라우저 320px에서 카드 발급 → 정지 → PIN 해제 → 분실, 상품 분류 → 상세 → 적금·입출금 가입, 오류 문구 확인.

## 면접 예상 질문

**Q. 상담에서 바로 이체하지 않은 이유는요?**

상담은 누락 정보를 물어본 뒤 초안을 만들어 줍니다. 사람이 받는 계좌와 금액을 보고 별도 화면에서 PIN을 입력합니다. 데모도 기존 백엔드의 상담과 거래 승인 경계를 화면 흐름으로 보여줍니다.

**Q. 카드 정지는 바로 되는데 해제는 왜 PIN이 필요한가요?**

정지는 도난·분실 때 빨리 막는 안전한 쪽이라 바로 적용합니다. 해제는 다시 돈을 쓸 수 있게 하는 쪽이라 서버가 승인 요청을 만들고 PIN을 받은 뒤 상태를 다시 확인하고 풉니다. 화면은 서버 실행 성공 뒤에만 완료를 알립니다.

**Q. 금리를 문자열로 받아 정수로 바꾸는 이유는요?**

0.1 + 0.2 같은 부동소수점 오차를 피하려고, 서버가 문자열로 준 금리를 0.01% 단위 정수로 바꿔 계산하고 표시할 때만 소수로 돌립니다.
