# 카드 화면

공통 앱의 `#cards` 메뉴에서 `mountCards(root, { embedded: true })`를 빈 전용 컨테이너에 호출합니다. 반환된 정리 함수를 화면 교체 전에 호출합니다. 스타일은 `cards.css`(`cards-` 접두사)를 씁니다.

실제 API로 동작합니다 (`api.mjs`, 승인은 `approval.mjs`).

| 기능 | API |
|---|---|
| 목록·상세 | `GET /cards`, `GET /cards/{id}` |
| 이용내역(이달 합계, 취소 건 표시) | `GET /cards/{id}/transactions` |
| 한도 | `GET /cards/{id}/limits` |
| 혜택·연회비 | `GET /products/cards` (상품 이름으로 연결) |
| 발급(상품·연결 입출금 계좌·신용은 결제일) | `POST /cards` |
| 일시정지·분실 신고 (확인 대화상자 뒤 바로 적용, 분실은 되돌릴 수 없음) | `POST /cards/{id}/suspend` |
| 정지 해제 | `POST /cards/{id}/unsuspend` → `202` → `openApproval(action_id)` (PIN) |

- 크게 보기·목록 보기, 카드 선택, 이용내역·혜택·관리·한도 화면은 이전 데모와 같습니다. 보기 방식·선택은 재진입하면 초기화합니다.
- 월 이용금액은 한국 날짜 기준 이달의 승인(`APPROVED`) 건 합계입니다. 신용 미결제 사용액(`credit_used`)은 전월분을 포함할 수 있어 따로 보여 줍니다. 할인 실적 집계는 서버에 없어 제공하지 않습니다.
- 로딩·빈 목록(발급 안내)·오류(다시 시도) 상태가 있고 서버가 준 문자열은 모두 이스케이프합니다.
- 데모 데이터와 독립 페이지(`cards.html`)는 없앴습니다.

## 검증

```bash
node --test frontend/*.test.mjs
```

수동 확인(서버 실행 중, 로그인 후): 카드 발급 → 목록·크게 보기 → 이용내역·혜택·한도 → 일시정지 → PIN으로 해제 → 분실 신고. 320px에서 가로 넘침과 포커스를 확인합니다. 정지·분실 시험은 새로 발급한 시험 카드로만 합니다.
