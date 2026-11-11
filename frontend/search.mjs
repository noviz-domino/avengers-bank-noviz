// 계좌 검색 화면 (#search, 계좌 탭 머리글): GET /transactions 조건 검색 + 조건 전체 합계. 카드 사용내역은 card-search.mjs
import { api } from "./api.mjs";
import { esc, won } from "./ext-ui.mjs";
import { header } from "./ui.mjs";

export const CATEGORIES = ["식사", "카페·간식", "외식·술자리", "교통", "쇼핑", "의료", "주거·통신", "여가", "이체", "저축·내 계좌", "수입", "대출", "카드 대금", "기타"];

// 폼 값 → 쿼리스트링. 잘못된 조합은 { error }로 돌려준다 (서버도 422로 막지만 먼저 안내)
export function buildQuery(v, before) {
  if (v.from_date && v.to_date && v.from_date > v.to_date) return { error: "시작일이 종료일보다 늦어요." };
  const num = (s) => (String(s ?? "").trim() === "" ? null : Number(s));
  const min = num(v.min_amount);
  const max = num(v.max_amount);
  if ([min, max].some((n) => n !== null && !(Number.isInteger(n) && n >= 0))) return { error: "금액은 0 이상의 숫자로 입력해 주세요." };
  if (min !== null && max !== null && min > max) return { error: "최소 금액이 최대 금액보다 커요." };
  const q = new URLSearchParams({ limit: "20" });
  for (const k of ["from_date", "to_date", "category", "direction", "keyword"]) if (v[k]?.trim()) q.set(k, v[k].trim());
  if (min !== null) q.set("min_amount", min);
  if (max !== null) q.set("max_amount", max);
  if (before) q.set("before", before);
  return { query: q.toString() };
}

// created_at(UTC ISO) → 한국 날짜·시각
const kst = (iso) => new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

const rowHtml = (t) => '<li><div><strong>' + esc(t.counterparty_name || t.memo || t.tx_type) + '</strong><small>' + kst(t.created_at) + (t.category ? " · " + esc(t.category) : "")
  + (t.counterparty_name && t.memo ? " · " + esc(t.memo) : "") + '</small></div><strong class="' + (t.amount > 0 ? "credit" : "") + '">' + (t.amount > 0 ? "+" : "−") + won(Math.abs(t.amount)) + "</strong></li>";

/** ctx: { go } */
export function mountSearch(container, ctx) {
  // 뒤로는 열기 전 화면으로 (홈·메뉴 어디서 왔든). 메뉴로 고정하면 메뉴의 뒤로와 서로 오가며 갇힌다
  container.innerHTML = header({ title: "계좌 검색", back: "back", heading: true }) + '<main class="ext-search"><form id="search-form" novalidate>'
    + '<label>검색어<input name="keyword" maxlength="50" placeholder="메모·상대방 이름"></label>'
    + '<div class="two"><label>시작일<input name="from_date" type="date"></label><label>종료일<input name="to_date" type="date"></label></div>'
    + '<div class="two"><label>구분<select name="direction"><option value="">전체</option><option value="IN">입금</option><option value="OUT">출금</option></select></label>'
    + '<label>카테고리<select name="category"><option value="">전체</option>' + CATEGORIES.map((c) => "<option>" + c + "</option>").join("") + "</select></label></div>"
    + '<div class="two"><label>최소 금액<input name="min_amount" inputmode="numeric" placeholder="0"></label><label>최대 금액<input name="max_amount" inputmode="numeric"></label></div>'
    + '<p class="error" id="e-form" role="alert"></p><button class="primary">검색</button></form>'
    + '<section id="result" aria-live="polite"></section></main>';
  const form = container.querySelector("#search-form");
  const result = container.querySelector("#result");
  const err = container.querySelector("#e-form");
  let values;

  async function load(before) {
    const built = buildQuery(values, before);
    err.textContent = built.error ?? "";
    if (built.error) return;
    if (!before) result.innerHTML = '<p class="status" role="status">검색하는 중이에요…</p>';
    try {
      const { data } = await api("/transactions?" + built.query);
      const rows = data.transactions.map(rowHtml).join("");
      if (!before) {
        result.innerHTML = '<div class="card sum"><dl><dt>입금 합계</dt><dd class="credit">+' + won(data.total_in) + "</dd><dt>출금 합계</dt><dd>−" + won(data.total_out) + "</dd></dl></div>"
          + (rows ? '<ul class="rows"></ul>' : '<p class="empty">조건에 맞는 거래가 없어요.</p>');
      }
      result.querySelector(".rows")?.insertAdjacentHTML("beforeend", rows);
      result.querySelector("#more")?.remove();
      if (data.next_before) {
        result.insertAdjacentHTML("beforeend", '<button type="button" class="outline" id="more">더 보기</button>');
        result.querySelector("#more").addEventListener("click", () => load(data.next_before));
      }
    } catch (error) {
      result.innerHTML = '<p class="error" role="alert">' + esc(error.message) + "</p>";
    }
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    values = Object.fromEntries(new FormData(form));
    load();
  });
}
