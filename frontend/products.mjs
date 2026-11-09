import { products, kinds, percent, maxRate, term, amount, onSale, listedProducts, todayKst } from "./products-data.mjs";

const shield = '<svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 6v10c0 8-5 14-13 18C8 30 3 24 3 16V6Z" fill="#fff" stroke="#132844" stroke-width="2.5"/><path d="M7 24c6-5 13-7 20-7" fill="none" stroke="#132844" stroke-width="3"/><path d="M10 29c4-3 9-5 14-6" fill="none" stroke="#b84039" stroke-width="3"/><path d="m16 7 1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5Z" fill="#132844"/></svg>';
const art = '<svg class="product-art" viewBox="0 0 180 160" aria-hidden="true"><ellipse cx="95" cy="147" rx="71" ry="7" fill="#d7d8bc"/><path d="m55 62-5-26q27 0 28 26" fill="#90a477"/><ellipse cx="96" cy="94" rx="60" ry="47" fill="#b6c49a"/><path d="M62 122v23h16l5-16m31-2 4 18h16v-28" fill="#98ad80"/><ellipse cx="43" cy="99" rx="25" ry="23" fill="#c7d2af"/><path d="M36 94v9m13-9v9" stroke="#6d8058" stroke-width="4" stroke-linecap="round"/><circle cx="67" cy="77" r="4" fill="#26394a"/><path d="M153 86q23-19 14-27-10-6-10 5" fill="none" stroke="#98ad80" stroke-width="5"/><path d="M89 53h29" stroke="#687c54" stroke-width="5" stroke-linecap="round"/><circle cx="104" cy="31" r="23" fill="#f0c65c" stroke="#d9a543" stroke-width="4"/><path d="m104 15 5 10 11 1-8 8 2 11-10-6-10 6 2-11-8-8 11-1Z" fill="#fff1b5"/><path d="M121 83v16c0 11-8 19-17 24-9-5-17-13-17-24V83l17-5Z" fill="#fff" opacity=".8"/><path d="m104 87 3 6 7 1-5 5 1 7-6-4-6 4 1-7-5-5 7-1Z" fill="#829668"/></svg>';
const icons = { checking: "⇄", deposit: "▥", savings: "♧" };
const link = (product, label, className = "") => `<a class="${className}" href="#product/${product.id}">${label}</a>`;
const rateNote = (product) => product.bonuses.some((bonus) => !bonus.available)
  ? '<p class="product-rate-note">우대조건 모두 충족 시 · 세전<br>급여이체 우대는 현재 가입 시 미적용</p>'
  : '<p class="product-rate-note">' + (product.bonuses.length ? "우대조건 충족 시 · " : "") + '세전</p>';
const header = (detail, embedded = false) => (embedded ? "" : '<div class="demo-label">DEMO · 실제 가입과 자금 이동이 없는 시연 화면</div>')
  + '<header class="topbar">' + (detail
    ? '<a class="product-back" href="#products" aria-label="상품 목록으로 돌아가기">← <span>상품 상세</span></a>'
    : '<span class="brand">' + shield + '캡아메리카뱅크</span>') + '</header>';

function rateBlock(product) {
  return `<div class="product-rates"><div><small>${product.bonuses.length ? "최고 연" : "연"}</small>
    <strong>${percent(maxRate(product))}</strong></div><div><small>기본 연</small><b>${percent(product.baseRate)}</b></div></div>${rateNote(product)}`;
}

function featured(product) {
  return `<section class="product-feature" aria-labelledby="featured-name"><span class="product-badge">♧ 적금</span>
    <h2 id="featured-name">${product.name}</h2><p class="product-headline">${product.headline}</p>
    ${rateBlock(product)}${art}<div class="product-facts"><p>기간 <strong>${term(product)}</strong></p>
    <p>월 납입액 <strong>${amount(product).replace(/^월 /, "")}</strong></p></div>
    ${link(product, '상품 자세히 보기 <span aria-hidden="true">→</span>', "primary product-cta")}</section>`;
}

function row(product) {
  return `<li>${link(product, `<span class="product-icon ${product.kind}" aria-hidden="true">${icons[product.kind]}</span>
    <span class="product-row-info">${product.saleEnd ? '<span class="product-special">특판</span>' : ""}
    <strong>${product.name}</strong><small>${term(product)} · ${amount(product)}</small>
    ${product.minAge ? `<small>만 ${product.minAge}세 이상</small>` : ""}
    ${product.saleEnd ? `<small>판매 ${product.saleStart} ~ ${product.saleEnd}</small>` : ""}</span>
    <span class="product-row-rate"><small>${product.bonuses.length ? "최고 연" : "연"}(세전)</small><b>${percent(maxRate(product))}</b>
    <small>기본 연 ${percent(product.baseRate)}</small></span><span class="product-chevron" aria-hidden="true">›</span>`, "product-row")}
    ${product.bonuses.length ? `<div class="product-row-note">${rateNote(product)}</div>` : ""}</li>`;
}

export function renderProducts(route = "", kind = "all", today = todayKst(), embedded = false) {
  const id = route.startsWith("product/") ? route.slice(8) : null;
  if (id !== null) {
    const product = products.find((item) => item.id === id && onSale(item, today));
    if (!product) return header(true, embedded) + '<main><h1 tabindex="-1">상품을 찾을 수 없어요</h1><p>판매가 끝났거나 존재하지 않는 상품이에요.</p><a href="#products" class="primary product-cta">상품 목록 보기</a></main>';
    return header(true, embedded) + `<main><section class="product-detail-hero ${product.kind}">
      <span class="product-badge">${kinds[product.kind]}</span><h1 tabindex="-1">${product.name}</h1><p>${product.description}</p>
      ${rateBlock(product)}</section>
      <section class="product-section"><h2>가입 조건</h2><dl><dt>가입 대상</dt><dd>${product.minAge ? `만 ${product.minAge}세 이상` : "누구나"}</dd>
      <dt>기간</dt><dd>${term(product)}</dd><dt>${product.kind === "savings" ? "월 납입액" : "가입 금액"}</dt><dd>${amount(product)}</dd>
      ${product.saleEnd ? `<dt>판매 기간</dt><dd>${product.saleStart}<br>~ ${product.saleEnd} (포함)</dd>` : ""}</dl></section>
      <section class="product-section"><h2>금리와 우대조건</h2><p class="note">모든 금리는 연 기준 · 세전입니다.</p>
      <ul class="product-bonuses"><li><span>기본금리</span><b>연 ${percent(product.baseRate)}</b></li>
      ${product.bonuses.map((bonus) => `<li><span>${bonus.label}${!bonus.available ? '<small>현재 가입 시 미적용</small>' : ""}</span><b>+${percent(bonus.rate)}p</b></li>`).join("")}</ul>
      ${product.bonuses.length ? `<p class="product-opening-rate">가입 시 적용 가능한 최고 <strong>연 ${percent(maxRate(product, true))}</strong></p>
      <p class="note">가입 때 확인할 수 있는 우대조건을 모두 충족한 경우예요. 실제 적용 금리는 가입자 조건에 따라 달라져요.</p>`
        : '<p class="note">별도 우대조건이 없어요.</p>'}</section>
      <section class="card product-notice"><h2>가입 전 확인해 주세요</h2><p>데모 상품 안내입니다. 이 화면에서는 계좌 개설이나 상품 가입을 실행하지 않아요.</p>
      <p>예·적금 금리는 가입일에 확정되며, 급여이체처럼 가입 후 확인하는 우대는 현재 가입 시 적용하지 않아요.</p></section>
      <a href="#products" class="primary product-cta">다른 상품 살펴보기</a></main>`;
  }
  if (!Object.hasOwn(kinds, kind)) kind = "all";
  const visible = listedProducts(kind, today);
  const star = visible.find((product) => product.id === "stark");
  const others = visible.filter((product) => product !== star);
  return header(false, embedded) + `<main><p class="product-eyebrow">상품</p><h1 tabindex="-1">목표를 담는 상품</h1>
    <div class="segments product-filters" role="group" aria-label="상품 종류">${Object.entries(kinds).map(([value, label]) =>
      `<button type="button" data-product-filter="${value}" aria-pressed="${value === kind}">${label}</button>`).join("")}</div>
    <div aria-live="polite" class="product-results"><p class="product-count">${kinds[kind]} 상품 ${visible.length}개</p>
    ${star ? featured(star) : ""}<section class="product-section"><h2>${star ? "함께 살펴보세요" : kinds[kind] + " 상품"}</h2>
    ${others.length ? `<ul class="product-list">${others.map(row).join("")}</ul>` : '<p class="empty">다른 상품은 다른 분류에서 살펴보세요.</p>'}</section></div>
    <p class="product-footer-note">최고금리는 우대조건 모두 충족 시 · 세전 · 데모 상품<br>가입 시 적용 가능한 우대는 상품 상세에서 확인해 주세요.</p></main>`;
}

// 통합 단계에서는 상품 전용 컨테이너에 mount하고, 이탈할 때 반환된 함수를 호출한다.
export function mountProducts(root) {
  const view = root.ownerDocument.defaultView;
  let kind = "all";
  const render = () => { root.innerHTML = renderProducts(view.location.hash.slice(1), kind); };
  const navigate = () => {
    render();
    root.querySelector("h1")?.focus({ preventScroll: true });
    view.scrollTo(0, 0);
  };
  const filter = (event) => {
    const button = event.target.closest("[data-product-filter]");
    if (!button || !Object.hasOwn(kinds, button.dataset.productFilter)) return;
    kind = button.dataset.productFilter;
    render();
    root.querySelector(`[data-product-filter="${kind}"]`)?.focus({ preventScroll: true });
  };
  root.addEventListener("click", filter);
  view.addEventListener("hashchange", navigate);
  render();
  return () => {
    root.removeEventListener("click", filter);
    view.removeEventListener("hashchange", navigate);
  };
}
