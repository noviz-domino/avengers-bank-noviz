import { mountChat, resetChat } from "./chat.mjs";
import { ApiError, api, idempotencyKey, isSignedIn, login as apiLogin, logout as apiLogout, onExpired } from "./api.mjs";
import { openApproval } from "./approval.mjs";
import { accountName, accountType, kindOf, longDate, money, normalizeAccountNum, parseAmount, recipientName, shortDate, txLabel } from "./format.mjs";
import { mountCards } from "./cards.mjs";
import { mountBudget } from "./budget.mjs";
import { mountProducts } from "./products.mjs";
import { mountSignup } from "./signup.mjs";
import { mountMenu } from "./settings.mjs";
import { mountSearch } from "./search.mjs";
import { loginView } from "./login.mjs";
import { esc as escape, header as uiHeader, button as uiButton, bottomTabs as nav, pageTitle, sectionHead, listRow, cardBox, stateBlock, icon, maskAccountNumber, restoreFocus, carouselPager } from "./ui.mjs";

const app = document.querySelector("#app");
const shield = '<svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 6v10c0 8-5 14-13 18C8 30 3 24 3 16V6Z" fill="#fff" stroke="#132844" stroke-width="2.5"/><path d="M7 24c6-5 13-7 20-7M10 28c4-3 9-5 14-6" fill="none" stroke="#132844" stroke-width="2.5"/><path d="M11 29c4-3 8-4 12-5" fill="none" stroke="#b84039" stroke-width="2"/><path d="m16 7 1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5Z" fill="#132844"/></svg>';
const brand = '<span class="brand">' + shield + '캡아메리카뱅크</span>';
const pages = new Set(["login", "home", "account", "manage", "chat", "transfer", "cards", "products", "signup", "menu", "search", "budget"]);
const stepOrder = ["recipient", "amount", "review"];
const hidden = "••••••";

let accounts; // GET /accounts 결과. undefined면 아직 불러오기 전
let total = 0;
let accountsError = "";
let recent = []; // 홈의 최근 거래 3건
let detail; // 계좌 상세(GET /accounts/{id})
let txs = { rows: [], next: null, loading: false, error: "" };
let loginState = { error: "", notice: "", busy: false };
let manageState = { closing: false, error: "", busy: false };
let accountId;
let privateBalance = false;
let expanded = { checking: true, savings: false };
let filter = "all";
let campaign = 0;
let campaignPaused = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let campaignTimer;
let unmountChat;
let transfer;
let unmountCards;
let unmountProducts;
let unmountBudget;
let budget;

const button = (action, label, className = "") => uiButton(label, { action, variant: className === "primary" ? "primary" : className === "outline" ? "outline" : "quiet", className });
const accountById = (id) => accounts?.find((account) => String(account.account_id) === String(id));
const currentPage = () => {
  const route = location.hash.slice(1);
  if (!isSignedIn()) return route === "signup" ? "signup" : "login";
  if (route.startsWith("product/")) return "products";
  if (!pages.has(route) || route === "login" || (route === "transfer" && !(transfer && accountById(transfer.source)))) return "home";
  if ((route === "account" || route === "manage") && !accountById(accountId)) return "home";
  return route;
};

// 서버 목록·상세를 불러온다. 실패해도 화면은 남기고 오류 문구만 보여 준다
async function loadAccounts() {
  try {
    const [list, latest] = await Promise.all([api("/accounts"), api("/transactions?limit=3")]);
    ({ accounts, total_balance: total } = list.data);
    recent = latest.data.transactions;
    accountsError = "";
    budget = await api("/budget").then(({ data }) => data).catch(() => undefined);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return;
    accountsError = error.message;
  }
  if (currentPage() !== "transfer") render(); // 입력 중인 이체 화면은 다시 그리지 않는다
}

async function loadTransactions(more = false) {
  if (txs.loading) return;
  const id = accountId;
  if (!more) txs = { rows: [], next: null, loading: true, error: "" };
  else txs.loading = true;
  render();
  try {
    const before = more ? "&before=" + txs.next : "";
    const { data } = await api("/accounts/" + id + "/transactions?limit=20" + before);
    if (id !== accountId) return;
    // 서버는 다음 쪽 커서를 따로 주지 않아서, 한 쪽이 꽉 차면 마지막 tx_id로 더 있는지 본다
    txs = { rows: [...txs.rows, ...data], next: data.length === 20 ? data.at(-1).tx_id : null, loading: false, error: "" };
  } catch (error) {
    if (id === accountId) txs = { ...txs, loading: false, error: error.message };
  }
  render();
}

async function openAccount(id) {
  accountId = id;
  detail = undefined;
  filter = "all";
  manageState = { closing: false, error: "", busy: false };
  go("account");
  api("/accounts/" + id).then(({ data }) => { if (id === accountId) { detail = data; render(); } }).catch(() => {});
  loadTransactions();
}

onExpired(() => {
  reset();
  loginState.notice = "로그인이 만료됐어요. 다시 로그인해 주세요.";
  go("login");
});

function go(route) {
  if (location.hash === "#" + route) render();
  else location.hash = route;
}

function reset() {
  accounts = detail = accountId = undefined;
  total = 0;
  budget = undefined;
  accountsError = "";
  recent = [];
  txs = { rows: [], next: null, loading: false, error: "" };
  privateBalance = false;
  expanded = { checking: true, savings: false };
  filter = "all";
  campaign = 0;
  resetChat();
  transfer = undefined;
}

// 계좌·이체 화면의 정보 행. 값은 이미 이스케이프했거나 부품으로 만든 HTML만 넘긴다
const infoRows = (rows) => '<dl class="info-rows">' + rows.filter(Boolean).map(([term, valueHtml]) =>
  "<div><dt>" + term + "</dt><dd>" + valueHtml + "</dd></div>").join("") + "</dl>";
const accountLines = (account) => "<strong>" + escape(accountName(account)) + "</strong><small>" + maskAccountNumber(account.account_num) + "</small>";
// 받는 은행은 이체 상단이 아니라 은행명 옆에만 작은 로고로 보여 준다
const bankLine = (number = "") => '<p class="bank-line"><span class="mini-logo">' + shield + "캡아메리카뱅크</span>"
  + (number ? "<small>" + escape(number) + "</small>" : "") + "</p>";
// 계좌 관리·상세·이체 화면의 상단. 공통 부품(uiHeader)으로 그린다
function header(title, back = "", right = "") {
  return uiHeader({ title, back, rightHtml: right });
}

// 날짜가 바뀔 때마다 날짜 줄을 넣고, 금액 아래에 거래 후 잔액을 둔다
function transactions(rows) {
  if (!rows.length) return stateBlock("empty", { message: "표시할 거래가 없어요." });
  let day;
  return '<ul class="tx-list">' + rows.map((tx) => {
    const date = shortDate(tx.created_at);
    const head = date === day ? "" : '<li class="tx-date">' + date + "</li>";
    day = date;
    return head + listRow({ title: txLabel(tx), subtitle: tx.category ?? "미분류", amount: (tx.amount > 0 ? "+" : "−") + money(Math.abs(tx.amount)),
      credit: tx.amount > 0, buttonHtml: "<small>" + (privateBalance ? hidden : money(tx.balance_after)) + "</small>" });
  }).join("") + "</ul>";
}

function campaignContent() {
  const [image, alt] = campaign
    ? ["banner-welcome.webp", "첫 만남을 위한 특별한 환영. 신규가입 이벤트 둘러보기"]
    : ["banner-opening.webp", "새로운 금융의 시작, 캡아메리카뱅크. 은행 소개 보기"];
  return '<a id="home-bank-intro" href="#products"><img src="./assets/' + image
    + '" alt="' + escape(alt) + '" width="1989" height="791"></a>'
    + carouselPager(campaign + 1, 2, { previous: "campaign-prev", next: "campaign" })
    + '<div class="ui-carousel-controls ui-campaign-playback">'
    + uiButton("", { action: "campaign-pause", icon: campaignPaused ? "play" : "pause", ariaLabel: campaignPaused ? "이벤트 자동 넘김 재생" : "이벤트 자동 넘김 일시정지", pressed: campaignPaused }) + '</div>';
}

function updateCampaign() {
  const slot = app.querySelector(".ui-campaign");
  if (!slot) return;
  const focus = restoreFocus(slot);
  slot.innerHTML = campaignContent();
  focus();
}

function syncCampaignTimer() {
  clearInterval(campaignTimer);
  if (currentPage() === "home" && accounts && !campaignPaused && !document.hidden) {
    campaignTimer = setInterval(() => { campaign = 1 - campaign; updateCampaign(); }, 5000);
  }
}
document.addEventListener("visibilitychange", syncCampaignTimer);

function home() {
  const head = uiHeader({ brandHtml: brand, rightHtml: uiButton("", { action: "search", icon: "search", ariaLabel: "거래내역 검색" }) });
  if (!accounts) return head + '<main class="ui-home">' + stateBlock(accountsError ? "error" : "loading", accountsError ? { message: accountsError, retryAction: "reload" } : {}) + '</main>' + nav("home");
  const groups = [["checking", "입출금", "blue", "wallet"], ["savings", "예금·적금", "sage", "pig"]];
  return head + '<main class="ui-home">'
    + '<section class="balance ui-balance" aria-label="내 총자산"><div><p>내 총자산</p>'
    + uiButton("", { action: "privacy", icon: privateBalance ? "eyeOff" : "eye", ariaLabel: privateBalance ? "잔액 보기" : "잔액 숨기기", pressed: privateBalance })
    + '</div><h1>' + (privateBalance ? hidden : money(total)) + '</h1></section>'
    + '<button type="button" class="ui-link-card" data-action="budget">' + icon("target") + '<span><strong>예산 가드</strong><small>'
    + (budget?.enrolled ? '지금 더 쓸 수 있는 돈</small></span><b>' + (privateBalance ? hidden : money(budget.free_to_spend)) + '</b>' : '생활비와 저축 목표를 지키게 도와줘요</small></span><b class="ui-link-card-cta">설정하기</b>')
    + icon("chevron") + '</button>'
    + '<section class="ui-campaign" aria-roledescription="캐러셀" aria-label="은행 이벤트">' + campaignContent() + '</section>'
    + (accountsError ? stateBlock("error", { message: accountsError, retryAction: "reload" }) : "")
    + groups.map(([kind, label, tone, glyph]) => {
      const list = accounts.filter((account) => kindOf(account) === kind);
      const sum = list.reduce((balance, account) => balance + account.balance, 0);
      return '<section class="account-group">' + sectionHead({ title: label, count: list.length, total: privateBalance ? hidden : money(sum), icon: glyph, tone, action: "toggle-" + kind, expanded: expanded[kind], controls: "home-" + kind })
        + '<div id="home-' + kind + '"' + (expanded[kind] ? "" : " hidden") + '>'
        + (list.length ? '<ul>' + list.map((account) => listRow({ title: accountName(account), subtitle: maskAccountNumber(account.account_num), amount: privateBalance ? hidden : money(account.balance), action: "account-" + account.account_id, icon: glyph, tone,
          buttonHtml: kind === "checking" ? uiButton("이체", { action: "send-" + account.account_id, variant: "outline" }) : "" })).join("") + '</ul>' : stateBlock("empty", { message: "아직 보유한 계좌가 없어요." })) + '</div></section>';
    }).join("")
    + '<section class="ui-recent">' + sectionHead({ title: "최근 거래", icon: "clock", tone: "amber", rightHtml: uiButton("전체보기 ›", { action: "search" }) })
    + (recent.length ? '<ul>' + recent.map((tx) => {
      const account = accountById(tx.account_id);
      return listRow({ title: txLabel(tx), subtitle: shortDate(tx.created_at) + " · " + (account ? accountName(account) : tx.category ?? "미분류"), amount: (tx.amount > 0 ? "+" : "−") + money(Math.abs(tx.amount)), credit: tx.amount > 0 });
    }).join("") + '</ul>' : stateBlock("empty", { message: "아직 거래내역이 없어요." })) + '</section>'
    + cardBox('<h2>' + icon("chat") + '금융 업무를 물어보세요</h2><button type="button" class="ui-button ui-ai-prompt" data-action="chat"><span>이번 달 카페에서 얼마 썼어?</span>' + icon("arrow") + '</button>', "ui-ai")
    + (location.pathname.startsWith("/app/") ? '<nav class="ui-quick-links" aria-label="바로가기"><a href="./benefits.html">' + icon("gift") + '내 혜택 찾기</a>'
      + '<a href="./protection.html">' + icon("shield") + '카드 보호 시연</a></nav>' : "")
    + '</main>' + nav("home");
}

function accountPage(manage) {
  const account = accountById(accountId);
  const checking = account.account_type === "CHECKING";
  const name = accountName(account);
  const terms = detail?.terms;
  if (manage) {
    const { closing, error, busy } = manageState;
    return header("계좌 관리", "account") + '<main><section class="card"><h1>' + escape(name)
      + '</h1><dl><dt>계좌번호</dt><dd>' + escape(account.account_num) + '</dd><dt>상품</dt><dd>'
      + escape(account.product_name) + '</dd><dt>개설일</dt><dd>' + escape(account.opened_at?.slice(0, 10)) + '</dd>'
      + (checking && detail ? '<dt>1회 이체 한도</dt><dd>' + (detail.per_transfer_limit == null ? '제한 없음' : money(detail.per_transfer_limit)) + '</dd><dt>1일 이체 한도</dt><dd>' + (detail.daily_transfer_limit == null ? '제한 없음' : money(detail.daily_transfer_limit)) + '</dd>' : '') + '</dl>'
      + (terms ? '<h2>상품 정보</h2><dl><dt>적용 금리</dt><dd>연 ' + escape(terms.applied_rate) + '%</dd><dt>만기일</dt><dd>' + escape(terms.maturity_date) + '</dd>'
        + (terms.monthly_payment ? '<dt>월 납입금</dt><dd>' + money(terms.monthly_payment) + ' (매월 ' + escape(terms.payment_day) + '일)</dd>' : '') + '</dl>' : '') + '</section>'
      + '<form data-form="rename"><label>계좌 별칭<input name="alias" maxlength="50" required value="'
      + escape(name) + '"></label><button class="primary"' + (busy ? " disabled" : "") + '>별칭 저장</button><p class="error" role="alert">'
      + (closing ? "" : escape(error)) + '</p></form>'
      + '<section class="card"><h2>계좌 해지</h2>'
      + (!checking ? '<p>예금·적금은 여기서 해지할 수 없어요.</p>'
        : closing ? '<p>정말 해지할까요? 해지한 계좌는 되돌릴 수 없어요.</p>'
          + button("close-confirm", "해지하기", "primary") + button("close-cancel", "취소", "outline")
        : '<p>잔액이 0원일 때만 해지할 수 있어요.</p>' + button("close-start", "계좌 해지", "outline"))
      + (closing ? '<p class="error" role="alert">' + escape(error) + "</p>" : "") + "</section></main>";
  }
  const rows = txs.rows.filter((tx) => filter === "all" || (filter === "in" ? tx.amount > 0 : tx.amount < 0));
  return header("계좌 상세", "home", button("manage", "관리", "quiet")) + '<main>'
    + '<section class="hero"><div class="spread"><h1>' + escape(name) + '</h1>'
    + uiButton('', { action: 'privacy', icon: privateBalance ? 'eyeOff' : 'eye', ariaLabel: privateBalance ? '금액 보기' : '금액 숨기기', pressed: privateBalance }) + "</div>"
    + '<p>' + escape(account.product_name) + '</p><small>' + escape(account.account_num) + '</small><div class="spread balance-line"><span>잔액</span><strong>'
    + (privateBalance ? hidden : money(account.balance)) + '</strong></div></section>'
    + '<section><h2>거래내역</h2><div class="segments" aria-label="거래 구분">'
    + [["all", "전체"], ["in", "입금"], ["out", "출금"]].map(([value, label]) =>
      '<button type="button" data-action="filter-' + value + '" aria-pressed="' + (filter === value) + '">' + label + "</button>").join("")
    + "</div>" + (txs.loading && !txs.rows.length ? '<p class="status" role="status">거래내역을 불러오고 있어요…</p>' : transactions(rows))
    + (txs.error ? '<p class="error" role="alert">' + escape(txs.error) + "</p>" : "")
    + (txs.next ? button("more-tx", txs.loading ? "불러오는 중…" : "더 보기", "outline") : "") + "</section>"
    + (checking ? '<div class="dock">' + button("send-" + account.account_id, "이체하기", "primary") + "</div>" : "") + "</main>";
}

function login() {
  return loginView(loginState, { shield });
}

function startTransfer(source, draft, from = currentPage()) {
  if (!accounts) return go("home");
  const checking = accounts.filter((account) => account.account_type === "CHECKING");
  // draft는 상담 화면이 미리 채워 줄 때 쓴다: { number, amount }
  transfer = { source: source ?? checking[0]?.account_id, from, step: draft?.number ? "amount" : "recipient", number: "", amount: 0, bank: "", ...draft };
  go("transfer");
  loadBanks();
}

// 타행 이체: ClearingHub 참가 은행 목록 (한 번만 부른다. 실패하면 우리 은행 이체만 보여 준다)
let hubBanks;
async function loadBanks() {
  if (hubBanks) return;
  hubBanks = { list: [], note: "" };
  try { hubBanks.list = (await api("/transfers/banks")).data; }
  catch { hubBanks = { list: [], note: "지금은 다른 은행 목록을 불러올 수 없어요. 우리 은행 계좌로는 보낼 수 있어요." }; }
  if (currentPage() === "transfer" && transfer?.step === "recipient") {
    const number = app.querySelector('[name="number"]')?.value;
    render();
    if (number !== undefined) app.querySelector('[name="number"]').value = number;
  }
}
const bankName = (code) => code ? hubBanks?.list.find((bank) => bank.bank_code === code)?.name ?? code : "캡아메리카뱅크";

async function step(next) {
  const draft = transfer;
  if (transfer.busy) return;
  await cancelTransferAction();
  if (transfer !== draft) return;
  transfer.action = undefined;
  transfer.step = next;
  transfer.error = "";
  transfer.key = undefined; // 내용이 바뀔 수 있으니 확인 단계로 다시 오면 새 멱등키를 쓴다
  render();
}

async function finishTransfer() {
  const draft = transfer;
  if (transfer.busy) return;
  await cancelTransferAction();
  if (transfer !== draft) return;
  const from = transfer.from;
  transfer = undefined;
  go(from);
}

// 서버가 만든 승인 요청을 PIN 창으로 승인한다. 잔액·한도 검사는 서버가 요청 때와 승인 때 모두 한다
async function cancelTransferAction() {
  const action = transfer?.action;
  if (action?.status === "PENDING") await api("/approvals/" + encodeURIComponent(action.action_id) + "/reject", { method: "POST" }).catch(() => {});
}

async function prepareTransfer() {
  const draft = transfer;
  if (draft.busy) return;
  draft.busy = true;
  draft.error = "";
  render();
  try {
    draft.key ??= idempotencyKey();
    const { data } = await api("/transfers", { method: "POST", body: {
      from_account_id: draft.source, to_account_num: draft.number, amount: draft.amount, idempotency_key: draft.key,
      ...(draft.bank ? { to_bank: draft.bank } : {}),
    } });
    if (transfer !== draft) {
      if (data.status === 'PENDING') await api('/approvals/' + encodeURIComponent(data.action_id) + '/reject', { method: 'POST' }).catch(() => {});
      return;
    }
    draft.action = data;
    draft.key = undefined;
    draft.step = data.status === "EXECUTED" ? "done" : "review";
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 0) draft.key = undefined;
    draft.error = error.message;
  }
  draft.busy = false;
  if (transfer === draft) render();
}

async function submitTransfer() {
  const draft = transfer;
  if (draft.busy) return;
  if (!draft.action || draft.action.status !== "PENDING") return prepareTransfer();
  draft.busy = true;
  draft.error = "";
  render();
  try {
    const result = await openApproval(draft.action.action_id);
    if (transfer !== draft) return;
    if (result.status === "EXECUTED") {
      draft.action = result.action;
      draft.step = "done";
      draft.balanceAfter = await api("/accounts/" + draft.source).then(({ data }) => data.balance).catch(() => undefined);
      loadAccounts();
    } else {
      draft.action = undefined;
      draft.error = result.status === "REJECTED" ? "이체를 취소했어요. 돈은 빠져나가지 않았어요." : result.error?.message ?? "이체가 처리되지 않았어요. 다시 확인해 주세요.";
    }
  } catch (error) { draft.error = error.message; }
  draft.busy = false;
  if (transfer === draft) render();
}

function transferPage() {
  const { source, step: active, number, amount, error, busy } = transfer;
  const fromAccount = accountById(source);
  const close = header("이체", "transfer-back", button("transfer-close", "닫기", "quiet"));
  const sourceCard = '<div class="card spread"><div><small>출금 계좌</small><strong>'
    + escape(accountName(fromAccount)) + '</strong><small>' + escape(maskAccountNumber(fromAccount.account_num)) + '</small></div><div class="right"><small>잔액</small><strong>'
    + money(fromAccount.balance) + "</strong></div></div>";
  const review = '<p class="transfer-summary">' + escape(transfer.action?.summary ?? '') + '</p>';
  const progress = '<p class="progress">' + ["받는 계좌", "금액", "확인"].map((label, i) =>
    i === stepOrder.indexOf(active) ? "<strong>" + label + "</strong>" : label).join(" · ") + "</p>";
  let content;
  if (active === "recipient") {
    // 내 다른 입출금 계좌와 적금(납입)을 빠른 선택으로 보여 준다. 예금은 받을 수 없다
    const own = accounts.filter((account) => account.account_id !== source && account.account_type !== "DEPOSIT");
    const bankOptions = [{ bank_code: "", name: "캡아메리카뱅크" }, ...(hubBanks?.list ?? [])].map((bank) =>
      '<option value="' + escape(bank.bank_code) + '"' + (transfer.bank === bank.bank_code ? " selected" : "") + ">"
      + escape(bank.name) + "</option>").join("");
    content = progress + '<h1>어디로 보낼까요?</h1>'
      + '<form data-form="recipient"><label>받는 은행<select name="bank">' + bankOptions + "</select></label>"
      + (hubBanks?.note ? '<p class="note">' + escape(hubBanks.note) + "</p>" : "")
      + '<label>출금 계좌<select name="source">'
      + accounts.filter((account) => account.account_type === "CHECKING").map((account) =>
        '<option value="' + account.account_id + '"' + (source === account.account_id ? " selected" : "") + ">"
        + escape(accountName(account)) + "</option>").join("")
      + '</select></label><label>받는 계좌번호<input name="number" inputmode="numeric" required placeholder="계좌번호를 입력하세요" value="'
      + escape(number) + '"></label><p class="error" role="alert"></p><p class="note">다른 사람의 입출금 계좌번호를 입력하거나 내 계좌를 선택할 수 있어요.</p>'
      + '<div class="chips">' + own.map((account) =>
        '<button type="button" class="outline" data-recipient="' + escape(account.account_num) + '">' + escape(accountName(account)) + '<small>' + (account.account_type === "SAVINGS" ? "적금 납입" : "입출금") + '</small></button>').join("")
      + '</div><div class="dock">' + sourceCard + '<button class="primary">다음</button></div></form>';
  } else if (active === "amount") {
    content = progress + '<h1>얼마를 보낼까요?</h1><p>' + escape(bankName(transfer.bank)) + " " + escape(number) + ' 계좌로 보내요.</p>'
      + '<form data-form="amount"><label>보낼 금액<input name="amount" required inputmode="numeric" placeholder="0원" value="'
      + (amount || "") + '"></label><p class="error" role="alert">' + escape(error) + '</p><div class="dock">' + sourceCard + '<button class="primary"' + (busy ? ' disabled' : '') + '>' + (busy ? '확인하는 중…' : '다음') + '</button></div></form>';
  } else if (active === "review") {
    content = progress + '<h1>이체 내용을 확인해 주세요</h1><section class="card">' + review + '</section>' + sourceCard
      + (error ? '<p class="error" role="alert">' + escape(error) + "</p>" : "")
      + (location.pathname.startsWith("/app/")
        ? '<p><a href="./protection.html#transfer-check" target="_blank" rel="noopener">받은 송금 요청 점검하기 (새 탭)</a></p>' : "")
      + '<div class="dock"><button type="button" class="primary" data-action="submit-transfer"' + (busy ? " disabled" : "") + ">"
      + (busy ? "요청하는 중…" : "PIN으로 승인하기") + "</button></div>";
  } else {
    content = '<p class="success-mark" aria-hidden="true">✓</p><h1>이체를 마쳤어요</h1><section class="card">'
      + review + (transfer.balanceAfter === undefined ? '<p class="note">최신 잔액은 계좌에서 확인해 주세요.</p>' : '<dl><dt>이체 후 잔액</dt><dd>' + money(transfer.balanceAfter) + '</dd></dl>') + '</section><div class="dock">' + button("transfer-close", "확인", "primary") + "</div>";
  }
  return close + '<main class="transfer">' + content + "</main>";
}

// 회원가입·메뉴·검색 모듈에 넘기는 화면 이동·세션 콜백
const extCtx = { go, startTransfer, onSignedIn: () => go("home"), onLoggedOut: () => { reset(); go("login"); } };

function render() {
  const focus = restoreFocus(app);
  const previousPage = app.dataset.page;
  unmountCards?.();
  unmountCards = undefined;
  unmountChat?.();
  unmountChat = undefined;
  unmountProducts?.();
  unmountProducts = undefined;
  unmountBudget?.();
  unmountBudget = undefined;
  const page = currentPage();
  const ext = () => '<div id="ext-screen"></div>';
  const body = {
    login, home, account: () => accountPage(false), manage: () => accountPage(true),
    chat: () => '<div class="chat-screen" id="chat-screen"></div>' + nav("chat"), transfer: transferPage,
    cards: () => '<div class="cards-screen" id="cards-screen"></div>' + nav("cards"),
    budget: ext, signup: ext, menu: () => ext() + nav("menu"), search: ext,
    products: () => '<div class="products-app" id="products-screen"></div>' + nav("products"),
  }[page]();
  app.innerHTML = body;
  app.dataset.page = page;
  if (page === "budget") unmountBudget = mountBudget(app.querySelector("#ext-screen"), { go, onChanged: loadAccounts });
  if (page === "signup") mountSignup(app.querySelector("#ext-screen"), extCtx);
  if (page === "menu") mountMenu(app.querySelector("#ext-screen"), extCtx);
  if (page === "search") mountSearch(app.querySelector("#ext-screen"), extCtx);
  if (page === "cards") unmountCards = mountCards(app.querySelector("#cards-screen"), { embedded: true });
  if (page === "products") unmountProducts = mountProducts(app.querySelector("#products-screen"), location.hash.slice(1));
  if (page === "chat") unmountChat = mountChat(app.querySelector("#chat-screen"), { shield });
  if (previousPage === page) focus();
  syncCampaignTimer();
}

function formError(form, error) {
  form.querySelector(".error").textContent = error;
}

app.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const data = new FormData(form);
  switch (form.dataset.form) {
    case "login": {
      loginState = { error: "", notice: "", busy: true };
      render();
      try {
        await apiLogin(data.get("login_id").trim(), data.get("password"));
        loginState = { error: "", notice: "", busy: false };
        loadAccounts();
        return go("home");
      } catch (error) {
        loginState = { error: error.message, notice: "", busy: false };
        return render();
      }
    }
    case "rename": {
      const name = data.get("alias").trim();
      if (!name) return formError(form, "계좌 별칭을 입력해 주세요.");
      manageState.busy = true;
      try {
        await api("/accounts/" + accountId, { method: "PATCH", body: { nickname: name } });
        manageState.busy = false;
        loadAccounts();
        detail = undefined;
        return openAccount(accountId);
      } catch (error) {
        manageState.busy = false;
        manageState.error = error.message;
        return render();
      }
    }
    case "recipient": {
      const number = normalizeAccountNum(data.get("number"));
      if (!number) return formError(form, "받는 계좌번호를 입력해 주세요.");
      transfer.bank = data.get("bank") ?? "";
      if (!transfer.bank && number === accountById(transfer.source).account_num) return formError(form, "출금 계좌와 다른 계좌를 입력해 주세요.");
      transfer.number = number;
      step("amount");
      break;
    }
    case "amount": {
      transfer.amount = parseAmount(data.get("amount"));
      if (!transfer.amount) return formError(form, "1원 이상의 금액을 숫자로 입력해 주세요.");
      return prepareTransfer();
      break;
    }
  }
});

app.addEventListener("click", async (event) => {
  const clicked = event.target.closest("button");
  if (!clicked) return;
  const { action, recipient } = clicked.dataset;
  if (recipient) {
    app.querySelector('[name="number"]').value = recipient;
    app.querySelector('[name="bank"]').value = transfer.bank = ""; // 내 계좌는 우리 은행
    return;
  }
  if (!action) return;
  if (action.startsWith("account-")) return openAccount(action.slice(8));
  if (action.startsWith("send-")) return startTransfer(Number(action.slice(5)));
  if (action.startsWith("filter-")) {
    filter = action.slice(7);
    return render();
  }
  if (action.startsWith("toggle-")) {
    const kind = action.slice(7);
    expanded[kind] = !expanded[kind];
    return render();
  }
  switch (action) {
    case "demo-login":
      app.querySelector('[name="login_id"]').value = "demo";
      app.querySelector('[name="password"]').value = "demo-password-1234";
      return app.querySelector('[name="password"]').form.requestSubmit();
    case "social-soon": app.querySelector("[data-social-note]").textContent = "간편 로그인은 준비 중이에요. 지금은 아이디로 로그인해 주세요."; return;
    case "logout": apiLogout(); reset(); loginState = { error: "", notice: "", busy: false }; return go("login");
    case "reload": accountsError = ""; render(); return loadAccounts();
    case "more-tx": return loadTransactions(true);
    case "close-start": manageState = { closing: true, error: "", busy: false }; return render();
    case "close-cancel": manageState = { closing: false, error: "", busy: false }; return render();
    case "close-confirm":
      try {
        await api("/accounts/" + accountId + "/close", { method: "POST" });
        accountId = undefined;
        loadAccounts();
        return go("home");
      } catch (error) {
        manageState.error = error.message;
        return render();
      }
    case "submit-transfer": return submitTransfer();
    case "privacy": privateBalance = !privateBalance; return render();
    case "campaign-prev":
    case "campaign": campaign = 1 - campaign; updateCampaign(); return syncCampaignTimer();
    case "campaign-pause": campaignPaused = !campaignPaused; updateCampaign(); return syncCampaignTimer();
    case "start-transfer": return startTransfer();
    case "transfer-close": return finishTransfer();
    case "transfer-back": {
      const previous = { amount: "recipient", review: "amount" }[transfer.step];
      return previous ? step(previous) : finishTransfer();
    }
    default: return go(action);
  }
});

app.addEventListener("change", (event) => {
  if (event.target.name === "bank") { transfer.bank = event.target.value; return; }
  if (event.target.name !== "source") return;
  const number = app.querySelector('[name="number"]').value;
  transfer.source = Number(event.target.value);
  render();
  app.querySelector('[name="number"]').value = number;
  app.querySelector('[name="source"]').focus();
});

window.addEventListener("hashchange", () => {
  if (location.hash !== "#transfer" && transfer) { cancelTransferAction(); transfer = undefined; }
  render();
  if (location.hash === "#home" && isSignedIn()) loadAccounts();
  const heading = app.querySelector("h1");
  heading?.setAttribute("tabindex", "-1");
  heading?.focus({ preventScroll: true });
  window.scrollTo(0, 0);
});
render();
if (isSignedIn()) loadAccounts();
