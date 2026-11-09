// shortcut: API 연결 전까지 src/avengers_bank/seed.py의 상품 조건을 복제한 데모 스냅샷이다.
const salary = (rate) => ({ label: "이 은행 입출금 계좌로 급여 수령", rate, available: false });
const marketing = (rate) => ({ label: "마케팅 정보 수신 동의", rate, available: true });
const first = { label: "이 은행에서 첫 예·적금 가입", rate: 30, available: true };

// 금리는 0.01% 단위 정수로 보관한다.
export const products = [
  {
    id: "stark", kind: "savings", name: "스타크 자유적금", headline: "차곡차곡, 나만의 목돈 만들기",
    description: "매달 정한 금액을 넣어 목돈을 만드는 적금입니다.",
    baseRate: 350, bonuses: [salary(50), marketing(20), first],
    minTerm: 12, maxTerm: 24, minAmount: 10_000, maxAmount: 1_000_000,
  },
  {
    id: "hero", kind: "deposit", name: "히어로 정기예금",
    description: "목돈을 한 번에 맡기고 만기에 이자와 함께 받는 예금입니다.",
    baseRate: 300, bonuses: [salary(30), marketing(20)],
    minTerm: 12, maxTerm: 36, minAmount: 1_000_000, maxAmount: 100_000_000,
  },
  {
    id: "shield", kind: "deposit", name: "쉴드 특판 예금",
    description: "정해진 기간에만 판매하는 특판 예금입니다.",
    baseRate: 380, bonuses: [], minTerm: 6, maxTerm: 12,
    minAmount: 1_000_000, maxAmount: 30_000_000, saleStart: "2026-11-01", saleEnd: "2027-12-31",
  },
  {
    id: "checking", kind: "checking", name: "캡아메리카 입출금통장",
    description: "수수료 없이 쓰는 기본 입출금 통장입니다. 이체·카드 결제 계좌로 씁니다.",
    baseRate: 10, bonuses: [],
  },
  {
    id: "junior", kind: "savings", name: "주니어 캡아메리카 적금",
    description: "사회 초년생을 위한 1년 적금입니다.",
    baseRate: 400, bonuses: [marketing(30)], minTerm: 12, maxTerm: 12,
    minAmount: 10_000, maxAmount: 300_000, minAge: 19,
  },
];

export const kinds = { all: "전체", checking: "입출금", deposit: "예금", savings: "적금" };
export const percent = (rate) => (rate / 100).toFixed(2) + "%";
export const maxRate = (product, atOpening = false) => product.baseRate
  + product.bonuses.filter((bonus) => !atOpening || bonus.available).reduce((sum, bonus) => sum + bonus.rate, 0);
export const term = (product) => product.minTerm
  ? (product.minTerm === product.maxTerm ? product.minTerm : `${product.minTerm}~${product.maxTerm}`) + "개월"
  : "기간 제한 없음";
const won = (amount) => amount >= 100_000_000 ? `${amount / 100_000_000}억 원` : `${amount / 10_000}만 원`;
export const amount = (product) => product.minAmount
  ? (product.kind === "savings" ? "월 " : "") + `${won(product.minAmount)}~${won(product.maxAmount)}`
  : "가입 금액 제한 없음";
export const todayKst = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date());
export const onSale = (product, today = todayKst()) =>
  (!product.saleStart || today >= product.saleStart) && (!product.saleEnd || today <= product.saleEnd);
export const listedProducts = (kind = "all", today = todayKst()) => products
  .filter((product) => onSale(product, today) && (kind === "all" || product.kind === kind));
