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

/** ctx: { go, onLoggedOut } */
export function mountMenu(container, ctx) {
  container.innerHTML = header({ title: "전체 메뉴", heading: true }) + '<main class="ext-menu">' + stateBlock('loading', { message: '내 정보를 불러오는 중이에요…' }) + '</main>';
  const main = container.querySelector("main");

  function draw(me, notice = "") {
    // 바로가기는 아이콘 타일 4칸. 누르면 app.mjs의 data-action 라우팅이 처리한다
    main.innerHTML = '<nav class="menu-shortcuts" aria-label="은행 업무">' + [['home', '계좌', 'wallet'], ['start-transfer', '이체', 'transfer'], ['search', '거래 검색', 'search'], ['budget', '예산', 'target'], ['products', '상품', 'products'], ['cards', '카드', 'cards'], ['chat', 'AI 상담', 'chat']].map(([action, label, glyph]) =>
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
