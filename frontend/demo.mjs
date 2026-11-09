export const recipients = [
  { name: "토니", number: "110-100-000101" },
  { name: "피터", number: "110-100-000102" },
];

export const dailyLimit = 1_000_000;
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
    pin: null,
    sentToday: 0,
  };
}

export function transferError(demo, draft) {
  const source = demo.accounts.find((account) => account.id === draft.source && account.kind === "checking");
  if (!source || !draft.recipient || source.number === draft.recipient.number) {
    return "출금 계좌와 다른 받는 계좌를 선택해 주세요.";
  }
  if (!Number.isSafeInteger(draft.amount) || draft.amount <= 0) return "1원 이상의 금액을 입력해 주세요.";
  if (draft.amount > source.balance) return "출금 계좌의 잔액이 부족해요.";
  if (draft.amount + demo.sentToday > dailyLimit) return "데모 일일 이체 한도를 초과했어요.";
  return "";
}

export function approveTransfer(demo, draft, pin) {
  if (!demo.pin || pin !== demo.pin) return "PIN이 일치하지 않아요.";
  const error = transferError(demo, draft);
  if (error) return error;
  const source = demo.accounts.find((account) => account.id === draft.source);
  const destination = demo.accounts.find((account) => account.number === draft.recipient.number);
  source.balance -= draft.amount;
  demo.sentToday += draft.amount;
  const date = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit" })
    .formatToParts(new Date()).filter((part) => part.type !== "literal").map((part) => part.value).join(".");
  demo.transactions.unshift({
    account: source.id, label: draft.recipient.name, date, category: "데모 이체", amount: -draft.amount,
  });
  if (destination) {
    destination.balance += draft.amount;
    demo.transactions.unshift({
      account: destination.id, label: source.name, date, category: "데모 이체", amount: draft.amount,
    });
  }
  return "";
}
