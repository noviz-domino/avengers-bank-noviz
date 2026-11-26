import assert from "node:assert/strict";
import { test } from "node:test";
import { parseSSE, stepsHtml } from "./chat.mjs";

test("SSE는 청크 경계가 이벤트 중간이어도 이어 붙여 읽는다", () => {
  const first = parseSSE('event: status\ndata: {"label":"조회"}\n\nevent: token\ndata: {"text":"안');
  assert.deepEqual(first.events, [{ event: "status", data: { label: "조회" } }]);
  const second = parseSSE(first.rest + '녕"}\r\n\r\nevent: done\ndata: {"reply":"끝"}\n\n');
  assert.deepEqual(second.events.map((e) => e.event), ["token", "done"]);
  assert.equal(second.events[0].data.text, "안녕");
  assert.equal(second.rest, "");
});

test("진행 단계: 지난 단계는 켜고 지금 단계는 강조하며 승인 대기는 마지막 칸을 바꾼다", () => {
  const states = (html) => [...html.matchAll(/class="chat-step( \w+)?"/g)].map((m) => (m[1] ?? "").trim());
  assert.deepEqual(states(stepsHtml("idle", "")), ["", "", "", ""]);
  assert.deepEqual(states(stepsHtml("tool", "계좌를 조회하고 있어요")), ["past", "past", "on", ""]);
  assert.deepEqual(states(stepsHtml("done", "")), ["past", "past", "past", "on"]);
  const waiting = stepsHtml("approval", "");
  assert.deepEqual(states(waiting), ["past", "past", "past", "wait"]);
  assert.match(waiting, />승인 대기</);
  assert.match(stepsHtml("routed", "<b>"), /&lt;b&gt;/); // 서버 문구는 이스케이프
});
