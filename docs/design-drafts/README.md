# 디자인 시안 보관

작성일: 2026-11-07 (Asia/Seoul)

최종 정리: 2026-11-08. **다른 컴퓨터에서 이어갈 때는 [HANDOFF.md](HANDOFF.md)를 먼저 읽으세요.** 최신 선택, 이미지와 결정 사이의 차이, 남은 작업을 한곳에 정리했습니다. 아래 문서는 시안 생성·수정 이력입니다. 과거의 선택 대기·선호 표현보다 HANDOFF.md의 최종 상태를 우선합니다.

이 대화에서 생성한 시안 43개를 선택 여부와 관계없이 모두 보관합니다. 파일 번호는 생성 순서이며, 화면별 선택 번호와 다릅니다. 원본 PNG를 복사했으며 이미지는 정적인 디자인 시안입니다.

바로 다음 작업과 순서는 [NEXT_STEPS.md](NEXT_STEPS.md)를 참고합니다.

## 선택한 방향

- 홈: 초기 1번을 바탕으로 수정. 최신 이미지: [14-home-compact-privacy-latest.png](14-home-compact-privacy-latest.png).
- 상품: **1번 선택** — [15-products-option-1-selected.png](15-products-option-1-selected.png).
- AI 상담: **3번 선택** — [20-ai-chat-option-3-selected.png](20-ai-chat-option-3-selected.png). 계좌·거래, 상품 안내, 이체의 질문 예시를 모두 제공합니다.

## 유지할 디자인과 후속 수정

- 모바일 중심, 좌우 여백 24px. 크림색·화이트·네이비 바탕, 방패 로고.
- 입출금 블루, 예금·적금 세이지 그린, 최근 거래 앰버로 제목 영역 구분.
- 계좌명·번호는 왼쪽, 잔액은 오른쪽, 이체 버튼은 잔액 아래 오른쪽 정렬.
- 총자산 숨김은 오른쪽 위의 작은 눈 아이콘으로 표시.
- 광고는 하나의 고정 영역에서 전환. 다음 장 미리 노출·동그란 페이지 표시는 제거. 페이지 수와 재생·정지는 이미지 위에 작게 겹침.
- **홈의 승인 대기 이체 안내는 제거하기로 결정했습니다. 최신 이미지에는 아직 남아 있으므로 후속 디자인에서 삭제해야 합니다.**
- 이체는 해당 진행 흐름에서 확인·PIN 승인·결과로 끝내며, 이탈·취소 시 종료하는 방향. 결과 불명 통신 오류는 실제 처리 여부를 먼저 확인. 기존 백엔드와의 정합성은 구현 시 확인합니다.
- 음성 입력은 추후 계획이며 현재 화면에 넣지 않습니다. 예산 관리도 현재 구현 범위가 아닙니다.
- 상품 금리와 이벤트는 프로젝트 데모 데이터·시안 예시입니다.

## 초기 생성 이미지 목록 (1~20)

| 파일 | 내용 |
|---|---|
| [01-home-option-1-blue.png](01-home-option-1-blue.png) | 홈 초기 1번 — 최초 선택 |
| [02-home-option-2-white-shield.png](02-home-option-2-white-shield.png) | 홈 초기 2번 — 방패 로고 참조 |
| [03-home-option-3-navy.png](03-home-option-3-navy.png) | 홈 초기 3번 |
| [04-home-revision-wide.png](04-home-revision-wide.png) | 홈 확장 수정 — 모바일 비율 수정 전 |
| [05-home-revision-mobile.png](05-home-revision-mobile.png) | 홈 확장 수정 — 모바일 세로형 |
| [06-banner-bank-opening.png](06-banner-bank-opening.png) | 신규 오픈 배너 |
| [07-banner-signup-event.png](07-banner-signup-event.png) | 신규가입 이벤트 배너 |
| [08-home-banner-carousel-peek.png](08-home-banner-carousel-peek.png) | 배너 배치 — 다음 장 노출 수정 전 |
| [09-home-banner-overlay-controls.png](09-home-banner-overlay-controls.png) | 배너 한 칸 전환·이미지 위 제어 |
| [10-home-right-aligned-balances.png](10-home-right-aligned-balances.png) | 계좌 잔액 오른쪽 정렬 |
| [11-home-shield-logo.png](11-home-shield-logo.png) | 방패 로고 반영 |
| [12-home-cream-neutral.png](12-home-cream-neutral.png) | 크림·중성색 조정 |
| [13-home-category-colors.png](13-home-category-colors.png) | 입출금 블루·예적금 세이지·최근 거래 앰버 |
| [14-home-compact-privacy-latest.png](14-home-compact-privacy-latest.png) | 최신 홈 이미지 — 눈 아이콘 축소; 승인 대기 안내 제거는 미반영 |
| [15-products-option-1-selected.png](15-products-option-1-selected.png) | 상품 1번 — 선택 |
| [16-products-option-2.png](16-products-option-2.png) | 상품 2번 |
| [17-products-option-3.png](17-products-option-3.png) | 상품 3번 |
| [18-ai-chat-option-1.png](18-ai-chat-option-1.png) | AI 상담 1번 |
| [19-ai-chat-option-2.png](19-ai-chat-option-2.png) | AI 상담 2번 |
| [20-ai-chat-option-3-selected.png](20-ai-chat-option-3-selected.png) | AI 상담 3번 — 선택 |

## 생성 방식

기본 제공 Imagegen 도구로 생성·수정했습니다. fallback CLI는 사용하지 않았습니다. 프롬프트 방향은 홈 모바일 자산 종합 보기 → 레이아웃·브랜드·색상 순차 수정, 오픈/가입 이벤트 배너, 상품 탐색 3안, AI 상담 3안입니다. 각 이미지의 원본 생성 ID와 SHA-256은 manifest.json에 기록했습니다.


## 카드 화면 시안 (2026-11-07)

- [21-cards-option-1.png](21-cards-option-1.png): 카드 이미지 중심.
- [22-cards-option-2.png](22-cards-option-2.png): 이용금액 중심.
- [23-cards-option-3.png](23-cards-option-3.png): 보유 카드 목록 중심.
- 선택 대기. 기존 크림·네이비·방패 브랜드와 이용 내역/한도 확인/카드 관리 구조를 적용했습니다.
- 시안 1의 요일 표기는 생성 오류입니다. 실제 2026-11-07은 토요일이며, 후속 정리 시 요일을 빼거나 바로잡아야 합니다.
- 모든 이용금액·한도·카드번호 끝자리는 디자인 예시입니다.
- 시안 2의 월 이용금액과 신용 미결제 사용액은 서로 다른 지표입니다. 남은 한도는 미결제 사용액을 기준으로 계산해야 하며 후속 설계에서 구분합니다.
- 생성 도구: 기본 제공 Imagegen. 프롬프트 방향: 내 카드 한 장 / 이용금액 먼저 / 내 지갑 한눈에. 상품 1번을 브랜드 참조 이미지로 첨부했습니다.

## 카드 화면 추가 결정 및 아이디어

### 카드 보기 방식

- 카드 시안 1번(크게 보기)과 3번(목록으로 보기)을 사용자가 선택하는 방향.
- 카드 선택 영역만 달리하고 이용금액·이용내역·관리 기능은 일관되게 유지.
- 기본값, 설정 위치와 화면 내 전환 방식은 후속 디자인에서 정리.

### 카드 혜택

- 카드 화면에 자주 접근할 수 있는 혜택 메뉴 추가.
- 상품별 혜택 설명·조건을 우선 디자인. 실제 받은 할인액과 남은 혜택 집계는 별도 추가 구현이 필요.
- 현재 제안: 이용내역 / 카드 혜택 / 카드 관리. 한도 확인의 최종 위치는 후속 디자인에서 확인.

### 내 주변 카드 혜택 찾기 (추가 아이디어, 배치 미정)

- 사용자 위치를 받아 보유 카드로 혜택을 받을 수 있는 주변 매장을 찾아주거나 추천.
- 사용자가 기능을 이용할 때 위치 권한을 요청하고, 위치 제공 없이 지역 검색도 가능하도록 검토.
- 매장과 카드 혜택의 연결, 적용 조건·혜택 유효기간·매장별 제외 여부를 확인할 수 있는 데이터가 필요.
- 카드 혜택 화면, 홈 등의 진입 위치는 아직 결정하지 않음.
- 현재는 기획 아이디어로만 보관하며 UI 배치·위치정보 수집·추천 기능을 구현하지 않음.

## 전체 메뉴 화면 시안 (2026-11-07)

- [24-all-menu-option-1.png](24-all-menu-option-1.png): 주요 은행 업무는 아이콘으로, 보안·설정·안내는 목록으로 구성.
- [25-all-menu-option-2.png](25-all-menu-option-2.png): 은행 업무 / 내 정보·보안 / 설정·안내를 구분하는 접기·펼치기 구성.
- [26-all-menu-option-3.png](26-all-menu-option-3.png): 왼쪽 분류를 선택하면 오른쪽에 세부 메뉴를 표시.
- **전체 메뉴 2번 선택**: 은행 업무 / 내 정보·보안 / 설정·안내를 나누어 접기·펼치기로 구성. [선택 이미지](25-all-menu-option-2.png).
- 공지사항·설정·비밀번호 변경 등의 노출은 UI 기획이며 현재 백엔드 구현 여부와 API 연결은 별도 확인 필요.
- 생성 도구: 기본 제공 Imagegen. 프롬프트 방향: 한눈에 모은 메뉴 / 업무별로 차분하게 / 분류로 찾는 메뉴. 상품 1번을 브랜드 참조 이미지로 첨부.

## 현재 선택 요약

- 홈: 초기 1번 기반 수정본. 승인 대기 안내 제거는 후속 수정에 반영.
- 상품: 1번.
- AI 상담: 3번. 계좌·거래 / 상품 안내 / 이체 예시 제공.
- 카드: 1번 크게 보기와 3번 목록 보기를 선택 가능하게 구성하는 방향. 카드 혜택 메뉴 추가.
- 전체 메뉴: **2번 선택** (25-all-menu-option-2.png).

## 계좌 상세 화면 시안 (2026-11-07)

- [27-account-detail-option-1.png](27-account-detail-option-1.png): 잔액 영역과 상단 이체 버튼을 강조.
- [28-account-detail-option-2.png](28-account-detail-option-2.png): 계좌 요약과 거래 검색·내역 중심.
- [29-account-detail-option-3.png](29-account-detail-option-3.png): 잔액 오른쪽 정렬, 하단 이체 버튼 고정.
- **계좌 화면 3번 선택**: [29-account-detail-option-3.png](29-account-detail-option-3.png). 하단 고정 이체 버튼을 사용하는 방향. 예·적금 상세 화면은 별도 설계 필요.
- 거래 금액과 잔액은 디자인 예시. 거래액과 거래 후 잔액은 구분해서 표시.
- 상세 화면에는 뒤로가기와 관리 메뉴를 두고 하단 주요 탭은 생략하는 방향을 비교.
- 생성 도구: 기본 제공 Imagegen. 프롬프트 방향: 잔액부터 편하게 / 거래를 한눈에 / 가볍게 보고 바로 이체. 선택된 상품 1번을 스타일 참조로 첨부.

## 계좌 화면 최종 선택 및 후속 수정

- 계좌 화면은 **3번 선택** (29-account-detail-option-3.png).
- 잔액·이체·거래내역 중심으로 구성하고 하단 고정 이체 버튼을 유지.
- 계좌 정보(상품명·개설일·금리·이체 한도)와 계좌 설정(별칭 변경·해지)은 오른쪽 위 관리에 모음.
- 선택 이미지에 남은 하단의 별도 계좌 정보 진입 영역은 후속 수정에서 제거하여 관리와 중복하지 않도록 함.
- 화면 제목은 계좌 이름을 사용하는 방향을 검토했으며 선택 이미지의 계좌 상세 표기는 아직 수정 전.

## 이체 입력 화면 시안 (2026-11-08)

- [30-transfer-option-1.png](30-transfer-option-1.png): 출금 계좌, 받는 계좌, 금액과 메모를 한 화면에서 입력.
- [31-transfer-option-2.png](31-transfer-option-2.png): 받는 계좌 → 금액 → 확인으로 나누는 흐름의 첫 화면.
- [32-transfer-option-3.png](32-transfer-option-3.png): 보내는·받는 계좌를 묶고 금액 입력을 강조.
- 선택 대기. 이번 시안은 입력 단계만 비교하며 확인·6자리 PIN·결과 화면은 후속 디자인 필요.
- 당행 계좌 이체 범위. 외부 은행 선택·예약 이체·수취인 이름 조회 API는 구현된 것으로 가정하지 않음.
- 예시 출금 계좌와 잔액은 디자인 데이터이며 키보드가 닫힌 상태. 구현 시 빈 입력의 다음 버튼 비활성화, 입력 오류·잔액/한도 검증, 키보드와 고정 버튼 배치 확인 필요.
- 이체 진행 중 취소·이탈 시 종료, 홈 승인 대기 목록은 사용하지 않는 사용자 결정 유지. 백엔드의 기존 승인 대기 상태와 UI 수명주기 정합성은 별도 구현 확인 필요.
- 생성 도구: 기본 제공 Imagegen. 프롬프트 방향: 한 화면에 차근차근 / 받는 분부터 / 보내는 흐름을 한눈에. 선택된 계좌 3번을 스타일 참조로 첨부.

## 이체 추가 레퍼런스 시안 (2026-11-08)

- 기존 이체 2번이 현재 선호 방향. 추가 시안은 같은 받는 계좌 → 금액 → 확인 → 6자리 PIN → 결과 흐름을 기준으로 비교.
- [33-transfer-reference-toss.png](33-transfer-reference-toss.png): 추가 세트 1번. 큰 질문, 간결한 입력 영역과 하단 출금 계좌 요약.
- [34-transfer-reference-kakaopay.png](34-transfer-reference-kakaopay.png): 추가 세트 2번. 간결한 계좌 정보, 밑줄 입력과 하단 고정 다음 버튼.
- **추가 시안 1번(토스 참조) 선택**: 33-transfer-reference-toss.png. 번호는 추가 세트의 표시 순서이며 기존 1~3번과 별개.
- 토스 공식 페이지: https://toss.im/service/easy-remittance (조회 시 영문 소개 페이지로 이동). 실제 화면 이미지: references/toss-official-transfer-contacts.png. 큰 질문과 단일 목적 화면의 계층을 참고. 연락처·카카오톡 송금 기능과 원본 브랜드는 도입하지 않음.
- 카카오페이 공식 가이드: https://t1.daumcdn.net/kakaopay/static/guide/account-remittance-app-link/index.html (2023-02-13 v1.0). 실제 화면 이미지: references/kakaopay-official-transfer-flow-2023.png. 입력·확인 단계의 간결한 배치만 참고하며 최신 앱 화면으로 주장하지 않음.
- 참고 폴더의 toss-official-transfer-flow.png는 장식 효과 이미지, toss-official-transfer-screen.png는 비어 있는 기기 목업으로, UI 시안 생성에는 사용하지 않음.
- 생성 도구: 기본 제공 Imagegen. 기존 이체 2번 이미지와 각 공식 화면 이미지를 실제 입력으로 첨부. 프롬프트 방향: 간결한 질문형 이체 / 차분한 계좌 입력.
- 두 안 모두 정적인 시안이며 입력 공백 상태의 버튼 활성/비활성·계좌번호 지우기 아이콘 노출 조건은 구현 전 정리 필요.

## 이체 선택 및 팀원 은행 연동 계획 (2026-11-08)

- 이체 입력은 추가 시안 1번(토스 공식 화면 참조)을 선택: [33-transfer-reference-toss.png](33-transfer-reference-toss.png). 기존 이체 2번 선호에서 이번 추가안으로 변경.
- 받는 계좌 → 금액 → 확인 → PIN 승인 → 결과의 단계별 흐름 유지.
- 현재는 당행 계좌만 대상으로 디자인했으며 선택 시안의 은행 표시는 고정.
- 사용자는 향후 다른 팀원 은행도 등록하여 은행 간 이체를 시험할 계획을 제시함.
- 후속 디자인에서 현재 고정 은행 표시를 받는 은행 선택 영역으로 확장하는 방안을 고려. 연결 가능한 팀원 은행만 노출하는 방향을 검토.
- 연동 대상·은행 식별자·API·인증·수취 계좌 확인·은행 간 실행 결과/실패·중복 요청 처리 규약은 아직 정해지지 않음. 현재 구현된 외부 은행 연동으로 표현하지 않음.
- 이번 작업은 선택 및 계획 기록이며 UI 수정이나 백엔드 연동은 수행하지 않음.

## 이체 후속 흐름 시안 (2026-11-08)

이번 네 이미지는 대안 네 개가 아니라 선택된 이체 입력 시안에 이어지는 순서별 화면입니다.

1. [35-transfer-flow-amount.png](35-transfer-flow-amount.png): 금액 입력. 50,000원·5만 원 표기와 금액용 숫자 키패드.
2. [36-transfer-flow-review.png](36-transfer-flow-review.png): 받는 분·계좌·출금 계좌·금액 확인과 선택 메모, PIN 진입.
3. [37-transfer-flow-pin.png](37-transfer-flow-pin.png): 6자리 거래 PIN, 숫자 미노출, 승인 버튼. 이미지의 키 배열은 예시이며 실제 보안 입력 구현을 의미하지 않음.
4. [38-transfer-flow-success.png](38-transfer-flow-success.png): 서버에서 실행 성공을 확인한 후에만 보여주는 완료 상태.

- 예시: 토니 / 캡아메리카뱅크 110-101-000003 / 50,000원 / 메모 식사비. 출금 계좌 생활비 통장 110-***-000001, 이전 잔액 2,350,000원 → 이체 후 2,300,000원.
- 각 화면의 수취인 이름은 현재 승인 응답의 summary 등 서버 검증 결과에 근거해 표시해야 하며 새로운 수취인 조회 API가 이미 있는 것으로 가정하지 않음. 확인 정보 구조화 필요성은 구현 시 검토.
- 메모를 변경하면 PIN 승인 전 서버 요청 내용과 다시 일치시켜야 하며, 확정 후 클라이언트 입력으로 승인 내용을 바꾸지 않도록 함.
- 흐름은 취소·이탈 시 종료. 실행 중 통신 결과 불명은 실제 처리 상태를 조회하여 중복 송금을 피해야 함.
- 실패·잔액 부족·한도 초과·잘못된 PIN·잠금·처리 중 상태는 다음 설계에서 다뤄야 함. 성공 화면을 낙관적으로 먼저 표시하지 않음.
- 기존 선택 시안33과 토스 공식 송금 소개의 실제 UI 이미지 references/toss-official-transfer-contacts.png를 네 생성 호출에 첨부. 토스 최신 금액/확인/PIN/완료 화면을 직접 캡처·복제한 것으로 주장하지 않음. 큰 질문, 간결한 입력, 여백을 우리 은행 흐름에 적용한 디자인.
- 공식 출처: https://toss.im/service/easy-remittance . 이번 추가 다운로드 references/toss-official-transfer-hero.jpg는 인물 홍보 사진으로, UI 생성에는 사용하지 않음.
- 생성 도구: 기본 제공 Imagegen. 공통 프롬프트는 기존 브랜드·390x844·24px 여백·큰 질문·단일 업무·일관된 5만 원 시나리오를 지정하고, 역할별로 금액 입력 / 승인 전 내용 확인 / 6자리 PIN / 성공 확인 후 결과를 각각 요청.

## 이체 로고 크기 수정 (2026-11-08, 최신본)

사용자 결정: 은행 로고는 여러 은행을 구분하는 데 유용하므로 받는 은행 정보 옆에 유지하되 작게 표시. 이체 상단 내비게이션에서는 로고 제거.

- [39-transfer-recipient-small-logo.png](39-transfer-recipient-small-logo.png): 받는 계좌 입력.
- [40-transfer-amount-small-logo.png](40-transfer-amount-small-logo.png): 금액 입력.
- [41-transfer-review-small-logo.png](41-transfer-review-small-logo.png): 내용 확인.
- [42-transfer-pin-small-logo.png](42-transfer-pin-small-logo.png): 6자리 PIN 입력.
- [43-transfer-success-small-logo.png](43-transfer-success-small-logo.png): 완료.
- 이체 최신 기준은 위 39~43번 수정본. 기존 33번·35~38번은 원본 이력으로 보존.
- 은행 식별 로고는 본문 크기의 작은 인라인 표시(구현 시 약 16~18px 높이 기준), 버튼이나 큰 배경 타일로 만들지 않음.
- 완료 체크 아이콘은 상태 표시로서 은행 로고와 다르므로 유지.
- 생성 도구: 기본 제공 Imagegen. 프롬프트: 원본 각 화면을 편집 대상으로 첨부하여 상단 방패 제거 및 수취 은행 로고만 축소하고 나머지 UI·금액·키패드를 유지하도록 요청.
