// 회원가입·메뉴·검색 화면이 함께 쓰는 작은 도구 (HTML 이스케이프, 머리글, 서버 오류 표시)
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const won = (n) => Number(n).toLocaleString("ko-KR") + "원";

export function topbar(title, backAct) {
  return '<header class="topbar"><div>' + (backAct ? '<button type="button" class="back" data-act="' + backAct + '" aria-label="뒤로 가기">←</button>' : "")
    + esc(title) + "</div></header>";
}

// 서버 422 details를 { 필드: 메시지 }로 바꾼다. 서버 문구는 영어라 필드별 안내만 보여 준다.
export function fieldErrors(error, labels) {
  const out = {};
  for (const d of error.details ?? []) {
    const key = d.loc?.[d.loc.length - 1];
    if (labels[key]) out[key] = labels[key] + " 형식을 확인해 주세요.";
  }
  return out;
}
