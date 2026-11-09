export const recipients = [
  { name: "토니", number: "110-100-000101" },
  { name: "피터", number: "110-100-000102" },
];

export const money = (amount) => `${amount.toLocaleString("ko-KR")}원`;

export function newDemo() {
  return {
    accounts: [
      { id: "living", name: "생활비 통장", number: "110-100-000001", balance: 2_350_000, kind: "checking" },
      { id: "reserve", name: "비상금 통장", number: "110-100-000002", balance: 750_000, kind: "checking" },
      { id: "deposit", name: "캡틴 정기예금", number: "110-100-000003", balance: 3_000_000, kind: "savings" },
      { id: "saving", name: "스타크 자유적금", number: "110-100-000004", balance: 2_000_000, kind: "savings" },
    ],
    transactions: [
      { account: "living", label: "스타크 카페", date: "11.07", category: "카페·간식", amount: -5_500 },
      { account: "living", label: "토니", date: "11.06", category: "이체", amount: -50_000 },
      { account: "living", label: "급여", date: "11.05", category: "급여", amount: 2_800_000 },
    ],
  };
}

function requestedAmount(question) {
  const match = question.match(/(?<![\d.,+−-])(\d+(?:,\d{3})*)\s*(만|천)?\s*원/);
  if (!match) return undefined;
  const amount = Number(match[1].replaceAll(",", "")) * ({ 만: 10_000, 천: 1_000 }[match[2]] ?? 1);
  return Number.isSafeInteger(amount) && amount > 0 ? amount : undefined;
}

export function replyTo(demo, question, pending) {
  if (pending || /이체|송금|보내/.test(question)) {
    if (/취소|그만/.test(question)) return { text: "데모 이체 요청을 취소했어요." };
    const draft = {
      recipient: recipients.find((person) => question.includes(person.name)) ?? pending?.recipient,
      amount: requestedAmount(question) ?? pending?.amount,
      source: demo.accounts.find((account) => account.kind === "checking" && question.includes(account.name))?.id
        ?? pending?.source,
    };
    if (!draft.recipient) return { pending: draft, text: "누구에게 보낼까요? 데모 수취인은 토니와 피터예요." };
    if (!draft.amount) return { pending: draft, text: `${draft.recipient.name}님에게 얼마를 보낼까요?` };
    if (!draft.source) return { pending: draft, text: "어느 통장에서 보낼까요? 생활비 통장과 비상금 통장 중 골라 주세요." };
    return {
      draft,
      text: `${draft.recipient.name}님에게 ${money(draft.amount)}을 보낼 준비가 됐어요. 이체 화면에서 내용을 확인하고 PIN으로 승인해 주세요.`,
    };
  }
  if (/카페|편의점|지출|썼/.test(question)) {
    const keyword = question.includes("편의점") ? "편의점" : question.includes("카페") ? "카페" : "전체";
    const total = demo.transactions
      .filter((tx) => tx.amount < 0 && tx.category !== "데모 이체" && (keyword === "전체" || tx.category.includes(keyword)))
      .reduce((sum, tx) => sum - tx.amount, 0);
    return { text: total ? `데모 거래내역의 ${keyword} 지출은 ${money(total)}이에요.` : `데모 거래내역에 ${keyword} 지출이 없어요.` };
  }
  if (/잔액|자산|얼마 있어|내 계좌/.test(question)) {
    return { text: demo.accounts.map((account) => `${account.name} ${money(account.balance)}`).join("\n") };
  }
  if (/차이|어떻게 달라/.test(question) && /예금|적금/.test(question)) {
    return { text: "정기예금은 목돈을 한 번에 맡기고, 적금은 기간을 두고 나누어 납입하는 상품이에요.", source: "데모 안내 · 예금과 적금" };
  }
  if (/스타크|적금/.test(question) && /상품|금리|조건|스타크/.test(question)) {
    return { text: "시연용 상품 안내에서는 자동이체 조건을 충족하면 우대금리를 적용하는 예시를 보여줘요.", source: "데모 안내 · 스타크 자유적금" };
  }
  if (/상품|금리|약관/.test(question)) return { text: "이 질문에 답할 상품 자료가 데모에 없어요." };
  if (/카드/.test(question)) return { text: "하단 카드 메뉴에서 보유 카드의 이용내역·혜택·한도를 확인하고, 데모 일시정지·분실 신고를 체험할 수 있어요." };
  if (/안녕|반가워/.test(question)) return { text: "안녕하세요! 계좌 잔액, 상품 안내, 이체를 물어보실 수 있어요." };
  return { text: "이 질문은 데모에서 처리하기 어려워요. 잔액, 상품, 이체 예시로 다시 물어보세요." };
}
