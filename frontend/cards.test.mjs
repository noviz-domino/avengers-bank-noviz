import assert from "node:assert/strict";
import { test } from "node:test";
import { changeCardStatus, monthTotal, monthTransactions, newCardsDemo } from "./cards-demo.mjs";

test("월 이용금액은 해당 월 카드 내역만 합산하며 신용 미결제액과 구분한다", () => {
  const [debit, credit] = newCardsDemo();
  assert.equal(monthTotal(debit), 238_500);
  assert.equal(monthTransactions(debit).length, 4);
  assert.equal(monthTotal(credit), 120_000);
  assert.equal(credit.outstanding, 420_000);
  assert.equal(monthTotal(debit, "2026-12"), 0);
  assert.equal(monthTotal(debit, "2026-10"), 4_500);
});

test("일시정지 후 분실 신고가 가능하고 분실은 되돌릴 수 없다", () => {
  const [card, other] = newCardsDemo();
  assert.equal(changeCardStatus(card, "SUSPENDED"), true);
  assert.equal(card.status, "SUSPENDED");
  assert.equal(other.status, "ACTIVE");
  assert.equal(changeCardStatus(card, "ACTIVE"), false);
  assert.equal(changeCardStatus(card, "LOST"), true);
  assert.equal(changeCardStatus(card, "SUSPENDED"), false);
  assert.equal(card.status, "LOST");
  assert.equal(newCardsDemo()[0].status, "ACTIVE");
});
