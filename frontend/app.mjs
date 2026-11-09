import { money, newDemo, replyTo } from "./demo.mjs";
import { ApiError, api, idempotencyKey, isSignedIn, login as apiLogin, logout as apiLogout, onExpired } from "./api.mjs";
import { openApproval } from "./approval.mjs";
import { accountName, kindOf, normalizeAccountNum, parseAmount, shortDate, txLabel } from "./format.mjs";
import { mountCards } from "./cards.mjs";
import { newCardsDemo } from "./cards-demo.mjs";
import { renderProducts } from "./products.mjs";

const app = document.querySelector("#app");
const shield = '<svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 6v10c0 8-5 14-13 18C8 30 3 24 3 16V6Z" fill="#fff" stroke="#132844" stroke-width="2.5"/><path d="M7 24c6-5 13-7 20-7M10 28c4-3 9-5 14-6" fill="none" stroke="#132844" stroke-width="2.5"/><path d="M11 29c4-3 8-4 12-5" fill="none" stroke="#b84039" stroke-width="2"/><path d="m16 7 1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5Z" fill="#132844"/></svg>';
const brand = '<span class="brand">' + shield + '캡아메리카뱅크</span>';
const questions = [
  ["계좌·거래", "내 계좌 잔액 알려줘", "이번 달 카페에서 얼마 썼어?"],
  ["상품 안내", "스타크 적금 우대조건 알려줘", "예금과 적금은 어떻게 달라?"],
  ["이체", "토니에게 5만 원 보내고 싶어"],
];
const pages = new Set(["login", "home", "account", "manage", "chat", "transfer", "cards", "products"]);
const stepOrder = ["recipient", "amount", "review"];
const hidden = "••••••";

let demo = newDemo(); // 상담(chat) 화면용 데모 데이터. 계좌·이체는 실제 API를 쓴다
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
let chat = [];
let pending;
let responding = false;
let chatTimer;
let transfer;
let cards = newCardsDemo();
let unmountCards;
let productKind = "all";

const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);
const button = (action, label, className = "") =>
  '<button type="button" class="' + className + '" data-action="' + action + '"'
  + (className === "back" ? ' aria-label="뒤로 가기"' : "") + '>' + label + "</button>";
const accountById = (id) => accounts?.find((account) => String(account.account_id) === String(id));
const currentPage = () => {
  const route = location.hash.slice(1);
  if (!isSignedIn()) return "login";
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
  clearTimeout(chatTimer);
  demo = newDemo();
  accounts = detail = accountId = undefined;
  total = 0;
  accountsError = "";
  recent = [];
  txs = { rows: [], next: null, loading: false, error: "" };
  privateBalance = false;
  expanded = { checking: true, savings: false };
  filter = "all";
  campaign = 0;
  chat = [];
  pending = undefined;
  responding = false;
  transfer = undefined;
  cards = newCardsDemo();
  productKind = "all";
}

function header(title, back = "", right = "") {
  return '<header class="topbar"><div>' + (back ? button(back, "←", "back") : "") + title
    + '</div><div>' + right + "</div></header>";
}

function nav(page) {
  return '<nav class="bottom-nav" aria-label="주 메뉴">'
    + [["home", "⌂", "홈"], ["account", "▤", "계좌"], ["start-transfer", "⇄", "이체"], ["cards", "▱", "카드"], ["products", "♧", "상품"], ["chat", "◌", "AI 상담"]]
      .map(([action, icon, label]) => '<button type="button" data-action="' + action + '"'
        + (page === action ? ' aria-current="page"' : "") + '><span aria-hidden="true">' + icon + '</span>' + label + '</button>').join("")
    + "</nav>";
}

function transactions(rows) {
  if (!rows.length) return '<p class="empty">표시할 거래가 없어요.</p>';
  return '<ul class="rows">' + rows.map((tx) =>
    '<li><div><strong>' + escape(txLabel(tx)) + '</strong><small>' + shortDate(tx.created_at) + " · " + escape(tx.category ?? "미분류")
    + '</small></div><strong class="' + (tx.amount > 0 ? "credit" : "") + '">'
    + (tx.amount > 0 ? "+" : "−") + money(Math.abs(tx.amount)) + "</strong></li>").join("") + "</ul>";
}

function home() {
  if (!accounts) {
    return header(brand, "", button("logout", "로그아웃", "quiet")) + '<main>'
      + (accountsError ? '<p class="error" role="alert">' + escape(accountsError) + "</p>" + button("reload", "다시 불러오기", "outline")
        : '<p class="status" role="status">계좌를 불러오고 있어요…</p>') + "</main>" + nav("home");
  }
  const groups = [["checking", "입출금", "blue"], ["savings", "예금·적금", "green"]];
  return header(brand, "", button("logout", "로그아웃", "quiet")) + '<main>'
    + '<section class="balance hero"><div class="spread"><p>내 총자산</p>'
    + button("privacy", privateBalance ? "금액 보기" : "금액 숨기기", "quiet")
    + '</div><h1>' + (privateBalance ? hidden : money(total)) + '</h1></section>'
    + '<section class="campaign"><div><small>' + (campaign ? "WELCOME" : "GRAND OPEN")
    + '</small><h2>' + (campaign ? "처음 만나는<br>나의 은행" : "새로운 금융의 시작<br>캡아메리카뱅크") + '</h2></div>'
    + '<span class="campaign-art">' + shield + '</span>'
    + button("campaign", (campaign + 1) + " / 2 다음", "campaign-next") + '</section>'
    + groups.map(([kind, label, tone]) => {
      const list = accounts.filter((account) => kindOf(account) === kind);
      const sum = list.reduce((balance, account) => balance + account.balance, 0);
      return '<section class="account-group"><button type="button" class="group-head ' + tone
        + '" aria-expanded="' + expanded[kind] + '" data-action="toggle-' + kind + '"><strong>' + label
        + " " + list.length + '개</strong><span>' + (privateBalance ? hidden : money(sum))
        + (expanded[kind] ? " ⌃" : " ⌄") + "</span></button>"
        + (expanded[kind] ? '<ul class="rows">' + list.map((account) =>
          '<li>' + button("account-" + account.account_id, "<strong>" + escape(accountName(account)) + "</strong><small>"
            + escape(account.account_num) + "</small>", "account-link")
          + '<div class="right"><strong>' + (privateBalance ? hidden : money(account.balance)) + "</strong>"
          + (kind === "checking" ? button("send-" + account.account_id, "이체", "outline") : "") + "</div></li>").join("") + "</ul>" : "")
        + "</section>";
    }).join("")
    + '<section><h2 class="group-head amber">최근 거래</h2>' + transactions(recent) + "</section>"
    + '<section class="card spread"><div><h2>금융 업무를 물어보세요</h2><small>계좌, 상품, 이체를 대화로</small></div>'
    + button("chat", "상담 시작", "outline") + "</section></main>" + nav("home");
}

function accountPage(manage) {
  const account = accountById(accountId);
  const checking = account.account_type === "CHECKING";
  const name = accountName(account);
  if (manage) {
    const { closing, error, busy } = manageState;
    return header("계좌 관리", "account") + '<main><section class="card"><h1>' + escape(name)
      + '</h1><dl><dt>계좌번호</dt><dd>' + escape(account.account_num) + '</dd><dt>상품</dt><dd>'
      + escape(account.product_name) + '</dd></dl></section>'
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
  const terms = detail?.terms;
  return header("계좌 상세", "home", button("manage", "관리", "quiet")) + '<main>'
    + '<section class="hero"><div class="spread"><h1>' + escape(name) + '</h1>'
    + button("privacy", privateBalance ? "금액 보기" : "금액 숨기기", "quiet") + "</div>"
    + '<small>' + escape(account.account_num) + '</small><div class="spread balance-line"><span>잔액</span><strong>'
    + (privateBalance ? hidden : money(account.balance)) + '</strong></div></section>'
    + (terms ? '<section class="card"><dl><dt>적용 금리</dt><dd>연 ' + escape(terms.applied_rate) + '%</dd><dt>만기일</dt><dd>'
      + escape(terms.maturity_date) + "</dd>"
      + (terms.monthly_payment ? "<dt>월 납입금</dt><dd>" + money(terms.monthly_payment) + " (매월 " + terms.payment_day + "일)</dd>" : "")
      + "</dl></section>" : "")
    + '<section><h2>거래내역</h2><div class="segments" aria-label="거래 구분">'
    + [["all", "전체"], ["in", "입금"], ["out", "출금"]].map(([value, label]) =>
      '<button type="button" data-action="filter-' + value + '" aria-pressed="' + (filter === value) + '">' + label + "</button>").join("")
    + "</div>" + (txs.loading && !txs.rows.length ? '<p class="status" role="status">거래내역을 불러오고 있어요…</p>' : transactions(rows))
    + (txs.error ? '<p class="error" role="alert">' + escape(txs.error) + "</p>" : "")
    + (txs.next ? button("more-tx", txs.loading ? "불러오는 중…" : "더 보기", "outline") : "") + "</section>"
    + (checking ? '<div class="dock">' + button("send-" + account.account_id, "이체하기", "primary") + "</div>" : "") + "</main>";
}

function login() {
  const { error, notice, busy } = loginState;
  return '<main class="login"><div>' + brand + '<p class="eyebrow">MOBILE BANKING</p>'
    + '<h1>나의 은행을<br>가볍게 시작해요.</h1></div>'
    + '<form data-form="login"><label>아이디<input name="login_id" required autocomplete="username" maxlength="50"></label>'
    + '<label>비밀번호<input name="password" type="password" required autocomplete="current-password"></label>'
    + (notice ? '<p class="note" role="status">' + escape(notice) + "</p>" : "")
    + '<p class="error" role="alert">' + escape(error) + '</p>'
    + '<button class="primary"' + (busy ? " disabled" : "") + '>' + (busy ? "로그인 중…" : "로그인") + "</button>"
    + button("demo-login", "데모 계정으로 시작하기", "outline") + "</form></main>";
}

function startTransfer(source, draft, from = currentPage()) {
  if (!accounts) return go("home");
  const checking = accounts.filter((account) => account.account_type === "CHECKING");
  // draft는 상담 화면이 미리 채워 줄 때 쓴다: { number, amount }
  transfer = { source: source ?? checking[0]?.account_id, from, step: draft?.number ? "amount" : "recipient", number: "", amount: 0, ...draft };
  go("transfer");
}

function step(next) {
  transfer.step = next;
  transfer.error = "";
  transfer.key = undefined; // 내용이 바뀔 수 있으니 확인 단계로 다시 오면 새 멱등키를 쓴다
  render();
}

function finishTransfer() {
  const from = transfer.from;
  transfer = undefined;
  go(from);
}

// 서버가 만든 승인 요청을 PIN 창으로 승인한다. 잔액·한도 검사는 서버가 요청 때와 승인 때 모두 한다
async function submitTransfer() {
  if (transfer.busy) return;
  transfer.busy = true;
  transfer.error = "";
  render();
  try {
    transfer.key ??= idempotencyKey();
    const { data: action } = await api("/transfers", { method: "POST", body: {
      from_account_id: transfer.source, to_account_num: transfer.number, amount: transfer.amount, idempotency_key: transfer.key,
    } });
    transfer.key = undefined;
    const result = action.status === "PENDING" ? await openApproval(action.action_id) : { status: action.status };
    if (!transfer) return;
    if (result.status === "EXECUTED") {
      transfer.step = "done";
      loadAccounts();
    } else if (result.status === "REJECTED") transfer.error = "이체를 취소했어요. 돈은 빠져나가지 않았어요.";
    else transfer.error = result.error?.message ?? action.failure_reason ?? "이체가 처리되지 않았어요.";
  } catch (error) {
    if (!transfer) return;
    // 서버가 답한 오류는 같은 키로 다시 보내면 같은 답이 오므로 키를 버린다. 연결 실패만 키를 유지한다
    if (!(error instanceof ApiError) || error.status !== 0) transfer.key = undefined;
    transfer.error = error.message;
  }
  transfer.busy = false;
  render();
}

function transferPage() {
  const { source, step: active, number, amount, error, busy } = transfer;
  const fromAccount = accountById(source);
  const close = header("이체", "transfer-back", button("transfer-close", "닫기", "quiet"));
  const sourceCard = '<div class="card spread"><div><small>출금 계좌</small><strong>'
    + escape(accountName(fromAccount)) + '</strong></div><div class="right"><small>잔액</small><strong>'
    + money(fromAccount.balance) + "</strong></div></div>";
  const review = '<dl><dt>받는 계좌</dt><dd>' + escape(number) + '</dd><dt>보낼 금액</dt><dd>' + money(amount) + "</dd></dl>";
  const progress = '<p class="progress">' + ["받는 계좌", "금액", "확인"].map((label, i) =>
    i === stepOrder.indexOf(active) ? "<strong>" + label + "</strong>" : label).join(" · ") + "</p>";
  let content;
  if (active === "recipient") {
    // 내 다른 입출금 계좌와 적금(납입)을 빠른 선택으로 보여 준다. 예금은 받을 수 없다
    const own = accounts.filter((account) => account.account_id !== source && account.account_type !== "DEPOSIT");
    content = progress + '<h1>어디로 보낼까요?</h1><div class="bank">' + brand + '</div>'
      + '<form data-form="recipient"><label>출금 계좌<select name="source">'
      + accounts.filter((account) => account.account_type === "CHECKING").map((account) =>
        '<option value="' + account.account_id + '"' + (source === account.account_id ? " selected" : "") + ">"
        + escape(accountName(account)) + "</option>").join("")
      + '</select></label><label>받는 계좌번호<input name="number" inputmode="numeric" required placeholder="계좌번호를 입력하세요" value="'
      + escape(number) + '"></label><p class="error" role="alert"></p><p class="note">다른 사람의 입출금 계좌번호를 입력하거나 내 계좌를 선택할 수 있어요.</p>'
      + '<div class="chips">' + own.map((account) =>
        '<button type="button" class="outline" data-recipient="' + escape(account.account_num) + '">' + escape(accountName(account)) + "</button>").join("")
      + '</div><div class="dock">' + sourceCard + '<button class="primary">다음</button></div></form>';
  } else if (active === "amount") {
    content = progress + '<h1>얼마를 보낼까요?</h1><p>' + escape(number) + ' 계좌로 보내요.</p>'
      + '<form data-form="amount"><label>보낼 금액<input name="amount" required inputmode="numeric" placeholder="0원" value="'
      + (amount || "") + '"></label><p class="error" role="alert"></p><div class="dock">' + sourceCard + '<button class="primary">다음</button></div></form>';
  } else if (active === "review") {
    content = progress + '<h1>이체 내용을 확인해 주세요</h1><section class="card">' + review + '</section>' + sourceCard
      + (error ? '<p class="error" role="alert">' + escape(error) + "</p>" : "")
      + '<div class="dock"><button type="button" class="primary" data-action="submit-transfer"' + (busy ? " disabled" : "") + ">"
      + (busy ? "요청하는 중…" : "PIN으로 승인하기") + "</button></div>";
  } else {
    content = '<p class="success-mark" aria-hidden="true">✓</p><h1>이체를 마쳤어요</h1><section class="card">'
      + review + '</section><div class="dock">' + button("transfer-close", "확인", "primary") + "</div>";
  }
  return close + '<main class="transfer">' + content + "</main>";
}

function chatPage() {
  const intro = '<section class="hero spread"><div><h2>무엇이 궁금하세요?</h2><p>은행 업무를 대화로 간편하게</p></div>'
    + '<span class="chat-art">' + shield + '</span></section><section><h2>이런 질문을 할 수 있어요</h2>'
    + questions.map(([group, ...examples]) => '<div class="question-group"><h3>' + group + "</h3>"
      + examples.map((question) => '<button type="button" data-question="' + question + '">' + question
        + '<span aria-hidden="true">›</span></button>').join("") + "</div>").join("") + "</section>";
  return header("AI 상담", "home", button("new-chat", "새 대화", "quiet"))
    + '<main class="chat"><div class="chat-feed" aria-live="polite">' + (chat.length ? chat.map((item, i) =>
      '<article class="bubble ' + item.role + '"><small>' + (item.role === "user" ? "나" : "데모 상담") + "</small><p>"
      + escape(item.text) + "</p>" + (item.source ? "<small>" + escape(item.source) + "</small>" : "")
      + (item.draft ? button("chat-transfer-" + i, "이체 내용 확인", "outline") : "") + "</article>").join("") : intro)
    + (responding ? '<p class="status" role="status">담당을 고르고 있어요…</p>' : "")
    + '</div><form class="composer" data-form="chat"><p class="note">이체는 확인 후 별도 화면에서 PIN으로 승인해요.</p>'
    + '<div><input name="question" aria-label="질문" placeholder="궁금한 내용을 입력하세요" maxlength="1000" required>'
    + '<button class="primary" aria-label="보내기"' + (responding ? " disabled" : "") + '>↑</button></div></form></main>' + nav("chat");
}

function sendQuestion(question) {
  if (!question || responding) return;
  if (/[0-9]{6}/.test(question) && /pin|비밀번호/i.test(question)) {
    chat.push({ role: "assistant", text: "PIN은 이체 승인 화면에 입력해 주세요." });
    render();
    return;
  }
  chat.push({ role: "user", text: question });
  responding = true;
  render();
  chatTimer = setTimeout(() => {
    const answer = replyTo(demo, question, pending);
    pending = answer.pending;
    chat.push({ role: "assistant", ...answer });
    responding = false;
    if (currentPage() === "chat") render();
  }, 350);
}

function render() {
  unmountCards?.();
  unmountCards = undefined;
  const page = currentPage();
  const body = {
    login, home, account: () => accountPage(false), manage: () => accountPage(true),
    chat: chatPage, transfer: transferPage,
    cards: () => '<div class="cards-screen" id="cards-screen"></div>' + nav("cards"),
    products: () => '<div class="products-app">' + renderProducts(location.hash.slice(1), productKind, undefined, true) + '</div>' + nav("products"),
  }[page]();
  app.innerHTML = (page === "login" ? "" : '<div class="demo-label">DEMO · 시연용 은행</div>') + body;
  if (page === "cards") unmountCards = mountCards(app.querySelector("#cards-screen"), { cards, embedded: true });
  if (page === "chat" && chat.length) document.querySelector(".composer").scrollIntoView({ block: "nearest" });
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
      if (number === accountById(transfer.source).account_num) return formError(form, "출금 계좌와 다른 계좌를 입력해 주세요.");
      transfer.number = number;
      step("amount");
      break;
    }
    case "amount": {
      transfer.amount = parseAmount(data.get("amount"));
      if (!transfer.amount) return formError(form, "1원 이상의 금액을 숫자로 입력해 주세요.");
      step("review");
      break;
    }
    case "chat":
      sendQuestion(data.get("question").trim());
      break;
  }
});

app.addEventListener("click", async (event) => {
  const clicked = event.target.closest("button");
  if (!clicked) return;
  if (clicked.dataset.productFilter) {
    productKind = clicked.dataset.productFilter;
    render();
    app.querySelector('[data-product-filter="' + productKind + '"]')?.focus();
    return;
  }
  const { action, question, recipient } = clicked.dataset;
  if (question) return sendQuestion(question);
  if (recipient) {
    app.querySelector('[name="number"]').value = recipient;
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
  if (action.startsWith("chat-transfer-")) {
    const item = chat[Number(action.slice(14))];
    const draft = item.draft;
    delete item.draft;
    return startTransfer(undefined, undefined, "chat"); // 상담 초안은 데모 데이터라 실제 계좌로 옮기지 않는다
  }
  switch (action) {
    case "demo-login":
      app.querySelector('[name="login_id"]').value = "demo";
      app.querySelector('[name="password"]').value = "demo-password-1234";
      return app.querySelector('[name="password"]').form.requestSubmit();
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
    case "campaign": campaign = 1 - campaign; return render();
    case "start-transfer": return startTransfer();
    case "transfer-close": return finishTransfer();
    case "transfer-back": {
      const previous = { amount: "recipient", review: "amount" }[transfer.step];
      return previous ? step(previous) : finishTransfer();
    }
    case "new-chat":
      clearTimeout(chatTimer);
      chat = [];
      pending = undefined;
      responding = false;
      return render();
    default: return go(action);
  }
});

app.addEventListener("change", (event) => {
  if (event.target.name !== "source") return;
  const number = app.querySelector('[name="number"]').value;
  transfer.source = Number(event.target.value);
  render();
  app.querySelector('[name="number"]').value = number;
  app.querySelector('[name="source"]').focus();
});

window.addEventListener("hashchange", () => {
  if (location.hash !== "#transfer") transfer = undefined;
  render();
  if (location.hash === "#home" && isSignedIn()) loadAccounts();
  const heading = app.querySelector("h1");
  heading?.setAttribute("tabindex", "-1");
  heading?.focus({ preventScroll: true });
  window.scrollTo(0, 0);
});
render();
if (isSignedIn()) loadAccounts();
