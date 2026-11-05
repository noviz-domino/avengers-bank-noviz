# 문서 목차

| 문서 | 내용 | 언제 고치나 |
|---|---|---|
| [planning/](planning/README.md) | 기획서: 과제 요구사항, 기능 목록, 이용 흐름, 요구사항 대비 현황 | 기능 범위·흐름이 바뀔 때 |
| [ERD.md](ERD.md) | 테이블 구조(Mermaid), 코드에서 지킬 규칙 | 테이블·컬럼·제약이 바뀔 때 |
| [API_ENDPOINTS.md](API_ENDPOINTS.md) | API 목록, 요청·응답 형식, 구현 상태 | API를 추가·변경할 때 |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | 폴더 구조, 계층 설명 | 폴더·계층 구조가 바뀔 때 |
| [decisions/](decisions/README.md) | 설계 결정 기록(ADR): 왜 그렇게 바꿨는지 | 설계·DB를 바꿀 때마다 새로 |
| [guides/](guides/README.md) | **코드 가이드(면접 대비)**: 기능별 요청 흐름, 코드 위치, 왜 그렇게 만들었나, 예상 질문 | 기능을 만들거나 바꿀 때 |

기획서의 원본은 팀 FigJam 보드이고, `planning/`에 옮겨 두었습니다. 둘이 다르면 레포 문서가 기준입니다.

## 규칙

- 코드와 문서는 **같은 PR**에서 함께 바꿉니다.
- 설계를 바꾸면 ADR을 쓰고, PR 본문에 링크합니다.
