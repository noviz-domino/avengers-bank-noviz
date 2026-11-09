// 전체 메뉴·설정 화면 (#menu): 내 정보, 거래 PIN 설정·변경, 거래 검색 링크, 로그아웃, 앱 정보
import { api, logout } from "./api.mjs";
import { esc, topbar } from "./ext-ui.mjs";

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
const pw = (name, label, extra = "") => '<label>' + label + '<input name="' + name + '" type="password" required autocomplete="off" ' + extra + '></label><p class="error" id="e-' + name + '" role="alert"></p>';

/** ctx: { go, onLoggedOut } */
export function mountMenu(container, ctx) {
  container.innerHTML = topbar("전체 메뉴", "to-home") + '<main class="ext-menu"><p class="status" role="status">내 정보를 불러오는 중이에요…</p></main>';
  const main = container.querySelector("main");
  container.querySelector('[data-act="to-home"]').addEventListener("click", () => ctx.go("home"));

  function draw(me, notice = "") {
    main.innerHTML = '<section class="card"><h2>내 정보</h2><dl>' + row("이름", esc(me.name)) + row("아이디", esc(me.login_id))
      + row("전화번호", esc(me.phone)) + row("거래 PIN", me.has_pin ? "설정됨" : "아직 설정 안 함") + "</dl></section>"
      + '<section class="card"><h2>' + (me.has_pin ? "거래 PIN 변경" : "거래 PIN 설정") + '</h2><form id="pin-form" novalidate>'
      + pw("password", "현재 로그인 비밀번호", 'autocomplete="current-password"')
      + pw("pin", "새 PIN (숫자 6자리)", 'inputmode="numeric" maxlength="6" pattern="[0-9]{6}"')
      + pw("pin2", "새 PIN 확인", 'inputmode="numeric" maxlength="6" pattern="[0-9]{6}"')
      + '<p class="error" id="e-form" role="alert"></p><p class="note" id="pin-ok" role="status">' + notice + '</p><button class="primary" id="pin-submit">' + (me.has_pin ? "PIN 변경" : "PIN 설정") + '</button></form></section>'
      + '<section class="card menu-list"><button type="button" data-act="to-search">거래내역 검색<span aria-hidden="true">›</span></button>'
      + '<button type="button" data-act="to-logout">로그아웃<span aria-hidden="true">›</span></button></section>'
      + '<section class="card"><h2>앱 정보</h2><dl>' + row("앱", "캡아메리카뱅크 모바일") + row("버전", APP_VERSION) + "</dl></section>";
    const form = main.querySelector("#pin-form");
    const show = (errors) => {
      for (const k of ["password", "pin", "pin2", "form"]) main.querySelector("#e-" + k).textContent = errors[k] ?? "";
      const first = ["password", "pin", "pin2"].find((k) => errors[k]);
      if (first) form.elements[first].focus();
    };
    main.querySelector('[data-act="to-search"]').addEventListener("click", () => ctx.go("search"));
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
        show({ form: error.code === "INVALID_CREDENTIALS" ? "비밀번호가 맞지 않아요." : error.message });
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
