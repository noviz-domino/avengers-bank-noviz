// 로그인 화면 시안 B·C. B가 선택되어 기본 화면이다 (2026-11-11).
// 고르지 않은 C와 app.mjs의 A도 기록으로 남겨 두며, 주소에 ?login=a 또는 ?login=c 를 붙이면 보인다.
// 폼 이름·액션(data-form="login", signup, demo-login, social-soon)은 세 시안이 같아서 동작은 app.mjs가 그대로 처리한다.
import { esc } from "./ui.mjs";

const fields = (busy, error, notice) =>
  '<label>아이디<input name="login_id" required autocomplete="username" maxlength="50"></label>'
  + '<label>비밀번호<input name="password" type="password" required autocomplete="current-password"></label>'
  + (notice ? '<p class="note" role="status">' + esc(notice) + "</p>" : "")
  + '<p class="error" role="alert">' + esc(error) + "</p>"
  + '<button class="primary"' + (busy ? " disabled" : "") + ">" + (busy ? "로그인 중…" : "로그인") + "</button>";
const link = (action, label) => '<button type="button" data-action="' + action + '">' + label + "</button>";

// B. 네이비 배경 위로 흰 시트가 올라오는 구성. 인사말이 주인공이고 간편 로그인은 동그란 아이콘
export function loginB({ error, notice, busy }, { shield, socialLogo }) {
  return '<main class="login-b"><div class="lb-hero"><span class="lb-watermark" aria-hidden="true">' + shield + "</span>"
    + '<p class="lb-brand">' + shield + "캡아메리카뱅크</p><h1>다시 만나서<br>반가워요</h1><p>로그인하고 내 자산을 확인하세요.</p></div>"
    + '<div class="lb-sheet"><form data-form="login">' + fields(busy, error, notice) + "</form>"
    + '<div class="lb-links">' + link("signup", "회원가입") + '<i aria-hidden="true"></i>' + link("demo-login", "데모 계정으로 둘러보기") + "</div>"
    + '<div class="lb-social"><span>간편 로그인</span>'
    + '<button type="button" data-action="social-soon" aria-label="Google로 로그인">' + socialLogo.google + "</button>"
    + '<button type="button" data-action="social-soon" aria-label="네이버로 로그인">' + socialLogo.naver + "</button></div>"
    + '<p class="note" role="status" data-social-note></p></div></main>';
}

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
