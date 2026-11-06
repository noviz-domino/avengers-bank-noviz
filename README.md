# AvengersBank

은행 서비스 백엔드: FastAPI + SQLAlchemy(async) + PostgreSQL + Alembic

## 문서

| 문서 | 내용 |
|---|---|
| [docs/planning/](docs/planning/README.md) | 기획서: 과제 요구사항, 기능 목록, 이용 흐름, 화면 구성 |
| [docs/ERD.md](docs/ERD.md) | ER 다이어그램 (Mermaid), 코드에서 지킬 규칙 · 원본: [AvengersBankDiagram.drawio](docs/AvengersBankDiagram.drawio) |
| [docs/API_ENDPOINTS.md](docs/API_ENDPOINTS.md) | API 엔드포인트 목록, 요청·응답 형식, 구현 상태 |
| [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | 폴더 구조, 계층(router → service → repository) 설명, 역할 분담 |
| [docs/decisions/](docs/decisions/README.md) | 설계 결정 기록(ADR): 팀 뼈대에서 무엇을 왜 바꿨는지 |
| [docs/guides/](docs/guides/README.md) | 코드 가이드: 기능별 흐름과 설계 이유, 면접 예상 질문 |

## 시작하기 (Docker)

Docker Desktop이 필요합니다. PostgreSQL은 컨테이너로 같이 뜹니다.

```bash
cp .env.example .env
```

`.env`의 `JWT_SECRET_KEY`를 32자 이상으로 채웁니다(`openssl rand -hex 32`). 신용카드 대금 출금 API(`/system/card-bills/run`)를 쓰려면 `SYSTEM_API_KEY`도 같은 방법으로 채웁니다(비우면 그 API는 꺼짐). `DATABASE_URL`은 compose가 컨테이너용 주소로 덮어쓰므로 그대로 둬도 됩니다.

```bash
docker compose up --build
```

시작할 때 `alembic upgrade head`와 데모 상품 seed가 자동으로 실행됩니다.

- API 문서: http://127.0.0.1:8000/docs
- DB 접속(내 PC에서): `localhost:5433`, 사용자·비밀번호 `postgres`, DB `avengers_bank`

모델을 바꾼 뒤 마이그레이션 만들기:

```bash
docker compose exec app alembic revision --autogenerate -m "변경 내용"
docker compose exec app alembic upgrade head
```

`alembic/versions`는 볼륨으로 연결돼 있어서 생성된 파일이 내 PC에도 남습니다.

DB까지 초기화하려면 `docker compose down -v`.

## 시작하기 (로컬)

[uv](https://docs.astral.sh/uv/)와 PostgreSQL이 필요합니다.

```bash
uv sync
cp .env.example .env
```

`.env`에 `DATABASE_URL`과 `JWT_SECRET_KEY`(32자 이상)를 채웁니다.

```bash
uv run alembic upgrade head
uv run python -m avengers_bank.seed
uv run fastapi dev
```

`avengers_bank.seed`는 데모 상품(입출금 1, 예금 2, 적금 2, 대출 1)과 **데모 사용자**를 넣습니다. 여러 번 실행해도 다시 넣지 않습니다.

### 데모 계정

메인 화면(총자산, 잔액 상위 3개 계좌)을 바로 볼 수 있게 잔액이 있는 계좌 4개를 가진 사용자입니다. 데모용 값이라 비밀이 아닙니다. 비밀번호가 공개돼 있어 누구나 5번 틀려 잠글 수 있어서, seed가 실행될 때(Docker 시작)마다 이 계정의 로그인 잠금을 풉니다.

| 아이디 | 비밀번호 |
|---|---|
| `demo` | `demo-password-1234` |

API 문서: http://127.0.0.1:8000/docs

## AI 상담 쓰기 (선택)

`.env`에 `GEMINI_API_KEY`가 있으면(아래 "RAG 쓰기" 1~2) 로그인한 뒤 `POST /chat`으로 자연어 요청을 보낼 수 있습니다. 같은 `session_id`를 보내면 앞 대화를 기억합니다.

| 예시 | 하는 일 |
|---|---|
| "내 계좌 얼마 있어?" | 계좌 담당 → `get_my_accounts` |
| "어제 카페에서 얼마 썼어?" | 계좌 담당 → `search_transactions`(어제 날짜, 카페·간식) |
| "피터한테 5만 원 보내줘" | 계좌 담당 → 받는 계좌를 되묻거나 `request_transfer` → **승인 대기**, PIN은 승인 화면에서 |
| "카드 잃어버렸어" | 카드 담당 → 어느 카드인지·분실 신고 확인 → `suspend_card(lost)` |
| "자유적금 우대금리 조건이 뭐야?" | 상품 담당 → `ask_bank_docs`(근거 인용) |
| "카드 정지하고 남은 잔액 알려줘" | 카드 담당 → 계좌 담당 (복합 요청) |

## Claude Desktop에서 쓰기 (MCP, 선택)

서버(`docker compose up`)를 띄운 뒤, 한 번 로그인해 refresh token을 파일(`~/.avengers-bank/mcp-token.json`)에 저장합니다. 비밀번호는 저장하지 않습니다.

```bash
uv run python -m avengers_bank.domains.mcp_server login
```

Claude Desktop 설정(`claude_desktop_config.json`)에 추가합니다. `--directory`는 이 레포 경로입니다.

```json
{ "mcpServers": { "avengers-bank": {
    "command": "uv",
    "args": ["--directory", "C:/Users/USER/Desktop/261103미니프로젝트/avengers-bank-noviz", "run", "python", "-m", "avengers_bank.domains.mcp_server"],
    "env": { "AVENGERS_API_URL": "http://localhost:8000" } } } }
```

"내 계좌 보여줘", "어제 카페에서 얼마 썼어?", "카드 잃어버렸어 정지해줘", "토니한테 3만 원 보내줘"(승인 대기까지, PIN은 은행 화면에서)처럼 쓸 수 있습니다. 승인·PIN·카드 결제는 도구에 없습니다([ADR 0014](docs/decisions/0014-mcp-server.md)).

## RAG 쓰기 (선택)

상품·약관 질문 답변(`/rag/*`)은 Gemini 키가 있어야 동작합니다. 없으면 그 API만 `503`이고 나머지 은행 기능은 그대로입니다.

1. [Google AI Studio](https://aistudio.google.com/apikey)에서 무료 키를 발급합니다. 결제 수단을 등록하지 않으면 과금되지 않습니다. 무료 티어는 입력이 구글 모델 개선에 쓰일 수 있어서 데모 데이터만 넣습니다.
2. `.env`의 `GEMINI_API_KEY`에 넣습니다. **GitHub Secrets에는 넣지 않습니다**(테스트·CI는 Gemini를 부르지 않음).
3. 서버를 띄운 뒤 색인을 만듭니다(바뀐 청크만 임베딩, 처음엔 30개 정도).

```bash
curl -X POST http://localhost:8000/system/rag/reindex -H "X-System-Key: $SYSTEM_API_KEY"
```

4. 검색 성능 평가(정답 세트 38문항, 질문마다 임베딩 1번):

```bash
uv run python -m avengers_bank.domains.rag.evaluate
```

## 테스트

```bash
uv run pytest
```

테스트는 SQLite로 돌아가서 PostgreSQL 없이도 실행됩니다.

### CI

PR을 올리거나 `main`에 push하면 GitHub Actions([`.github/workflows/ci.yml`](.github/workflows/ci.yml))가 두 가지를 검사합니다.

| 검사 | 하는 일 |
|---|---|
| 테스트 (pytest) | `uv run pytest` |
| 마이그레이션 (PostgreSQL) | 빈 PostgreSQL에 `alembic upgrade head` → `alembic check`(모델과 마이그레이션이 맞는지) → `alembic downgrade base` → 다시 `upgrade head` |

두 번째 검사는 **PostgreSQL에서 마이그레이션이 적용되고 되돌려지는지**를 확인합니다(테스트는 SQLite로 테이블을 바로 만들어서 마이그레이션 파일을 거치지 않습니다). `alembic check`는 CHECK 제약 변경을 감지하지 못해서, CHECK 내용이 모델과 같은지는 `tests/test_account_number.py`가 맡습니다. 새 도메인의 `models.py`를 `alembic/env.py`에 import했는지는 `tests/test_alembic_env.py`가 확인합니다.

## 현재 상태

| 도메인 | 상태 |
|---|---|
| users | ✅ 회원가입(생년월일·마케팅 동의), 로그인(5회 실패 15분 잠금), refresh token 교체·도난 감지, 로그아웃(기기별), 내 정보 조회 |
| products | ✅ 판매 중인 상품 목록·상세(우대금리 조건 포함), 데모 상품 seed |
| accounts | ✅ 입출금·적금 개설(가입 조건·적용 금리), **예금 개설(PIN 승인)**, 내 계좌 목록과 총자산, 상세, 거래내역, 별칭, 입출금 계좌 해지 |
| transactions | ✅ 내 모든 계좌 거래 검색(기간·금액·키워드·카테고리)과 합계, 카테고리 자동 분류·수정 |
| transfers, approvals | ✅ 이체 요청 → 승인 대기 → 거래 PIN 승인 → 실행(잔액·한도 재검사, 장부 두 줄), 거절, 멱등키, PIN 5회 잠금, 감사 기록 |
| chat | ✅ AI 상담(`POST /chat`): 감독관 + 계좌·카드·상품 Agent, 대화 기억, 이체는 승인 대기까지. Gemini 무료 키 필요 |
| mcp | ✅ AI 도구 16개(계좌·카드·상품, 이체는 승인 대기까지). HTTP `/mcp`(Bearer), 로컬 stdio(Claude Desktop) |
| rag | ✅ 상품·약관 질문에 근거와 함께 답변(`/rag/ask`), 검색, 색인 갱신(`/system/rag/reindex`). Gemini 무료 키 필요 |
| cards | ✅ 카드 상품, 발급(Luhn 번호·가린 번호), 정지·분실(바로), 정지 해제(PIN 승인), 결제·취소·사용내역·한도(카드 행 잠금), 신용 대금 출금(`/system`, 서버 키) |
