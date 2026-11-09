import assert from "node:assert/strict";
import { test } from "node:test";
import { newDemo, recipients, replyTo } from "./demo.mjs";

const draft = { source: "living", recipient: recipients[0], amount: 50_000 };

test("상담 이체는 출금 계좌를 되묻고 초안만 만든다", () => {
  const demo = newDemo();
  const question = replyTo(demo, "토니에게 5만 원 보내고 싶어");
  assert.match(question.text, /어느 통장/);
  assert.deepEqual(replyTo(demo, "생활비 통장", question.pending).draft, draft);
  assert.match(replyTo(demo, "취소", question.pending).text, /취소/);
  assert.equal(replyTo(demo, "토니에게 -5만 원 보내줘").pending.amount, undefined);
  assert.equal(demo.accounts[0].balance, 2_350_000);
});
