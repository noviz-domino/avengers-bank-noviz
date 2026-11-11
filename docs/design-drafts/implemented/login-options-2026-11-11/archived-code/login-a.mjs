// 보관된 로그인 시안 A (캐릭터 + 알약). 2026-11-11 시안 비교에서 B를 골라 앱에서는 뺐다.
// 원래 frontend/app.mjs 안에 있던 코드. 다시 쓰려면 app.mjs에 붙이고 login-a.css를 styles.css에 합친다.
// 필요한 것: app.mjs의 shield·socialLogo·button·escape·loginState
// 로그인 화면 캐릭터: 망토를 두르고 은행 방패를 든 동글이 (장식이라 읽어 주지 않음)
const mascot = '<svg class="mascot" viewBox="0 0 160 150" aria-hidden="true">'
  + '<ellipse cx="80" cy="142" rx="46" ry="6" fill="#132844" opacity=".08"/>'
  + '<path d="M50 66Q38 118 50 134H110Q122 118 110 66Z" fill="#b84039"/>'
  + '<path d="m80 8 4 8.5 9.3 1.2-6.8 6.4 1.8 9.2L80 28.8l-8.3 4.5 1.8-9.2-6.8-6.4 9.3-1.2Z" fill="#e0a43a"/>'
  + '<rect x="46" y="36" width="68" height="96" rx="34" fill="#fff" stroke="#132844" stroke-width="4"/>'
  + '<circle cx="68" cy="72" r="5.5" fill="#132844"/><circle cx="92" cy="72" r="5.5" fill="#132844"/>'
  + '<circle cx="70" cy="70" r="1.8" fill="#fff"/><circle cx="94" cy="70" r="1.8" fill="#fff"/>'
  + '<ellipse cx="60" cy="85" rx="6" ry="3.6" fill="#f3b9b1"/><ellipse cx="100" cy="85" rx="6" ry="3.6" fill="#f3b9b1"/>'
  + '<path d="M72 86q8 8 16 0" fill="none" stroke="#132844" stroke-width="3.5" stroke-linecap="round"/>'
  + '<path d="M48 96Q30 88 30 66" fill="none" stroke="#132844" stroke-width="4" stroke-linecap="round"/>'
  + '<circle cx="30" cy="61" r="6.5" fill="#fff" stroke="#132844" stroke-width="3.5"/>'
  + '<ellipse cx="67" cy="136" rx="10" ry="5" fill="#132844"/><ellipse cx="93" cy="136" rx="10" ry="5" fill="#132844"/>'
  + '<g transform="translate(96 82) scale(1.45)">' + shield.replace(/^<svg[^>]*>|<\/svg>$/g, "") + "</g></svg>";

function login() {
  const { error, notice, busy } = loginState;
  return '<main class="login"><div class="login-head">' + mascot
    + '<h1 class="login-brand">' + shield + "캡아메리카뱅크</h1></div>"
    // 입력칸 이름은 칸 안 안내 글로 보여 주고, 화면 낭독용 label은 숨겨 둔다
    + '<form data-form="login"><label><span class="ui-sr-only">아이디</span><input name="login_id" placeholder="아이디" required autocomplete="username" maxlength="50"></label>'
    + '<label><span class="ui-sr-only">비밀번호</span><input name="password" type="password" placeholder="비밀번호" required autocomplete="current-password"></label>'
    + (notice ? '<p class="note" role="status">' + escape(notice) + "</p>" : "")
    + '<p class="error" role="alert">' + escape(error) + '</p>'
    + '<button class="primary"' + (busy ? " disabled" : "") + '>' + (busy ? "로그인 중…" : "로그인") + "</button>"
    + "</form>"
    + '<div class="login-links">' + button("signup", "회원가입", "link") + '<i aria-hidden="true"></i>' + button("demo-login", "데모 계정으로 둘러보기", "link") + "</div>"
    // 간편 로그인은 자리만 잡아 둔다. 아직 연결 전이라 누르면 준비 중 안내만 한다
    + '<section class="login-social" aria-label="간편 로그인"><p class="login-or">간편 로그인</p><div>'
    + '<button type="button" data-action="social-soon">' + socialLogo.google + "Google</button>"
    + '<button type="button" data-action="social-soon">' + socialLogo.naver + "네이버</button></div>"
    + '<p class="note" role="status" data-social-note></p></section></main>';
}
