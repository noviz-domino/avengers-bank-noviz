// 전체 거래내역 화면 (#search)과 거래 검색 조건 만들기(buildQuery). 계좌별 검색은 app.mjs 계좌 상세, 카드 사용내역은 card-search.mjs
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

/** 전체 거래내역 (#search, 홈 "최근 거래"의 전체보기): 모든 계좌의 거래를 최근 것부터. 검색은 계좌 상세에서 한다 */
export function mountSearch(container) {
  container.innerHTML = header({ title: "전체 거래내역", back: "back", heading: true }) + '<main class="ext-search"><section id="result" aria-live="polite"><p class="status" role="status">불러오는 중이에요…</p></section></main>';
  const result = container.querySelector("#result");

  async function load(before) {
    try {
      const { data } = await api("/transactions?" + buildQuery({}, before).query);
      if (!before) result.innerHTML = data.transactions.length ? '<ul class="rows"></ul>' : '<p class="empty">아직 거래가 없어요.</p>';
      result.querySelector(".rows")?.insertAdjacentHTML("beforeend", data.transactions.map(rowHtml).join(""));
      result.querySelector("#more")?.remove();
      if (data.next_before) {
        result.insertAdjacentHTML("beforeend", '<button type="button" class="outline" id="more">더 보기</button>');
        result.querySelector("#more").addEventListener("click", () => load(data.next_before));
      }
    } catch (error) {
      result.innerHTML = '<p class="error" role="alert">' + esc(error.message) + "</p>";
    }
  }
  load();
}
