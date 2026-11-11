import assert from "node:assert/strict";
import { test } from "node:test";
import { amount, detailView, joinView, listView, maxRate, openingRate, percent, term } from "./products.mjs";

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
  const list = listView([{ ...stark, name: "<img src=x onerror=1>" }]);
  assert.doesNotMatch(list, /<img src=x/);
  assert.match(list, /&lt;img src=x onerror=1&gt;/);
});

test("예금 출금 계좌는 활성 입출금 계좌만 줄바꿈 가능한 선택지로 표시한다", () => {
  const active = { account_id: 7, account_type: "CHECKING", status: "ACTIVE", nickname: "<생활비> 아주 긴 계좌 별칭", account_num: "110-101-000001", balance: 1200000 };
  const html = joinView(special, [active, { ...active, account_id: 8, status: "CLOSED" }, { ...active, account_id: 9, account_type: "SAVINGS" }]);
  assert.match(html, /name="from_account_id" value="7" checked required/);
  assert.match(html, /&lt;생활비&gt; 아주 긴 계좌 별칭/);
  assert.match(html, /110-\*\*\*-000001/);
  assert.doesNotMatch(html, /value="[89]"/);
  assert.match(joinView(special, []), /사용 중인 입출금 계좌가 필요해요/);
  assert.match(joinView(special, []), /type="submit" disabled/);
});

test("비어 있는 상품 분류도 상태 안내를 제공한다", () => {
  assert.match(listView([], "DEPOSIT"), /role="status"/);
  assert.match(listView([], "DEPOSIT"), /가입할 수 있는 상품이 없어요/);
});

test("판매 중인 상품만 이미지 배너에 연결하고 목록에서도 보여 준다", () => {
  const hero = { ...special, product_id: 2, name: "히어로 정기예금" };
  const both = listView([stark, hero, special]);
  assert.match(both, /class="product-banner" href="#product\/4"><img src="\.\/assets\/product-savings\.webp"/);
  assert.match(both, /class="product-banner" href="#product\/2"><img src="\.\/assets\/product-deposit\.webp"/);
  assert.match(both, /data-action="product-banner-next"/);
  assert.match(both, /<strong>스타크 자유적금<\/strong>/);
  assert.doesNotMatch(listView([stark, hero], "DEPOSIT"), /product-savings\.webp|data-action="product-banner-next"/);
  assert.doesNotMatch(listView([special]), /product-banner-track/);
});
