// 카드 검색 화면 (#card-search): GET /cards/transactions 로 내 모든 카드의 사용내역을 찾는다.
// 계좌 검색(search.mjs)과 같은 모양이고, 신용카드 결제처럼 계좌 장부에 건마다 남지 않는 내역은 여기서 본다.
import { api } from "./api.mjs";
import { esc, won } from "./ext-ui.mjs";
import { header } from "./ui.mjs";
import { CATEGORIES } from "./search.mjs";

// 폼 값 → 쿼리스트링. 날짜 순서는 서버도 422로 막지만 먼저 안내한다
export function buildCardQuery(v) {
  if (v.from_date && v.to_date && v.from_date > v.to_date) return { error: "시작일이 종료일보다 늦어요." };
  const q = new URLSearchParams();
  for (const k of ["card_id", "keyword", "category", "from_date", "to_date"]) if (v[k]?.trim()) q.set(k, v[k].trim());
  return { query: q.toString() };
}

const kst = (iso) => new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
const cardLabel = (card) => (card.card_type === "DEBIT" ? "체크 " : "신용 ") + card.masked_card_num.slice(-4);

const rowHtml = (t, cards) => {
  const card = cards.find((c) => c.card_id === t.card_id);
  const canceled = t.status === "CANCELED";
  return '<li><div><strong>' + esc(t.merchant_name) + '</strong><small>' + kst(t.approved_at) + (card ? " · " + esc(cardLabel(card)) : "") + " · " + esc(t.category)
    + (canceled ? " · 취소" : "") + '</small></div><strong' + (canceled ? ' class="canceled"' : "") + ">−" + won(t.amount) + "</strong></li>";
};

export function mountCardSearch(container) {
  container.innerHTML = header({ title: "카드 검색", back: "back", heading: true }) + '<main class="ext-search"><form id="card-search-form" novalidate>'
    + '<label>가맹점<input name="keyword" maxlength="50" placeholder="예: 스타벅스"></label>'
    + '<div class="two"><label>카드<select name="card_id"><option value="">전체 카드</option></select></label>'
    + '<label>카테고리<select name="category"><option value="">전체</option>' + CATEGORIES.map((c) => "<option>" + c + "</option>").join("") + "</select></label></div>"
    + '<div class="two"><label>시작일<input name="from_date" type="date"></label><label>종료일<input name="to_date" type="date"></label></div>'
    + '<p class="error" id="e-card-search" role="alert"></p><button class="primary">검색</button></form>'
    + '<section id="card-result" aria-live="polite"></section></main>';
  const form = container.querySelector("#card-search-form");
  const result = container.querySelector("#card-result");
  const err = container.querySelector("#e-card-search");
  let cards = [];
  api("/cards").then(({ data }) => {
    cards = data;
    form.elements.card_id.insertAdjacentHTML("beforeend", cards.map((c) => '<option value="' + c.card_id + '">' + esc(cardLabel(c)) + (c.status === "LOST" ? " (분실)" : "") + "</option>").join(""));
  }).catch(() => {});

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const built = buildCardQuery(Object.fromEntries(new FormData(form)));
    err.textContent = built.error ?? "";
    if (built.error) return;
    result.innerHTML = '<p class="status" role="status">검색하는 중이에요…</p>';
    try {
      const { data } = await api("/cards/transactions" + (built.query ? "?" + built.query : ""));
      result.innerHTML = '<div class="card sum"><dl><dt>사용 합계 (취소 제외)</dt><dd>' + (data.total_amount ? "−" : "") + won(data.total_amount) + "</dd><dt>건수</dt><dd>" + data.count + "건</dd></dl></div>"
        + (data.transactions.length ? '<ul class="rows">' + data.transactions.map((t) => rowHtml(t, cards)).join("") + "</ul>" : '<p class="empty">조건에 맞는 카드 사용내역이 없어요.</p>')
        + (data.count > data.transactions.length ? '<p class="note">최근 ' + data.transactions.length + "건만 보여 줘요. 기간을 좁혀 보세요.</p>" : "");
    } catch (error) {
      result.innerHTML = '<p class="error" role="alert">' + esc(error.message) + "</p>";
    }
  });
}
