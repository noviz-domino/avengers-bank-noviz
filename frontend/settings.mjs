// 전체 메뉴·설정 화면 (#menu): 내 정보, 거래 PIN 설정·변경, 거래 검색 링크, 로그아웃, 앱 정보
import { api, logout } from "./api.mjs";
import { esc } from "./ext-ui.mjs";
import { header, icon, stateBlock } from "./ui.mjs";

export const APP_VERSION = "1.0.0";

// 서버 PinSet 규칙: PIN은 숫자 6자리, 비밀번호는 다시 받는다
export function validatePinChange({ password, pin, pin2 }) {
  const e = {};
  if (!password) e.password = "현재 로그인 비밀번호를 입력해 주세요.";
  if (!/^\d{6}$/.test(pin)) e.pin = "PIN은 숫자 6자리예요.";
  else if (pin !== pin2) e.pin2 = "PIN이 서로 달라요.";
  return e;
}

const row = (k, v) => "<dt>" + k + "</dt><dd>" + v + "</dd>";
const pw = (name, label, extra = "") => '<label for="menu-' + name + '">' + label + '<input id="menu-' + name + '" name="' + name + '" type="password" required aria-describedby="e-' + name + '" aria-invalid="false" ' + extra + '></label><p class="error" id="e-' + name + '" role="alert"></p>';
const group = (title, tone, content, open) => '<details class="menu-group"' + (open ? ' open' : '') + '><summary class="ui-section-head ui-tone-' + tone + '">' + title + icon('down') + '</summary><div class="menu-group-body">' + content + '</div></details>';

// 바로가기 타일 (2줄 x 4칸). 누르면 app.mjs의 data-action 라우팅이 처리한다
const SHORTCUTS = [['accounts', '계좌', 'wallet'], ['start-transfer', '이체', 'transfer'], ['search', '계좌 검색', 'search'], ['card-search', '카드 검색', 'search'],
  ['budget', '예산', 'target'], ['products', '상품', 'products'], ['cards', '카드', 'cards'], ['chat', 'AI 상담', 'chat']];
// 메뉴 검색 대상: [액션, 이름, 아이콘, 같이 찾을 말]. "act:"로 시작하면 이 화면 안의 동작
export const MENUS = [
  ['home', '홈', 'home', '총자산 처음'], ['accounts', '계좌', 'wallet', '잔액 통장 목록'], ['start-transfer', '이체', 'transfer', '송금 보내기 돈'],
  ['search', '계좌 검색', 'search', '거래내역 입금 출금 조회'], ['card-search', '카드 검색', 'search', '카드 사용내역 결제 가맹점'],
  ['budget', '예산', 'target', '예산 가드 생활비 저축 목표'], ['products', '상품', 'products', '예금 적금 가입 금리 계좌 만들기'],
  ['cards', '카드', 'cards', '발급 분실 정지 한도 이용내역'], ['chat', 'AI 상담', 'chat', '챗봇 질문 물어보기'],
  ['event/opening', '그랜드 오픈 이벤트', 'gift', '은행 소개 이벤트'], ['event/welcome', '신규가입 이벤트', 'gift', '환영 이벤트 추천 적금'],
  ['act:pin', '거래 PIN 설정·변경', 'shield', '비밀번호 PIN 보안'], ['act:to-logout', '로그아웃', 'logout', '나가기 종료'],
];
const squash = (text) => String(text).toLowerCase().replace(/\s+/g, "");
// 띄어쓰기·대소문자를 무시하고 이름이나 같이 찾을 말에 들어 있으면 찾는다
export const findMenus = (query) => {
  const q = squash(query);
  return q ? MENUS.filter(([, label, , words]) => squash(label + words).includes(q)) : [];
};

/** ctx: { go, onLoggedOut } */
export function mountMenu(container, ctx) {
  container.innerHTML = header({ title: "전체 메뉴", heading: true, back: "back" }) + '<main class="ext-menu">' + stateBlock('loading', { message: '내 정보를 불러오는 중이에요…' }) + '</main>';
  const main = container.querySelector("main");

  function draw(me, notice = "") {
    // 바로가기는 아이콘 타일 4칸. 누르면 app.mjs의 data-action 라우팅이 처리한다
    main.innerHTML = '<label class="menu-search"><span class="ui-sr-only">메뉴 검색</span>' + icon("search") + '<input type="search" id="menu-search" placeholder="메뉴 검색 (예: 이체, PIN, 분실)" autocomplete="off"></label>'
      + '<ul class="menu-search-results" id="menu-search-results" aria-live="polite" hidden></ul>'
      + '<nav class="menu-shortcuts" aria-label="은행 업무">' + SHORTCUTS.map(([action, label, glyph]) =>
        '<button type="button" data-action="' + action + '">' + icon(glyph) + '<span>' + label + '</span></button>').join('') + '</nav>'
      + '<section class="card"><h2>내 정보</h2><dl>' + row("이름", esc(me.name)) + row("아이디", esc(me.login_id))
      + row("전화번호", esc(me.phone)) + row("거래 PIN", me.has_pin ? "설정됨" : "아직 설정 안 함") + "</dl></section>"
      // PIN 폼은 자주 쓰지 않아 접어 둔다. 아직 PIN이 없거나 방금 저장했을 때만 펼친다
      + group(me.has_pin ? "거래 PIN 변경" : "거래 PIN 설정", 'sage', '<form id="pin-form" novalidate>'
      + pw("password", "현재 로그인 비밀번호", 'autocomplete="current-password"')
      + pw("pin", "새 PIN (숫자 6자리)", 'inputmode="numeric" maxlength="6" pattern="[0-9]{6}"')
      + pw("pin2", "새 PIN 확인", 'inputmode="numeric" maxlength="6" pattern="[0-9]{6}"')
      + '<p class="error" id="e-form" role="alert"></p><p class="note" id="pin-ok" role="status">' + esc(notice) + '</p><button class="ui-button ui-button--primary primary" id="pin-submit">' + (me.has_pin ? "PIN 변경" : "PIN 설정") + '</button></form>', !me.has_pin || !!notice)
      + '<button type="button" class="menu-logout" data-act="to-logout">' + icon("logout") + '로그아웃</button>'
      + '<p class="note menu-version">캡아메리카뱅크 모바일 · 버전 ' + APP_VERSION + '</p>';
    const form = main.querySelector("#pin-form");
    const show = (errors) => {
      for (const k of ["password", "pin", "pin2", "form"]) main.querySelector("#e-" + k).textContent = errors[k] ?? "";
      for (const k of ["password", "pin", "pin2"]) form.elements[k].setAttribute('aria-invalid', !!errors[k]);
      const first = ["password", "pin", "pin2"].find((k) => errors[k]);
      if (first) { form.elements[first].focus(); form.elements[first].scrollIntoView({ block: 'center' }); }
    };
    main.querySelector('[data-act="to-logout"]').addEventListener("click", async () => { await logout(); ctx.onLoggedOut(); });
    const search = main.querySelector("#menu-search");
    const results = main.querySelector("#menu-search-results");
    search.addEventListener("input", () => {
      const found = findMenus(search.value);
      results.hidden = !search.value.trim();
      main.querySelector(".menu-shortcuts").hidden = !results.hidden;
      results.innerHTML = found.length
        ? found.map(([action, label, glyph]) => '<li><button type="button" ' + (action.startsWith("act:") ? 'data-act="' + action.slice(4) + '"' : 'data-action="' + action + '"') + '>' + icon(glyph) + '<span>' + label + '</span>' + icon("chevron") + '</button></li>').join("")
        : '<li class="note">찾는 메뉴가 없어요. AI 상담에 물어보세요.</li>';
    });
    // 메뉴 검색 결과 중 이 화면 안의 동작(PIN 폼 펼치기·로그아웃)
    results.addEventListener("click", async (event) => {
      const act = event.target.closest("[data-act]")?.dataset.act;
      if (act === "pin") { const box = main.querySelector(".menu-group"); box.open = true; box.scrollIntoView({ block: "start" }); box.querySelector("input")?.focus(); }
      if (act === "to-logout") { await logout(); ctx.onLoggedOut(); }
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const v = { password: form.elements.password.value, pin: form.elements.pin.value, pin2: form.elements.pin2.value };
      const errors = validatePinChange(v);
      show(errors);
      main.querySelector("#pin-ok").textContent = "";
      if (Object.keys(errors).length) return;
      const button = main.querySelector("#pin-submit");
      button.disabled = true;
      try {
        await api("/users/me/pin", { method: "PUT", body: { password: v.password, pin: v.pin } });
        draw({ ...me, has_pin: true }, "거래 PIN을 저장했어요.");
      } catch (error) {
        show(["INVALID_CREDENTIALS", "INVALID_PASSWORD"].includes(error.code) ? { password: "비밀번호가 맞지 않아요." } : { form: error.message });
        form.elements.password.value = "";
        button.disabled = false;
      }
    });
  }

  api("/users/me").then(({ data }) => draw(data)).catch((error) => {
    main.innerHTML = '<p class="error" role="alert">' + esc(error.message) + '</p><button type="button" class="outline" id="retry">다시 시도</button>';
    main.querySelector("#retry").addEventListener("click", () => mountMenu(container, ctx));
  });
}
