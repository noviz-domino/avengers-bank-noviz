import assert from "node:assert/strict";
import { test } from "node:test";
import { cardName, kstMonth, last4, monthTotal, monthTransactions } from "./cards.mjs";

const tx = (approved_at, amount, status = "APPROVED") => ({ approved_at, amount, status });

test("카드 표시 이름과 끝 네 자리는 서버 응답에서 뽑는다", () => {
  const card = { masked_card_num: "9410-10**-****-0019", nickname: null, product_name: "스타크 신용카드" };
  assert.equal(last4(card), "0019");
  assert.equal(cardName(card), "스타크 신용카드");
  assert.equal(cardName({ ...card, nickname: "생활비 카드" }), "생활비 카드");
});

test("월 이용금액은 한국 날짜 기준 해당 월의 승인 건만 합산한다", () => {
  // 2026-10-31 16:00Z = 한국 11월 1일 01:00
  const list = [tx("2026-10-31T16:00:00Z", 1_000), tx("2026-11-05T03:00:00Z", 5_500), tx("2026-11-06T03:00:00Z", 9_000, "CANCELED"), tx("2026-10-30T03:00:00Z", 700)];
  assert.equal(kstMonth("2026-10-31T16:00:00Z"), "2026-11");
  assert.equal(monthTransactions(list, "2026-11").length, 3);
  assert.equal(monthTotal(list, "2026-11"), 6_500);
  assert.equal(monthTotal(list, "2026-10"), 700);
  assert.equal(monthTotal(list, "2026-12"), 0);
});
