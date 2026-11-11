import assert from "node:assert/strict";
import { test } from "node:test";
import { budgetInput, essentialText } from "./budget.mjs";

const form = (values = {}) => {
  const data = new FormData();
  for (const [name, value] of Object.entries({ monthly_income: "3000000", payday: "25", ...values })) data.set(name, value);
  return data;
};
test("예산 확인값은 정수 원, 목표는 선택이며 고정 지출과 업종을 유지한다", () => {
  const data = form({ "amt_식사": "15000", "freq_식사": "day", "amt_외식·술자리": "30000", "freq_외식·술자리": "week:2", "amt_의료": "", "freq_의료": "month:1", goal_name: "휴대폰", goal_amount: "1500000", goal_months: "6" });
  data.append("fixed_name", "월세"); data.append("fixed_amount", "600000"); data.append("fixed_day", "25"); data.append("always_allow", "의료");
  assert.deepEqual(budgetInput(data), { monthly_income: 3000000, payday: 25, essentials: { 식사: { amount: 15000, per: "day", times: 1 }, "외식·술자리": { amount: 30000, per: "week", times: 2 } }, fixed_expenses: [{ name: "월세", amount: 600000, day: 25 }], goal: { name: "휴대폰", target_amount: 1500000, months: 6 }, always_allow_categories: ["의료"] });
  assert.equal(budgetInput(form()).goal, null);
});
test("불완전한 목표, 음수 생활비와 잘못된 월급날은 전송 전에 막는다", () => {
  for (const values of [{ payday: "29" }, { monthly_income: "1.5" }, { "amt_식사": "-1" }, { goal_name: "휴대폰" }, { goal_amount: "10000" }]) assert.throws(() => budgetInput(form(values)));
});

test("생활비는 매일·주·월 횟수로 읽기 쉽게 보여 준다", () => {
  assert.equal(essentialText({ amount: 15000, per: "day", times: 1 }), "매일 15,000원");
  assert.equal(essentialText({ amount: 30000, per: "week", times: 2 }), "주 2회 × 30,000원");
  assert.equal(essentialText({ amount: 20000, per: "month", times: 1 }), "월 1회 × 20,000원");
});
