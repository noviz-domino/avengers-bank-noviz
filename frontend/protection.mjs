const byId = (id) => document.getElementById(id);
const notice = byId("notice");
const settings = byId("settings");
const reviews = byId("reviews");
const locationButton = byId("location");
let accessToken;
const chatSessions = new Map();
let polling = false;
let locationTimer;
let locating = false;
let activityEnabled = false;
let nextActivityAt = 0;

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    cache: "no-store",
    headers: {
      ...(accessToken && { Authorization: "Bearer " + accessToken }),
      ...(body !== undefined && { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const json = await response.json();
  if (response.status === 401 && path !== "/users/login") {
    accessToken = undefined;
    chatSessions.clear();
    activityEnabled = false;
    nextActivityAt = 0;
    stopLocation();
    reviews.replaceChildren();
    byId("chat-messages").replaceChildren();
    byId("transfer-check-form-messages").replaceChildren();
    byId("bank").hidden = true;
    byId("login").hidden = false;
    throw new Error("다시 로그인해 주세요.");
  }
  if (!response.ok) throw new Error(json.error?.message || "은행 서버에서 요청을 처리하지 못했어요.");
  return json.data;
}

function showSettings(data) {
  activityEnabled = Boolean(data.active_from);
  settings.elements.location_check.checked = data.location_check;
  settings.elements.active_from.value = data.active_from || "";
  settings.elements.active_until.value = data.active_until || "";
  if (!data.location_check) stopLocation();
  locationButton.disabled = !data.location_check;
}

function submit(form, run) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    notice.textContent = "";
    try {
      await run(new FormData(form));
    } catch (error) {
      notice.textContent = error.message;
    } finally {
      if (form.elements.pin) form.elements.pin.value = "";
      button.disabled = false;
    }
  });
}

function reviewForm(action) {
  const form = document.createElement("form");
  form.dataset.action = action.action_id;
  form.innerHTML = '<p></p><label>거래 PIN<input name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required></label>'
    + '<button class="primary">내 결제예요 · 승인</button> <button type="button" class="outline">내 결제가 아니에요 · 거절</button>';
  form.querySelector("p").textContent = action.summary + " · "
    + new Date(action.expires_at).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul" }) + "까지 확인";
  const path = "/approvals/" + encodeURIComponent(action.action_id);
  submit(form, async (data) => {
    await api(path + "/approve", { method: "POST", body: { pin: data.get("pin") } });
    await refreshReviews();
    notice.textContent = "확인한 결제를 처리했어요.";
  });
  const reject = form.querySelector('button[type="button"]');
  reject.addEventListener("click", async () => {
    reject.disabled = true;
    try {
      await api(path + "/reject", { method: "POST" });
      await refreshReviews();
      notice.textContent = "결제를 거절했어요.";
    } catch (error) {
      notice.textContent = error.message;
    } finally {
      reject.disabled = false;
    }
  });
  return form;
}

async function refreshReviews() {
  if (polling) return;
  polling = true;
  try {
    const actions = (await api("/approvals")).filter((action) => action.action_type === "CARD_PAYMENT");
    const existing = new Map(Array.from(reviews.querySelectorAll("form"), (form) => [form.dataset.action, form]));
    const forms = actions.map((action) => existing.get(action.action_id) || reviewForm(action));
    if (!forms.length) {
      reviews.textContent = "확인할 결제가 없어요.";
    } else if (forms.some((form, index) => reviews.children[index] !== form) || reviews.children.length !== forms.length) {
      reviews.replaceChildren(...forms);
    }
  } finally {
    polling = false;
  }
}

submit(byId("login"), async (data) => {
  const tokens = await api("/users/login", { method: "POST", body: Object.fromEntries(data) });
  accessToken = tokens.access_token;
  byId("login").reset();
  const user = await api("/users/me");
  showSettings(await api("/cards/protection"));
  byId("pin-setup").open = !user.has_pin;
  byId("bank").hidden = false;
  byId("login").hidden = true;
  if (location.hash === "#transfer-check") byId("transfer-check").scrollIntoView();
  await refreshReviews();
});

submit(byId("pin"), async (data) => {
  await api("/users/me/pin", { method: "PUT", body: Object.fromEntries(data) });
  byId("pin").reset();
  byId("pin-setup").open = false;
  notice.textContent = "거래 PIN을 등록했어요.";
});

submit(settings, async (data) => {
  const saved = await api("/cards/protection", {
    method: "PUT",
    body: {
      location_check: data.has("location_check"),
      active_from: data.get("active_from") || null,
      active_until: data.get("active_until") || null,
      pin: data.get("pin"),
    },
  });
  showSettings(saved);
  notice.textContent = "보호 설정을 저장했어요.";
});

function stopLocation() {
  clearInterval(locationTimer);
  locationTimer = undefined;
  locationButton.textContent = "스마트폰 위치 공유 시작";
  locationButton.setAttribute("aria-pressed", "false");
}

async function updateLocation() {
  const sharing = locationTimer;
  if (!sharing || locating || document.hidden) return;
  locating = true;
  try {
    if (!navigator.geolocation) throw new Error("HTTPS로 카드 보호 페이지를 열어 위치를 공유해 주세요.");
    const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true, maximumAge: 0, timeout: 15000,
    }));
    if (locationTimer !== sharing || document.hidden) return;
    await api("/cards/protection/location", {
      method: "PUT",
      body: {
        latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy_m: position.coords.accuracy,
        observed_at: new Date(position.timestamp).toISOString(),
      },
    });
    if (locationTimer === sharing) notice.textContent = "스마트폰 위치를 공유했어요.";
  } catch (error) {
    if (locationTimer === sharing) {
      stopLocation();
      notice.textContent = error instanceof Error ? error.message : "현재 위치를 가져올 수 없어요. 브라우저 위치 권한을 확인해 주세요.";
    }
  } finally {
    locating = false;
  }
}

locationButton.addEventListener("click", () => {
  if (locationTimer) {
    stopLocation();
    notice.textContent = "위치 공유를 중지했어요. 마지막으로 공유한 위치는 최대 15분간 판단에 쓰여요.";
    return;
  }
  locationTimer = setInterval(updateLocation, 300_000);
  locationButton.textContent = "스마트폰 위치 공유 중지";
  locationButton.setAttribute("aria-pressed", "true");
  void updateLocation();
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) void updateLocation(); });

function reportMobileActivity(event) {
  const now = performance.now();
  if (!accessToken || !activityEnabled || document.hidden || !event.isTrusted || now < nextActivityAt) return;
  nextActivityAt = now + 60_000;
  void api("/cards/protection/activity", { method: "PUT" }).catch(() => {
    // The server can still ask for confirmation if the signal did not arrive.
  });
}

document.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "touch") reportMobileActivity(event);
}, { passive: true });
document.addEventListener("keydown", (event) => {
  if (navigator.maxTouchPoints > 0 && !event.repeat) reportMobileActivity(event);
});

const refresh = () => refreshReviews().catch((error) => { notice.textContent = error.message; });
byId("refresh").addEventListener("click", refresh);
setInterval(() => { if (accessToken && !document.hidden) void refresh(); }, 15000);

function setupChat(formId, path) {
  const form = byId(formId);
  submit(form, async (data) => {
    const message = data.get("message");
    const result = await api(path, { method: "POST", body: { message, session_id: chatSessions.get(path) } });
    chatSessions.set(path, result.session_id);
    for (const text of ["나 · " + message, "AI · " + result.reply]) {
      const line = document.createElement("p");
      line.textContent = text;
      byId(formId + "-messages").append(line);
    }
    form.reset();
  });
}

setupChat("chat", "/chat");
setupChat("transfer-check-form", "/chat/transfer-check");
