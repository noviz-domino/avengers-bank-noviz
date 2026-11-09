export const demoMonth = "2026-11";

export function newCardsDemo() {
  return [
    {
      id: "captain", name: "캡아메리카 체크카드", type: "DEBIT", last4: "4821", status: "ACTIVE",
      account: "생활비 통장 · 110-***-000001", dailyLimit: 1_000_000, annualFee: 0,
      benefits: "연회비 없음. 결제하면 연결된 입출금 계좌에서 바로 빠져나갑니다. 편의점·카페 5% 할인.",
      transactions: [
        { date: "2026-11-07", name: "스타크 카페", category: "카페", amount: 5_500 },
        { date: "2026-11-06", name: "히어로 마트", category: "쇼핑", amount: 38_000 },
        { date: "2026-11-05", name: "편의점", category: "편의점", amount: 8_000 },
        { date: "2026-11-03", name: "어벤져스 스토어", category: "쇼핑", amount: 187_000 },
        { date: "2026-10-28", name: "스타크 카페", category: "카페", amount: 4_500 },
      ],
    },
    {
      id: "stark", name: "스타크 신용카드", type: "CREDIT", last4: "0914", status: "ACTIVE",
      account: "생활비 통장 · 110-***-000001", dailyLimit: 1_000_000, annualFee: 15_000,
      creditLimit: 3_000_000, outstanding: 420_000, paymentDay: 14,
      benefits: "연회비 1만 5천 원. 쓴 금액은 대금 출금일에 한 번에 빠져나갑니다. 해외 결제 수수료 없음.",
      transactions: [
        { date: "2026-11-08", name: "히어로 마트", category: "쇼핑", amount: 75_000 },
        { date: "2026-11-04", name: "스타크 다이닝", category: "식사", amount: 45_000 },
        { date: "2026-10-29", name: "어벤져스 스토어", category: "쇼핑", amount: 300_000 },
      ],
    },
  ];
}

export function monthTransactions(card, month = demoMonth) {
  return card.transactions.filter((tx) => tx.date.startsWith(`${month}-`));
}

export function monthTotal(card, month = demoMonth) {
  return monthTransactions(card, month).reduce((sum, tx) => sum + tx.amount, 0);
}

export function changeCardStatus(card, status) {
  if (card.status === "LOST" || !["SUSPENDED", "LOST"].includes(status)) return false;
  card.status = status;
  return true;
}
