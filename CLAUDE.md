# 캡아메리카뱅크 (개인 구현 레포, 코드 이름 avengers_bank)

팀 공통 뼈대(jjh7757/avengers-bank)에서 시작해 각자 구현하는 레포다. 구조와 실행 방법은 [README.md](README.md)와 [docs/](docs/README.md)를 본다.

## 변경과 문서화
- DB 구조와 기본 구조는 **개선이 필요하면 바꿔도 된다.** 대신 변경 이유를 누구나 쉽게 찾아볼 수 있게 문서로 남긴다
- 설계·DB를 바꾸면 [docs/decisions/](docs/decisions/README.md)에 ADR(설계 결정 기록)을 새로 쓴다: 배경, 결정, 검토한 대안, 결과(좋아지는 점·감수할 점)
- 코드와 문서는 같은 PR에서 함께 바꾼다: 테이블이 바뀌면 `docs/ERD.md`, API가 바뀌면 `docs/API_ENDPOINTS.md`, 구조가 바뀌면 `docs/PROJECT_STRUCTURE.md`, 기능 범위·흐름이 바뀌면 `docs/planning/`
- 기능을 구현하면 `docs/planning/README.md`의 "요구사항 대비 현황"과 `user-flows.md`의 "실패 상황 모음"을 갱신한다
- 기능을 구현하면 `docs/guides/`의 코드 가이드(면접 대비)도 같은 PR에서 갱신한다: 두괄식 요약, 코드 위치 표, 요청 흐름, 핵심 코드, 왜 그렇게 했나, 면접 예상 질문
- PR 본문에는 관련 ADR 링크를 넣는다
- 팀 공통 뼈대와 달라진 점은 ADR에 "팀 뼈대와의 차이"로 적는다 (매일 아침 공유 때 그대로 쓸 수 있게)

## DB 마이그레이션
- 모델을 바꾸면 마이그레이션을 같이 만든다: `docker compose exec app alembic revision --autogenerate -m "..."`
- `alembic check`는 CHECK 제약 변경을 감지하지 못한다. CHECK는 마이그레이션에 직접 쓰고 `tests/test_account_number.py`처럼 테스트로 모델과 맞는지 확인한다
- 마이그레이션 파일에는 앱 코드를 import하지 않고 값을 그대로 적는다 (과거 기록이 바뀌지 않게)
