import assert from "node:assert/strict";
import { test } from "node:test";
import { products, maxRate, percent, listedProducts, onSale, term, amount } from "./products-data.mjs";
import { renderProducts, mountProducts } from "./products.mjs";

const today = "2026-11-09";
test("최고금리와 가입 시 적용 가능한 우대를 구분한다", () => {
  const stark = products.find((product) => product.id === "stark");
  const hero = products.find((product) => product.id === "hero");
  assert.equal(percent(maxRate(stark)), "4.50%");
  assert.equal(percent(maxRate(stark, true)), "4.00%");
  assert.equal(percent(maxRate(hero)), "3.50%");
  assert.equal(percent(maxRate(hero, true)), "3.20%");
  assert.match(renderProducts("product/stark", "all", today), /현재 가입 시 미적용/);
  assert.match(renderProducts("product/stark", "all", today), /연 4.00%/);
});

test("분류별 목록과 고정 기간·금액·나이 조건을 표시한다", () => {
  assert.equal(listedProducts("all", today).length, 5);
  assert.deepEqual(listedProducts("deposit", today).map((product) => product.id), ["hero", "shield"]);
  assert.deepEqual(listedProducts("checking", today).map((product) => product.id), ["checking"]);
  assert.equal(listedProducts("savings", today).length, 2);
  assert.doesNotMatch(renderProducts("products", "checking", today), /스타크 자유적금/);
  assert.match(renderProducts("product/junior", "all", today), /만 19세 이상/);
  const junior = products.find((product) => product.id === "junior");
  assert.equal(term(junior), "12개월");
  assert.equal(amount(junior), "월 1만 원~30만 원");
  assert.match(renderProducts("products", "constructor", today), /전체 상품 5개/);
});

test("특판 시작·종료일은 포함하며 기간 밖 목록·상세는 차단한다", () => {
  const shield = products.find((product) => product.id === "shield");
  assert.equal(onSale(shield, "2026-10-31"), false);
  assert.equal(onSale(shield, "2026-11-01"), true);
  assert.equal(onSale(shield, "2027-12-31"), true);
  assert.equal(onSale(shield, "2028-01-01"), false);
  assert.doesNotMatch(renderProducts("products", "all", "2028-01-01"), /쉴드 특판 예금/);
  assert.match(renderProducts("product/shield", "all", "2028-01-01"), /상품을 찾을 수 없어요/);
  assert.match(renderProducts("product/%3Cscript%3E", "all", today), /상품을 찾을 수 없어요/);
});

test("분류를 유지해 목록·상세·뒤로 가기를 처리하고 이탈 시 리스너를 해제한다", () => {
  const listeners = new Map();
  const viewListeners = new Map();
  let focused = false;
  const view = {
    location: { hash: "#products" }, scrollTo() {},
    addEventListener: (name, fn) => viewListeners.set(name, fn),
    removeEventListener: (name, fn) => { assert.equal(viewListeners.get(name), fn); viewListeners.delete(name); },
  };
  const root = {
    ownerDocument: { defaultView: view }, innerHTML: "",
    querySelector: () => ({ focus: () => { focused = true; } }),
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: (name, fn) => { assert.equal(listeners.get(name), fn); listeners.delete(name); },
  };
  const unmount = mountProducts(root);
  listeners.get("click")({ target: { closest: () => ({ dataset: { productFilter: "checking" } }) } });
  assert.match(root.innerHTML, /입출금 상품 1개/);
  assert.equal(focused, true);
  view.location.hash = "#product/checking";
  viewListeners.get("hashchange")();
  assert.match(root.innerHTML, /가입 조건/);
  view.location.hash = "#products";
  viewListeners.get("hashchange")();
  assert.match(root.innerHTML, /입출금 상품 1개/);
  unmount();
  assert.equal(listeners.size + viewListeners.size, 0);
});
