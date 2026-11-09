// 실제 백엔드 API 클라이언트. 서버가 /app으로 서빙하면 같은 주소, 로컬 개발 서버(다른 포트)면 8000번을 부른다.
const local = ["127.0.0.1", "localhost"].includes(globalThis.location?.hostname);
const BASE = local && globalThis.location.port !== "8000" ? "http://127.0.0.1:8000" : "";
const KEY = "capbank.tokens";

const store = {
  get() { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } },
  set(value) { try { value ? sessionStorage.setItem(KEY, JSON.stringify(value)) : sessionStorage.removeItem(KEY); } catch { /* 저장 불가: 메모리만 */ } },
};
let tokens = store.get();
let refreshing;

export class ApiError extends Error {
  constructor(status, code, message, details = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const isSignedIn = () => !!tokens?.access_token;
export const accessToken = () => tokens?.access_token;
export const apiBase = () => BASE;

async function send(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && tokens) headers.Authorization = "Bearer " + tokens.access_token;
  let response;
  try {
    response = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.");
  }
  const json = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = json?.error ?? {};
    throw new ApiError(response.status, error.code ?? "HTTP_" + response.status, error.message ?? "요청을 처리하지 못했어요.", error.details ?? []);
  }
  return json;
}

async function refresh() {
  if (!tokens?.refresh_token) return false;
  refreshing ??= send("/users/token/refresh", { method: "POST", body: { refresh_token: tokens.refresh_token }, auth: false })
    .then((json) => { tokens = json.data; store.set(tokens); return true; })
    .catch(() => { tokens = null; store.set(null); return false; })
    .finally(() => { refreshing = undefined; });
  return refreshing;
}

// 성공 응답 전체({data, message})를 돌려준다. access token이 만료되면 한 번 갱신하고 다시 보낸다.
export async function api(path, options = {}) {
  try {
    return await send(path, options);
  } catch (error) {
    if (error.status !== 401 || options.auth === false || !(await refresh())) {
      if (error.status === 401 && options.auth !== false) onSessionExpired();
      throw error;
    }
    return send(path, options);
  }
}

let expiredHandler = () => {};
export const onExpired = (handler) => { expiredHandler = handler; };
function onSessionExpired() { tokens = null; store.set(null); expiredHandler(); }

export async function login(loginId, password) {
  const json = await send("/users/login", { method: "POST", body: { login_id: loginId, password, device_name: "모바일 웹" }, auth: false });
  tokens = json.data;
  store.set(tokens);
}

export async function logout() {
  const refreshToken = tokens?.refresh_token;
  tokens = null;
  store.set(null);
  if (refreshToken) await send("/users/logout", { method: "POST", body: { refresh_token: refreshToken }, auth: false }).catch(() => {});
}

// 이체·예금 등 돈 이동 요청의 중복 방지 키
export const idempotencyKey = () => crypto.randomUUID();
