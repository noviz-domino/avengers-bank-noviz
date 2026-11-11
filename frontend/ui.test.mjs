import test from "node:test";
import assert from "node:assert/strict";
import { esc, maskAccountNumber, button, carouselPager, socialButton, header, pageTitle, sectionHead, listRow, cardBox, stateBlock, field, bottomTabs, restoreFocus } from "./ui.mjs";

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

test("하단 탭은 홈·계좌·카드·상품·AI 상담 순서의 고정 목적지 5개다 (전체 메뉴는 머리글)", () => {
  const html = bottomTabs("accounts");
  assert.deepEqual([...html.matchAll(/data-action="([^"]+)"/g)].map((match) => match[1]), ["home", "accounts", "cards", "products", "chat"]);
  assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1);
  assert.match(html, /data-action="accounts" aria-current="page"/);
});

test("머리글은 menu: true일 때만 오른쪽 끝에 전체 메뉴 버튼을 둔다", () => {
  assert.doesNotMatch(header({ title: "이체" }), /data-action="menu"/);
  const html = header({ title: "카드", rightHtml: button("발급", { action: "issue" }), menu: true });
  assert.match(html, /data-action="issue".*data-action="menu" aria-label="전체 메뉴"/);
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

test("배너 넘김 부품은 두 화살표와 현재 페이지를 표시한다", () => {
  const html = carouselPager(2, 3, { previous: "prev", next: "next" });
  assert.match(html, /data-action="prev" aria-label="이전 배너"/);
  assert.match(html, /class="ui-carousel-page" role="status">2 \/ 3</);
  assert.match(html, /data-action="next" aria-label="다음 배너"/);
});

test("간편 로그인 버튼은 로고와 플랫폼 이름을 버튼 안에 함께 넣는다", () => {
  const google = socialButton("google");
  assert.match(google, /^<button type="button" class="ui-social ui-social--google" data-action="social-soon" aria-label="Google 간편로그인"><svg/);
  assert.match(google, /<span>Google<\/span><\/button>$/);
  assert.match(socialButton("naver", { action: "naver-login" }), /data-action="naver-login".*<span>NAVER<\/span>/);
  assert.doesNotMatch(socialButton("<x>"), /<x>/);
});
