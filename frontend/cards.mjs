import { api, idempotencyKey } from "./api.mjs";
import { openApproval } from "./approval.mjs";
import { esc as escape, header, stateBlock, restoreFocus, maskAccountNumber, iconToggle, icon as uiIcon, button as uiButton } from "./ui.mjs";

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
const won = (amount) => `${Number(amount ?? 0).toLocaleString("ko-KR")}원`;
const typeText = (card) => card.card_type === "DEBIT" ? "체크" : "신용";
const titles = { history: "이용내역", benefits: "카드 혜택", limit: "한도 확인", manage: "카드 관리", issue: "카드 발급" };
const statusText = (card) => ({ ACTIVE: "사용 중", SUSPENDED: "일시정지", LOST: "분실 신고" }[card.status] ?? card.status);
const button = (action, label, className = "quiet", extra = "") => `<button type="button" class="${className}${["primary", "outline", "quiet"].includes(className) ? ` ui-button ui-button--${className}` : ""}" data-card-action="${action}" ${extra}>${label}</button>`;

// 순수 함수: 서버 값을 화면용으로 바꾼다 (테스트 대상)
export const last4 = (card) => String(card.masked_card_num ?? "").slice(-4);
export const cardName = (card) => card.nickname || card.product_name;
const kstFormat = (iso) => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date(iso));
export const kstMonth = (iso = new Date().toISOString()) => kstFormat(iso).slice(0, 7);
export const monthTransactions = (transactions, month = kstMonth()) => transactions.filter((tx) => kstMonth(tx.approved_at) === month);
// 취소된 결제는 이용금액에서 뺀다
export const monthTotal = (transactions, month = kstMonth()) => monthTransactions(transactions, month)
  .filter((tx) => tx.status === "APPROVED").reduce((sum, tx) => sum + tx.amount, 0);

function artwork(card, miniature = false) {
  return `<div class="cards-art ${card.card_type === "CREDIT" ? "cards-art-credit" : ""} ${miniature ? "cards-art-mini" : ""}" aria-hidden="true">
    <span class="cards-art-title">${escape(cardName(card))}</span><span class="cards-chip"></span>
    <span class="cards-art-shield">${shield}</span><span class="cards-art-number">•••• ${escape(last4(card))}</span>
  </div>`;
}

const txIcon = (tx) => /카페|커피/.test(tx.category) ? ["green", "cafe"] : /편의점/.test(tx.category) ? ["blue", "store"] : ["amber", "shop"];
function transactionRows(transactions) {
  if (!transactions.length) return stateBlock("empty", { message: "이달 이용내역이 없어요." });
  return `<ul class="rows cards-transactions">${transactions.map((tx) => {
    const [color, name] = txIcon(tx);
    const canceled = tx.status !== "APPROVED";
    return `<li><span class="cards-tx-icon ${color}">${icon(name)}</span>
    <span class="cards-tx-name"><strong>${escape(tx.merchant_name)}</strong><small>${kstFormat(tx.approved_at).slice(5).replace("-", ".")} · ${escape(tx.category)}${canceled ? " · 취소됨" : ""}</small></span>
    <strong>${canceled ? "−" : ""}${won(tx.amount)}</strong></li>`;
  }).join("")}</ul>`;
}

// 카드 화면. 서버 데이터를 불러와 root에만 그리고, 반환된 함수로 정리한다.
export function mountCards(root, { embedded = false } = {}) {
  let alive = true;
  let loading = true;
  let error = "";
  let notice = "";
  let busy = false;
  let cards = [];
  let accounts = [];
  let products = [];
  const extra = {}; // card_id → { transactions, limits, error }
  let selectedId;
  let view = "large";
  let page = "overview";
  let confirmStatus = "";
  let focusReturn;
  const selected = () => cards.find((card) => card.card_id === selectedId);
  const accountLabel = (id) => {
    const account = accounts.find((item) => item.account_id === id);
    return account ? `${escape(account.nickname || account.product_name)} · ${maskAccountNumber(account.account_num)}` : "연결 계좌";
  };
  const productOf = (card) => products.find((item) => item.name === card.product_name);
  const message = (e) => e?.message ?? "요청을 처리하지 못했어요.";

  async function loadAll() {
    loading = true; error = ""; render();
    try {
      [cards, accounts, products] = await Promise.all([
        api("/cards").then((r) => r.data),
        api("/accounts").then((r) => r.data.accounts),
        api("/products/cards").then((r) => r.data).catch(() => []), // 혜택 문구만 못 불러와도 화면은 연다
      ]);
      // 처음 열 때는 쓸 수 있는 카드(분실 아님)를 먼저 보여 준다. 분실 카드는 목록에 기록으로 남는다
      selectedId = cards.find((card) => card.card_id === selectedId)?.card_id ?? (cards.find((card) => card.status !== "LOST") ?? cards[0])?.card_id;
    } catch (e) { error = message(e); }
    loading = false;
    if (!alive) return;
    render();
    if (selectedId !== undefined) loadCard(selectedId);
  }

  // 카드 상세·사용내역·한도를 함께 불러온다 (선택할 때마다 새로 확인)
  async function loadCard(id) {
    extra[id] = { loading: true };
    try {
      const [detail, transactions, limits] = await Promise.all([
        api(`/cards/${id}`).then((r) => r.data),
        api(`/cards/${id}/transactions`).then((r) => r.data),
        api(`/cards/${id}/limits`).then((r) => r.data),
      ]);
      cards = cards.map((card) => card.card_id === id ? detail : card);
      extra[id] = { transactions, limits };
    } catch (e) { extra[id] = { error: message(e) }; }
    if (alive) render();
  }

  function selection(card) {
    if (view === "list") return `<section aria-label="보유 카드"><h2>보유 카드 ${cards.length}장</h2><div class="cards-list">${cards.map((item) => button(`select-${item.card_id}`,
      `${artwork(item, true)}<span class="cards-list-info"><strong>${escape(cardName(item))}</strong><span>•••• ${escape(last4(item))}</span><small class="cards-status ${item.status === "ACTIVE" ? "" : "cards-status-alert"}">${statusText(item)}</small></span><span class="cards-check" aria-hidden="true">${item.card_id === card.card_id ? "✓" : "›"}</span>`,
      "cards-list-item", `aria-pressed="${item.card_id === card.card_id}" aria-label="${escape(cardName(item))} 끝 네 자리 ${escape(last4(item))}, ${statusText(item)}"`)).join("")}</div></section>`;
    // 카드가 한 장이면 고를 것이 없으니 선택 줄을 그리지 않는다. 이름은 카드 그림에 이미 있다
    return `<section aria-label="보유 카드">${cards.length > 1 ? `<div class="cards-type" role="group" aria-label="카드 선택">${cards.map((item) => button(`select-${item.card_id}`, `${typeText(item)} ${escape(last4(item))}`, "", `aria-pressed="${item.card_id === card.card_id}"`)).join("")}</div>` : ""}
      ${artwork(card)}<div class="cards-selected"><span>${typeText(card)}카드 •••• ${escape(last4(card))}</span><span class="cards-status ${card.status === "ACTIVE" ? "" : "cards-status-alert"}">${statusText(card)}</span></div></section>`;
  }

  function summary(card) {
    const data = extra[card.card_id] ?? {};
    const total = data.transactions ? won(monthTotal(data.transactions)) : "…";
    const credit = card.card_type === "CREDIT";
    return `<section class="cards-summary" aria-label="선택 카드 이용 요약"><div class="spread"><h2>이달 이용금액</h2><strong>${total}</strong></div>
      <p>${accountLabel(card.linked_account_id)}</p><small>${credit
        ? `매월 ${card.payment_day}일 결제${data.limits ? ` · 신용 미결제 사용액 ${won(data.limits.credit_used)}` : ""}`
        : "체크카드 결제는 연결 계좌에서 바로 출금돼요."}</small></section>`;
  }

  const cardData = (card, render) => {
    const data = extra[card.card_id];
    if (!data || data.loading) return stateBlock("loading");
    if (data.error) return stateBlock("error", { message: data.error, retryAction: "retry-card" }).replace('data-action=', 'data-card-action=');
    return render(data);
  };

  function overview(card) {
    return `${selection(card)}${summary(card)}<nav class="cards-actions" aria-label="선택 카드 메뉴">
      ${[["history", "이용내역"], ["benefits", "카드 혜택"], ["manage", "카드 관리"]].map(([action, label]) => button(action, `${icon(action)}<span>${label}</span>`, "")).join("")}</nav>
      <section><h2>최근 이용내역</h2>
      ${cardData(card, (data) => transactionRows(monthTransactions(data.transactions).slice(0, 3)))}</section>`;
  }

  function detail(card) {
    const product = productOf(card);
    if (page === "history") return `<p class="note">${kstMonth().replace("-", "년 ")}월 · ${escape(cardName(card))}</p>${summary(card)}
      ${cardData(card, (data) => transactionRows(monthTransactions(data.transactions)))}`;
    if (page === "benefits") return `<p class="note">${escape(cardName(card))}</p><section class="cards-summary"><h2>상품 혜택 안내</h2><p>${escape(product?.benefits ?? "혜택 안내를 불러오지 못했어요.")}</p></section>
      ${product ? `<dl><dt>연회비</dt><dd>${won(product.annual_fee)}</dd></dl>` : ""}<p class="note">실제 할인액·남은 혜택 집계는 제공하지 않아요. 세부 적용 조건은 상품 약관 확인이 필요해요.</p>`;
    if (page === "limit") return `<p class="note">${escape(cardName(card))}</p>
      ${cardData(card, ({ limits, transactions }) => `<section class="cards-summary"><dl><dt>1일 이용 한도</dt><dd>${won(limits.daily_limit)}</dd><dt>오늘 사용액</dt><dd>${won(limits.daily_used)}</dd>${card.card_type === "CREDIT" ? `<dt>신용 한도</dt><dd>${won(limits.credit_limit)}</dd><dt>신용 미결제 사용액</dt><dd>${won(limits.credit_used)}</dd><dt>신용 잔여 한도</dt><dd>${won(limits.credit_limit - limits.credit_used)}</dd>` : ""}</dl></section>
      <p class="note">월 이용금액은 ${won(monthTotal(transactions))}이에요. ${card.card_type === "CREDIT" ? "신용 미결제 사용액은 지난달 사용액도 포함할 수 있어 월 이용금액과 달라요. 신용 잔여 한도는 오늘 결제 가능한 금액과 달라요." : "체크카드 결제는 연결 계좌 잔액과 오늘 사용한 금액에 따라서도 제한돼요."} 한도 변경은 제공하지 않아요.</p>`)}`;
    return `<p class="note">${escape(cardName(card))} · •••• ${escape(last4(card))}</p><section class="cards-summary"><dl><dt>카드 상태</dt><dd>${statusText(card)}</dd><dt>연결 계좌</dt><dd>${accountLabel(card.linked_account_id)}</dd>${card.card_type === "CREDIT" ? `<dt>대금 결제일</dt><dd>매월 ${card.payment_day}일</dd>` : ""}</dl></section>
      ${notice ? `<p class="note" role="status">${escape(notice)}</p>` : ""}
      ${button("limit", '한도 확인 <span aria-hidden="true">›</span>', "cards-manage-row")}
      ${card.status === "SUSPENDED" ? button("unsuspend", "정지 해제 (PIN 승인)", "cards-manage-row", busy ? "disabled" : "") : button("suspend", "일시정지", "cards-manage-row", card.status !== "ACTIVE" || busy ? "disabled" : "")}
      ${button("lost", "분실 신고", "cards-manage-row cards-danger", card.status === "LOST" || busy ? "disabled" : "")}
      <p class="note">정지는 바로 적용돼요. 정지 해제에는 PIN 승인이 필요해요. 분실 신고는 되돌릴 수 없고 새 카드를 발급받아야 해요.</p>`;
  }

  function issueForm() {
    const checking = accounts.filter((account) => account.account_type === "CHECKING" && account.status === "ACTIVE");
    if (error) return "";
    return `<form class="cards-issue" data-form="issue">
      <fieldset><legend>카드 상품</legend>${products.map((product, index) => `<label class="cards-issue-option"><input type="radio" name="product_id" value="${product.product_id}" data-type="${escape(product.type)}" ${index === 0 ? "checked" : ""}>
        <span><strong>${escape(product.name)}</strong><small>${product.type === "CREDIT" ? "신용" : "체크"} · 연회비 ${won(product.annual_fee)}<br>${escape(product.benefits)}</small></span></label>`).join("") || '<p class="empty">발급 가능한 카드 상품이 없어요.</p>'}</fieldset>
      <label>연결할 입출금 계좌<select name="linked_account_id" required>${checking.map((account) => `<option value="${account.account_id}">${escape(account.nickname || account.product_name)} · ${escape(account.account_num)}</option>`).join("")}</select></label>
      <label data-credit-only hidden>대금 결제일 (매월 1~28일)<input name="payment_day" type="number" inputmode="numeric" min="1" max="28" value="14"></label>
      <p class="error" role="alert"></p>
      <button class="primary" type="submit" ${products.length && checking.length ? "" : "disabled"}>카드 발급하기</button></form>`;
  }

  function body() {
    if (loading) return `<main>${stateBlock("loading", { message: "카드를 불러오는 중이에요." })}</main>`;
    if (error) return `<main>${stateBlock("error", { message: error, retryAction: "reload" }).replace('data-action=', 'data-card-action=')}</main>`;
    if (page === "issue") return `<main>${issueForm()}</main>`;
    const card = selected();
    if (!card) return `<main>${stateBlock("empty", { message: "아직 발급받은 카드가 없어요." })}${notice ? `<p class="note" role="status">${escape(notice)}</p>` : ""}${button("issue", "카드 발급받기", "primary")}</main>`;
    return `<main>${page === "overview" ? `${notice ? `<p class="note" role="status">${escape(notice)}</p>` : ""}${overview(card)}` : detail(card)}</main>`;
  }

  function render() {
    const focus = restoreFocus(root);
    const activeAction = root.contains(root.ownerDocument.activeElement) ? root.ownerDocument.activeElement.dataset.cardAction : undefined;
    const card = selected();
    const back = page === "limit" ? "manage" : "overview";
    const tools = card && !loading && !error && page === "overview"
      ? iconToggle([["large", "single", "카드 크게 보기"], ["list", "list", "카드 목록으로 보기"]], { label: "카드 보기 방식", current: view, prefix: "view-", attr: "data-card-action" })
        // 머리글에 버튼이 5개라 발급은 아이콘만 (읽어 줄 이름은 "카드 발급")
        + button("issue", uiIcon("plus"), "quiet", 'aria-label="카드 발급" title="카드 발급"') : "";
    root.innerHTML = `${page === "overview" || (!card && page !== "issue")
      // 카드 검색·전체 메뉴 버튼은 data-action 그대로 앱 라우팅으로
      ? header({ title: "카드", heading: true, rightHtml: tools + uiButton("", { action: "card-search", icon: "search", ariaLabel: "카드 검색" }), menu: true })
      : header({ title: titles[page], heading: true, back }).replace('data-action=', 'data-card-action=')}
      ${body()}
      <dialog class="cards-dialog" aria-labelledby="cards-confirm-title">${confirmStatus && card ? `<h2 id="cards-confirm-title">${confirmStatus === "LOST" ? "분실 신고할까요?" : "일시정지할까요?"}</h2><p>${escape(cardName(card))} · •••• ${escape(last4(card))}</p><p class="note">${confirmStatus === "LOST" ? "분실 신고 후에는 다시 사용할 수 없어요. 되돌릴 수 없고 새 카드를 발급받아야 해요." : "카드 사용을 잠시 멈춰요. 정지 해제는 PIN 승인이 필요해요."}</p><div class="cards-dialog-actions">${button("cancel", "취소", "outline")}${button("confirm", confirmStatus === "LOST" ? "분실 신고" : "일시정지", "primary")}</div>` : ""}</dialog>`;
    focus();
    if (activeAction) root.querySelector(`[data-card-action="${activeAction}"]`)?.focus({ preventScroll: true });
    if (confirmStatus && card) {
      const dialog = root.querySelector("dialog");
      dialog.addEventListener("close", () => { confirmStatus = ""; focusReturn?.focus(); });
      dialog.showModal();
      dialog.querySelector('[data-card-action="cancel"]').focus();
    }
  }

  // 정지·분실은 바로, 해제는 PIN 승인 뒤에 반영된다
  async function changeStatus(action) {
    const card = selected();
    busy = true; notice = ""; render();
    try {
      if (action === "unsuspend") {
        const { data } = await api(`/cards/${card.card_id}/unsuspend`, { method: "POST", body: { idempotency_key: idempotencyKey() } });
        const result = await openApproval(data.action_id);
        notice = result.status === "EXECUTED" ? "정지를 해제했어요." : result.status === "REJECTED" ? "정지 해제 요청을 취소했어요." : message(result.error);
      } else {
        await api(`/cards/${card.card_id}/suspend`, { method: "POST", body: { reason: action } });
        notice = action === "LOST" ? "분실 신고를 접수했어요. 새 카드를 발급받아 주세요." : "카드를 일시정지했어요.";
      }
    } catch (e) { notice = message(e); }
    busy = false;
    if (!alive) return;
    await loadCard(card.card_id);
  }

  async function submitIssue(form) {
    const data = new FormData(form);
    const type = form.querySelector("[name=product_id]:checked")?.dataset.type;
    const body = { product_id: Number(data.get("product_id")), linked_account_id: Number(data.get("linked_account_id")) };
    if (type === "CREDIT") body.payment_day = Number(data.get("payment_day"));
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const { data: card } = await api("/cards", { method: "POST", body });
      cards = [...cards, card];
      selectedId = card.card_id;
      page = "overview";
      notice = "카드를 발급했어요.";
      render();
      loadCard(card.card_id);
    } catch (e) {
      form.querySelector(".error").textContent = message(e);
      submit.disabled = false;
    }
  }

  function handleSubmit(event) {
    if (event.target.dataset.form !== "issue" || !root.contains(event.target)) return;
    event.preventDefault();
    submitIssue(event.target);
  }
  const handleChange = (event) => {
    if (event.target.name !== "product_id") return;
    root.querySelector("[data-credit-only]").hidden = event.target.dataset.type !== "CREDIT";
  };

  function handleClick(event) {
    const target = event.target.closest("[data-card-action]");
    if (!target || !root.contains(target)) return;
    event.stopPropagation();
    const action = target.dataset.cardAction;
    if (action === "cancel") return root.querySelector("dialog").close();
    if (action === "reload") return loadAll();
    if (action === "retry-card") return loadCard(selectedId);
    if (action === "suspend" || action === "lost") {
      confirmStatus = action === "lost" ? "LOST" : "SUSPENDED";
      focusReturn = target;
      render();
      focusReturn = root.querySelector(`[data-card-action="${action}"]`);
      return;
    }
    if (action === "confirm") {
      const status = confirmStatus;
      confirmStatus = "";
      root.querySelector("dialog").close();
      return changeStatus(status);
    }
    if (action === "unsuspend") return changeStatus("unsuspend");
    notice = "";
    if (action.startsWith("view-")) view = action.slice(5);
    else if (action.startsWith("select-")) { selectedId = Number(action.slice(7)); loadCard(selectedId); }
    else page = action;
    render();
    const focusTarget = action.startsWith("view-") || action.startsWith("select-")
      ? root.querySelector(`[data-card-action="${action}"]`) : root.querySelector("h1");
    if (focusTarget?.tagName === "H1") focusTarget.setAttribute("tabindex", "-1");
    focusTarget?.focus();
    if (page === "issue") handleChange({ target: root.querySelector("[name=product_id]:checked") ?? {} });
  }

  root.addEventListener("click", handleClick);
  root.addEventListener("submit", handleSubmit);
  root.addEventListener("change", handleChange);
  loadAll();
  return () => {
    alive = false;
    root.removeEventListener("click", handleClick);
    root.removeEventListener("submit", handleSubmit);
    root.removeEventListener("change", handleChange);
    root.replaceChildren();
  };
}
