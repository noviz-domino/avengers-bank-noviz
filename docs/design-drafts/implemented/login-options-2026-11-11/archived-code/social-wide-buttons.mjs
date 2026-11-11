// 보관된 간편 로그인 안: 가로로 긴 버튼 두 줄 (2026-11-11 PR #46 리뷰 중 만들었다가 둥근 정사각형 타일로 바꿈)
// 원래 frontend/ui.mjs의 socialButton. 로고 SVG(socialLogos)는 지금 ui.mjs에 그대로 있다.
const socialLabels = { google: "구글 간편로그인", naver: "네이버 간편로그인" };
export function socialButton(provider, { action = "social-soon" } = {}) {
  return `<button type="button" class="ui-social ui-social--${esc(provider)}" data-action="${esc(action)}">${socialLogos[provider] ?? ""}<span>${esc(socialLabels[provider] ?? provider)}</span></button>`;
}
