# 13. 모바일 은행 앱: 로그인·홈·계좌·이체

> **로그인, 홈(총자산), 계좌 상세·거래내역, 별칭·해지, 이체까지 실제 백엔드 API로 동작합니다. 이체는 서버가 만든 승인 요청을 PIN 창(`openApproval`)으로 승인해야 실행됩니다.**

| 하는 일 | 코드 |
|---|---|
| 화면 이동·그리기 | `frontend/app.mjs`의 `go`, `render`, `currentPage` |
| 로그인·세션 유지·만료 | `app.mjs`의 `login` 화면, `submit` 핸들러, `onExpired` / `api.mjs`의 `login`, `isSignedIn` |
| 홈 총자산·계좌 목록 | `app.mjs`의 `loadAccounts`, `home` (`GET /accounts`, `GET /transactions?limit=3`) |
| 계좌 상세·더 보기 | `app.mjs`의 `openAccount`, `loadTransactions`, `accountPage` |
| 별칭 변경·해지 | `app.mjs`의 `rename` 폼, `close-confirm` (`PATCH /accounts/{id}`, `POST /accounts/{id}/close`) |
| 이체 | `app.mjs`의 `submitTransfer`, `transferPage` / `approval.mjs`의 `openApproval` |
| 화면용 순수 함수 | `frontend/format.mjs` (`normalizeAccountNum`, `parseAmount`, `txLabel`) + `format.test.mjs` |
| 상담 응답(아직 데모 데이터) | `frontend/demo.mjs`의 `replyTo` |
| 카드 화면·상태 | `frontend/cards.mjs`의 `mountCards`, `cards-demo.mjs` |
| 상품 목록·상세·금리 | `frontend/products.mjs`의 `renderProducts`, `products-data.mjs` |

## 요청 흐름

1. **로그인**: 아이디·비밀번호 → `POST /users/login` → 토큰은 `sessionStorage`에 저장되어 새로고침해도 유지됩니다. 틀리면 서버의 `error.message`(`INVALID_CREDENTIALS`, `LOGIN_LOCKED`)를 그대로 보여 줍니다. “데모 계정으로 시작하기”는 데모 계정 값을 채워 같은 폼을 제출합니다. 토큰이 완전히 만료되면 `onExpired`가 로그인 화면으로 돌려보내며 안내 문구를 띄웁니다.
2. **홈**: `GET /accounts`(총자산·계좌)와 `GET /transactions?limit=3`(최근 거래)를 함께 부릅니다. 서버 응답이 오기 전엔 “불러오는 중”, 실패하면 오류와 “다시 불러오기”를 보여 줍니다.
3. **계좌 상세**: `GET /accounts/{id}`(예·적금은 적용 금리·만기·월 납입금)와 `GET /accounts/{id}/transactions?limit=20`. 한 쪽이 꽉 차면 마지막 `tx_id`를 `before`로 넘겨 “더 보기”로 다음 쪽을 이어 붙입니다.
4. **관리**: 별칭은 `PATCH`로 바꾸고, 해지는 입출금만 두 번 눌러(확인) `POST .../close`. `BALANCE_REMAINING`, `LINKED_CARD_EXISTS` 같은 서버 오류는 문구 그대로 표시합니다.
5. **이체**: 받는 계좌번호 → 금액 → 확인 → `POST /transfers`(`202` 승인 대기) → `openApproval(action_id)`의 PIN 창 → 실행 성공 뒤 완료 화면과 잔액 새로고침. 내 다른 입출금·적금은 빠른 선택으로 보여 줍니다(예금은 입금 불가라 제외).

## 핵심 코드

```javascript
transfer.key ??= idempotencyKey();
const { data: action } = await api("/transfers", { method: "POST", body: {
  from_account_id: transfer.source, to_account_num: transfer.number, amount: transfer.amount, idempotency_key: transfer.key,
} });
transfer.key = undefined;
const result = action.status === "PENDING" ? await openApproval(action.action_id) : { status: action.status };
```

화면은 돈을 직접 움직이지 않습니다. 서버가 이체 요청을 승인 대기로 만들고, PIN 승인 때 잔액·한도를 다시 검사해 실행합니다. 완료 화면은 서버 실행이 성공한 뒤에만 보입니다. 취소하면 “돈은 빠져나가지 않았어요”, 잔액 부족·한도 초과 같은 실패는 서버 `error.message`를 그대로 보여 줍니다.

## 왜 이렇게 했나

- **멱등키**: 확인 단계에서 요청을 보낼 때 키를 만들고, 연결 실패(`status 0`)일 때만 유지합니다. 같은 키로 다시 보내면 서버가 처음 요청을 돌려주므로 두 번 이체되지 않습니다. 서버가 답한 오류나 내용이 바뀐 경우(뒤로 가기)에는 키를 새로 만듭니다(같은 키·다른 내용은 `409 IDEMPOTENCY_KEY_REUSED`).
- **검사는 서버가**: 화면은 “1원 이상 정수”만 확인하고 잔액·한도는 서버 응답을 보여 줍니다. 화면 검사는 우회할 수 있고, 서버가 요청·승인 두 번 같은 검사를 하기 때문입니다.
- **계좌번호 정리**: 숫자 12자리면 `110-101-000002` 꼴로 맞춰 보냅니다. 그 밖의 입력은 서버가 `RECEIVER_NOT_FOUND`로 거릅니다.
- **모든 서버 문자열은 `escape`**: 별칭·거래 메모처럼 사용자가 넣은 값이 HTML로 해석되지 않게 합니다.
- **상담 화면은 아직 데모 데이터**: 상담은 별도 작업에서 실제 Agent로 바꿉니다. 상담의 “이체 내용 확인”은 데모 초안이라 실제 이체 화면의 첫 단계로만 연결합니다.

## 카드·상품 통합과 검증

공통 라우터는 `#cards`, `#products`, `#product/<id>`를 로그인 이후 허용합니다. 상품은 `renderProducts`로 공통 라우터에서 렌더링해 독립 페이지의 해시 리스너와 충돌하지 않게 했습니다. 상품 분류는 앱 상태에 보관합니다. 카드는 전용 컨테이너에 마운트하고 화면 교체 전에 반환된 정리 함수를 호출합니다. 카드 상태 배열은 앱에 보관해 메뉴 왕복 후에도 정지·분실 상태가 유지됩니다. 보기 방식과 선택 카드는 재진입 시 초기화합니다. 로그아웃은 계좌·카드·상품 상태를 모두 초기화합니다.

`cards.html`·`products.html`은 독립 확인용으로 유지합니다. 통합 화면에서는 `embedded` 옵션으로 중복 데모 표시를 숨기고 공통 메뉴를 표시합니다. 새 패키지나 서버 변경은 없습니다.

검증: 정적 서버로 앱을 연 뒤 브라우저 개발자 도구에서 아래를 실행합니다. 데모 상태를 초기화하며 로그인 보호·메뉴·카드 확인 대화상자·상태 유지·상품 필터·뒤로/앞으로·없는 상품·계좌 별칭·직접/상담 이체·로그아웃 초기화를 확인합니다. 모바일 320·390·480px에서 반복합니다.

```javascript
await (await import('/integration.browser.mjs')).verifyIntegration()
```

## 면접 예상 질문

**Q. 이체 완료 화면은 언제 보여 주나요?**

서버가 PIN 승인으로 이체를 실행했다는 응답(`EXECUTED`)을 받은 뒤에만 보여 줍니다. 요청만 보낸 상태는 승인 대기이고 돈이 움직이지 않았기 때문입니다.

**Q. 이체 버튼을 두 번 누르거나 네트워크가 끊겨 다시 보내면 어떻게 되나요?**

요청마다 멱등키를 보내고, 연결 실패 때는 같은 키로 다시 보냅니다. 서버가 같은 키를 알아보고 처음 요청을 돌려주므로 두 번 이체되지 않습니다. 버튼은 요청 중 비활성화합니다.

**Q. 새로고침하면 로그인이 풀리나요?**

토큰을 `sessionStorage`에 저장해 탭이 살아 있는 동안 유지합니다. access token이 만료되면 refresh token으로 한 번 갱신하고, 그것도 실패하면 로그인 화면으로 돌려보냅니다.

**Q. 상담에서 바로 이체하지 않은 이유는요?**

상담은 누락 정보를 물어본 뒤 초안을 만들어 줍니다. 사람이 받는 계좌와 금액을 보고 별도 화면에서 PIN을 입력합니다. 기존 백엔드의 상담과 거래 승인 경계를 화면 흐름으로도 지킵니다.
