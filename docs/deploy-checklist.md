# 배포 체크리스트

컨테이너 하나(FastAPI + 모바일 웹 `/app`)와 PostgreSQL(pgvector)로 배포합니다. 서빙 방식은 [ADR 0020](decisions/0020-mobile-app-real-api.md)을 봅니다. 아래 "배포 전"까지 끝난 상태이고, "배포할 때"부터 진행합니다.

## 배포 전 (완료)

- [x] `Dockerfile` 하나로 빌드. 시작할 때 `alembic upgrade head` → `seed` → `uvicorn` (상품·데모 사용자·이체 받는 사람이 없을 때만 넣음)
- [x] 모바일 웹을 같은 서버의 `/app`에서 서빙: 같은 출처라 CORS·API 주소 설정 없음
- [x] CORS는 내 PC 개발 서버(127.0.0.1·localhost)만 허용
- [x] 필수 비밀 값이 없으면 서버가 뜨지 않음: `JWT_SECRET_KEY`는 32자 이상, `SYSTEM_API_KEY`는 비우면 시스템 API 꺼짐
- [x] 테스트: `uv run pytest`(백엔드), `node --test frontend/*.test.mjs`(화면 로직), `node tests/browser/run-integration.mjs`(실제 백엔드 + 브라우저 전체 흐름)

## 배포할 때

1. **DB**: pgvector를 쓸 수 있는 PostgreSQL 17 (Neon, Supabase, Railway 등). 연결 문자열을 `postgresql+psycopg://...` 형식으로.
2. **비밀 값**을 호스팅 설정에 넣기 (레포·이미지에 넣지 않음)
   - `DATABASE_URL`, `JWT_SECRET_KEY`(새로 생성: `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `GEMINI_API_KEY`(유료 키), 필요하면 `GEMINI_MODEL`
   - `SYSTEM_API_KEY`(32자 이상): 아래 RAG 색인에 필요. 선택: `LANGFUSE_*`
3. **컨테이너 배포** (Render, Railway, Fly.io, Cloud Run 등): 포트 8000, 헬스 체크 경로 `/`
4. **RAG 색인**: 첫 배포 뒤 한 번 `POST /system/rag/reindex` (헤더 `X-System-Key`)
5. **확인**: `https://<주소>/app/` → 데모 계정 로그인 → 이체(PIN 등록·승인) → AI 상담 한 번 → `/docs` 열림

## 지금 서버 구성 (AWS)

- 서울 EC2 t3.small 한 대에 `docker compose -p avengers-bank -f compose.yaml -f compose.prod.yaml up -d --build` (app·db·caddy·duckdns)
- 주소: `https://<DUCKDNS_SUBDOMAIN>.duckdns.org/app/`, HTTPS는 Caddy가 자동 발급 ([ADR 0025](decisions/0025-https-caddy-duckdns.md))
- 보안 그룹 인바운드는 TCP 80·443만. 서버 관리는 SSM Session Manager (SSH 안 씀)
- 비밀 값은 서버 `/opt/avengers-bank/.env`(root 600)에만 둠. 앱 폴더의 `.env`는 그 파일을 가리키는 링크
- 서버의 `/opt/avengers-bank/app`은 이 레포를 `git clone`한 폴더. **main에 머지된 커밋만 배포**하고, 지금 버전은 `git -C /opt/avengers-bank/app log -1`로 확인
- 배포 (SSM으로 서버에서 root로 실행):
  ```bash
  cd /opt/avengers-bank/app
  git fetch origin && git checkout --detach origin/main
  docker compose -p avengers-bank -f compose.yaml -f compose.prod.yaml up -d --build
  ```
- 마이그레이션이 있는 커밋을 되돌릴 때는 코드보다 먼저 `alembic downgrade`로 DB를 내림 (서버 DB가 코드보다 새 버전이면 앱이 뜨지 않음)
- 평일 11:25~18:00에만 켜짐 (EventBridge Scheduler). 그 밖의 시간에는 주소가 열리지 않음

## 배포 뒤 점검

- 실제 휴대폰에서: 키보드가 하단 고정 버튼을 가리지 않는지, 새로고침 후 로그인 유지
- 데모 계정 비밀번호가 README에 공개돼 있음: 데모 데이터만 두고, 시작할 때마다 로그인 잠금을 풉니다(`seed`)
- Gemini 요청 한도·비용: 사용자별 1분 10회 + 서버 전체 하루 `AI_DAILY_LIMIT`(기본 100, ADR 0026). Langfuse로 지연·실패 확인
- HTTPS 주소에서만 공개 (토큰을 `sessionStorage`에 두므로)
