// AI 상담 화면: POST /chat/stream(SSE)으로 실제 에이전트와 대화한다.
// 이체 등은 에이전트가 승인 대기만 만들고, 사용자가 버튼 → 공통 PIN 창(approval.mjs)에서 직접 승인한다.
import { api, accessToken, apiBase } from "./api.mjs";
import { openApproval } from "./approval.mjs";

const questions = [
  ["계좌·거래", "내 계좌 잔액 알려줘", "이번 달 카페에서 얼마 썼어?"],
  ["카드", "내 카드 한도 얼마 남았어?", "카드 이용내역 보여줘"],
  ["상품 안내", "스타크 적금 우대조건 알려줘", "예금과 적금은 어떻게 달라?"],
  ["예산", "이번 달 얼마 더 쓸 수 있어?", "30만 원짜리 사도 돼?"],
  ["이체", "생활비 통장에서 비상금 통장으로 1,000원 보내줘"],
];
const RATE_LIMIT_MESSAGE = "요청이 많아요. 잠시 후 다시 물어봐 주세요.";
const NETWORK_MESSAGE = "서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.";

const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// 마크다운은 렌더링하지 않고 굵게(**)와 목록 표시만 걷어 읽기 좋게 한다
const plain = (text) => text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/`/g, "").replace(/^[-*] /gm, "• ");

/** SSE 버퍼에서 완성된 이벤트를 꺼낸다. 덜 온 조각은 rest로 돌려줘 다음 청크와 이어 붙인다 */
export function parseSSE(buffer) {
  const events = [];
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop();
  for (const block of blocks) {
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (!data.length) continue;
    try { events.push({ event, data: JSON.parse(data.join("\n")) }); } catch { /* 깨진 조각은 건너뜀 */ }
  }
  return { events, rest };
}

// 대화 상태는 화면을 다시 그려도 유지된다 (로그아웃·새 대화에서만 비운다)
let messages = [];
let sessionId;
let responding = false;
let progress = "";
let draw = () => {};
let controller; // 진행 중인 답변 요청. 새 대화·로그아웃 때 끊어 옛 답이 새 대화에 섞이지 않게 한다

export function resetChat() {
  controller?.abort();
  controller = undefined;
  messages = [];
  sessionId = undefined;
  responding = false;
  progress = "";
}

async function post(message, signal) {
  const send = () => fetch(apiBase() + "/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + accessToken() },
    body: JSON.stringify({ message, ...(sessionId ? { session_id: sessionId } : {}) }),
    signal,
  });
  let response;
  try {
    response = await send();
    if (response.status === 401) {
      await api("/users/me"); // 만료된 토큰이면 여기서 갱신된다
      response = await send();
    }
  } catch (error) {
    if (error.status || error.name === "AbortError") throw error;
    throw new Error(NETWORK_MESSAGE);
  }
  if (response.status === 429) throw new Error(RATE_LIMIT_MESSAGE);
  if (!response.ok) {
    const json = await response.json().catch(() => null);
    throw new Error(json?.error?.message ?? "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요.");
  }
  return response;
}

const pendingActions = async () => (await api("/approvals")).data;

async function ask(question) {
  if (!question || responding) return;
  if (/[0-9]{6}/.test(question) && /pin|비밀번호/i.test(question)) {
    messages.push({ role: "assistant", text: "PIN은 AI 상담에 입력하지 마세요. 이체 승인 창에서만 입력해 주세요." });
    return draw();
  }
  messages.push({ role: "user", text: question });
  const reply = { role: "assistant", text: "", actions: [] };
  responding = true;
  progress = "담당을 고르고 있어요…";
  draw();
  const mine = (controller = new AbortController());
  try {
    const response = await post(question, mine.signal);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let failed = "";
    let requested = false; // 이번 턴에 승인 대기를 만드는 도구가 돌았는가
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSSE(buffer);
      buffer = parsed.rest;
      for (const { event, data } of parsed.events) {
        if (event === "status") {
          progress = data.label;
          requested ||= /^request_/.test(data.tool ?? "");
        }
        else if (event === "token") {
          if (!messages.includes(reply)) messages.push(reply);
          reply.text += data.text;
        } else if (event === "done") {
          sessionId = data.session_id;
          if (!messages.includes(reply)) messages.push(reply);
          reply.text = data.reply; // 미리보기를 최종 답으로 바꿔 끼운다
        } else if (event === "error") failed = data.message ?? "답변을 만들지 못했어요.";
      }
      draw();
    }
    if (failed) throw new Error(failed);
    // 승인 대기는 스트림에 id가 없어 목록에서 찾는다. 이미 화면에 버튼이 있는 건 다시 만들지 않는다
    const shown = new Set(messages.flatMap((m) => (m.actions ?? []).map((a) => a.id)));
    if (requested) {
      for (const action of await pendingActions()) {
        if (action.requested_by === "AGENT" && !shown.has(action.action_id)) reply.actions.push({ id: action.action_id, summary: action.summary });
      }
    }
  } catch (error) {
    if (mine.signal.aborted) return; // 새 대화로 넘어간 뒤의 응답은 버린다
    if (!messages.includes(reply)) messages.push(reply);
    reply.text = (reply.text ? reply.text + "\n\n" : "") + (error.message || NETWORK_MESSAGE);
  }
  if (mine.signal.aborted) return;
  responding = false;
  progress = "";
  draw();
}

async function approve(messageIndex, actionId) {
  const item = messages[messageIndex];
  const action = item?.actions.find((a) => a.id === actionId);
  if (!action || action.busy) return;
  action.busy = true;
  draw();
  let result;
  try {
    result = await openApproval(actionId);
  } catch (error) {
    result = { status: "FAILED", error };
  }
  action.busy = false;
  if (result.status === "EXECUTED") {
    item.actions = item.actions.filter((a) => a !== action);
    messages.push({ role: "assistant", text: "승인했어요. " + action.summary + " 처리가 끝났어요." });
  } else if (result.status === "REJECTED") {
    item.actions = item.actions.filter((a) => a !== action);
    messages.push({ role: "assistant", text: "요청을 취소했어요." });
  } else {
    messages.push({ role: "assistant", text: result.error?.message || "승인하지 못했어요. 잠시 후 다시 시도해 주세요." });
  }
  draw();
}

function intro(shield) {
  return '<section class="hero spread"><div><h2>무엇이 궁금하세요?</h2><p>은행 업무를 대화로 간편하게</p></div>'
    + '<span class="chat-art">' + shield + '</span></section><section><h2>이런 질문을 할 수 있어요</h2>'
    + questions.map(([group, ...examples]) => '<div class="question-group"><h3>' + group + "</h3>"
      + examples.map((q) => '<button type="button" data-chat-question="' + q + '">' + q + '<span aria-hidden="true">›</span></button>').join("") + "</div>").join("") + "</section>";
}

/** 상담 화면을 root에 그린다. 하단 메뉴는 app.mjs가 붙인다. 정리 함수를 돌려준다 */
export function mountChat(root, { shield = "" } = {}) {
  root.innerHTML = '<header class="topbar"><div><button type="button" class="back" data-action="home" aria-label="뒤로 가기">←</button>AI 상담</div>'
    + '<div><button type="button" class="quiet" data-chat-new>새 대화</button></div></header>'
    + '<main class="chat"><div class="chat-feed" aria-live="polite"></div>'
    + '<form class="composer" data-form="chat"><p class="note">이체는 확인 후 별도 창에서 PIN으로 승인해요.</p>'
    + '<div><input name="question" aria-label="질문" placeholder="궁금한 내용을 입력하세요" maxlength="1000" required>'
    + '<button class="primary" aria-label="보내기">↑</button></div></form></main>';
  const feed = root.querySelector(".chat-feed");
  const send = root.querySelector(".composer .primary");
  const input = root.querySelector("input");
  let alive = true;
  draw = () => {
    if (!alive) return;
    feed.innerHTML = (messages.length ? messages.map((item, i) =>
      '<article class="bubble ' + item.role + '"><small>' + (item.role === "user" ? "나" : "AI 상담") + "</small><p>" + escape(plain(item.text)) + "</p>"
      + (item.actions ?? []).map((a) => "<small>" + escape(a.summary) + '</small><button type="button" class="outline" data-chat-approve="' + i + '" data-action-id="' + escape(a.id) + '"'
        + (a.busy ? " disabled" : "") + ">이체 확인하기</button>").join("") + "</article>").join("") : intro(shield))
      + (responding ? '<p class="status" role="status">' + escape(progress) + "</p>" : "");
    send.disabled = responding;
    if (messages.length) feed.lastElementChild?.scrollIntoView({ block: "nearest" });
  };
  const onClick = (event) => {
    const el = event.target.closest("button");
    if (!el) return;
    if (el.dataset.chatQuestion) ask(el.dataset.chatQuestion);
    else if (el.dataset.chatApprove) approve(Number(el.dataset.chatApprove), el.dataset.actionId);
    else if ("chatNew" in el.dataset) { resetChat(); draw(); }
  };
  const onSubmit = (event) => {
    event.preventDefault();
    const question = input.value.trim();
    input.value = "";
    ask(question);
  };
  root.addEventListener("click", onClick);
  root.addEventListener("submit", onSubmit);
  draw();
  return () => { alive = false; root.removeEventListener("click", onClick); root.removeEventListener("submit", onSubmit); };
}
