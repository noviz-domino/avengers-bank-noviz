import assert from "node:assert/strict";
import { test } from "node:test";
import { amount, detailView, listView, maxRate, openingRate, percent, term } from "./products.mjs";

const stark = {
  product_id: 4, type: "SAVINGS", name: "스타크 자유적금", base_rate: "3.50", max_preferential_rate: "1.00",
  min_term_months: 12, max_term_months: 24, min_amount: 10000, max_amount: 1000000, min_age: null, sale_start: null, sale_end: null,
  description: "<b>매달</b> 넣는 적금", conditions: "월 1만 원부터",
  preferential_rates: [
    { code: "SALARY_TRANSFER", description: "급여를 받으면", rate: "0.50" },
    { code: "MARKETING_AGREED", description: "마케팅 동의", rate: "0.20" },
    { code: "FIRST_PRODUCT", description: "첫 예·적금", rate: "0.30" },
  ],
};
const checking = { product_id: 1, type: "CHECKING", name: "입출금통장", base_rate: "0.10", max_preferential_rate: "0.00", min_term_months: null, max_term_months: null, min_amount: null, max_amount: null, min_age: null, sale_start: null, sale_end: null };
const loan = { ...checking, product_id: 6, type: "LOAN", name: "신용대출" };
const special = { ...stark, product_id: 3, type: "DEPOSIT", name: "특판 예금", sale_start: "2026-11-01", sale_end: "2027-12-31", min_age: 19 };

test("최고금리와 개설 시 적용 가능한 최고금리를 구분한다", () => {
  assert.equal(maxRate(stark), "4.50%");
  assert.equal(openingRate(stark), "4.00%"); // 급여이체 0.50 제외
  assert.equal(openingRate({ ...stark, max_preferential_rate: "0.30" }), "3.80%"); // 우대 상한
  assert.match(detailView(stark), /현재 가입 시 미적용/);
  assert.match(detailView(stark), /연 4.00%/);
  assert.equal(percent("0.1"), "0.10%");
});

test("기간·금액 문구와 분류별 목록, 대출 제외", () => {
  assert.equal(term(stark), "12~24개월");
  assert.equal(amount(stark), "월 1만 원~100만 원");
  assert.equal(term(checking), "기간 제한 없음");
  const all = [checking, stark, special, loan];
  assert.match(listView(all, "all"), /전체 상품 3개/);
  assert.doesNotMatch(listView(all, "all"), /신용대출/);
  assert.match(listView(all, "CHECKING"), /입출금 상품 1개/);
  assert.doesNotMatch(listView(all, "CHECKING"), /스타크 자유적금/);
  assert.match(listView(all, "constructor"), /전체 상품 3개/);
  assert.match(listView(all, "DEPOSIT"), /만 19세 이상/);
  assert.match(listView(all, "DEPOSIT"), /판매 2026-11-01 ~ 2027-12-31/);
});

test("서버 문자열은 이스케이프한다", () => {
  assert.doesNotMatch(detailView(stark), /<b>매달/);
  assert.match(detailView(stark), /&lt;b&gt;매달/);
  assert.doesNotMatch(listView([{ ...stark, name: "<img src=x onerror=1>" }]), /<img/);
});
