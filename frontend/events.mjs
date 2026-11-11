// 홈 배너의 상세 페이지 (#event/<id>). 관리자 게시판이 없어서 배너 내용은 여기에 둔다 (ADR 0029)
// 금리·기간 같은 금융 조건은 지어내지 않고 서버 상품 정보(/products/accounts)를 그대로 보여 준다.
import { api } from "./api.mjs";
import { esc, header, stateBlock } from "./ui.mjs";
import { amount, maxRate, term } from "./products.mjs";

export const events = {
  opening: {
    image: "banner-opening.webp",
    title: "새로운 금융의 시작, 캡아메리카뱅크",
    lead: "계좌·카드·상품을 앱 하나에서, 말하듯 물어보는 AI 상담과 함께 시작하세요.",
    points: [
      ["앱 하나로", "입출금·예금·적금 계좌와 체크·신용카드를 한 화면에서 봐요."],
      ["말하듯 물어보기", "AI 상담에 \"이번 달 카페에서 얼마 썼어?\"처럼 물으면 내 거래로 답해요."],
      ["돈은 내가 승인", "이체처럼 돈이 나가는 일은 AI가 대신하지 않아요. 내용을 확인하고 거래 PIN으로 직접 승인해요."],
      ["예산 가드", "생활비와 저축 목표를 정하면 지금 더 써도 되는 돈을 알려 줘요."],
    ],
    actions: [["#products", "상품 둘러보기", "primary"], ["#chat", "AI 상담 시작하기", "outline"]],
  },
  welcome: {
    image: "banner-welcome.webp",
    title: "첫 만남을 위한 특별한 환영",
    lead: "처음 오신 분께 부담 없이 시작할 수 있는 적금을 추천해요.",
    product: "스타크 자유적금",
    steps: ["추천 상품의 금리와 우대조건을 확인해요.", "\"바로 가입하기\"를 눌러 기간과 월 납입액을 정해요.", "가입하면 계좌 탭에서 바로 확인할 수 있어요."],
  },
};

const cta = (href, label, variant) => `<a class="ui-button ui-button--${variant} ui-event-cta" href="${href}">${esc(label)}</a>`;

function body(event, product) {
  const recommend = product
    ? `<section class="ui-event-product"><p class="ui-event-label">추천 상품</p><h2>${esc(product.name)}</h2>
      <p class="ui-event-rate"><small>${Number(product.max_preferential_rate) ? "최고 연" : "연"}(세전)</small><b>${maxRate(product)}</b></p>
      <p class="ui-event-meta">${term(product)} · ${amount(product)}</p></section>` : "";
  return `<main class="ui-event"><img src="./assets/${event.image}" alt="" width="1989" height="791">
    <h1>${esc(event.title)}</h1><p class="ui-event-lead">${esc(event.lead)}</p>
    ${event.points ? `<ul class="ui-event-points">${event.points.map(([title, text]) => `<li><strong>${esc(title)}</strong><span>${esc(text)}</span></li>`).join("")}</ul>` : ""}
    ${recommend}
    ${event.steps ? `<section><h2>참여 방법</h2><ol class="ui-event-steps">${event.steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ol></section>` : ""}
    <p class="ui-event-note">시연용 이벤트 화면이에요. 별도 경품이나 혜택은 지급되지 않아요.</p>
    <div class="ui-event-actions">${(product
      ? [[`#product/${product.product_id}/join`, `${product.name} 바로 가입하기`, "primary"], [`#product/${product.product_id}`, "상품 자세히 보기", "outline"]]
      : event.actions ?? [["#products", "상품 둘러보기", "primary"]]).map(([href, label, variant]) => cta(href, label, variant)).join("")}</div></main>`;
}

export function mountEvent(root, id) {
  let alive = true;
  const event = Object.hasOwn(events, id) ? events[id] : null;
  const head = header({ title: "이벤트", back: "back" });
  if (!event) {
    root.innerHTML = head + `<main>${stateBlock("empty", { message: "끝났거나 없는 이벤트예요." })}<a class="ui-button ui-button--outline ui-event-cta" href="#home">홈으로</a></main>`;
    return () => {};
  }
  root.innerHTML = head + body(event);
  if (event.product) {
    // 추천 상품이 판매 중이 아니면 상품 목록으로만 안내한다
    api("/products/accounts").then(({ data }) => {
      const product = data.find((item) => item.name === event.product);
      if (alive && product) root.innerHTML = head + body(event, product);
    }).catch(() => {});
  }
  return () => { alive = false; };
}
