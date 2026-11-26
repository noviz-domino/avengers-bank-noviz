// AI 상담 화면: POST /chat/stream(SSE)으로 실제 에이전트와 대화한다.
// 이체 등은 에이전트가 승인 대기만 만들고, 사용자가 버튼 → 공통 PIN 창(approval.mjs)에서 직접 승인한다.
import { api, accessToken, apiBase } from "./api.mjs";
import { openApproval } from "./approval.mjs";
import { esc as escape, header, icon } from "./ui.mjs";

// 첫 화면에서 "이렇게 치면 된다"를 보여 주는 예시. 누르면 보내지 않고 입력칸에 채운다 (고쳐서 보낼 수 있게)
const examples = [
  "내 계좌 잔액 알려줘",
  "이번 달 카페에서 얼마 썼어?",
  "내 카드 한도 얼마 남았어?",
  "스타크 적금 우대조건 알려줘",
  "생활비 통장에서 비상금 통장으로 1,000원 보내줘",
];
const RATE_LIMIT_MESSAGE = "요청이 많아요. 잠시 후 다시 물어봐 주세요.";
const NETWORK_MESSAGE = "서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.";

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
// 에이전트 진행 표시 (ADR 0031): 서버의 status 이벤트(routed → agent → tool)와 끝 상태를 단계로 보여 준다
let stage = "idle"; // idle | routed | agent | tool | approval | done
let flow = "";
let draft = ""; // 입력칸에 쓰던 글
let draw = () => {};

export const STEPS = [["routed", "담당 고르기"], ["agent", "담당 확인"], ["tool", "도구 실행"], ["done", "답변"]];
const IDLE_FLOW = "말을 걸면 라우터가 담당을 고르고 담당이 도구를 써요.";

/** 단계 표시 HTML. 지난 단계는 켜고 지금 단계는 강조한다. 승인 대기면 마지막 칸을 "승인 대기"로 바꾼다 */
export function stepsHtml(current, text) {
  const order = ["routed", "agent", "tool", "done"];
  const at = current === "approval" ? 3 : order.indexOf(current);
  return '<div class="chat-steps" aria-label="에이전트 진행 단계">' + STEPS.map(([key, label], i) => {
    const wait = current === "approval" && key === "done";
    const state = wait ? " wait" : i < at ? " past" : i === at ? " on" : "";
    return '<span class="chat-step' + state + '"' + (i === at ? ' aria-current="step"' : "") + ">" + (wait ? "승인 대기" : label) + "</span>";
  }).join("") + '</div><p class="chat-flow">' + escape(text || IDLE_FLOW) + "</p>";
}
let controller; // 진행 중인 답변 요청. 새 대화·로그아웃 때 끊어 옛 답이 새 대화에 섞이지 않게 한다

export function resetChat() {
  controller?.abort();
  controller = undefined;
  messages = [];
  sessionId = undefined;
  responding = false;
  progress = "";
  stage = "idle";
  flow = "";
  draft = "";
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
  if (!response.ok) {
    // 429는 1분 한도와 하루 한도(AI_DAILY_LIMIT) 두 가지라 서버 안내를 그대로 보여 준다
    const json = await response.json().catch(() => null);
    const fallback = response.status === 429 ? RATE_LIMIT_MESSAGE : "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요.";
    throw new Error(json?.error?.message ?? fallback);
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
  stage = "routed";
  flow = progress;
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
          if (["routed", "agent", "tool"].includes(data.stage)) stage = data.stage;
          flow = data.label;
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
    const waiting = reply.actions.length > 0;
    stage = waiting ? "approval" : "done";
    flow = waiting ? "승인 대기를 만들었어요. 돈은 PIN으로 승인해야 움직여요." : "요청 하나를 끝까지 처리했어요.";
  } catch (error) {
    if (mine.signal.aborted) return; // 새 대화로 넘어간 뒤의 응답은 버린다
    if (!messages.includes(reply)) messages.push(reply);
    reply.text = (reply.text ? reply.text + "\n\n" : "") + (error.message || NETWORK_MESSAGE);
    stage = "idle";
    flow = "처리하지 못했어요.";
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

const GREETING = "안녕하세요, 캡아메리카뱅크 AI 상담이에요.\n계좌·카드·상품·예산을 말하듯이 물어보세요. 이체는 내용을 확인한 뒤 PIN으로 직접 승인해요.";

/** 상담 화면을 root에 그린다. 하단 메뉴는 app.mjs가 붙인다. 정리 함수를 돌려준다 */
export function mountChat(root, { shield = "" } = {}) {
  root.innerHTML = header({ title: "AI 상담", heading: true, menu: true, rightHtml: '<button type="button" class="ui-button ui-button--quiet" data-chat-new>' + icon("plus") + "새 대화</button>" })
    + '<main class="chat"><section class="chat-progress" aria-label="지금 에이전트는"></section><div class="chat-feed" aria-live="polite"></div>'
    + '<form class="composer" data-form="chat"><div><input name="question" aria-label="질문" placeholder="예: 이번 달 카페에서 얼마 썼어?" maxlength="1000" autocomplete="off" required>'
    + '<button class="ui-button ui-button--primary primary" aria-label="보내기">' + icon("send") + "</button></div></form></main>";
  const feed = root.querySelector(".chat-feed");
  const steps = root.querySelector(".chat-progress");
  const send = root.querySelector(".composer .primary");
  const input = root.querySelector("input");
  const newChat = root.querySelector("[data-chat-new]");
  let alive = true;
  // 넓은 화면에서는 왼쪽 화면이 바뀔 때마다 상담 칸도 다시 그린다. 쓰던 글이 지워지지 않게 이어 붙인다
  input.value = draft;
  const onInput = () => { draft = input.value; };
  input.addEventListener("input", onInput);
  // AI 말풍선은 방패 아바타와 한 줄, 내 말풍선은 오른쪽
  const avatar = '<span class="chat-avatar">' + shield + "</span>";
  const fromAi = (inner) => '<div class="chat-row">' + avatar + '<article class="bubble assistant"><span class="ui-sr-only">AI 상담</span>' + inner + "</article></div>";
  const bubble = (item, i) => item.role === "user"
    ? '<article class="bubble user"><span class="ui-sr-only">나</span><p>' + escape(item.text) + "</p></article>"
    : fromAi("<p>" + escape(plain(item.text)) + "</p>") + (item.actions ?? []).map((a) => '<div class="chat-action"><span class="chat-action-kind">' + icon("shield")
      + '승인이 필요해요</span><p>' + escape(a.summary) + '</p><button type="button" class="ui-button ui-button--primary" data-chat-approve="' + i + '" data-action-id="' + escape(a.id) + '"' + (a.busy ? " disabled" : "") + ">내용 확인하고 PIN으로 승인</button></div>").join("");
  const intro = () => fromAi("<p>" + escape(GREETING) + "</p>")
    + '<p class="chat-hint">이렇게 입력해 보세요. 누르면 입력칸에 들어가요.</p><div class="chat-examples">'
    + examples.map((q) => '<button type="button" class="chat-example" data-chat-question="' + escape(q) + '">' + escape(q) + "</button>").join("") + "</div>";
  draw = () => {
    if (!alive) return;
    steps.innerHTML = stepsHtml(stage, flow);
    feed.innerHTML = (messages.length ? messages.map(bubble).join("") : intro())
      + (responding ? '<div class="chat-row">' + avatar + '<p class="bubble assistant status" role="status">' + escape(progress) + '<span class="chat-dots" aria-hidden="true"><i></i><i></i><i></i></span></p></div>' : "");
    send.disabled = responding;
    newChat.hidden = !messages.length;
    if (messages.length) feed.lastElementChild?.scrollIntoView({ block: "nearest" });
  };
  const onClick = (event) => {
    const el = event.target.closest("button");
    if (!el) return;
    if (el.dataset.chatQuestion) { input.value = draft = el.dataset.chatQuestion; input.focus(); }
    else if (el.dataset.chatApprove) approve(Number(el.dataset.chatApprove), el.dataset.actionId);
    else if ("chatNew" in el.dataset) { resetChat(); draw(); input.focus(); }
  };
  const onSubmit = (event) => {
    event.preventDefault();
    const question = input.value.trim();
    input.value = draft = "";
    ask(question);
  };
  root.addEventListener("click", onClick);
  root.addEventListener("submit", onSubmit);
  draw();
  return () => { alive = false; root.removeEventListener("click", onClick); root.removeEventListener("submit", onSubmit); input.removeEventListener("input", onInput); };
}
