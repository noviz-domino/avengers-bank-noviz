// 로그인 화면 (2026-11-11 시안 비교에서 고른 B: 네이비 배경 + 흰 시트).
// 고르지 않은 A·C는 앱에 두지 않고 docs/design-drafts/implemented/login-options-2026-11-11/archived-code/ 에 기록으로만 남겼다.
// 폼 이름·액션(data-form="login", signup, demo-login, social-soon)의 동작은 app.mjs가 처리한다.
import { esc, socialButton } from "./ui.mjs";

const fields = (busy, error, notice) =>
  // 입력칸 이름은 칸 안의 흐린 안내 글로 보여 주고, 화면 낭독용 label은 숨겨 둔다
  '<label><span class="ui-sr-only">아이디</span><input name="login_id" placeholder="아이디" required autocomplete="username" maxlength="50"></label>'
  + '<label><span class="ui-sr-only">비밀번호</span><input name="password" type="password" placeholder="비밀번호" required autocomplete="current-password"></label>'
  + (notice ? '<p class="note" role="status">' + esc(notice) + "</p>" : "")
  + '<p class="error" role="alert">' + esc(error) + "</p>"
  + '<button class="primary"' + (busy ? " disabled" : "") + ">" + (busy ? "로그인 중…" : "로그인") + "</button>";
const link = (action, label) => '<button type="button" data-action="' + action + '">' + label + "</button>";

// 네이비 배경 위로 흰 시트가 올라오는 구성. 인사말이 주인공이고 아래 흰 시트에 폼과 간편 로그인
export function loginView({ error, notice, busy }, { shield }) {
  return '<main class="login-b"><div class="lb-hero"><span class="lb-watermark" aria-hidden="true">' + shield + "</span>"
    + '<p class="lb-brand">' + shield + "캡아메리카뱅크</p><h1>다시 만나서<br>반가워요</h1><p>로그인하고 내 자산을 확인하세요.</p></div>"
    + '<div class="lb-sheet"><form data-form="login">' + fields(busy, error, notice) + "</form>"
    + '<div class="lb-links">' + link("signup", "회원가입") + '<i aria-hidden="true"></i>' + link("demo-login", "데모 계정으로 둘러보기") + "</div>"
    // 흐린 구분선 가운데에 "간편 로그인", 그 아래 가운데에 둥근 정사각형 버튼 두 개(로고 + 이름)
    + '<section class="lb-social" aria-label="간편 로그인"><p class="lb-or">간편 로그인</p><div>'
    + socialButton("google") + socialButton("naver") + "</div></section>"
    + '<p class="note" role="status" data-social-note></p></div></main>';
}
