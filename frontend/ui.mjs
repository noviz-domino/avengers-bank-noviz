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
  menu: '<rect x="3" y="3" width="6" height="6" rx="2"/><rect x="15" y="3" width="6" height="6" rx="2"/><rect x="3" y="15" width="6" height="6" rx="2"/><rect x="15" y="15" width="6" height="6" rx="2"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="m3 3 18 18M10 5a12 12 0 0 1 12 7s-1 3-4 5M6 6a20 20 0 0 0-4 6s4 7 10 7c2 0 4-.6 5-1.5M10 10a3 3 0 0 0 4 4"/>',
  pause: '<path d="M9 6v12M15 6v12"/>',
  play: '<path d="m9 5 10 7-10 7Z"/>',
};
export function icon(name) {
  return `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] ?? ""}</svg>`;
}

export function button(label, { action, variant = "quiet", icon: glyph, ariaLabel, pressed, className = "" } = {}) {
  return `<button type="button" class="ui-button ui-button--${esc(variant)} ${esc(className)}"${action ? ` data-action="${esc(action)}"` : ""}${ariaLabel ? ` aria-label="${esc(ariaLabel)}"` : ""}${pressed === undefined ? "" : ` aria-pressed="${!!pressed}"`}>${glyph ? icon(glyph) : ""}${esc(label)}</button>`;
}

export function header({ title = "", brandHtml = "", back, rightHtml = "" } = {}) {
  return `<header class="ui-header">${back ? button("", { action: back, icon: "back", ariaLabel: "뒤로 가기", className: "ui-back" }) : ""}<div class="ui-header-title">${brandHtml || esc(title)}</div><div class="ui-header-actions">${rightHtml}</div></header>`;
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
  return '<nav class="ui-tabs" aria-label="주 메뉴">' + [["home", "홈"], ["products", "상품"], ["chat", "AI 상담"], ["cards", "카드"], ["menu", "전체"]].map(([action, label]) =>
    `<button type="button" class="ui-tab" data-action="${action}"${page === action ? ' aria-current="page"' : ""}>${icon(action)}<span>${label}</span></button>`).join("") + "</nav>";
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
