// 회원가입 화면 (#signup). 가입이 끝나면 바로 로그인한다.
import { api, login } from "./api.mjs";
import { fieldErrors, topbar } from "./ext-ui.mjs";

const LABELS = { login_id: "아이디", password: "비밀번호", name: "이름", phone: "전화번호", birth_date: "생년월일" };

// 서버 UserCreate 규칙과 같게 검사한다 (서버가 최종 판단, 여기는 빠른 안내용)
export function validateSignup(v, today = new Date().toISOString().slice(0, 10)) {
  const e = {};
  if (v.login_id.length < 4 || v.login_id.length > 50) e.login_id = "아이디는 4~50자로 입력해 주세요.";
  if (v.password.length < 8 || v.password.length > 128) e.password = "비밀번호는 8자 이상 입력해 주세요.";
  else if (v.password !== v.password2) e.password2 = "비밀번호가 서로 달라요.";
  if (!/^[가-힣a-zA-Z]+( [가-힣a-zA-Z]+)*$/.test(v.name) || v.name.length > 30) e.name = "이름은 한글·영문과 띄어쓰기만, 30자까지 입력할 수 있어요.";
  if (!/^[0-9-]{9,20}$/.test(v.phone)) e.phone = "전화번호는 숫자와 -로 9~20자 입력해 주세요.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v.birth_date) || v.birth_date >= today) e.birth_date = "생년월일을 오늘 이전 날짜로 입력해 주세요.";
  return e;
}

const field = (name, label, attrs = "") =>
  '<label>' + label + '<input name="' + name + '" required aria-describedby="e-' + name + '" ' + attrs + '></label><p class="error" id="e-' + name + '" role="alert"></p>';

/** container에 회원가입 화면을 그린다. ctx: { go, onSignedIn } */
export function mountSignup(container, ctx) {
  container.innerHTML = topbar("회원가입", "to-login") + '<main><form class="ext-form" novalidate><h1 class="ui-page-title">새로 가입해요</h1>'
    + field("login_id", "아이디", 'autocomplete="username" maxlength="50" autocapitalize="none"')
    + field("password", "비밀번호 (8자 이상)", 'type="password" autocomplete="new-password" maxlength="128"')
    + field("password2", "비밀번호 확인", 'type="password" autocomplete="new-password" maxlength="128"')
    + field("name", "이름", 'autocomplete="name" maxlength="30"')
    + field("phone", "전화번호", 'type="tel" inputmode="tel" autocomplete="tel" placeholder="010-1234-5678" maxlength="20"')
    + field("birth_date", "생년월일", 'type="date" autocomplete="bday"')
    + '<label class="check"><input type="checkbox" name="marketing_agreed"> 마케팅 정보 수신에 동의해요 (선택)</label>'
    + '<p class="error" id="e-form" role="alert"></p><button class="primary" id="signup-submit">가입하기</button></form></main>';
  const form = container.querySelector("form");
  const show = (errors) => {
    for (const k of [...Object.keys(LABELS), "password2", "form"]) container.querySelector("#e-" + k).textContent = errors[k] ?? "";
    for (const k of [...Object.keys(LABELS), "password2"]) form.elements[k].setAttribute('aria-invalid', !!errors[k]);
    const first = Object.keys(errors).find((k) => form.elements[k]);
    if (first) form.elements[first].focus();
  };
  container.querySelector('[data-act="to-login"]').addEventListener("click", () => ctx.go("login"));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const d = new FormData(form);
    const v = Object.fromEntries(["login_id", "name", "phone", "birth_date"].map((k) => [k, String(d.get(k)).trim()]));
    v.password = String(d.get("password")); // 비밀번호는 공백도 그대로
    v.password2 = String(d.get("password2"));
    const errors = validateSignup(v);
    show(errors);
    if (Object.keys(errors).length) return;
    const button = container.querySelector("#signup-submit");
    button.disabled = true;
    try {
      await api("/users/signup", { method: "POST", auth: false, body: { login_id: v.login_id, password: v.password, name: v.name, phone: v.phone, birth_date: v.birth_date, marketing_agreed: d.get("marketing_agreed") === "on" } });
      await login(v.login_id, v.password);
      ctx.onSignedIn();
    } catch (error) {
      if (error.code === "LOGIN_ID_ALREADY_EXISTS") show({ login_id: "이미 사용 중인 아이디예요." });
      else show({ ...fieldErrors(error, LABELS), form: error.status === 422 ? "입력값을 확인해 주세요." : error.message });
      button.disabled = false;
    }
  });
  form.elements.login_id.focus();
}
