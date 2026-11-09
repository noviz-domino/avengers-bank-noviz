// 실제 앱(실제 백엔드)을 DOM으로 끝까지 눌러 보는 통합 점검. tests/browser/run-integration.mjs가 integration.html을 열어 실행한다.
// win은 320px iframe 안의 앱 창이다. 데모 계정(demo / demo-password-1234, PIN 123456)과 실행 중인 서버가 필요하다.
export async function verifyIntegration(win = window) {
  const doc = win.document;
  const checked = [];
  const step = (name) => { checked.push(name); };
  const q = (selector) => doc.querySelector(selector);
  const text = () => doc.querySelector("#app").textContent;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function waitFor(condition, message, timeout = 10000) {
    const end = Date.now() + timeout;
    for (;;) {
      let value;
      try { value = condition(); } catch { value = false; }
      if (value) return value;
      if (Date.now() > end) throw new Error("시간 초과: " + message);
      await sleep(50);
    }
  }
  const waitText = (part, timeout) => waitFor(() => text().includes(part), `화면에 "${part}"가 나타나야 함`, timeout);
  const waitSel = (selector, timeout) => waitFor(() => q(selector), `${selector} 요소가 나타나야 함`, timeout);
  async function click(selector) {
    const element = await waitSel(selector);
    if (element.disabled) throw new Error("비활성 버튼: " + selector);
    element.click();
  }
  const action = (name) => click(`[data-action="${name}"]`);
  async function submit(selector, values) {
    const form = await waitSel(selector);
    for (const [name, value] of Object.entries(values)) form.elements[name].value = value;
    form.requestSubmit();
  }
  const fits = (name) => {
    const width = doc.documentElement.scrollWidth;
    if (width > win.innerWidth) throw new Error(`${name}: 가로 넘침 (${width} > ${win.innerWidth})`);
    step(`${name}: 가로 넘침 없음`);
  };
  const won = (value) => Number(String(value).replace(/[^0-9]/g, ""));
  // 홈 입출금 목록의 계좌별 { id, num, balance }
  const checkingRows = () => [...doc.querySelectorAll('li:has([data-action^="send-"])')].map((li) => ({
    id: li.querySelector('[data-action^="send-"]').dataset.action.slice(5),
    num: li.querySelector(".account-link small").textContent,
    balance: won(li.querySelector(".right strong").textContent),
  }));

  // 1. 로그아웃 상태 딥링크는 로그인으로
  if (q('[data-action="logout"]')) await action("logout");
  win.location.hash = "cards";
  await waitSel('[data-form="login"]');
  step("로그아웃 상태에서 #cards 딥링크는 로그인 화면으로");
  fits("로그인");

  // 2. 잘못된 비밀번호
  await submit('[data-form="login"]', { login_id: "demo", password: "wrong-password-1" });
  await waitFor(() => q('[data-form="login"] .error')?.textContent.trim(), "로그인 오류 문구");
  step("틀린 비밀번호는 오류 문구를 보여 줌");

  // 3. 로그인 → 홈
  await submit('[data-form="login"]', { login_id: "demo", password: "demo-password-1234" });
  await waitFor(() => /\d원/.test(q(".balance h1")?.textContent ?? ""), "홈 총자산");
  step("데모 로그인 후 홈에 총자산 표시");
  fits("홈");

  // 4. 계좌 상세 + 거래내역, 별칭 변경·복원
  const rows = await waitFor(() => (checkingRows().length >= 2 ? checkingRows() : false), "입출금 계좌 2개 이상");
  const [from, to] = rows;
  await click(`[data-action="account-${from.id}"]`);
  await waitFor(() => q(".rows li") || q(".empty"), "거래내역 목록");
  await waitText("잔액");
  step("계좌 상세와 거래내역 표시");
  fits("계좌 상세");
  await action("manage");
  const original = await waitFor(() => q('[data-form="rename"] [name="alias"]')?.value, "별칭 입력칸");
  const alias = "QA" + String(Date.now()).slice(-5);
  await submit('[data-form="rename"]', { alias });
  await waitFor(() => q("h1")?.textContent === alias, "별칭 변경 반영");
  step("별칭 변경");
  await action("manage");
  await submit('[data-form="rename"]', { alias: original });
  await waitFor(() => q("h1")?.textContent === original, "별칭 복원");
  step("별칭 복원");
  await action("home");
  await waitFor(() => checkingRows().length >= 2, "홈 복귀");

  // 5. 이체 1,000원 (내 입출금 계좌 사이) + PIN 승인 창
  const before = checkingRows().find((row) => row.id === from.id).balance;
  await click(`[data-action="send-${from.id}"]`);
  await submit('[data-form="recipient"]', { number: to.num });
  await submit('[data-form="amount"]', { amount: "1000" });
  await waitText("이체 내용을 확인해 주세요");
  await action("submit-transfer");
  const dialog = await waitSel("dialog.approval[open]");
  step("이체 요청 후 PIN 승인 창이 열림");
  // DB를 막 초기화했으면 PIN이 없어서 창이 비밀번호를 받고 PIN을 등록한다
  const password = dialog.querySelector('[name="password"]');
  if (password) password.value = "demo-password-1234";
  dialog.querySelector('[name="pin"]').value = "123456";
  dialog.querySelector("form").requestSubmit();
  await waitText("이체를 마쳤어요");
  step("PIN 승인 후 완료 화면");
  await action("transfer-close");
  await waitFor(() => checkingRows().find((row) => row.id === from.id)?.balance === before - 1000, "출금 계좌 잔액 1,000원 감소");
  step("이체 후 출금 계좌 잔액이 1,000원 줄어듦");

  // 6. 잔액 초과 이체
  await click(`[data-action="send-${from.id}"]`);
  await submit('[data-form="recipient"]', { number: to.num });
  await submit('[data-form="amount"]', { amount: "999999999" });
  await waitText("이체 내용을 확인해 주세요");
  await action("submit-transfer");
  await waitFor(() => q("main.transfer .error")?.textContent.trim(), "잔액 초과 오류");
  if (q("dialog.approval")) throw new Error("잔액 초과인데 PIN 창이 열림");
  step("잔액 초과 이체는 서버 오류 문구를 보여 주고 PIN 창이 열리지 않음");
  fits("이체");
  await action("transfer-close");
  await waitFor(() => checkingRows().length >= 2, "홈 복귀");

  // 7. 카드
  await action("cards");
  await waitSel('[data-card-action^="select-"]');
  step("카드 목록 표시");
  fits("카드");
  await click('[data-card-action="view-list"]');
  (await waitSel('[data-card-action^="select-"]')).click();
  await click('[data-card-action="manage"]');
  await click('[data-card-action="limit"]');
  await waitText("1일 이용 한도");
  step("카드 한도 화면");
  fits("카드 상세");

  // 8. 상품
  await action("products");
  await waitSel("[data-product-filter]");
  await click('[data-product-filter="SAVINGS"]');
  await waitText("적금 상품");
  step("상품 목록 종류 필터");
  fits("상품");
  await click("a.product-row");
  await waitSel("[data-product-join]");
  await waitText("가입 조건");
  step("상품 상세");
  fits("상품 상세");

  // 9. AI 상담 (실제 Gemini)
  await action("chat");
  await submit('[data-form="chat"]', { question: "내 계좌 잔액 알려줘" });
  await waitFor(() => !q(".chat-feed .status") && q(".bubble.assistant p")?.textContent.includes("원"),
    "AI 답변에 '원'이 포함되어야 함", 60000);
  step("AI 상담이 잔액 질문에 실제로 답함");
  fits("AI 상담");

  // 10. 메뉴, 거래 검색, 로그아웃
  await action("home");
  await action("menu");
  await waitText("demo");
  await waitText("내 정보");
  step("메뉴에 내 정보 표시");
  fits("메뉴");
  await click('[data-act="to-search"]');
  await submit("#search-form", { keyword: "이체" });
  await waitText("입금 합계");
  step("거래 검색 결과에 합계 표시");
  fits("거래 검색");
  await click('[data-act="to-menu"]');
  await click('[data-act="to-logout"]');
  await waitSel('[data-form="login"]');
  step("로그아웃하면 로그인 화면");
  return { passed: true, width: win.innerWidth, checked };
}
