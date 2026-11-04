# 0004. Agent 연결 구조: REST API 위의 MCP, 승인은 서버가 강제

- 상태: 제안 (이 PR에서 리뷰)
- 날짜: 2026-11-04
- 관련 PR: (이 문서를 추가하는 PR)

## 결정

1. **규칙은 service 한 곳**, 그 위에 **REST API**, 그 위에 **MCP 서버**를 얇은 어댑터로 둔다. MCP 서버는 DB나 service를 직접 부르지 않고, **사용자 토큰으로 REST API만** 호출한다.
2. 우리 LangGraph Agent도 같은 도구(MCP 클라이언트 또는 REST)를 쓴다. **Agent에게 사용자보다 큰 권한을 주지 않는다.**
3. **돈이 움직이는 도구는 실행하지 않고 `pending_actions`만 만든다.** 승인은 사용자가 은행 화면에서 **PIN 또는 패스키**로 한다(ADR 0005). **승인 API는 Agent·MCP 도구에 넣지 않는다.**
4. MCP 도구는 API를 그대로 옮기지 않고 **Agent가 쓰기 좋은 단위로 골라** 만든다.

```
                 ┌─ 웹 화면 (React)
service (규칙) ──┼─ REST API (FastAPI) ──┬─ 우리 LangGraph Agent
                 │                        └─ MCP 서버 ── Claude Desktop, Claude Code, 다른 Agent
                 └─ (승인 API는 웹 화면에서만, PIN·패스키 필요)
```

## 배경

- 과제는 "모든 기능을 자연어로" 요구한다. 이 레포는 거기서 나아가 **어떤 Agent가 붙어도 은행 기능을 안전하게 쓸 수 있는** 구조를 목표로 한다.
- 이전 포트폴리오(langgraph-financial-agent)는 Agent 안에서 승인(`interrupt`)을 처리했다. Agent 하나일 때는 맞지만, **입구가 여러 개**(웹, 우리 Agent, MCP)가 되면 승인 규칙이 입구마다 갈라질 수 있다.
- MCP 도구의 "위험함" 표시(`destructiveHint`)는 **클라이언트에게 주는 힌트일 뿐 보안이 아니다.** 어떤 MCP 앱은 이를 무시하고 바로 실행할 수 있다.

## 검토한 대안

| 대안 | 장점 | 단점 | 결과 |
|---|---|---|---|
| Agent가 service 함수를 직접 호출 | 단순, 빠름 | 인증·권한 검사를 우회하기 쉬움. Agent가 백엔드 안에 묶임 | 버림 |
| REST API만 (MCP 없음) | 웹과 같은 검사 경로 | 우리 Agent 전용. 다른 Agent를 붙일 수 없음 | 일부 채택 (우리 Agent는 REST도 가능) |
| FastAPI 엔드포인트를 MCP로 자동 변환 (`FastMCP.from_fastapi`, `fastapi-mcp`) | 빠름 | 도구가 수십 개가 되고 위험한 것(승인 등)이 섞임 | 버림 |
| **골라 만든 MCP 도구 + REST + 서버 강제 승인** | 어떤 Agent든 같은 규칙. Agent 교체 가능 | 층 하나가 늘어남 | **채택** |

### 승인을 어디서 강제하나

| 대안 | 결과 |
|---|---|
| Agent가 사용자에게 "진행할까요?"를 물음 | Agent를 거치지 않는 입구(MCP 앱)에서는 보장되지 않음. 버림 |
| MCP `destructiveHint`로 클라이언트에 맡김 | 힌트일 뿐. 버림 |
| **서버가 `pending_actions` + PIN·패스키로 강제** | **채택**. Agent는 사용자 토큰은 가질 수 있어도 PIN 입력 화면과 기기의 패스키는 가질 수 없음 |

## MCP 도구 목록 (초안)

| 도구 | 종류 | 동작 |
|---|---|---|
| `get_my_accounts` | 조회 | 내 계좌 목록과 잔액 |
| `search_transactions` | 조회 | 기간·금액·키워드·카테고리로 거래 검색 |
| `get_budget_status` | 조회 | 자유 사용 가능액, 이번 주기 상황 |
| `search_products` | 조회 | 상품 목록·가입 조건·우대금리 |
| `ask_bank_docs` | 조회 | RAG: 약관·FAQ·상품 설명 질문 |
| `list_recipients` | 조회 | 수취인 (별칭으로 찾기) |
| `request_transfer` | **돈 이동** | `pending_actions`만 생성 → "앱에서 승인해 주세요" + 링크 |
| `request_card_action` | 상태 변경 | 카드 정지·해제도 승인 대기 |
| `request_loan` | **돈 이동** | 대출 신청은 바로, **실행**은 승인 대기 |
| (없음) | — | **승인·확인 API, PIN·패스키 관련 API는 도구로 만들지 않음** |

## 결과

**좋아지는 점**
- 웹, 우리 Agent, Claude Desktop 등 **어느 입구로 들어와도 같은 검사**를 거친다.
- "어떤 AI가 붙어도 돈은 사람이 승인해야 움직인다"를 **테스트로 증명**할 수 있다: MCP로 이체 요청 → `pending_actions`만 생기고 잔액은 그대로인지.
- Agent를 바꿔 끼울 수 있다(Gemini 기반 LangGraph ↔ Claude Desktop).

**감수할 점**
- MCP 서버라는 층이 하나 늘어난다.
- 승인을 위해 사용자가 은행 화면으로 이동해야 해서, Agent만으로 끝나지 않는다. 이것은 의도한 것이다.
- 원격 MCP(인터넷 너머의 MCP 앱)는 OAuth 인증이 필요하다. 처음에는 **로컬(stdio) MCP에 사용자 토큰을 설정으로 넣는 방식**으로 시작하고, 원격은 배포 단계에서 다시 정한다.

**과제 요구와의 관계**
- 과제가 요구한 것은 **웹 안의 자연어 채팅**이다. 웹 채팅을 먼저 만들고, MCP는 그 다음이다.
