import assert from "node:assert/strict";
import { test } from "node:test";
import { budgetInput } from "./budget.mjs";

const form = (values = {}) => {
  const data = new FormData();
  for (const [name, value] of Object.entries({ monthly_income: "3000000", payday: "25", ...values })) data.set(name, value);
  return data;
};
test("예산 확인값은 정수 원, 목표는 선택이며 고정 지출과 업종을 유지한다", () => {
  const data = form({ "daily_식사": "15000", goal_name: "휴대폰", goal_amount: "1500000", goal_months: "6" });
  data.append("fixed_name", "월세"); data.append("fixed_amount", "600000"); data.append("fixed_day", "25"); data.append("always_allow", "의료");
  assert.deepEqual(budgetInput(data), { monthly_income: 3000000, payday: 25, essentials: { 식사: 15000 }, fixed_expenses: [{ name: "월세", amount: 600000, day: 25 }], goal: { name: "휴대폰", target_amount: 1500000, months: 6 }, always_allow_categories: ["의료"] });
  assert.equal(budgetInput(form()).goal, null);
});
test("불완전한 목표, 음수 생활비와 잘못된 월급날은 전송 전에 막는다", () => {
  for (const values of [{ payday: "29" }, { monthly_income: "1.5" }, { "daily_식사": "-1" }, { goal_name: "휴대폰" }, { goal_amount: "10000" }]) assert.throws(() => budgetInput(form(values)));
});
