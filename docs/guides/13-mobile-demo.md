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
| 카드 화면·상태 | `frontend/cards.mjs`의 `mountCards` (실제 API) |
| 상품 목록·상세·가입 | `frontend/products.mjs`의 `mountProducts` (실제 API) |

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

**Q. 이체 완료 화면은 언제 보여 주나요?**

서버가 PIN 승인으로 이체를 실행했다는 응답(`EXECUTED`)을 받은 뒤에만 보여 줍니다. 요청만 보낸 상태는 승인 대기이고 돈이 움직이지 않았기 때문입니다.

**Q. 이체 버튼을 두 번 누르거나 네트워크가 끊겨 다시 보내면 어떻게 되나요?**

요청마다 멱등키를 보내고, 연결 실패 때는 같은 키로 다시 보냅니다. 서버가 같은 키를 알아보고 처음 요청을 돌려주므로 두 번 이체되지 않습니다. 버튼은 요청 중 비활성화합니다.

**Q. 새로고침하면 로그인이 풀리나요?**

토큰을 `sessionStorage`에 저장해 탭이 살아 있는 동안 유지합니다. access token이 만료되면 refresh token으로 한 번 갱신하고, 그것도 실패하면 로그인 화면으로 돌려보냅니다.

**Q. 상담에서 바로 이체하지 않은 이유는요?**

상담은 누락 정보를 물어본 뒤 초안을 만들어 줍니다. 사람이 받는 계좌와 금액을 보고 별도 화면에서 PIN을 입력합니다. 기존 백엔드의 상담과 거래 승인 경계를 화면 흐름으로도 지킵니다.

**Q. 카드 정지는 바로 되는데 해제는 왜 PIN이 필요한가요?**

정지는 도난·분실 때 빨리 막는 안전한 쪽이라 바로 적용합니다. 해제는 다시 돈을 쓸 수 있게 하는 쪽이라 서버가 승인 요청을 만들고 PIN을 받은 뒤 상태를 다시 확인하고 풉니다. 화면은 서버 실행 성공 뒤에만 완료를 알립니다.

**Q. 금리를 문자열로 받아 정수로 바꾸는 이유는요?**

0.1 + 0.2 같은 부동소수점 오차를 피하려고, 서버가 문자열로 준 금리를 0.01% 단위 정수로 바꿔 계산하고 표시할 때만 소수로 돌립니다.

## 회원가입·전체 메뉴·PIN 변경·거래 검색

**요약**: 로그인 전에는 `#signup`으로 가입하고(가입 직후 자동 로그인), 로그인 후에는 홈 머리글의 "메뉴"(`#menu`)에서 내 정보 확인·거래 PIN 설정/변경·로그아웃을 하고, 메뉴에서 거래내역 검색(`#search`)으로 갑니다. 세 화면은 `app.mjs`와 분리한 모듈이고, 실제 백엔드 API를 `api.mjs`로 부릅니다.

| 위치 | 역할 |
|---|---|
| `frontend/signup.mjs` | 회원가입 폼, `validateSignup`(서버 `UserCreate` 규칙과 같은 클라이언트 검증) |
| `frontend/settings.mjs` | 메뉴: `GET /users/me`, `PUT /users/me/pin`, 로그아웃, 앱 정보, `validatePinChange` |
| `frontend/search.mjs` | 거래 검색: `GET /transactions`, `buildQuery`(조건 → 쿼리스트링) |
| `frontend/ext-ui.mjs`, `settings.css` | 이스케이프·머리글·422 오류 변환, 화면 스타일 |
| `frontend/app.mjs` | 라우트 3개와 마운트 호출, 로그인 화면의 "회원가입" 링크, 홈의 "메뉴" 버튼 |

**요청 흐름**
1. 가입: 폼 검증 → `POST /users/signup` → 성공하면 `login()` → 홈. `409 LOGIN_ID_ALREADY_EXISTS`는 아이디 칸 아래에, `422`는 `details`의 필드명(`loc` 마지막)으로 해당 칸에 표시합니다.
2. PIN: 현재 로그인 비밀번호 + 새 PIN 6자리 + 확인 → `PUT /users/me/pin`. 비밀번호가 틀리면 `401 INVALID_CREDENTIALS`라 "비밀번호가 맞지 않아요"를 보여 주고, 성공하면 `has_pin`을 갱신해 "PIN 변경"으로 문구가 바뀝니다.
3. 검색: 비어 있지 않은 조건만 쿼리로 만들어 `GET /transactions?...&limit=20`. 합계(`total_in`, `total_out`)는 이번 쪽이 아닌 조건 전체 합계이고, `next_before`가 있으면 "더 보기"로 다음 쪽을 이어 붙입니다.

**핵심 코드**

```javascript
// 서버 PinSet 규칙과 같게: PIN은 숫자 6자리, 비밀번호는 다시 받는다
if (!/^\d{6}$/.test(pin)) e.pin = "PIN은 숫자 6자리예요.";
else if (pin !== pin2) e.pin2 = "PIN이 서로 달라요.";
```

**왜 이렇게 했나**
- 화면을 모듈로 나누고 `mountX(container, {go, ...})` 형태로 만들어 `app.mjs`에는 라우트·마운트 몇 줄만 두었습니다. 다른 화면과 동시에 작업해도 충돌이 적습니다.
- 서버가 최종 판단하고 클라이언트 검증은 빠른 안내용입니다. 같은 규칙을 순수 함수로 두어 `node --test`로 확인합니다.
- 서버 오류 문구는 영어라 필드별 한국어 안내로 바꿉니다. 서버가 준 문자열은 모두 `esc`로 이스케이프해 넣습니다.
- 메뉴 탭은 이미 6개라 7번째 탭 대신 홈 머리글 버튼으로 연결했습니다.
- PIN 변경에 로그인 비밀번호를 다시 받는 것은 서버 규칙입니다. 토큰만 훔친 사람이 PIN을 바꾸지 못하게 합니다.

**면접 예상 질문**
- Q. 클라이언트 검증이 있는데 서버 검증이 왜 또 필요한가요? 클라이언트는 우회할 수 있어서 서버가 최종 방어선이고, 클라이언트는 사용자 안내용입니다.
- Q. 검색 합계는 왜 화면의 행을 더하지 않았나요? 페이지네이션 때문에 화면에는 일부 행만 있어서, 서버가 조건 전체를 집계한 값을 씁니다.
- Q. 가입 후 자동 로그인은 어떻게 하나요? 가입 응답에는 토큰이 없어서, 입력했던 아이디·비밀번호로 `login()`을 한 번 더 부릅니다.

**검증**: `node --test frontend/*.test.mjs`, 그리고 320px 브라우저에서 가입(중복 아이디 오류 포함)→자동 로그인→메뉴 정보→PIN 설정→틀린 비밀번호로 변경 실패→변경 성공→로그아웃, 데모 계정 키워드·카테고리 검색과 합계를 확인했습니다.
