# AvengersBank

은행 서비스 백엔드: FastAPI + SQLAlchemy(async) + PostgreSQL + Alembic

## 문서

| 문서 | 내용 |
|---|---|
| [docs/ERD.md](docs/ERD.md) | ER 다이어그램 (Mermaid), 코드에서 지킬 규칙 · 원본: [AvengersBankDiagram.drawio](docs/AvengersBankDiagram.drawio) |
| [docs/API_ENDPOINTS.md](docs/API_ENDPOINTS.md) | API 엔드포인트 목록, 요청·응답 형식, 구현 상태 |
| [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | 폴더 구조, 계층(router → service → repository) 설명, 역할 분담 |

## 시작하기 (Docker)

Docker Desktop이 필요합니다. PostgreSQL은 컨테이너로 같이 뜹니다.

```bash
cp .env.example .env
```

`.env`의 `JWT_SECRET_KEY`를 32자 이상으로 채웁니다(`openssl rand -hex 32`). `DATABASE_URL`은 compose가 컨테이너용 주소로 덮어쓰므로 그대로 둬도 됩니다.

```bash
docker compose up --build
```

시작할 때 `alembic upgrade head`가 자동으로 실행됩니다.

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
uv run fastapi dev
```

API 문서: http://127.0.0.1:8000/docs

## 테스트

```bash
uv run pytest
```

테스트는 SQLite로 돌아가서 PostgreSQL 없이도 실행됩니다.

## 현재 상태

| 도메인 | 상태 |
|---|---|
| users | ✅ 회원가입, 로그인, 내 정보 조회 |
| products, accounts, transfers, cards | 📝 모델(테이블)만 완성. router·service·repository는 TODO 주석 |
