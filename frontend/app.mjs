import { approveTransfer, dailyLimit, money, newDemo, recipients, transferError } from "./demo.mjs";
import { mountChat, resetChat } from "./chat.mjs";
import { mountCards } from "./cards.mjs";
import { newCardsDemo } from "./cards-demo.mjs";
import { renderProducts } from "./products.mjs";

const app = document.querySelector("#app");
const shield = '<svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 6v10c0 8-5 14-13 18C8 30 3 24 3 16V6Z" fill="#fff" stroke="#132844" stroke-width="2.5"/><path d="M7 24c6-5 13-7 20-7M10 28c4-3 9-5 14-6" fill="none" stroke="#132844" stroke-width="2.5"/><path d="M11 29c4-3 8-4 12-5" fill="none" stroke="#b84039" stroke-width="2"/><path d="m16 7 1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5Z" fill="#132844"/></svg>';
const brand = '<span class="brand">' + shield + '캡아메리카뱅크</span>';
const pages = new Set(["login", "home", "account", "manage", "chat", "transfer", "cards", "products"]);
const stepOrder = ["recipient", "amount", "review"];
const hidden = "••••••";

let demo = newDemo();
let signedIn = false;
let accountId = "living";
let privateBalance = false;
let expanded = { checking: true, savings: false };
let filter = "all";
let campaign = 0;
let transfer;
let cards = newCardsDemo();
let unmountCards;
let unmountChat;
let productKind = "all";

const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);
const button = (action, label, className = "") =>
  '<button type="button" class="' + className + '" data-action="' + action + '"'
  + (className === "back" ? ' aria-label="뒤로 가기"' : "") + '>' + label + "</button>";
const accountById = (id) => demo.accounts.find((account) => account.id === id);
const currentPage = () => {
  const route = location.hash.slice(1);
  if (!signedIn) return "login";
  if (route.startsWith("product/")) return "products";
  if (!pages.has(route) || route === "login" || (route === "transfer" && !transfer)) return "home";
  if ((route === "account" || route === "manage") && !accountById(accountId)) return "home";
  return route;
};

function go(route) {
  if (location.hash === "#" + route) render();
  else location.hash = route;
}

function reset() {
  demo = newDemo();
  accountId = "living";
  privateBalance = false;
  expanded = { checking: true, savings: false };
  filter = "all";
  campaign = 0;
  resetChat();
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
    '<li><div><strong>' + escape(tx.label) + '</strong><small>' + tx.date + " · " + escape(tx.category)
    + '</small></div><strong class="' + (tx.amount > 0 ? "credit" : "") + '">'
    + (tx.amount > 0 ? "+" : "−") + money(Math.abs(tx.amount)) + "</strong></li>").join("") + "</ul>";
}

function home() {
  const total = demo.accounts.reduce((sum, account) => sum + account.balance, 0);
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
      const accounts = demo.accounts.filter((account) => account.kind === kind);
      const sum = accounts.reduce((balance, account) => balance + account.balance, 0);
      return '<section class="account-group"><button type="button" class="group-head ' + tone
        + '" aria-expanded="' + expanded[kind] + '" data-action="toggle-' + kind + '"><strong>' + label
        + " " + accounts.length + '개</strong><span>' + (privateBalance ? hidden : money(sum))
        + (expanded[kind] ? " ⌃" : " ⌄") + "</span></button>"
        + (expanded[kind] ? '<ul class="rows">' + accounts.map((account) =>
          '<li>' + button("account-" + account.id, "<strong>" + escape(account.name) + "</strong><small>"
            + account.number + "</small>", "account-link")
          + '<div class="right"><strong>' + (privateBalance ? hidden : money(account.balance)) + "</strong>"
          + (kind === "checking" ? button("send-" + account.id, "이체", "outline") : "") + "</div></li>").join("") + "</ul>" : "")
        + "</section>";
    }).join("")
    + '<section><h2 class="group-head amber">최근 거래</h2>' + transactions(demo.transactions.slice(0, 3)) + "</section>"
    + '<section class="card spread"><div><h2>금융 업무를 물어보세요</h2><small>계좌, 상품, 이체를 대화로</small></div>'
    + button("chat", "상담 시작", "outline") + "</section></main>" + nav("home");
}

function accountPage(manage) {
  const account = accountById(accountId);
  const checking = account.kind === "checking";
  if (manage) {
    return header("계좌 관리", "account") + '<main><section class="card"><h1>' + escape(account.name)
      + '</h1><dl><dt>계좌번호</dt><dd>' + account.number + '</dd><dt>상품 구분</dt><dd>'
      + (checking ? "입출금" : "예금·적금") + '</dd></dl></section>'
      + '<form data-form="rename"><label>계좌 별칭<input name="alias" maxlength="24" required value="'
      + escape(account.name) + '"></label><button class="primary">별칭 저장</button><p class="error" role="alert"></p></form>'
      + '<section class="card"><h2>계좌 해지</h2><p>시연용 계좌는 해지할 수 없어요.</p></section></main>';
  }
  const rows = demo.transactions.filter((tx) => tx.account === accountId
    && (filter === "all" || (filter === "in" ? tx.amount > 0 : tx.amount < 0)));
  return header("계좌 상세", "home", button("manage", "관리", "quiet")) + '<main>'
    + '<section class="hero"><div class="spread"><h1>' + escape(account.name) + '</h1>'
    + button("privacy", privateBalance ? "금액 보기" : "금액 숨기기", "quiet") + "</div>"
    + '<small>' + account.number + '</small><div class="spread balance-line"><span>잔액</span><strong>'
    + (privateBalance ? hidden : money(account.balance)) + '</strong></div></section>'
    + '<section><h2>거래내역</h2><div class="segments" aria-label="거래 구분">'
    + [["all", "전체"], ["in", "입금"], ["out", "출금"]].map(([value, label]) =>
      '<button type="button" data-action="filter-' + value + '" aria-pressed="' + (filter === value) + '">' + label + "</button>").join("")
    + "</div>" + transactions(rows) + "</section>"
    + (checking ? '<div class="dock">' + button("send-" + account.id, "이체하기", "primary") + "</div>" : "") + "</main>";
}

function login() {
  return '<main class="login"><div>' + brand + '<p class="eyebrow">MOBILE BANKING DEMO</p>'
    + '<h1>나의 은행을<br>가볍게 시작해요.</h1><p>시연용 계좌와 거래내역으로<br>은행 업무와 AI 상담을 경험해 보세요.</p></div>'
    + '<div>' + button("login", "데모로 시작하기", "primary") + '<p class="note">실제 개인정보 없이 체험할 수 있어요.</p></div></main>';
}

function startTransfer(source = "living", draft, from = currentPage()) {
  transfer = { source, from, step: draft ? "review" : "recipient", ...draft };
  go("transfer");
}

function step(next) {
  transfer.step = next;
  transfer.error = "";
  render();
}

function finishTransfer() {
  const from = transfer.from;
  transfer = undefined;
  go(from);
}

function transferPage() {
  const { source, step: active, recipient, amount, error } = transfer;
  const fromAccount = accountById(source);
  const close = header("이체", "transfer-back", button("transfer-close", "닫기", "quiet"));
  const sourceCard = '<div class="card spread"><div><small>출금 계좌</small><strong>'
    + escape(fromAccount.name) + '</strong></div><div class="right"><small>잔액</small><strong>'
    + money(fromAccount.balance) + "</strong></div></div>";
  const review = recipient ? '<dl><dt>받는 사람</dt><dd>' + escape(recipient.name)
    + '</dd><dt>받는 계좌</dt><dd>' + recipient.number + '</dd><dt>보낼 금액</dt><dd>'
    + money(amount ?? 0) + "</dd></dl>" : "";
  const progress = '<p class="progress">' + ["받는 계좌", "금액", "확인"].map((label, i) =>
    i === stepOrder.indexOf(active) ? "<strong>" + label + "</strong>" : label).join(" · ") + "</p>";
  let content;
  if (active === "recipient") {
    const own = demo.accounts.filter((account) => account.kind === "checking" && account.id !== source);
    content = progress + '<h1>어디로 보낼까요?</h1><div class="bank">' + brand + '</div>'
      + '<form data-form="recipient"><label>출금 계좌<select name="source">'
      + demo.accounts.filter((account) => account.kind === "checking").map((account) =>
        '<option value="' + account.id + '"' + (source === account.id ? " selected" : "") + ">"
        + escape(account.name) + "</option>").join("")
      + '</select></label><label>받는 계좌번호<input name="number" inputmode="numeric" required placeholder="계좌번호를 입력하세요" value="'
      + (recipient?.number ?? "") + '"></label><p class="error" role="alert"></p><p class="note">데모 수취인 또는 내 다른 입출금 계좌를 선택할 수 있어요.</p>'
      + '<div class="chips">' + [...recipients, ...own].map((person) =>
        '<button type="button" class="outline" data-recipient="' + person.number + '">' + escape(person.name) + "</button>").join("")
      + '</div><div class="dock">' + sourceCard + '<button class="primary">다음</button></div></form>';
  } else if (active === "amount") {
    content = progress + '<h1>얼마를 보낼까요?</h1><p>' + escape(recipient.name) + '님에게 보내요.</p>'
      + '<form data-form="amount"><label>보낼 금액<input name="amount" required inputmode="numeric" placeholder="0원" value="'
      + (amount ?? "") + '"></label><p class="note">오늘 남은 한도 ' + money(dailyLimit - demo.sentToday) + '</p>'
      + '<p class="error" role="alert"></p><div class="dock">' + sourceCard + '<button class="primary">다음</button></div></form>';
  } else if (active === "review") {
    content = progress + '<h1>이체 내용을 확인해 주세요</h1><section class="card">' + review + '</section>' + sourceCard
      + (error ? '<p class="error" role="alert">' + error + "</p>" : "")
      + '<div class="dock">' + button("to-pin", "PIN으로 승인하기", "primary") + "</div>";
  } else if (active === "done") {
    content = '<p class="success-mark" aria-hidden="true">✓</p><h1>데모 이체를 마쳤어요</h1><section class="card">'
      + review + '</section><p class="note">이체 결과는 이 화면의 데모 데이터에 반영됐어요.</p>'
      + '<div class="dock">' + button("transfer-close", "확인", "primary") + "</div>";
  } else {
    const registering = active === "register";
    content = '<h1>' + (registering ? "데모 PIN을 등록해 주세요" : "PIN 6자리를 입력해 주세요") + '</h1>'
      + '<p class="note">이 시연에서만 사용할 숫자를 입력하세요.</p><form data-form="' + active + '">'
      + '<label>' + (registering ? "새 데모 PIN" : "데모 PIN")
      + '<input name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required autocomplete="off"></label>'
      + '<p class="error" role="alert"></p><div class="dock"><button class="primary">'
      + (registering ? "등록하고 계속" : "이체 승인") + "</button></div></form>";
  }
  return close + '<main class="transfer">' + content + "</main>";
}

function render() {
  unmountCards?.();
  unmountCards = undefined;
  unmountChat?.();
  unmountChat = undefined;
  const page = currentPage();
  const body = {
    login, home, account: () => accountPage(false), manage: () => accountPage(true),
    chat: () => '<div class="chat-screen" id="chat-screen"></div>' + nav("chat"), transfer: transferPage,
    cards: () => '<div class="cards-screen" id="cards-screen"></div>' + nav("cards"),
    products: () => '<div class="products-app">' + renderProducts(location.hash.slice(1), productKind, undefined, true) + '</div>' + nav("products"),
  }[page]();
  app.innerHTML = (page === "login" ? "" : '<div class="demo-label">DEMO · 시연용 은행</div>') + body;
  if (page === "cards") unmountCards = mountCards(app.querySelector("#cards-screen"), { cards, embedded: true });
  if (page === "chat") unmountChat = mountChat(app.querySelector("#chat-screen"), { shield });
}

function formError(form, error) {
  form.querySelector(".error").textContent = error;
}

app.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const data = new FormData(form);
  switch (form.dataset.form) {
    case "rename": {
      const name = data.get("alias").trim();
      if (!name) return formError(form, "계좌 별칭을 입력해 주세요.");
      accountById(accountId).name = name;
      go("account");
      break;
    }
    case "recipient": {
      const number = data.get("number").replace(/[-\s]/g, "");
      const options = [...recipients, ...demo.accounts.filter((account) => account.kind === "checking" && account.id !== transfer.source)];
      const recipient = options.find((person) => person.number.replaceAll("-", "") === number);
      if (!recipient) return formError(form, "보낼 수 있는 데모 계좌를 입력하거나 선택해 주세요.");
      transfer.recipient = recipient;
      step("amount");
      break;
    }
    case "amount": {
      const value = data.get("amount").trim();
      transfer.amount = /^[0-9][0-9,]*$/.test(value) ? Number(value.replaceAll(",", "")) : 0;
      const error = transferError(demo, transfer);
      if (error) return formError(form, error);
      step("review");
      break;
    }
    case "register":
      demo.pin = data.get("pin");
      step("pin");
      break;
    case "pin": {
      const error = approveTransfer(demo, transfer, data.get("pin"));
      form.reset();
      if (error) return formError(form, error);
      step("done");
      break;
    }
  }
});

app.addEventListener("click", (event) => {
  const clicked = event.target.closest("button");
  if (!clicked) return;
  if (clicked.dataset.productFilter) {
    productKind = clicked.dataset.productFilter;
    render();
    app.querySelector('[data-product-filter="' + productKind + '"]')?.focus();
    return;
  }
  const { action, recipient } = clicked.dataset;
  if (recipient) {
    app.querySelector('[name="number"]').value = recipient;
    return;
  }
  if (!action) return;
  if (action.startsWith("account-")) {
    accountId = action.slice(8);
    filter = "all";
    return go("account");
  }
  if (action.startsWith("send-")) return startTransfer(action.slice(5));
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
    case "login": signedIn = true; return go("home");
    case "logout": signedIn = false; reset(); return go("login");
    case "privacy": privateBalance = !privateBalance; return render();
    case "campaign": campaign = 1 - campaign; return render();
    case "start-transfer": return startTransfer();
    case "transfer-close": return finishTransfer();
    case "transfer-back": {
      const previous = { amount: "recipient", review: "amount", register: "review", pin: "review" }[transfer.step];
      return previous ? step(previous) : finishTransfer();
    }
    case "to-pin":
      transfer.error = transferError(demo, transfer);
      return transfer.error ? render() : step(demo.pin ? "pin" : "register");
    default: return go(action);
  }
});

app.addEventListener("change", (event) => {
  if (event.target.name !== "source") return;
  const number = app.querySelector('[name="number"]').value;
  transfer.source = event.target.value;
  render();
  app.querySelector('[name="number"]').value = number;
  app.querySelector('[name="source"]').focus();
});

window.addEventListener("hashchange", () => {
  if (location.hash !== "#transfer") transfer = undefined;
  render();
  const heading = app.querySelector("h1");
  heading?.setAttribute("tabindex", "-1");
  heading?.focus({ preventScroll: true });
  window.scrollTo(0, 0);
});
render();
