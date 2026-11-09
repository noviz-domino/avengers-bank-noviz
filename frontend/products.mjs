import { api, idempotencyKey } from "./api.mjs";
import { openApproval } from "./approval.mjs";

const shield = '<svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 6v10c0 8-5 14-13 18C8 30 3 24 3 16V6Z" fill="#fff" stroke="#132844" stroke-width="2.5"/><path d="M7 24c6-5 13-7 20-7" fill="none" stroke="#132844" stroke-width="3"/><path d="M10 29c4-3 9-5 14-6" fill="none" stroke="#b84039" stroke-width="3"/><path d="m16 7 1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5Z" fill="#132844"/></svg>';
const art = '<svg class="product-art" viewBox="0 0 180 160" aria-hidden="true"><ellipse cx="95" cy="147" rx="71" ry="7" fill="#d7d8bc"/><path d="m55 62-5-26q27 0 28 26" fill="#90a477"/><ellipse cx="96" cy="94" rx="60" ry="47" fill="#b6c49a"/><path d="M62 122v23h16l5-16m31-2 4 18h16v-28" fill="#98ad80"/><ellipse cx="43" cy="99" rx="25" ry="23" fill="#c7d2af"/><path d="M36 94v9m13-9v9" stroke="#6d8058" stroke-width="4" stroke-linecap="round"/><circle cx="67" cy="77" r="4" fill="#26394a"/><path d="M153 86q23-19 14-27-10-6-10 5" fill="none" stroke="#98ad80" stroke-width="5"/><path d="M89 53h29" stroke="#687c54" stroke-width="5" stroke-linecap="round"/><circle cx="104" cy="31" r="23" fill="#f0c65c" stroke="#d9a543" stroke-width="4"/><path d="m104 15 5 10 11 1-8 8 2 11-10-6-10 6 2-11-8-8 11-1Z" fill="#fff1b5"/><path d="M121 83v16c0 11-8 19-17 24-9-5-17-13-17-24V83l17-5Z" fill="#fff" opacity=".8"/><path d="m104 87 3 6 7 1-5 5 1 7-6-4-6 4 1-7-5-5 7-1Z" fill="#829668"/></svg>';
const icons = { CHECKING: "⇄", DEPOSIT: "▥", SAVINGS: "♧" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// 서버 type 값 → 화면 분류. 대출은 개설할 수 없어 목록에서 뺀다.
export const kinds = { all: "전체", CHECKING: "입출금", DEPOSIT: "예금", SAVINGS: "적금" };
const badge = { CHECKING: "⇄ 입출금", DEPOSIT: "▥ 예금", SAVINGS: "♧ 적금" };

// 금리는 서버가 문자열("3.50")로 준다. 부동소수점 오차를 피하려고 0.01% 단위 정수로 계산한다.
export const hundredths = (value) => Math.round(Number(value) * 100);
export const percent = (value) => (hundredths(value) / 100).toFixed(2) + "%";
export const maxRate = (product) => percent((hundredths(product.base_rate) + hundredths(product.max_preferential_rate)) / 100);
// 개설할 때 적용 가능한 최고 금리: 급여이체 우대는 가입 후에야 알 수 있어 뺀다. 우대 상한은 넘지 않는다.
export const openingRate = (product) => {
  const sum = (product.preferential_rates ?? []).filter((r) => r.code !== "SALARY_TRANSFER").reduce((s, r) => s + hundredths(r.rate), 0);
  return percent((hundredths(product.base_rate) + Math.min(sum, hundredths(product.max_preferential_rate))) / 100);
};
export const term = (p) => p.min_term_months
  ? (p.min_term_months === p.max_term_months ? p.min_term_months : `${p.min_term_months}~${p.max_term_months}`) + "개월"
  : "기간 제한 없음";
const won = (n) => n >= 100_000_000 ? `${n / 100_000_000}억 원` : n % 10_000 === 0 ? `${n / 10_000}만 원` : `${n.toLocaleString("ko-KR")}원`;
export const amount = (p) => p.min_amount
  ? (p.type === "SAVINGS" ? "월 " : "") + `${won(p.min_amount)}~${won(p.max_amount)}`
  : "가입 금액 제한 없음";
const isOpen = (p) => p.type !== "LOAN";

const link = (product, label, className = "") => `<a class="${className}" href="#product/${product.product_id}">${label}</a>`;
const rateNote = (product) => '<p class="product-rate-note">' + (Number(product.max_preferential_rate) ? "우대조건 충족 시 · " : "") + "세전</p>";
const header = (detail) => '<header class="topbar">' + (detail
  ? '<a class="product-back" href="#products" aria-label="상품 목록으로 돌아가기">← <span>상품 상세</span></a>'
  : '<span class="brand">' + shield + "캡아메리카뱅크</span>") + "</header>";

function rateBlock(product) {
  const bonus = Number(product.max_preferential_rate) > 0;
  return `<div class="product-rates"><div><small>${bonus ? "최고 연" : "연"}</small>
    <strong>${maxRate(product)}</strong></div><div><small>기본 연</small><b>${percent(product.base_rate)}</b></div></div>${rateNote(product)}`;
}

function featured(product) {
  return `<section class="product-feature" aria-labelledby="featured-name"><span class="product-badge">${badge[product.type]}</span>
    <h2 id="featured-name">${esc(product.name)}</h2>
    ${rateBlock(product)}${art}<div class="product-facts"><p>기간 <strong>${term(product)}</strong></p>
    <p>${product.type === "SAVINGS" ? "월 납입액" : "가입 금액"} <strong>${amount(product).replace(/^월 /, "")}</strong></p></div>
    ${link(product, '상품 자세히 보기 <span aria-hidden="true">→</span>', "primary product-cta")}</section>`;
}

function row(product) {
  return `<li>${link(product, `<span class="product-icon ${product.type.toLowerCase()}" aria-hidden="true">${icons[product.type]}</span>
    <span class="product-row-info">${product.sale_end ? '<span class="product-special">특판</span>' : ""}
    <strong>${esc(product.name)}</strong><small>${term(product)} · ${amount(product)}</small>
    ${product.min_age ? `<small>만 ${product.min_age}세 이상</small>` : ""}
    ${product.sale_end ? `<small>판매 ${esc(product.sale_start ?? "")} ~ ${esc(product.sale_end)}</small>` : ""}</span>
    <span class="product-row-rate"><small>${Number(product.max_preferential_rate) ? "최고 연" : "연"}(세전)</small><b>${maxRate(product)}</b>
    <small>기본 연 ${percent(product.base_rate)}</small></span><span class="product-chevron" aria-hidden="true">›</span>`, "product-row")}</li>`;
}

// 순수 렌더링: 서버에서 받은 상품 배열과 분류만으로 목록 화면을 만든다
export function listView(products, kind = "all") {
  if (!Object.hasOwn(kinds, kind)) kind = "all";
  const visible = products.filter((p) => isOpen(p) && (kind === "all" || p.type === kind));
  const star = visible.find((p) => p.type === "SAVINGS");
  const others = visible.filter((p) => p !== star);
  return header(false) + `<main><p class="product-eyebrow">상품</p><h1 tabindex="-1">목표를 담는 상품</h1>
    <div class="segments product-filters" role="group" aria-label="상품 종류">${Object.entries(kinds).map(([value, label]) =>
      `<button type="button" data-product-filter="${value}" aria-pressed="${value === kind}">${label}</button>`).join("")}</div>
    <div aria-live="polite" class="product-results"><p class="product-count">${kinds[kind]} 상품 ${visible.length}개</p>
    ${star ? featured(star) : ""}<section class="product-section"><h2>${star ? "함께 살펴보세요" : kinds[kind] + " 상품"}</h2>
    ${others.length ? `<ul class="product-list">${others.map(row).join("")}</ul>` : '<p class="empty">다른 상품은 다른 분류에서 살펴보세요.</p>'}</section></div>
    <p class="product-footer-note">최고금리는 우대조건 모두 충족 시 · 세전<br>가입 시 적용 가능한 우대는 상품 상세에서 확인해 주세요.</p></main>`;
}

const notFound = () => header(true) + '<main><h1 tabindex="-1">상품을 찾을 수 없어요</h1><p>판매가 끝났거나 존재하지 않는 상품이에요.</p><a href="#products" class="primary product-cta">상품 목록 보기</a></main>';

export function detailView(product) {
  const rates = product.preferential_rates ?? [];
  const salary = (r) => r.code === "SALARY_TRANSFER";
  return header(true) + `<main><section class="product-detail-hero ${product.type.toLowerCase()}">
    <span class="product-badge">${badge[product.type] ?? ""}</span><h1 tabindex="-1">${esc(product.name)}</h1><p>${esc(product.description)}</p>
    ${rateBlock(product)}</section>
    <section class="product-section"><h2>가입 조건</h2><dl><dt>가입 대상</dt><dd>${product.min_age ? `만 ${product.min_age}세 이상` : "누구나"}</dd>
    <dt>기간</dt><dd>${term(product)}</dd><dt>${product.type === "SAVINGS" ? "월 납입액" : "가입 금액"}</dt><dd>${amount(product)}</dd>
    ${product.sale_end ? `<dt>판매 기간</dt><dd>${esc(product.sale_start ?? "")}<br>~ ${esc(product.sale_end)} (포함)</dd>` : ""}</dl>
    ${product.conditions ? `<p class="note">${esc(product.conditions)}</p>` : ""}</section>
    <section class="product-section"><h2>금리와 우대조건</h2><p class="note">모든 금리는 연 기준 · 세전입니다.</p>
    <ul class="product-bonuses"><li><span>기본금리</span><b>연 ${percent(product.base_rate)}</b></li>
    ${rates.map((r) => `<li><span>${esc(r.description)}${salary(r) ? "<small>현재 가입 시 미적용</small>" : ""}</span><b>+${percent(r.rate)}p</b></li>`).join("")}</ul>
    ${rates.length ? `<p class="product-opening-rate">가입 시 적용 가능한 최고 <strong>연 ${openingRate(product)}</strong></p>
    <p class="note">가입 때 확인할 수 있는 우대조건을 모두 충족한 경우예요. 실제 적용 금리는 가입자 조건에 따라 달라져요.</p>`
      : '<p class="note">별도 우대조건이 없어요.</p>'}</section>
    <button type="button" class="primary product-cta" data-product-join>가입하기 <span aria-hidden="true">→</span></button>
    <a href="#products" class="product-more">다른 상품 살펴보기</a></main>`;
}

// 가입 입력 화면. 서버가 조건 검사를 다시 하므로 입력 힌트만 준다.
function joinView(product, accounts) {
  const checking = accounts.filter((a) => a.account_type === "CHECKING" && a.status === "ACTIVE");
  const field = (label, name, extra = "") => `<label>${label}<input name="${name}" ${extra}></label>`;
  const termField = field(`가입 기간 (${term(product)})`, "term_months", `type="number" inputmode="numeric" min="${product.min_term_months}" max="${product.max_term_months}" required`);
  const nickname = field("계좌 별칭 (선택)", "nickname", 'maxlength="20" autocomplete="off"');
  let fields = nickname;
  if (product.type === "SAVINGS") {
    fields = termField + field(`월 납입액 (${amount(product).replace(/^월 /, "")}, 원)`, "monthly_payment", `type="number" inputmode="numeric" min="${product.min_amount}" max="${product.max_amount}" required`)
      + field("납입일 (매월 1~28일)", "payment_day", 'type="number" inputmode="numeric" min="1" max="28" value="25" required') + nickname;
  } else if (product.type === "DEPOSIT") {
    fields = `<label>출금 계좌<select name="from_account_id" required>${checking.map((a) => `<option value="${a.account_id}">${esc(a.nickname || a.product_name)} · ${esc(a.account_num)} · ${a.balance.toLocaleString("ko-KR")}원</option>`).join("")}</select></label>`
      + field(`맡길 금액 (${amount(product)}, 원)`, "amount", `type="number" inputmode="numeric" min="${product.min_amount}" max="${product.max_amount}" required`) + termField + nickname;
  }
  return header(true) + `<main><h1 tabindex="-1">${esc(product.name)} 가입</h1>
    <p class="note">${product.type === "DEPOSIT" ? "신청 뒤 거래 PIN으로 승인하면 계좌가 열리고 돈이 옮겨져요." : "입력한 내용으로 바로 계좌를 개설해요."}</p>
    <form class="product-join" data-form="join">${fields}<p class="error" role="alert"></p>
    <button class="primary" type="submit" ${product.type === "DEPOSIT" && !checking.length ? "disabled" : ""}>${product.type === "DEPOSIT" ? "예금 신청하기" : "계좌 개설하기"}</button>
    <button class="outline" type="button" data-product-cancel>취소</button></form></main>`;
}

const doneView = (title, lines) => header(true) + `<main><p class="success-mark" aria-hidden="true">✓</p><h1 tabindex="-1">${esc(title)}</h1>
  <section class="card">${lines.map((line) => `<p>${esc(line)}</p>`).join("")}</section>
  <a href="#home" class="primary product-cta">홈에서 확인하기</a><a href="#products" class="product-more">다른 상품 살펴보기</a></main>`;

const errorView = (message) => header(false) + `<main><h1>상품</h1><p class="error" role="alert">${esc(message)}</p><button type="button" class="outline" data-product-retry>다시 시도</button></main>`;
const loadingView = (detail) => header(detail) + '<main><p class="empty" role="status">불러오는 중이에요.</p></main>';
const message = (e) => e?.message ?? "요청을 처리하지 못했어요.";

let kind = "all"; // 목록·상세를 오가도 분류를 유지한다

// 상품 화면. route는 location.hash.slice(1) ("products" 또는 "product/<id>")이고, 이동은 호출한 쪽이 다시 mount한다.
export function mountProducts(root, route = "") {
  let alive = true;
  let product; // 상세 상품
  let list; // 목록 (분류를 바꿔도 다시 받지 않는다)
  const id = route.startsWith("product/") ? route.slice(8) : null;
  const set = (html) => { if (alive) { root.innerHTML = html; root.querySelector("h1")?.focus({ preventScroll: true }); } };

  async function load() {
    set(loadingView(id !== null));
    try {
      if (id === null) { list = (await api("/products/accounts")).data; return set(listView(list, kind)); }
      product = (await api("/products/accounts/" + encodeURIComponent(id))).data;
      set(detailView(product));
    } catch (e) {
      set(id !== null && e.code === "PRODUCT_NOT_FOUND" ? notFound() : errorView(message(e)));
    }
  }

  async function join() {
    set(loadingView(true));
    try {
      const accounts = product.type === "DEPOSIT" ? (await api("/accounts")).data.accounts : [];
      set(joinView(product, accounts));
    } catch (e) { set(errorView(message(e))); }
  }

  // 체크·적금은 바로 개설, 예금은 승인 대기(202) 뒤 PIN 승인
  async function submit(form) {
    const data = Object.fromEntries(new FormData(form));
    const number = (key) => Number(data[key]);
    const nickname = String(data.nickname ?? "").trim() || undefined;
    const submitButton = form.querySelector("[type=submit]");
    const error = form.querySelector(".error");
    submitButton.disabled = true;
    error.textContent = "";
    try {
      if (product.type === "DEPOSIT") {
        const body = { product_id: product.product_id, from_account_id: number("from_account_id"), amount: number("amount"), term_months: number("term_months"), nickname, idempotency_key: idempotencyKey() };
        const { data: pending } = await api("/accounts/deposits", { method: "POST", body });
        const result = await openApproval(pending.action_id);
        if (result.status === "REJECTED") { error.textContent = "예금 신청을 취소했어요."; return; }
        if (result.status === "FAILED") { error.textContent = message(result.error); return; }
        return set(doneView("예금을 개설했어요", [product.name, `${number("amount").toLocaleString("ko-KR")}원 · ${number("term_months")}개월`]));
      }
      const body = { product_id: product.product_id, nickname };
      if (product.type === "SAVINGS") Object.assign(body, { term_months: number("term_months"), monthly_payment: number("monthly_payment"), payment_day: number("payment_day") });
      const { data: account } = await api("/accounts", { method: "POST", body });
      const lines = [account.product_name, "계좌번호 " + account.account_num];
      if (account.terms?.applied_rate) lines.push(`적용 금리 연 ${percent(account.terms.applied_rate)} · 만기 ${account.terms.maturity_date}`);
      set(doneView("계좌를 개설했어요", lines));
    } catch (e) {
      error.textContent = message(e);
    } finally {
      submitButton.disabled = false;
    }
  }

  function handleClick(event) {
    const target = event.target.closest("button");
    if (!target || !root.contains(target)) return;
    const filter = target.dataset.productFilter;
    if (filter !== undefined && Object.hasOwn(kinds, filter)) {
      kind = filter;
      set(listView(list, kind));
      root.querySelector(`[data-product-filter="${kind}"]`)?.focus({ preventScroll: true });
    } else if ("productJoin" in target.dataset) join();
    else if ("productCancel" in target.dataset) set(detailView(product));
    else if ("productRetry" in target.dataset) load();
  }
  function handleSubmit(event) {
    if (event.target.dataset.form !== "join" || !root.contains(event.target)) return;
    event.preventDefault();
    submit(event.target);
  }

  root.addEventListener("click", handleClick);
  root.addEventListener("submit", handleSubmit);
  load();
  return () => {
    alive = false;
    root.removeEventListener("click", handleClick);
    root.removeEventListener("submit", handleSubmit);
    root.replaceChildren();
  };
}
