import { api } from "./api.mjs";
import { openApproval } from "./approval.mjs";
import { CATEGORIES } from "./search.mjs";
import { money } from "./format.mjs";
import { esc, header, pageTitle, button, cardBox, sectionHead, stateBlock } from "./ui.mjs";

// 생활비 주기: 매일 쓰는 돈(식사·교통)과 가끔 쓰는 돈(외식·쇼핑·의료 등 주·월 몇 번)
export const FREQUENCIES = [["day", "매일"], ...[1, 2, 3, 4, 5, 6, 7].map((n) => ["week:" + n, "주 " + n + "회"]), ...[1, 2, 3, 4, 5, 6, 8, 10].map((n) => ["month:" + n, "월 " + n + "회"])];
const DAILY_DEFAULT = new Set(["식사", "교통", "카페·간식"]); // 아직 안 적은 업종의 기본 주기: 이 셋은 매일, 나머지는 월 1회
// 생활비가 아닌 분류(돈이 들어오거나 내 계좌 사이를 오가는 것)는 생활비 칸에서 뺀다
export const LIVING = CATEGORIES.filter((name) => !["이체", "저축·내 계좌", "수입", "대출", "카드 대금"].includes(name));
const freqValue = (e) => (!e || e.per === "day" ? "day" : e.per + ":" + e.times);
export const essentialText = (e) => (e.per === "day" ? "매일 " + money(e.amount) : (e.per === "week" ? "주 " : "월 ") + e.times + "회 × " + money(e.amount));

// 확인 화면에 보인 값 그대로 전송한다.
export function budgetInput(form) {
  const goalName = String(form.get("goal_name") ?? "").trim();
  const fixed = form.getAll("fixed_name").map((name, i) => ({ name: String(name).trim(),
    amount: Number(form.getAll("fixed_amount")[i]), day: Number(form.getAll("fixed_day")[i]) }));
  const essentials = Object.fromEntries(LIVING.map((name) => {
    const [per, times = "1"] = String(form.get("freq_" + name) || "day").split(":");
    return [name, { amount: Number(form.get("amt_" + name) || 0), per, times: Number(times) }];
  }).filter(([, e]) => e.amount > 0));
  const goal = goalName ? { name: goalName, target_amount: Number(form.get("goal_amount")), months: Number(form.get("goal_months")) } : null;
  const data = { monthly_income: Number(form.get("monthly_income")), payday: Number(form.get("payday")),
    essentials, fixed_expenses: fixed, goal, always_allow_categories: form.getAll("always_allow") };
  if (!Number.isSafeInteger(data.monthly_income) || data.monthly_income <= 0 || data.monthly_income > 10_000_000_000
    || !Number.isInteger(data.payday) || data.payday < 1 || data.payday > 28) throw new Error("월 수입과 월급날을 확인해 주세요.");
  if (LIVING.some((name) => { const n = Number(form.get("amt_" + name) || 0); return !Number.isInteger(n) || n < 0 || n > 10_000_000; })) throw new Error("생활비는 0원부터 1,000만 원까지 정수로 입력해 주세요.");
  if (fixed.some((f) => !f.name || f.name.length > 50 || !Number.isSafeInteger(f.amount) || f.amount <= 0 || f.amount > 10_000_000_000 || !Number.isInteger(f.day) || f.day < 1 || f.day > 31)) throw new Error("고정 지출의 이름·금액·날짜를 확인해 주세요.");
  if (goal && (!Number.isSafeInteger(goal.target_amount) || goal.target_amount <= 0 || goal.target_amount > 10_000_000_000 || !Number.isInteger(goal.months) || goal.months < 1 || goal.months > 60)) throw new Error("목표 금액과 기간(1~60개월)을 입력해 주세요.");
  if (!goal && (form.get("goal_amount") || form.get("goal_months"))) throw new Error("목표 이름도 입력해 주세요. 목표를 없애려면 세 칸을 모두 비워 주세요.");
  return data;
}

const numberField = (name, label, value = "", min = 0, max = 10_000_000_000, required = false) =>
  `<label>${esc(label)}<input name="${esc(name)}" type="number" inputmode="numeric" min="${min}" max="${max}" step="1" value="${esc(value)}"${required ? " required" : ""}></label>`;
// 업종 한 줄: [금액] [주기]. 아직 안 적은 업종은 식사·교통·카페는 매일, 나머지는 월 1회로 시작
const essentialField = (name, e) => {
  const value = e ? freqValue(e) : DAILY_DEFAULT.has(name) ? "day" : "month:1";
  return `<fieldset class="budget-essential"><legend>${esc(name)}</legend><label><span class="ui-sr-only">${esc(name)} 금액</span><input name="amt_${esc(name)}" type="number" inputmode="numeric" min="0" max="10000000" step="1" placeholder="금액 (원)" value="${esc(e?.amount ?? "")}"></label>`
    + `<label><span class="ui-sr-only">${esc(name)} 주기</span><select name="freq_${esc(name)}">${FREQUENCIES.map(([v, label]) => `<option value="${v}"${v === value ? " selected" : ""}>${label}</option>`).join("")}</select></label></fieldset>`;
};
const fixedRow = (f = {}) => `<fieldset class="budget-fixed"><legend>고정 지출</legend><label>이름<input name="fixed_name" maxlength="50" required value="${esc(f.name)}"></label>${numberField("fixed_amount", "금액 (원)", f.amount, 1, 10_000_000_000, true)}${numberField("fixed_day", "매월 나가는 날", f.day, 1, 31, true)}${button("삭제", { action: "budget-remove", variant: "outline" })}</fieldset>`;
const rows = (items) => `<dl class="budget-info">${items.map(([name, value]) => `<div><dt>${esc(name)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>`;
const configRows = (data) => rows([
  ["월 수입", money(data.monthly_income)], ["월급날", `매월 ${data.payday}일`],
  ...Object.entries(data.essentials).map(([name, e]) => [name, essentialText(e)]),
  ...data.fixed_expenses.map((f) => [f.name, `${money(f.amount)} · 매월 ${f.day}일`]),
  ["목표", data.goal ? `${data.goal.name} · ${money(data.goal.target_amount)} · ${data.goal.months}개월` : "없음"],
  ["항상 통과 업종", data.always_allow_categories.join(", ") || "없음"],
]);

export function mountBudget(container, { go, onChanged = () => {} }) {
  let alive = true, summary, draft, editing = false, busy = false;
  container.innerHTML = header({ title: "예산 관리", back: "budget-home" }) + '<main class="budget-page">' + stateBlock("loading") + "</main>";
  const main = container.querySelector("main");
  const message = (text) => { const node = main.querySelector(".budget-message"); if (node) node.textContent = text; };

  function draw(notice = "") {
    if (!alive) return;
    if (draft) {
      main.innerHTML = pageTitle("이 내용으로 저장할까요?") + configRows(draft)
        + '<p class="note">예산 검사를 약하게 하는 변경은 PIN 승인이 필요해요. 저장하기 전에는 적용되지 않아요.</p><p class="budget-message error" role="alert"></p>'
        + button("다시 입력", { action: "budget-back", variant: "outline" }) + button("확인하고 저장", { action: "budget-save", variant: "primary" });
      return;
    }
    if (editing || !summary.enrolled) {
      const initial = summary.enrolled ? { ...summary, payday: Number(summary.cycle.start.slice(-2)) } : { payday: 25, essentials: {}, fixed_expenses: [], always_allow_categories: ["의료"] };
      main.innerHTML = pageTitle(summary.enrolled ? "예산 바꾸기" : "예산을 시작해 볼까요?")
        + '<p class="note">월급날까지 생활비와 목표 저축을 지키며 쓸 수 있는 돈을 계산해요. 예산을 넘는 지출은 이유와 PIN으로 직접 확인해요.</p>'
        + '<form data-form="budget">' + numberField("monthly_income", "월 수입 (원)", initial.monthly_income, 1, 10_000_000_000, true)
        + numberField("payday", "월급날 (1~28일)", initial.payday, 1, 28, true)
        + (summary.enrolled ? '<p class="note">월급날은 신청 후 바꿀 수 없어요.</p>' : "")
        + '<details><summary>생활비 (업종별로 쓰는 돈)</summary><p class="note">평소에 쓰는 금액과 횟수를 적어요. 식사·교통처럼 매일 쓰면 "매일"에 하루 금액을, 외식·쇼핑·의료처럼 가끔이면 한 번에 쓰는 금액과 주·월 몇 번인지 골라요. 비워 두면 0원이에요.</p>'
        + LIVING.map((name) => essentialField(name, initial.essentials[name])).join("") + "</details>"
        + '<section><h2>고정 지출</h2><p class="note">월세·통신비와 청구 예정 카드값 등을 넣어요. 나가는 날이 지나면 낸 것으로 계산해요.</p><div id="budget-fixed-rows">'
        + initial.fixed_expenses.map(fixedRow).join("") + '</div>' + button("고정 지출 추가", { action: "budget-add", variant: "outline" }) + "</section>"
        + '<details' + (initial.goal ? " open" : "") + '><summary>목표 저축 (선택)</summary><label>목표 이름<input name="goal_name" maxlength="50" value="' + esc(initial.goal?.name) + '"></label>'
        + numberField("goal_amount", "목표 금액 (원)", initial.goal?.target_amount ?? "", 1)
        + numberField("goal_months", "모을 기간 (개월)", initial.goal?.months ?? "", 1, 60) + "</details>"
        + '<details><summary>항상 통과할 카드 업종</summary><p class="note">예산을 넘겨도 결제를 허용해요. 이체에는 적용되지 않아요.</p>'
        + CATEGORIES.map((name) => `<label class="budget-check"><input name="always_allow" type="checkbox" value="${esc(name)}"${initial.always_allow_categories.includes(name) ? " checked" : ""}>${esc(name)}</label>`).join("") + "</details>"
        + '<p class="budget-message error" role="alert"></p><button type="submit" class="ui-button ui-button--primary">내용 확인하기</button></form>';
      if (summary.enrolled) main.querySelector('[name="payday"]').readOnly = true;
      return;
    }
    main.innerHTML = pageTitle("월급날까지의 예산") + `<p class="note">${esc(summary.cycle.start)} ~ ${esc(summary.cycle.end)} · 오늘 포함 ${summary.cycle.days_left}일</p>`
      + cardBox(rows([["생활비만 보면", money(summary.free_before_saving)], ["저축까지 지키면", money(summary.free_to_spend)], ["하루에 쓸 수 있는 돈", money(summary.daily_allowance)]]))
      + sectionHead({ title: "계산 내역", icon: "wallet" })
      + rows([["이번 주기 수입", money(summary.monthly_income)], ["이번 주기에 쓴 돈", money(summary.spent)], ["아직 안 낸 고정 지출", money(summary.unpaid_fixed)], ["남겨 둘 생활비", money(summary.essential_reserve)], ["목표 저축", money(summary.goal_saving)]])
      + sectionHead({ title: "업종별 지출", icon: "clock", tone: "amber" })
      + (summary.by_category.length ? rows(summary.by_category.map((r) => [r.category, money(r.amount)])) : stateBlock("empty", { message: "이번 주기 지출이 없어요." }))
      + '<p class="budget-message note" role="status">' + esc(notice) + "</p>"
      + button("예산 바꾸기", { action: "budget-edit", variant: "outline" }) + button("예산 관리 해지", { action: "budget-disable" });
  }
  async function load(notice = "") {
    const { data } = await api("/budget");
    if (!alive) return;
    summary = data; draw(notice);
  }
  async function save(path, method, body) {
    if (busy) return;
    busy = true;
    container.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      const { data } = await api(path, { method, ...(body ? { body } : {}) });
      if (data.action_id) {
        const result = await openApproval(data.action_id);
        if (result.status !== "EXECUTED") {
          message(result.error?.message ?? "변경을 취소했어요.");
          return;
        }
      }
      draft = undefined; editing = false;
      await load(method === "DELETE" ? "예산 관리를 해지했어요." : "예산을 저장했어요.");
      onChanged();
    } catch (error) { message(error.message); }
    finally { busy = false; container.querySelectorAll("button").forEach((b) => { b.disabled = false; }); }
  }
  container.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!action?.startsWith("budget-")) return;
    event.stopPropagation();
    if (busy) return;
    if (action === "budget-home") return history.length > 1 ? history.back() : go("home"); // 열기 전 화면으로
    if (action === "budget-edit") { editing = true; draw(); }
    if (action === "budget-add" && main.querySelectorAll(".budget-fixed").length < 30) main.querySelector("#budget-fixed-rows").insertAdjacentHTML("beforeend", fixedRow());
    if (action === "budget-remove") event.target.closest("fieldset").remove();
    if (action === "budget-back") { const previous = draft; draft = undefined; draw(); fill(previous); }
    if (action === "budget-save") {
      const body = { ...draft };
      if (summary.enrolled) delete body.payday;
      save("/budget", summary.enrolled ? "PATCH" : "POST", body);
    }
    if (action === "budget-disable") save("/budget", "DELETE");
    if (action === "budget-retry") load().catch((error) => message(error.message));
  });
  function fill(data) {
    const form = main.querySelector("form");
    form.elements.monthly_income.value = data.monthly_income;
    form.elements.payday.value = data.payday;
    for (const name of LIVING) {
      form.elements["amt_" + name].value = data.essentials[name]?.amount ?? "";
      if (data.essentials[name]) form.elements["freq_" + name].value = freqValue(data.essentials[name]);
    }
    main.querySelector("#budget-fixed-rows").innerHTML = data.fixed_expenses.map(fixedRow).join("");
    form.elements.goal_name.value = data.goal?.name ?? "";
    form.elements.goal_amount.value = data.goal?.target_amount ?? "";
    form.elements.goal_months.value = data.goal?.months ?? "";
    form.querySelectorAll('[name="always_allow"]').forEach((input) => { input.checked = data.always_allow_categories.includes(input.value); });
  }
  container.addEventListener("submit", (event) => {
    if (!event.target.matches('[data-form="budget"]')) return;
    event.preventDefault(); event.stopPropagation();
    try { draft = budgetInput(new FormData(event.target)); draw(); }
    catch (error) { message(error.message); }
  });
  load().catch((error) => { if (alive) main.innerHTML = stateBlock("error", { message: error.message, retryAction: "budget-retry" }) + '<p class="budget-message error" role="alert"></p>'; });
  return () => { alive = false; };
}
