import assert from "node:assert/strict";
import { test } from "node:test";
import { parseSSE } from "./chat.mjs";

test("SSE는 청크 경계가 이벤트 중간이어도 이어 붙여 읽는다", () => {
  const first = parseSSE('event: status\ndata: {"label":"조회"}\n\nevent: token\ndata: {"text":"안');
  assert.deepEqual(first.events, [{ event: "status", data: { label: "조회" } }]);
  const second = parseSSE(first.rest + '녕"}\r\n\r\nevent: done\ndata: {"reply":"끝"}\n\n');
  assert.deepEqual(second.events.map((e) => e.event), ["token", "done"]);
  assert.equal(second.events[0].data.text, "안녕");
  assert.equal(second.rest, "");
});
