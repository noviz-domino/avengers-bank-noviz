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

## 시작하기 (Docker)

Docker Desktop이 필요합니다. PostgreSQL은 컨테이너로 같이 뜹니다.

```bash
cp .env.example .env
```

`.env`의 `JWT_SECRET_KEY`를 32자 이상으로 채웁니다(`openssl rand -hex 32`). `DATABASE_URL`은 compose가 컨테이너용 주소로 덮어쓰므로 그대로 둬도 됩니다.

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
| accounts | ✅ 입출금·적금 개설(가입 조건·적용 금리), 내 계좌 목록과 총자산, 상세, 거래내역, 별칭 |
| approvals | 📝 테이블만 완성. API는 이체 PR에서 |
| transfers, cards | 📝 TODO 주석. 카드 테이블은 카드 기능 PR에서 새로 만듦 |
