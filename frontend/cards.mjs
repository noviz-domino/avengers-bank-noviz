import { money } from "./demo.mjs";
import { changeCardStatus, demoMonth, monthTotal, monthTransactions, newCardsDemo } from "./cards-demo.mjs";

const shield = '<svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 6v10c0 8-5 14-13 18C8 30 3 24 3 16V6Z" fill="#fff8e9" stroke="#132844" stroke-width="2.5"/><path d="M7 24c6-5 13-7 20-7M10 28c4-3 9-5 14-6" fill="none" stroke="#132844" stroke-width="2.5"/><path d="M11 29c4-3 8-4 12-5" fill="none" stroke="#b84039" stroke-width="2"/><path d="m16 7 1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5Z" fill="#132844"/></svg>';
const icons = {
  history: '<rect x="6" y="3" width="20" height="26" rx="3"/><path d="M11 10h10M11 16h10M11 22h6"/>',
  benefits: '<rect x="4" y="12" width="24" height="17" rx="2"/><path d="M2 8h28v7H2zM16 8v21M16 8C5 9 6 0 11 3c3 1 5 5 5 5Zm0 0c11 1 10-8 5-5-3 1-5 5-5 5Z"/>',
  manage: '<path d="m13 3-1 4-4 2-4-1-2 5 3 3-1 5 4 2 2 5h6l2-4 5-1 3-4-2-4 1-5-5-2-2-4Z"/><circle cx="14" cy="16" r="5"/>',
  cafe: '<path d="M5 12h18v10a7 7 0 0 1-7 7h-4a7 7 0 0 1-7-7ZM23 13h3a4 4 0 0 1 0 8h-3M9 3v4M15 3v4M21 3v4"/>',
  shop: '<path d="M3 4h4l4 18h15l4-13H8M13 28h1M25 28h1"/>',
  store: '<path d="M5 14v15h22V14M3 13l4-9h18l4 9M3 13q4 7 9 0 4 7 9 0 4 7 8 0M12 29V19h8v10"/>',
};
const icon = (name) => `<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const statusText = (card) => ({ ACTIVE: "사용 중", SUSPENDED: "일시정지", LOST: "분실 신고" }[card.status]);
const button = (action, label, className = "quiet", extra = "") => `<button type="button" class="${className}" data-card-action="${action}" ${extra}>${label}</button>`;

function artwork(card, miniature = false) {
  return `<div class="cards-art ${card.type === "CREDIT" ? "cards-art-credit" : ""} ${miniature ? "cards-art-mini" : ""}" aria-hidden="true">
    <span class="cards-art-title">${card.name}</span><span class="cards-chip"></span>
    <span class="cards-art-shield">${shield}</span><span class="cards-art-number">•••• ${card.last4}</span>
  </div>`;
}

function transactionRows(transactions) {
  if (!transactions.length) return '<p class="empty">이달 이용내역이 없어요.</p>';
  return `<ul class="rows cards-transactions">${transactions.map((tx) => `<li>
    <span class="cards-tx-icon ${tx.category === "카페" ? "green" : tx.category === "편의점" ? "blue" : "amber"}">${icon(tx.category === "카페" ? "cafe" : tx.category === "편의점" ? "store" : "shop")}</span>
    <span class="cards-tx-name"><strong>${escape(tx.name)}</strong><small>${tx.date.slice(5).replace("-", ".")} · ${tx.category}</small></span>
    <strong>${money(tx.amount)}</strong></li>`).join("")}</ul>`;
}

// Owns only the supplied root; the common app router can mount/unmount this at integration.
export function mountCards(root, { cards = newCardsDemo(), embedded = false } = {}) {
  let selectedId = cards[0].id;
  let view = "large";
  let page = "overview";
  let confirmStatus = "";
  let focusReturn;
  const selected = () => cards.find((card) => card.id === selectedId);

  function selection(card) {
    const picker = `<div class="cards-view" role="group" aria-label="카드 보기 방식">
      ${button("view-large", "▣ 크게 보기", "", `aria-pressed="${view === "large"}"`)}
      ${button("view-list", "☷ 목록 보기", "", `aria-pressed="${view === "list"}"`)}</div>`;
    if (view === "list") return `${picker}<section aria-label="보유 카드"><h2>보유 카드 ${cards.length}장</h2><div class="cards-list">${cards.map((item) => button(`select-${item.id}`,
      `${artwork(item, true)}<span class="cards-list-info"><strong>${item.name}</strong><span>•••• ${item.last4}</span><small class="cards-status ${item.status === "ACTIVE" ? "" : "cards-status-alert"}">${statusText(item)}</small></span><span class="cards-check" aria-hidden="true">${item.id === card.id ? "✓" : "›"}</span>`,
      "cards-list-item", `aria-pressed="${item.id === card.id}" aria-label="${item.name} 끝 네 자리 ${item.last4}, ${statusText(item)}"`)).join("")}</div></section>`;
    return `${picker}<section aria-label="보유 카드"><div class="spread"><h2>내 카드 한 장</h2><span class="note">${cards.findIndex((item) => item.id === card.id) + 1} / ${cards.length}</span></div>
      <div class="cards-type" role="group" aria-label="카드 선택">${cards.map((item) => button(`select-${item.id}`, item.type === "DEBIT" ? "체크카드" : "신용카드", "", `aria-pressed="${item.id === card.id}"`)).join("")}</div>
      ${artwork(card)}<div class="cards-selected"><strong>${card.name}</strong><span>•••• ${card.last4} <span class="cards-status ${card.status === "ACTIVE" ? "" : "cards-status-alert"}">${statusText(card)}</span></span></div></section>`;
  }

  function summary(card) {
    return `<section class="cards-summary" aria-label="선택 카드 이용 요약"><div class="spread"><h2>11월 이용금액</h2><strong>${money(monthTotal(card))}</strong></div>
      <p>${card.account}</p><small>${card.type === "DEBIT" ? "체크카드 결제는 연결 계좌에서 바로 출금돼요." : `매월 ${card.paymentDay}일 결제 · 신용 미결제 사용액 ${money(card.outstanding)}`}</small></section>`;
  }

  function overview(card) {
    return `${selection(card)}${summary(card)}<nav class="cards-actions" aria-label="선택 카드 메뉴">
      ${[ ["history", "이용내역"], ["benefits", "카드 혜택"], ["manage", "카드 관리"] ].map(([action, label]) => button(action, `${icon(action)}<span>${label}</span>`, "")).join("")}</nav>
      <section><div class="spread"><h2>최근 이용내역</h2>${button("history", "전체보기 ›")}</div>${transactionRows(monthTransactions(card).slice(0, 3))}</section>`;
  }

  function detail(card) {
    if (page === "history") return `<h1>이용내역</h1><p class="note">2026년 11월 · ${card.name}</p>${summary(card)}${transactionRows(monthTransactions(card))}`;
    if (page === "benefits") return `<h1>카드 혜택</h1><p class="note">${card.name}</p><section class="cards-summary"><h2>상품 혜택 안내</h2><p>${card.benefits}</p></section>
      <dl><dt>연회비</dt><dd>${money(card.annualFee)}</dd></dl><p class="note">데모 상품 설명입니다. 실제 할인액·남은 혜택 집계는 제공하지 않아요. 세부 적용 조건은 상품 약관 확인이 필요해요.</p>`;
    if (page === "limit") return `<h1>한도 확인</h1><p class="note">${card.name}</p><section class="cards-summary"><dl><dt>1일 이용 한도</dt><dd>${money(card.dailyLimit)}</dd>${card.type === "CREDIT" ? `<dt>신용 한도</dt><dd>${money(card.creditLimit)}</dd><dt>신용 미결제 사용액</dt><dd>${money(card.outstanding)}</dd><dt>신용 잔여 한도</dt><dd>${money(card.creditLimit - card.outstanding)}</dd>` : ""}</dl></section>
      <p class="note">월 이용금액은 ${money(monthTotal(card))}이에요. ${card.type === "CREDIT" ? "신용 미결제 사용액은 지난달 사용액도 포함할 수 있어 월 이용금액과 달라요. 신용 잔여 한도는 오늘 결제 가능한 금액과 달라요." : "체크카드 결제는 연결 계좌 잔액과 오늘 사용한 금액에 따라서도 제한돼요."} 한도 변경은 제공하지 않아요.</p>`;
    return `<h1>카드 관리</h1><p class="note">${card.name} · •••• ${card.last4}</p><section class="cards-summary"><dl><dt>카드 상태</dt><dd>${statusText(card)}</dd><dt>연결 계좌</dt><dd>${card.account}</dd>${card.type === "CREDIT" ? `<dt>대금 결제일</dt><dd>매월 ${card.paymentDay}일</dd>` : ""}</dl></section>
      ${button("limit", '한도 확인 <span aria-hidden="true">›</span>', "cards-manage-row")}
      ${button("suspend", "일시정지", "cards-manage-row", card.status !== "ACTIVE" ? "disabled" : "")}
      ${button("lost", "분실 신고", "cards-manage-row cards-danger", card.status === "LOST" ? "disabled" : "")}
      <p class="note">정지·분실은 이 카드 데모에만 적용돼요. 정지 해제에는 PIN 승인이 필요하며 이 화면에서는 제공하지 않아요. 분실 신고 후에는 재발급이 필요해요. 새로고침하면 데모 상태가 초기화돼요.</p>`;
  }

  function render() {
    const card = selected();
    root.innerHTML = `${embedded ? "" : '<div class="demo-label">카드 전용 데모 · 2026.11 · 실제 결제·API 연결 없음</div>'}
      <header class="topbar"><div>${page === "overview" ? `<span class="brand">${shield}캡아메리카뱅크</span>` : button(page === "limit" ? "manage" : "overview", "←", "back", 'aria-label="뒤로 가기"') + '<span>내 카드</span>'}</div></header>
      <main>${page === "overview" ? '<div class="spread"><h1>카드</h1><span class="cards-demo-tag">내 지갑 한눈에</span></div>' + overview(card) : detail(card)}</main>
      <footer class="cards-footer">시연 기준 ${demoMonth} · 카드 ${cards.length}장<br>${embedded ? "실제 결제·API 연결 없음 · 로그아웃하면 초기화돼요." : "카드 전용 데모 · 실제 결제·API 연결 없음"}</footer>
      <dialog class="cards-dialog"><h2 id="cards-confirm-title">${confirmStatus === "LOST" ? "분실 신고할까요?" : "일시정지할까요?"}</h2><p>${card.name} · •••• ${card.last4}</p><p class="note">${confirmStatus === "LOST" ? "분실 신고 후에는 다시 사용할 수 없어요. 재발급이 필요해요." : "카드 사용을 잠시 멈춰요. 정지 해제는 PIN 승인이 필요해요."} 이 변경은 데모에만 적용돼요.</p><div class="cards-dialog-actions">${button("cancel", "취소", "outline")}${button("confirm", "데모에서 적용", "primary")}</div></dialog>`;
    if (confirmStatus) {
      const dialog = root.querySelector("dialog");
      dialog.setAttribute("aria-labelledby", "cards-confirm-title");
      dialog.addEventListener("close", () => { confirmStatus = ""; focusReturn?.focus(); });
      dialog.showModal();
      dialog.querySelector('[data-card-action="cancel"]').focus();
    }
  }

  function handleClick(event) {
    const target = event.target.closest("[data-card-action]");
    if (!target || !root.contains(target)) return;
    const action = target.dataset.cardAction;
    if (action === "cancel") return root.querySelector("dialog").close();
    if (action === "suspend" || action === "lost") {
      confirmStatus = action === "lost" ? "LOST" : "SUSPENDED";
      render();
      focusReturn = root.querySelector(`[data-card-action="${action}"]`);
      return;
    }
    if (action === "confirm") {
      changeCardStatus(selected(), confirmStatus);
      confirmStatus = "";
    } else if (action.startsWith("view-")) view = action.slice(5);
    else if (action.startsWith("select-")) selectedId = action.slice(7);
    else page = action;
    render();
    const focusTarget = action.startsWith("view-") || action.startsWith("select-")
      ? root.querySelector(`[data-card-action="${action}"]`) : root.querySelector("h1");
    if (focusTarget?.tagName === "H1") focusTarget.setAttribute("tabindex", "-1");
    focusTarget?.focus();
  }

  root.addEventListener("click", handleClick);
  render();
  return () => { root.removeEventListener("click", handleClick); root.replaceChildren(); };
}
