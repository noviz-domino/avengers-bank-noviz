const get = (id) => document.getElementById(id);
const notice = get("status");
const demo = get("demo");
const options = get("options");
const bundleResult = get("bundle-result");
const planResult = get("plan-result");
const won = (amount) => amount.toLocaleString("ko-KR") + "원";
const groups = { cafe: "카페", meal: "식사", transit: "교통", convenience: "편의점" };
const routeLabels = { fastest: "시간이 짧은 코스", cheapest: "결제액이 낮은 코스", fastest_and_cheapest: "시간·금액을 함께 아끼는 코스" };
const sessions = new Map();
let token;
let locationSample;

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method,
    cache: "no-store",
    headers: {
      ...(token && { Authorization: "Bearer " + token }),
      ...(body !== undefined && { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json();
  if (response.status === 401 && path !== "/users/login") {
    token = undefined;
    locationSample = undefined;
    sessions.clear();
    bundleResult.replaceChildren();
    planResult.replaceChildren();
    get("benefits").hidden = true;
    get("login").hidden = false;
    throw new Error("다시 로그인해 주세요.");
  }
  if (!response.ok) throw new Error(payload.error?.message || "은행 서버에서 요청을 처리하지 못했어요.");
  return payload.data;
}

function onSubmit(form, run) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button:not([type="button"])');
    submit.disabled = true;
    notice.textContent = "";
    try {
      await run(new FormData(form));
    } catch (error) {
      notice.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
}

function showCredits() {
  const picked = [...options.querySelectorAll("input:checked")];
  const credits = picked.reduce((total, input) => total + Number(input.dataset.credits), 0);
  get("credits").textContent = credits + " / 100크레딧";
}

function selectOffers(offers) {
  const ids = new Set(offers.map((offer) => offer.offer_id));
  for (const input of options.querySelectorAll("input")) input.checked = ids.has(input.value);
  showCredits();
}

onSubmit(get("login"), async (data) => {
  token = (await api("/users/login", "POST", Object.fromEntries(data))).access_token;
  get("login").reset();
  const settings = await api("/products/benefits");
  const labels = settings.catalogue.map((offer) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = "offer_ids";
    input.value = offer.offer_id;
    input.dataset.credits = offer.credits;
    label.append(input, " " + offer.label + " · " + offer.credits + "크레딧 · 월 최대 " + won(offer.monthly_cap_won));
    return label;
  });
  options.replaceChildren(...labels);
  selectOffers(settings.saved.offers);
  if (settings.needs_review) notice.textContent = "상품 조건이 바뀌었어요. 혜택 구성을 다시 골라주세요.";
  get("login").hidden = true;
  get("benefits").hidden = false;
});
options.addEventListener("change", showCredits);

onSubmit(get("selection-form"), async (data) => {
  const saved = await api("/products/benefits", "PUT", { offer_ids: data.getAll("offer_ids") });
  selectOffers(saved.offers);
  notice.textContent = "혜택 구성안을 저장했어요. 코스 화면에서 예상 절감액을 미리 볼 수 있어요.";
});

async function chat(mode, message, fields = {}) {
  const useDemo = demo.checked;
  const sessionKey = mode + ":" + useDemo;
  const result = await api("/chat/benefits", "POST", {
    mode, demo: useDemo, message, session_id: sessions.get(sessionKey), ...fields,
  });
  sessions.set(sessionKey, result.session_id);
  return result;
}

onSubmit(get("bundle-form"), async (data) => {
  const result = await chat("bundle", data.get("message"));
  bundleResult.replaceChildren(element("p", result.reply));
  const rec = result.recommendation;
  if (!rec) return;
  bundleResult.append(element("p", (rec.source === "demo" ? "시연 소비 · " : "내 카드 소비 · ")
    + "최근 " + rec.periods + "개월"));
  const patterns = document.createElement("ul");
  for (const pattern of rec.patterns) {
    const names = pattern.frequent_merchants.join(", ");
    patterns.append(element("li", groups[pattern.group] + " · " + pattern.months + "개월 이용 · "
      + pattern.visits + "회 · 월평균 " + won(pattern.monthly_spend_won) + " · " + names));
  }
  bundleResult.append(patterns);
  if (!rec.bundle.offers.length) {
    bundleResult.append(element("p", "과거 기록에서 예상 할인이 있는 조합을 찾지 못했어요."));
    return;
  }
  bundleResult.append(element("strong", rec.bundle.credits + "크레딧 · 월평균 예상 할인 " + won(rec.monthly_saving_won)));
  bundleResult.append(element("p", rec.bundle.offers.map((offer) => offer.label).join(" · ")));
  const adopt = element("button", "추천 구성 선택");
  adopt.className = "outline";
  adopt.type = "button";
  adopt.addEventListener("click", () => selectOffers(rec.bundle.offers));
  bundleResult.append(adopt);
});

demo.addEventListener("change", () => {
  get("live-inputs").hidden = demo.checked;
  get("live-inputs").disabled = demo.checked;
  if (demo.checked) locationSample = undefined;
  bundleResult.replaceChildren();
  planResult.replaceChildren();
});

get("share-location").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    if (!navigator.geolocation) throw new Error("HTTPS에서 현재 위치를 공유할 수 있어요.");
    const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true, maximumAge: 0, timeout: 15000,
    }));
    if (demo.checked || !token) return;
    locationSample = { at: Date.now(), latitude: Number(position.coords.latitude.toFixed(4)),
      longitude: Number(position.coords.longitude.toFixed(4)) };
    notice.textContent = "위치를 확인했어요. 코스 검색 시 카카오맵에 전달돼요.";
  } catch (error) {
    locationSample = undefined;
    notice.textContent = error instanceof Error ? error.message : "위치를 확인할 수 없어요. 위치 권한을 확인해 주세요.";
  } finally {
    button.disabled = false;
  }
});

function link(text, url) {
  const node = element("a", text);
  node.href = url;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}

function showRoute(route, budget) {
  const article = document.createElement("article");
  article.append(element("h3", routeLabels[route.label]));
  article.append(element("p", "왕복 약 " + route.estimated_minutes + "분 · 예상 " + won(route.total_won)
    + " · 혜택 전 " + won(route.total_before_benefits_won)));
  if (route.total_without_coupons_won > route.total_won) {
    article.append(element("p", "쿠폰을 쓰지 않으면 " + won(route.total_without_coupons_won) + " 예상"
      + (route.total_without_coupons_won > budget ? " · 예산 초과" : "")));
  }
  const stops = document.createElement("ol");
  for (const stop of route.stops) {
    const item = document.createElement("li");
    item.append(stop.map_url ? link(stop.name, stop.map_url) : element("strong", stop.name));
    item.append(element("small", stop.address + " · 예상 " + won(stop.price_won)));
    if (stop.benefit) {
      item.append(element("p", stop.benefit + " · " + won(stop.discount_won) + " 절감"
        + (stop.card_name ? " · " + stop.card_name : "")));
    }
    if (stop.coupon_until) {
      item.append(element("small", stop.coupon_until + "까지"
        + (stop.coupon_minimum_won ? " · " + won(stop.coupon_minimum_won) + " 이상" : "")
        + (stop.coupon_requires_channel ? " · 채널 추가 필요" : "")));
    }
    if (stop.coupon_url) item.append(link("쿠폰 출처 보기", stop.coupon_url));
    stops.append(item);
  }
  article.append(stops);
  return article;
}

onSubmit(get("plan-form"), async (data) => {
  const fields = {
    budget_won: Number(data.get("budget")),
    available_minutes: Number(data.get("minutes")),
    allow_channel_coupon: data.has("allow_channel"),
    preview_bundle: data.has("preview"),
  };
  if (!demo.checked) {
    if (!locationSample || Date.now() - locationSample.at > 300_000) throw new Error("먼저 현재 위치를 공유해 주세요.");
    fields.location = { latitude: locationSample.latitude, longitude: locationSample.longitude };
    fields.meal_price_won = Number(data.get("meal"));
    fields.cafe_price_won = Number(data.get("cafe"));
  }
  const result = await chat("nearby", data.get("message"), fields);
  planResult.replaceChildren(element("p", result.reply));
  const plan = result.plan;
  if (!plan) return;
  planResult.append(element("small", (plan.source === "demo" ? "시연 매장·가격" : "카카오맵 매장 · 입력한 예상 가격")
    + " · 도보·체류시간 추정 · 영업 및 대기시간은 매장에서 확인"));
  if (plan.preview_bundle) planResult.append(element("small", "100크레딧 조합은 미리보기 금액이에요."));
  if (!plan.routes.length) planResult.append(element("p", "이 조건에 맞는 코스를 찾지 못했어요."));
  for (const route of plan.routes) planResult.append(showRoute(route, plan.budget_won));
});
