// 공통 부품은 문자열만 만든다. 서버 값은 esc, 조합한 부품만 *Html 인자로 넘긴다.
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const paths = {
  back: '<path d="m14 5-7 7 7 7M7 12h13"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  chevron: '<path d="m8 4 8 8-8 8"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  wallet: '<path d="M20 8V5a2 2 0 0 0-2-2L5 6a3 3 0 0 0-2 3v10a2 2 0 0 0 2 2h15V8H5a2 2 0 0 1 0-4"/><path d="M20 12h-5a2 2 0 0 0 0 4h5"/>',
  pig: '<path d="M7 7c-2 1-3 3-3 5H2v4h3l2 4h3v-3h5v3h3l2-5c2-1 2-5 0-6V5l-4 2H7Z"/><path d="M9 7V5a3 3 0 1 1 6 0v2M8 11h.01"/>',
  clock: '<path d="M3 5v5h5M3 10a9 9 0 1 1 0 5M12 6v6l4 3"/>',
  home: '<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z"/>',
  products: '<path d="m2 8 10-5 10 5-10 5Zm1 5 9 5 9-5M3 18l9 5 9-5"/>',
  chat: '<path d="M21 11c0 5-4 8-9 8l-8 3 2-6a7 7 0 0 1-3-5c0-5 4-8 9-8s9 3 9 8Z"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>',
  cards: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  transfer: '<path d="M4 8h15m-4-4 4 4-4 4M20 16H5m4-4-4 4 4 4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
  logout: '<path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9"/>',
  menu: '<rect x="3" y="3" width="6" height="6" rx="2"/><rect x="15" y="3" width="6" height="6" rx="2"/><rect x="3" y="15" width="6" height="6" rx="2"/><rect x="15" y="15" width="6" height="6" rx="2"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="m3 3 18 18M10 5a12 12 0 0 1 12 7s-1 3-4 5M6 6a20 20 0 0 0-4 6s4 7 10 7c2 0 4-.6 5-1.5M10 10a3 3 0 0 0 4 4"/>',
  pause: '<path d="M9 6v12M15 6v12"/>',
  play: '<path d="m9 5 10 7-10 7Z"/>',
  single: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3 10h18"/>',
  list: '<path d="M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  send: '<path d="M12 19V5m-6 6 6-6 6 6"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  bell: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  gift: '<rect x="3" y="9" width="18" height="12" rx="2"/><path d="M3 13h18M12 9v12M12 9C8 9 6 4 9 4s3 5 3 5Zm0 0c4 0 6-5 3-5s-3 5-3 5Z"/>',
  shield: '<path d="M12 3 20 6v6c0 5-3 8-8 10-5-2-8-5-8-10V6Z"/><path d="m9 12 2 2 4-4"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12h.01"/>',
};
export function icon(name) {
  return `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] ?? ""}</svg>`;
}

export function button(label, { action, variant = "quiet", icon: glyph, ariaLabel, pressed, className = "" } = {}) {
  return `<button type="button" class="ui-button ui-button--${esc(variant)} ${esc(className)}"${action ? ` data-action="${esc(action)}"` : ""}${ariaLabel ? ` aria-label="${esc(ariaLabel)}"` : ""}${pressed === undefined ? "" : ` aria-pressed="${!!pressed}"`}>${glyph ? icon(glyph) : ""}${esc(label)}</button>`;
}

// 간편 로그인 버튼: 둥근 정사각형 안에 로고(위)와 플랫폼 이름(아래)을 함께 넣어 글자까지 누르는 영역이 되게 한다 (아직 연결 전이면 action으로 안내만)
const socialLogos = {
  google: '<svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>',
  naver: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="5" fill="#03C75A"/><path fill="#fff" d="M13.7 12.4 10.1 7H7v10h3.3v-5.4l3.6 5.4H17V7h-3.3z"/></svg>',
};
const socialLabels = { google: "Google", naver: "NAVER" };
export function socialButton(provider, { action = "social-soon" } = {}) {
  return `<button type="button" class="ui-social ui-social--${esc(provider)}" data-action="${esc(action)}" aria-label="${esc(socialLabels[provider] ?? provider)} 간편로그인">${socialLogos[provider] ?? ""}<span>${esc(socialLabels[provider] ?? provider)}</span></button>`;
}

export function carouselPager(page, count, { previous, next }) {
  return `<div class="ui-carousel-controls">
    ${button("", { action: previous, icon: "back", ariaLabel: "이전 배너" })}
    <span class="ui-carousel-page" role="status">${esc(page)} / ${esc(count)}</span>
    ${button("", { action: next, icon: "arrow", ariaLabel: "다음 배너" })}
  </div>`;
}

// heading: 탭 화면처럼 상단바 제목이 곧 페이지 제목일 때 h1로 그린다 (본문에 pageTitle을 또 두지 않는다)
// menu: true면 오른쪽 끝에 전체 메뉴 버튼을 둔다 (탭 화면 공통 레이아웃. 전체 메뉴는 하단 탭에서 뺐다)
export function header({ title = "", brandHtml = "", back, rightHtml = "", heading = false, menu = false } = {}) {
  const tag = heading ? "h1" : "div";
  return `<header class="ui-header">${back ? button("", { action: back, icon: "back", ariaLabel: "뒤로 가기", className: "ui-back" }) : ""}<${tag} class="ui-header-title">${brandHtml || esc(title)}</${tag}><div class="ui-header-actions">${rightHtml}${menu ? button("", { action: "menu", icon: "menu", ariaLabel: "전체 메뉴" }) : ""}</div></header>`;
}
// 아이콘만 있는 둘 중 하나 고르기. options: [[값, 아이콘, 읽어 줄 이름]], attr은 화면 모듈의 액션 속성 이름
export function iconToggle(options, { label, current, prefix = "", attr = "data-action" }) {
  return `<div class="ui-icon-toggle" role="group" aria-label="${esc(label)}">${options.map(([value, glyph, name]) =>
    `<button type="button" ${attr}="${esc(prefix + value)}" aria-label="${esc(name)}" title="${esc(name)}" aria-pressed="${value === current}">${icon(glyph)}</button>`).join("")}</div>`;
}
export const pageTitle = (title) => `<h1 class="ui-page-title">${esc(title)}</h1>`;

export function sectionHead({ title, count, total = "", icon: glyph, tone = "blue", action, expanded, controls, rightHtml = "" }) {
  const content = `<span class="ui-section-label">${icon(glyph)}<strong>${esc(title)}${count === undefined ? "" : ` <span>${esc(count)}개</span>`}</strong></span><span class="ui-section-end">${total ? `<span>${esc(total)}</span>` : ""}${action ? icon("down") : rightHtml}</span>`;
  return action
    ? `<h2 class="ui-section-head ui-tone-${esc(tone)}"><button type="button" data-action="${esc(action)}" aria-expanded="${!!expanded}" aria-controls="${esc(controls)}">${content}</button></h2>`
    : `<div class="ui-section-head ui-tone-${esc(tone)}"><h2>${icon(glyph)}${esc(title)}</h2>${rightHtml}</div>`;
}

export function listRow({ title, subtitle = "", amount, action, buttonHtml = "", icon: glyph, tone = "blue", credit = false }) {
  const copy = `<span class="ui-row-copy"><strong>${esc(title)}</strong><small>${esc(subtitle)}</small></span>`;
  return `<li class="ui-row">${glyph ? `<span class="ui-row-icon ui-tone-${esc(tone)}">${icon(glyph)}</span>` : ""}${action ? `<button type="button" class="ui-row-title account-link" data-action="${esc(action)}">${copy}</button>` : `<div class="ui-row-title">${copy}</div>`}<div class="ui-row-end right"><strong${credit ? ' class="ui-credit"' : ""}>${esc(amount)}</strong>${buttonHtml}</div></li>`;
}
export const cardBox = (contentHtml, className = "") => `<section class="ui-card ${esc(className)}">${contentHtml}</section>`;

export function stateBlock(kind, { message, retryAction } = {}) {
  const defaults = { loading: "불러오고 있어요…", empty: "아직 표시할 내용이 없어요.", error: "불러오지 못했어요. 다시 시도해 주세요." };
  return `<div class="ui-state ui-state--${esc(kind)}"><p role="${kind === "error" ? "alert" : "status"}">${esc(message ?? defaults[kind])}</p>${retryAction ? button("다시 시도", { action: retryAction, variant: "outline" }) : ""}</div>`;
}

export function field({ id, label, name = id, type = "text", value = "", hint = "", error = "", required = false, autocomplete }) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).map(esc).join(" ");
  return `<div class="ui-field"><label for="${esc(id)}">${esc(label)}</label><input id="${esc(id)}" name="${esc(name)}" type="${esc(type)}" value="${esc(value)}"${required ? " required" : ""}${autocomplete ? ` autocomplete="${esc(autocomplete)}"` : ""}${describedBy ? ` aria-describedby="${describedBy}"` : ""} aria-invalid="${!!error}">${hint ? `<p class="ui-hint" id="${esc(id)}-hint">${esc(hint)}</p>` : ""}${error ? `<p class="ui-field-error" id="${esc(id)}-error" role="alert">${esc(error)}</p>` : ""}</div>`;
}

export function maskAccountNumber(number) {
  const match = /^(\d{3})-?\d{3}-?(\d{6})$/.exec(String(number ?? ""));
  return match ? `${match[1]}-***-${match[2]}` : "***";
}

export function bottomTabs(page) {
  return '<nav class="ui-tabs" aria-label="주 메뉴">' + [["home", "홈", "home"], ["accounts", "계좌", "wallet"], ["cards", "카드", "cards"], ["products", "상품", "products"], ["chat", "AI 상담", "chat"]].map(([action, label, glyph]) =>
    `<button type="button" class="ui-tab" data-action="${action}"${page === action ? ' aria-current="page"' : ""}>${icon(glyph)}<span>${label}</span></button>`).join("") + "</nav>";
}

// 다시 그리기 직전에 호출하고, 같은 화면의 새 DOM을 만든 뒤 반환 함수를 실행한다.
export function restoreFocus(root) {
  const active = root.ownerDocument.activeElement;
  if (!active || !root.contains(active)) return () => {};
  const key = ["data-action", "id", "name"].find((attr) => active.getAttribute(attr));
  if (!key) return () => {};
  const value = active.getAttribute(key);
  const start = active.selectionStart;
  const end = active.selectionEnd;
  return () => {
    const next = [...root.querySelectorAll(`[${key}]`)].find((element) => element.getAttribute(key) === value);
    next?.focus({ preventScroll: true });
    if (start != null && next?.setSelectionRange) next.setSelectionRange(start, end);
  };
}
