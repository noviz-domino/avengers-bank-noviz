// 보관된 로그인 시안 C (글자 + 사선 띠). 2026-11-11 시안 비교에서 B를 골라 앱에서는 뺐다.
// 원래 frontend/login-variants.mjs에 있던 코드 (입력칸 fields·링크 link 도우미 포함, 이 파일만으로 완결).
// 필요한 것: app.mjs의 shield·socialLogo (loginView 대신 이 함수를 부르면 된다)
import { esc } from "./ui.mjs";

const fields = (busy, error, notice) =>
  '<label>아이디<input name="login_id" required autocomplete="username" maxlength="50"></label>'
  + '<label>비밀번호<input name="password" type="password" required autocomplete="current-password"></label>'
  + (notice ? '<p class="note" role="status">' + esc(notice) + "</p>" : "")
  + '<p class="error" role="alert">' + esc(error) + "</p>"
  + '<button class="primary"' + (busy ? " disabled" : "") + ">" + (busy ? "로그인 중…" : "로그인") + "</button>";
const link = (action, label) => '<button type="button" data-action="' + action + '">' + label + "</button>";


// C. 그림 없이 글자로 여는 왼쪽 정렬 구성. 카드의 사선 띠를 위에 두고 입력칸은 밑줄만
export function loginC({ error, notice, busy }, { shield, socialLogo }) {
  return '<main class="login-c"><div class="lc-band" aria-hidden="true"></div>'
    + '<span class="lc-mark" aria-hidden="true">' + shield + "</span><h1>안녕하세요,<br>캡아메리카뱅크입니다</h1>"
    + '<form data-form="login">' + fields(busy, error, notice) + "</form>"
    + '<p class="lc-links">처음이신가요? ' + link("signup", "회원가입") + '<i aria-hidden="true"></i>' + link("demo-login", "데모 계정으로 둘러보기") + "</p>"
    + '<ul class="lc-social" aria-label="간편 로그인">'
    + '<li><button type="button" data-action="social-soon">' + socialLogo.google + "<span>Google로 계속하기</span></button></li>"
    + '<li><button type="button" data-action="social-soon">' + socialLogo.naver + "<span>네이버로 계속하기</span></button></li></ul>"
    + '<p class="note" role="status" data-social-note></p></main>';
}
