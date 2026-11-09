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
