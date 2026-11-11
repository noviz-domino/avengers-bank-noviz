# 공통 UI 부품

새 화면과 2단계 이관 화면은 `ui.mjs`의 부품과 `ui.css`의 디자인 값만 사용해요. 빌드나 추가 라이브러리가 필요 없는 ES 모듈이에요. 기준은 [홈 14번](../docs/design-drafts/14-home-compact-privacy-latest.png)과 [디자인 인계](../docs/design-drafts/HANDOFF.md)예요.

## 디자인 값

| 용도 | CSS 변수 | 값 |
|---|---|---|
| 크림 / 흰색 / 네이비 | `--ui-cream`, `--ui-white`, `--ui-navy` | `#fbf5e9` / `#fff` / `#10233b` |
| 입출금 / 옅은 배경 | `--ui-blue`, `--ui-blue-soft` | `#1d5fa8` / `#edf4fd` |
| 조용한 회색 면 (총자산·대화 영역·타일) | `--ui-surface` | `#f4f6f8` |
| 예금·적금 / 옅은 배경 | `--ui-sage`, `--ui-sage-soft` | `#487657` / `#eef6f0` |
| 최근 거래 / 옅은 배경 | `--ui-amber`, `--ui-amber-soft` | `#96611c` / `#fcf3e3` |
| 오류 / 보조 글자 / 구분선 | `--ui-error`, `--ui-muted`, `--ui-line` | `#a22938` / `#647083` / `#e6eaef` |
| 페이지 / 섹션 / 본문 / 보조 | `--ui-title-size`, `--ui-section-size`, `--ui-body-size`, `--ui-small-size` | 26 / 18 / 15 / 13px |
| 좌우 여백 | `--ui-page-gutter` | 24px, 340px 이하 16px |
| 여백 단위 | `--ui-space-xs`, `--ui-space-sm`, `--ui-space-md`, `--ui-space-lg` | 4 / 8 / 16 / 24px |
| 작은 / 큰 모서리 | `--ui-radius-sm`, `--ui-radius` | 10 / 16px |
| 그림자 | `--ui-shadow` | `0 4px 18px #10233b0a` |
| 최소 터치 | `--ui-touch` | 44px |

홈 총자산만 36px(340px 이하 32px)로 강조해요. 페이지 제목은 `pageTitle`을 써요. 시안의 작은 배너 컨트롤도 터치 영역은 44px이에요. 폰트는 기존 Pretendard → 맑은 고딕 → 시스템 글꼴 순서를 유지해요.

## 사용 규칙

- 모든 화면은 `ui.mjs` 부품을 사용해요. 기존 카드·상품·설정·계좌·이체·상담 화면은 **2단계에 이관**해요. 기존 클래스를 전체 재정의하지 말아요.
- 새 색·글자 크기를 화면별로 추가하지 않아요. 필요한 공통 변경은 `ui.css`의 디자인 값에서 해요.
- 누르는 영역은 가로·세로 최소 44px, 제목은 `word-break: keep-all; overflow-wrap: anywhere`, 긴 별칭의 부모에는 `min-width: 0`을 유지해요.
- `ui.css`는 `index.html`의 **첫 스타일시트**예요. 새 부품 규칙은 `ui-` 클래스로 한정해 기존 화면 CSS와 충돌을 막아요. `[hidden]`만 전역으로 숨김을 보장해요.
- 화면에는 의미 있는 `h1`을 하나 두어요. 탭 화면(상품·AI 상담·카드·전체)은 `header({ heading: true })`의 제목이 `h1`이고, 오른쪽 도구(보기 전환·발급·새 대화)를 같은 줄에 둬요. 은행명은 홈 머리글에만 작게 둬요.
- 디자인을 바꾸면 [버전별 캡처](../docs/design-drafts/implemented/README.md)에 새 버전 폴더를 추가하고 이유를 ADR에 남겨요.
- 같은 높이에 놓을 수 있는 것은 한 줄에 둬요 (제목+도구, 금액+이체 버튼, 설명+값). 한 줄을 버튼 하나가 차지하지 않게 해요.
- 부품의 일반 문자열은 자동 이스케이프돼요. `*Html` 인자는 **부품으로 조합한 신뢰할 수 있는 HTML만** 받아요. 서버·사용자 문자열을 그대로 넘기지 말아요. 서버 문구와 금융 조건은 임의로 고치지 않아요.
- 이벤트는 기존 컨테이너의 위임 핸들러에서 `data-action`으로 연결해요. 부품은 API·라우팅·이벤트 등록을 하지 않아요. 금액은 `format.mjs`의 `money`로 먼저 표시 문자열을 만들어요.
- 카드·상품처럼 모듈 내부 액션을 처리할 때는 위임 핸들러에서 `event.stopPropagation()`으로 앱의 전역 라우팅과 구분해요. 기존 `data-card-action`·`data-product-*`를 옮길 때 이 연결도 함께 바꿔요. 주 화면 탭은 `app.mjs`가 한 번만 붙이므로 모듈에서 중복 생성하지 말아요.
- 로딩·빈 상태·고정 안내는 “~해요” 말투를 써요. 오류는 `role="alert"`, 로딩과 빈 상태는 `role="status"`예요.

## 함수

모든 마크업 함수는 HTML 문자열을 반환해요. 아래 옵션 객체는 필요한 항목만 넘겨요.

| 함수 시그니처 | 설명 |
|---|---|
| `esc(value)` | `null`·`undefined`는 빈 문자열, HTML 특수문자 5개를 이스케이프해요 |
| `icon(name)` | 장식용 인라인 SVG. `back`, `arrow`, `chevron`, `down`, `wallet`, `pig`, `clock`, `home`, `products`, `chat`, `cards`, `menu`, `eye`, `eyeOff`, `pause`, `play`, `single`, `list`, `send`, `gift`, `shield`, `target` 등 |
| `button(label, {action, variant='quiet', icon, ariaLabel, pressed, className=''})` | `primary` / `outline` / `quiet` / `pill`. 아이콘만 있는 버튼은 `ariaLabel` 필수예요 |
| `carouselPager(page, count, {previous, next})` | 홈·상품 배너 공용 넘김 표시. 이전·다음 액션과 현재 페이지를 표시해요 |
| `header({title='', brandHtml='', back, rightHtml='', heading=false})` | 52px 머리글. `back`은 뒤로 가기 버튼의 액션, 버튼은 44×44px이에요. `heading: true`면 제목을 `h1`으로 그려요 (탭 화면처럼 머리글 제목이 곧 페이지 제목일 때. 본문에 `pageTitle`을 또 두지 않아요) |
| `iconToggle(options, {label, current, prefix='', attr='data-action'})` | 아이콘만 있는 보기 전환. `options`는 `[값, 아이콘, 읽어 줄 이름]` 배열, 액션 값은 `prefix + 값`이에요. 카드 화면의 크게/목록 전환에 써요 |
| `pageTitle(title)` | 26px `h1`, 긴 제목을 어절 단위로 줄바꿈해요 |
| `sectionHead({title, count, total='', icon, tone='blue', action, expanded, controls, rightHtml=''})` | `blue` / `sage` / `amber`. 액션이 있으면 접기 버튼을 만들고 `aria-expanded`·`aria-controls`를 연결해요 |
| `listRow({title, subtitle='', amount, action, buttonHtml='', icon, tone='blue', credit=false})` | `li`를 반환해요. `ul` 안에 배치해요. 제목은 왼쪽, 금액과 선택 버튼은 같은 오른쪽 끝선이에요 |
| `cardBox(contentHtml, className='')` | 크림색 카드 상자예요 |
| `stateBlock(kind, {message, retryAction}={})` | `loading` / `empty` / `error`, 같은 24px 여백. `retryAction`은 44px 다시 시도 버튼이에요 |
| `field({id, label, name=id, type='text', value='', hint='', error='', required=false, autocomplete})` | 고유 `id` 필수. label·힌트·오류를 `for`·`aria-describedby`·`aria-invalid`로 연결해요 |
| `maskAccountNumber(number)` | 하이픈 유무와 관계없이 12자리 계좌번호를 `110-***-000001`로 표시해요. 잘못된 형식은 `***`로 숨겨요 |
| `bottomTabs(page)` | `home` / `products` / `chat` / `cards` / `menu` 순서예요. `page`와 일치하면 현재 탭으로 표시해요 |
| `restoreFocus(root)` | 다시 그리기 전에 호출해 복원 함수를 받아요. 다시 그린 뒤 호출하면 같은 `data-action` → `id` → `name` 순서의 요소에 포커스·선택 영역을 복원해요 |

### 머리글·제목·버튼·상태

```js
import { header, pageTitle, button, stateBlock, field } from './ui.mjs';
container.innerHTML = header({ title: '계좌 상세', back: 'home',
  rightHtml: button('관리', { action: 'manage' }) })
  + '<main>' + pageTitle('생활비 통장')
  + stateBlock('error', { message: '불러오지 못했어요.', retryAction: 'reload' })
  + field({ id: 'nickname', label: '계좌 별칭', hint: '50자까지 입력해요.',
      error: '별칭을 입력해 주세요.', required: true })
  + button('저장', { action: 'save', variant: 'primary' }) + '</main>';
```

`button`은 `type="button"`이에요. 네이티브 폼 제출은 `<button type="submit" class="ui-button ui-button--primary">저장</button>`을 사용해요. 입력 검증 뒤에는 첫 잘못된 입력에 포커스를 두어요.

### 접기·목록·카드·탭

```js
import { sectionHead, listRow, maskAccountNumber, cardBox, bottomTabs, button } from './ui.mjs';
const html = sectionHead({ title: '입출금', count: 2, total: '3,100,000원',
  icon: 'wallet', tone: 'blue', action: 'toggle-checking', expanded: true,
  controls: 'checking-list' })
  + '<ul id="checking-list">' + listRow({ title: '생활비 통장',
      subtitle: maskAccountNumber('110-101-000001'), amount: '2,350,000원',
      action: 'account-1', icon: 'wallet',
      buttonHtml: button('이체', { action: 'send-1', variant: 'outline' }) }) + '</ul>'
  + cardBox(button('AI 상담 시작', { action: 'chat' })) + bottomTabs('home');
```

접으면 목록에 `hidden`을 붙이고 `expanded`도 함께 바꿔요. 이체는 계좌 행·상세에서 진입하며, 전체 탭의 목적지는 기존 `#menu`예요.

### 포커스와 수명주기

```js
const focus = restoreFocus(container);
container.innerHTML = draw();
focus();
```

같은 화면의 토글·필터 갱신에 사용해요. 화면 이동에는 본문 제목에 `tabindex="-1"`를 붙여 포커스해요. 고유 `data-action`·`id`를 사용하고, 여러 폼이 같은 `name`을 쓰면 `id`도 지정해요. 홈 배너는 5초마다 배너 영역만 바꾸며 포커스를 복원해요. 일시정지·문서 비활성·다른 화면에서는 타이머를 정리하고, 동작 줄이기 설정에서는 처음부터 정지해요.

## 배너 그림과 확인

홈 배너는 문구·배경·그림이 한 장에 담긴 WebP 파일이에요. 오픈 기념은 `assets/banner-opening.webp`, 신규가입은 `assets/banner-welcome.webp`를 같은 이름으로 교체하면 돼요. 두 이미지의 비율은 1989:791을 기준으로 맞춰요. 문구나 목적지가 바뀌면 `app.mjs`의 대체 텍스트나 링크도 함께 바꿔요. 페이지 넘김과 재생·정지는 이미지 위의 버튼으로 동작해요.

`node --test frontend/*.test.mjs`와 `node tests/browser/run-integration.mjs`로 확인해요. 브라우저 점검은 실제 데모 DB에 1,000원 이체·별칭 변경과 복원을 수행해요. 390px·320px에서 전체보기·이체·숨김·접기·하단 탭과 긴 별칭의 가로 넘침을 추가로 확인해요.
