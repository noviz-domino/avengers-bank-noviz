// 서버 응답을 화면에 보여 주는 순수 함수 모음 (DOM 없이 테스트한다)
export const accountName = (account) => account.nickname ?? account.product_name;
export const kindOf = (account) => (account.account_type === "CHECKING" ? "checking" : "savings");

// 숫자 12자리면 110-101-000002 꼴로 맞춘다. 그 밖에는 서버가 거르게 입력 그대로 보낸다
export function normalizeAccountNum(text) {
  const digits = text.replace(/[-\s]/g, "");
  return /^\d{12}$/.test(digits) ? `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}` : text.trim();
}

// 1 이상의 정수만 받는다 (쉼표 허용). 아니면 0
export function parseAmount(text) {
  const value = text.trim();
  if (!/^[0-9][0-9,]*$/.test(value)) return 0;
  const amount = Number(value.replaceAll(",", ""));
  return Number.isSafeInteger(amount) ? amount : 0;
}

const dateFormat = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit" });
export const shortDate = (iso) => dateFormat.formatToParts(new Date(iso)).filter((p) => p.type !== "literal").map((p) => p.value).join(".");

const TYPE_LABEL = {
  DEPOSIT: "입금", WITHDRAW: "출금", TRANSFER_IN: "입금", TRANSFER_OUT: "이체", INTERNAL_IN: "내 계좌 입금",
  INTERNAL_OUT: "내 계좌 이체", CARD_PAYMENT: "카드 결제", CARD_BILL: "카드 대금", INTEREST: "이자", REFUND: "환불",
};
export const txLabel = (tx) => tx.counterparty_name ?? tx.memo ?? TYPE_LABEL[tx.tx_type] ?? tx.tx_type;

export const money = (amount) => `${amount.toLocaleString("ko-KR")}원`;

// 개설일처럼 연도까지 보여 줄 날짜. 서버 UTC 시각을 한국 날짜로 바꾼다 (2026.11.09)
const longFormat = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" });
export const longDate = (iso) => longFormat.format(new Date(iso)).replaceAll("-", ".");

const ACCOUNT_TYPE = { CHECKING: "입출금", DEPOSIT: "예금", SAVINGS: "적금" };
export const accountType = (account) => ACCOUNT_TYPE[account.account_type] ?? "계좌";

// 서버 승인 summary("생활비(110-…)에서 토니 스타크님(110-…)에게 1,000원 보내기")에서 남의 계좌 받는 분 이름만 꺼낸다.
// 서버가 확인한 이름만 쓰고, 문장 꼴이 다르면 null이라 화면은 이름 없이 금액만 보여 준다
export function recipientName(summary) {
  return /\)에서 ([^()]+님)\(\d{3}-\d{3}-\d{6}\)에게 [\d,]+원 보내기$/.exec(summary ?? "")?.[1] ?? null;
}
