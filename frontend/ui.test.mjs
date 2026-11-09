import test from "node:test";
import assert from "node:assert/strict";
import { esc, maskAccountNumber, button, header, pageTitle, sectionHead, listRow, cardBox, stateBlock, field, bottomTabs, restoreFocus } from "./ui.mjs";

test("계좌번호는 가운데 3자리를 가리고, 잘못된 형식은 노출하지 않는다", () => {
  assert.equal(maskAccountNumber("110-101-000001"), "110-***-000001");
  assert.equal(maskAccountNumber("110101000001"), "110-***-000001");
  for (const value of [null, undefined, "", "110-101-1", "abc", "110-***-000001"]) assert.equal(maskAccountNumber(value), "***");
});

test("텍스트·속성의 서버 값은 공통 부품에서 이스케이프한다", () => {
  const value = '<img src=x onerror="bad">&\'';
  assert.equal(esc(value), "&lt;img src=x onerror=&quot;bad&quot;&gt;&amp;&#39;");
  for (const html of [button(value, { action: value, ariaLabel: value }), header({ title: value, back: value }), pageTitle(value), sectionHead({ title: value, total: value, icon: "wallet", action: value, controls: value }), listRow({ title: value, subtitle: value, amount: value, action: value }), stateBlock("error", { message: value, retryAction: value }), field({ id: value, label: value, value, error: value, hint: value })]) {
    assert.ok(!html.includes("<img"));
    assert.ok(!html.includes('onerror="bad"'));
  }
  assert.match(cardBox(pageTitle(value)), /&lt;img/);
});

test("입력 오류와 힌트를 입력칸에 연결한다", () => {
  const html = field({ id: "alias", label: "별칭", hint: "50자까지 입력해요", error: "별칭을 입력해 주세요.", required: true });
  assert.match(html, /for="alias"/);
  assert.match(html, /aria-describedby="alias-hint alias-error"/);
  assert.match(html, /aria-invalid="true"/);
  assert.match(html, /id="alias-error" role="alert"/);
  assert.match(field({ id: "name", label: "이름" }), /aria-invalid="false"/);
  assert.doesNotMatch(field({ id: "name", label: "이름" }), /aria-describedby/);
});

test("하단 탭은 홈·상품·AI 상담·카드·전체의 고정 목적지 5개다", () => {
  const html = bottomTabs("menu");
  assert.deepEqual([...html.matchAll(/data-action="([^"]+)"/g)].map((match) => match[1]), ["home", "products", "chat", "cards", "menu"]);
  assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1);
  assert.match(html, /data-action="menu" aria-current="page"/);
});

test("다시 그린 버튼에 포커스를 되돌리고, 사라진 버튼에는 아무 일도 하지 않는다", () => {
  const active = { getAttribute: (key) => key === "data-action" ? "privacy" : null };
  let focused = false;
  let elements = [{ getAttribute: () => "privacy", focus: (options) => { focused = options.preventScroll; } }];
  const root = { ownerDocument: { activeElement: active }, contains: () => true, querySelectorAll: () => elements };
  const restore = restoreFocus(root);
  restore();
  assert.ok(focused);
  elements = [];
  assert.doesNotThrow(restore);
  root.contains = () => false;
  assert.doesNotThrow(restoreFocus(root));
});
