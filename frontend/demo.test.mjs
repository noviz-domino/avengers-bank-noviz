import assert from "node:assert/strict";
import { test } from "node:test";
import { approveTransfer, newDemo, recipients, transferError } from "./demo.mjs";

const draft = { source: "living", recipient: recipients[0], amount: 50_000 };

test("잔액과 거래내역은 데모 PIN을 승인한 뒤에만 바뀐다", () => {
  const demo = newDemo();
  assert.match(approveTransfer(demo, draft, "123456"), /PIN/);
  demo.pin = "123456";
  assert.match(approveTransfer(demo, draft, "000000"), /PIN/);
  assert.equal(demo.accounts[0].balance, 2_350_000);
  assert.equal(demo.transactions.length, 3);

  assert.equal(approveTransfer(demo, draft, "123456"), "");
  assert.equal(demo.accounts[0].balance, 2_300_000);
  assert.equal(demo.transactions[0].amount, -50_000);
});

test("승인 시에도 수취 계좌와 잔액·한도를 확인한다", () => {
  const demo = newDemo();
  demo.pin = "123456";
  assert.match(transferError(demo, { ...draft, recipient: demo.accounts[0] }), /다른/);
  assert.match(approveTransfer(demo, { ...draft, source: "reserve", amount: 800_000 }, demo.pin), /잔액/);
  assert.match(approveTransfer(demo, { ...draft, amount: 1_100_000 }, demo.pin), /한도/);
  assert.equal(demo.sentToday, 0);
});

test("내 계좌 이체는 출금과 입금 양쪽을 반영한다", () => {
  const demo = newDemo();
  demo.pin = "123456";
  assert.equal(approveTransfer(demo, { ...draft, recipient: demo.accounts[1] }, demo.pin), "");
  assert.equal(demo.accounts[0].balance, 2_300_000);
  assert.equal(demo.accounts[1].balance, 800_000);
  assert.deepEqual(demo.transactions.slice(0, 2).map((tx) => tx.amount), [50_000, -50_000]);
});
