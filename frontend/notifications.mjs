// 알림 화면 (#notifications, 홈 머리글의 종 버튼). 위쪽 하위 메뉴 4개: 입출금내역·카드내역·혜택(광고)·공지사항
// 알림 서버(푸시·읽음 표시)는 아직 없어서, 입출금·카드는 최근 거래를 알림처럼 보여 주고 혜택·공지는 코드에 둔다.
import { api } from "./api.mjs";
import { esc, header, stateBlock, listRow, icon } from "./ui.mjs";
import { money, shortDate } from "./format.mjs";
import { events } from "./events.mjs";

export const TABS = [["tx", "입출금내역"], ["card", "카드내역"], ["benefit", "혜택(광고)"], ["notice", "공지사항"]];

// 공지는 이 서비스에 대한 사실만 적는다 (금융 조건·혜택을 지어내지 않음)
export const NOTICES = [
  { date: "2026-11-11", title: "캡아메리카뱅크는 시연용 서비스예요", body: "포트폴리오용으로 만든 은행 앱이에요. 계좌·카드·이체는 모두 시연 데이터이고 실제 돈은 오가지 않아요." },
  { date: "2026-11-11", title: "공개 서버 운영 시간 안내", body: "공개 주소는 평일 11:25~18:00에만 열려요. 그 밖의 시간에는 접속되지 않아요." },
  { date: "2026-11-11", title: "AI 상담 이용 안내", body: "짧은 시간에 여러 번 물으면 잠시 기다린 뒤 다시 물어봐야 해요. 이체처럼 돈이 나가는 일은 AI가 대신하지 않고, 내용을 확인한 뒤 거래 PIN으로 직접 승인해요." },
];

const txRow = (t) => listRow({
  title: (t.amount > 0 ? "입금 " : "출금 ") + money(Math.abs(t.amount)),
  subtitle: shortDate(t.created_at) + " · " + (t.counterparty_name || t.memo || t.category || ""),
  amount: (t.amount > 0 ? "+" : "−") + money(Math.abs(t.amount)), credit: t.amount > 0, icon: "wallet",
});
const cardRow = (t) => listRow({
  title: (t.status === "CANCELED" ? "승인 취소 " : "카드 승인 ") + money(t.amount),
  subtitle: shortDate(t.approved_at) + " · " + t.merchant_name, amount: "−" + money(t.amount), icon: "cards",
});

async function body(tab) {
  if (tab === "tx") {
    const { data } = await api("/transactions?limit=20");
    return data.transactions.length ? '<ul class="ui-notify-list">' + data.transactions.map(txRow).join("") + "</ul>" : stateBlock("empty", { message: "아직 입출금 알림이 없어요." });
  }
  if (tab === "card") {
    const { data } = await api("/cards/transactions");
    return data.transactions.length ? '<ul class="ui-notify-list">' + data.transactions.slice(0, 20).map(cardRow).join("") + "</ul>" : stateBlock("empty", { message: "아직 카드 알림이 없어요." });
  }
  if (tab === "benefit") {
    return '<ul class="ui-notify-links">' + Object.entries(events).map(([id, e]) =>
      `<li><a href="#event/${id}">${icon("gift")}<span><strong>${esc(e.title)}</strong><small>${esc(e.lead)}</small></span>${icon("chevron")}</a></li>`).join("") + "</ul>";
  }
  return '<div class="ui-notices">' + NOTICES.map((n) =>
    `<details><summary><strong>${esc(n.title)}</strong><small>${esc(n.date)}</small></summary><p>${esc(n.body)}</p></details>`).join("") + "</div>";
}

export function mountNotifications(root) {
  let alive = true;
  let tab = "tx";
  async function draw() {
    root.innerHTML = header({ title: "알림", back: "back", heading: true })
      + '<main class="ui-notify"><div class="segments ui-notify-tabs" role="group" aria-label="알림 종류">'
      + TABS.map(([id, label]) => `<button type="button" data-notify-tab="${id}" aria-pressed="${id === tab}">${label}</button>`).join("")
      + '</div><section id="notify-body" aria-live="polite">' + stateBlock("loading") + "</section></main>";
    const current = tab;
    let html;
    try { html = await body(current); } catch (error) { html = stateBlock("error", { message: error.message }); }
    if (alive && current === tab) root.querySelector("#notify-body").innerHTML = html;
  }
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-notify-tab]");
    if (!button) return;
    tab = button.dataset.notifyTab;
    draw();
  });
  draw();
  return () => { alive = false; };
}
