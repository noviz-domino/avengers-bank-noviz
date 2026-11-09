// 모바일 앱 통합 점검 실행기 (Node 24, 의존성 없음)
// 사용법: 백엔드(http://127.0.0.1:8000)를 띄운 뒤 `node tests/browser/run-integration.mjs`
//   - frontend/를 python http.server로 빈 포트에 서빙하고, 임시 프로필의 헤드리스 Chrome으로 frontend/integration.html을 연다
//   - 결과(제목이 RESULT/ERROR로 시작)를 출력하고, 실패하면 종료 코드 1. 자신이 띄운 Chrome·서버만 종료한다
//   - 환경 변수: CHROME(Chrome 경로), PYTHON(기본 python)
// 데모 계정(demo)으로 1,000원 이체·별칭 변경 등 실제 쓰기를 하므로 시연용 DB에서만 돌린다.
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const chromePath = process.env.CHROME ?? ["C:/Program Files/Google/Chrome/Application/chrome.exe", "/usr/bin/google-chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].find(existsSync);

const freePort = () => new Promise((done) => {
  const server = createServer().listen(0, "127.0.0.1", () => { const { port } = server.address(); server.close(() => done(port)); });
});
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

const children = [];
const profile = mkdtempSync(join(tmpdir(), "capbank-chrome-"));
function cleanup() {
  for (const child of children) {
    // Windows는 자식 프로세스 트리까지 끝내야 Chrome이 남지 않는다. 우리가 띄운 PID만 대상으로 한다
    try { process.platform === "win32" ? execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" }) : child.kill(); } catch { /* 이미 종료 */ }
  }
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* 프로필 정리 실패는 무시 */ }
}

async function main() {
  if (!chromePath) throw new Error("Chrome을 찾지 못했어요. CHROME 환경 변수로 경로를 알려 주세요.");
  const health = await fetch("http://127.0.0.1:8000/health").catch(() => null);
  if (!health) throw new Error("백엔드(http://127.0.0.1:8000)에 연결할 수 없어요. 먼저 서버를 띄워 주세요.");

  const webPort = await freePort();
  children.push(spawn(process.env.PYTHON ?? "python", ["-m", "http.server", String(webPort), "--bind", "127.0.0.1", "--directory", join(root, "frontend")], { stdio: "ignore" }));
  const debugPort = await freePort();
  children.push(spawn(chromePath, ["--headless=new", "--disable-gpu", "--window-size=500,900", `--remote-debugging-port=${debugPort}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" }));

  const pageUrl = `http://127.0.0.1:${webPort}/integration.html`;
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    await sleep(500);
    target = await fetch(`http://127.0.0.1:${debugPort}/json/new?${pageUrl}`, { method: "PUT" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  }
  if (!target) throw new Error("Chrome 디버깅 포트에 연결하지 못했어요.");

  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((done, fail) => { socket.onopen = done; socket.onerror = () => fail(new Error("WebSocket 연결 실패")); });
  let id = 0;
  const pending = new Map();
  socket.onmessage = ({ data }) => { const message = JSON.parse(data); pending.get(message.id)?.(message); };
  const title = () => new Promise((done) => {
    pending.set(++id, (message) => done(message.result?.result?.value ?? ""));
    socket.send(JSON.stringify({ id, method: "Runtime.evaluate", params: { expression: "document.title" } }));
  });

  const end = Date.now() + 180000;
  for (;;) {
    const value = await title();
    if (value.startsWith("RESULT ")) {
      const result = JSON.parse(value.slice(7));
      console.log(`통과: ${result.checked.length}개 항목 (화면 너비 ${result.width}px)`);
      result.checked.forEach((item) => console.log(" - " + item));
      return 0;
    }
    if (value.startsWith("ERROR ")) { console.error("실패: " + value.slice(6)); return 1; }
    if (Date.now() > end) { console.error("실패: 3분 안에 결과가 나오지 않았어요."); return 1; }
    await sleep(1000);
  }
}

let code = 1;
try { code = await main(); } catch (error) { console.error("실패: " + error.message); } finally { cleanup(); }
process.exit(code);
