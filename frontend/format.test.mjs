import assert from "node:assert/strict";
import { test } from "node:test";
import { accountName, accountType, longDate, normalizeAccountNum, parseAmount, recipientName, txLabel } from "./format.mjs";

test("받는 분 이름은 서버 승인 문장에서만 꺼내고, 꼴이 다르면 null", () => {
  assert.equal(recipientName("생활비 통장(110-101-000001)에서 토니 스타크님(110-101-000003)에게 1,000원 보내기"), "토니 스타크님");
  assert.equal(recipientName("내 계좌(110-101-000001)에서 비상금(110-101-000002)에게 1,000원 보내기"), null);
  assert.equal(recipientName(undefined), null);
});

test("개설일은 한국 날짜, 계좌 종류는 한국어 이름", () => {
  assert.equal(longDate("2026-11-08T15:30:00Z"), "2026.11.09");
  assert.equal(accountType({ account_type: "SAVINGS" }), "적금");
});

test("계좌번호는 숫자 12자리면 하이픈 형식으로 맞춘다", () => {
  assert.equal(normalizeAccountNum("110101000002"), "110-101-000002");
  assert.equal(normalizeAccountNum(" 110-101-000002 "), "110-101-000002");
  assert.equal(normalizeAccountNum("123"), "123");
});

test("금액은 1 이상의 정수만 받는다", () => {
  assert.equal(parseAmount("50,000"), 50_000);
  assert.equal(parseAmount("-5"), 0);
  assert.equal(parseAmount("1.5"), 0);
  assert.equal(parseAmount("0"), 0);
});

test("별칭이 없으면 상품명, 거래 이름은 상대방 > 메모 > 종류", () => {
  assert.equal(accountName({ nickname: null, product_name: "히어로 정기예금" }), "히어로 정기예금");
  assert.equal(txLabel({ counterparty_name: "피터", memo: "밥값", tx_type: "TRANSFER_OUT" }), "피터");
  assert.equal(txLabel({ counterparty_name: null, memo: null, tx_type: "INTEREST" }), "이자");
});
