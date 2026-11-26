# AI 상담 응답 시간 줄이기와 RAG 검색 엔진 검토

- 날짜: 2026-11-27
- 범위: 조사만 했다. 코드는 바꾸지 않았고 새로 재지도 않았다. 숫자는 레포의 결정 기록(빠른 길 측정, 응답 시간 측정, RAG 평가)과 공식 문서에서 가져왔다.
- 대상 코드: `agent/graph.py`, `agent/service.py`, `agent/quick.py`, `rag/service.py`

## 결론 먼저

1. **"담당을 고르면 그 담당의 데이터를 미리 읽어 넣기"는 반만 맞는 방향이다.** 줄여야 할 것은 REST 호출이 아니라 LLM 호출이다. 미리 읽기가 없애는 것은 담당 Agent의 "도구 고르기" 호출 하나뿐이고 그마저 이미 빠른 길이 처리하는 질문(잔액, 카드 목록, 남은 예산)과 많이 겹친다. 정작 느린 꼬리인 검색형 질문("이번 달 식비 얼마 썼어?")은 최근 10건 같은 미리 읽은 창 밖에 답이 있어서 미리 읽기로 풀리지 않고 오히려 틀린 합계를 만들 위험이 커진다.
2. **가장 먼저 할 일은 검색형 질문의 빠른 길이다.** 라우터가 기간·업종·방향을 채우고(slot-filling) 코드가 `search_transactions`를 부른 뒤 서버가 준 합계로 템플릿 답을 쓴다. 이 도구는 이미 조건 전체의 합계를 돌려주므로 모델이 더하기를 할 일이 없다. p95를 끌어올리는 4~5번 호출 질문이 1번이 된다.
3. **두 번째는 라우터를 가벼운 모델로 바꾸는 것이다.** 라우터는 모든 턴에 한 번씩 돌기 때문에 여기서 1초를 줄이면 모든 질문이 1초 빨라진다. `gemini-3.8-flash`는 생각 수준 `minimal`을 지원하지 않지만 `gemini-3.5-flash-lite`와 `gemini-3.6-flash`는 지원한다. 라우팅 평가 세트로 정확도가 그대로인지 확인한 뒤 바꾼다.
4. **미리 읽기는 작고 경계가 분명한 데이터에만 좁혀서 쓴다.** 계좌 목록과 카드 목록처럼 "전부"를 넣을 수 있는 것만 넣고 "언제 기준, 무엇이 빠졌는지"를 함께 적는다. 거래내역은 넣지 않는다.
5. **RAG는 지금의 PostgreSQL + pgvector + Kiwi BM25를 유지한다.** 청크가 29개이고 벡터만으로도 Hit@1이 1.0이다. 서버는 메모리 2GB인 t3.small 한 대라서 Elasticsearch를 같이 띄우면 앱과 DB가 쓸 메모리가 거의 남지 않는다. 문서가 수천 청크 이상으로 늘거나 단어 검색이 느려지면 그때 ParadeDB(pg_search, Lindera 한국어 사전)를 먼저 검토하고 Elasticsearch는 검색이 제품의 중심이 될 때 고른다.

---

## 1. 응답 시간: 미리 읽기와 다른 방법들

### 1-1. 지금 구조에서 시간이 어디에 드는가

- 한 턴은 라우터(LLM 1번) → 담당 Agent가 도구 고르기(1번) → 도구 → 담당이 답 쓰기(1번)다. LLM 한 번이 3~4초다.
- 빠른 길(아직 커밋 전)은 라우터가 단순 조회를 표시하면 코드가 도구를 부르고 템플릿으로 답한다. 21개 질문에서 p50이 11.3초에서 8.7초로 p95가 17.1초에서 15.9초로 줄었다.
- p95가 덜 줄어든 이유는 검색형 질문이다. "이번 달 식비 얼마 썼어?"와 "카드 사용내역"이 4~5번 호출한다. 기간과 업종을 골라야 하고 한 번에 못 찾으면 다시 찾는다.
- 도구는 앱 안의 MCP 서버를 메모리로 거쳐 같은 서버의 REST를 부른다. 이 호출은 수십 밀리초 단위라서 LLM 한 번(3~4초)에 비하면 거의 0이다. 그래서 **REST를 미리 부르는 것 자체로는 시간이 줄지 않고 LLM 호출 수가 줄어야 시간이 준다.**

OpenAI의 응답 시간 가이드도 같은 순서로 말한다. 요청 수를 줄이고 서로 상관없는 일은 동시에 하고 답을 이미 아는 일에는 LLM을 쓰지 말라는 것이다. Anthropic도 가장 단순한 방법에서 시작해서 결과가 분명히 좋아질 때만 Agent다운 복잡함을 더하라고 권한다. 정해진 길로 충분한 일은 워크플로(코드가 정한 경로)가 맞다는 뜻이다.

### 1-2. 제안("담당별 미리 읽기 + 도구는 예비로")을 따져 보면

**줄어드는 것**

- 담당 Agent의 "도구 고르기" 호출 하나. 3번이 2번이 된다(라우터 + 답 쓰기).
- 빠른 길이 일부러 빼 둔 질문 일부가 빨라진다. 예: "생활비 통장 잔액만", "스타크 카드 상태". 계좌 목록 전체가 컨텍스트에 있으면 모델이 골라서 답할 수 있다.

**줄지 않는 것**

- 검색형 질문. 이번 달 식비 합계는 최근 10건에 없다. 모델은 결국 `search_transactions`를 불러야 하고 그러면 지금과 같은 3~5번이다.
- 빠른 길이 이미 1번으로 끝내는 질문. 미리 읽기는 2번이라 오히려 느리다. 빠른 길은 그대로 두어야 한다.

**환각 위험과 막는 법**

| 위험 | 예 | 막는 법 |
|---|---|---|
| 창 밖 데이터를 있는 것처럼 답함 | 최근 10건만 넣었는데 "이번 달 카드 사용액 합계"를 10건으로 더해서 답함 | 거래내역은 넣지 않는다. 넣는다면 "최근 10건만이며 합계·기간 질문은 반드시 검색 도구"라고 데이터 바로 위에 적는다 |
| 비슷한 숫자 칸을 헷갈림 | `free_before_saving`과 `free_to_spend`, 카드 한도와 남은 한도, 잔액과 출금 가능액 | 넣기 전에 코드가 칸 이름을 뜻이 분명한 한국어 이름으로 바꾸고 답에 필요 없는 칸은 뺀다 |
| 모델이 계산함 | 계좌 잔액을 더해 총자산을 만듦 | 서버가 계산한 값(총자산, 조건 합계)만 넣고 "계산하지 않는다"는 지금 예산 담당 규칙을 모든 담당에 쓴다 |
| 오래된 값 | 같은 턴에서 이체 요청을 만든 뒤 미리 읽은 잔액을 말함 | 상태를 바꾸는 도구가 성공하면 미리 읽은 값을 버리거나 "요청 전 기준"이라고 적는다. 돈은 어차피 PIN 승인 뒤에만 움직인다 |
| 긴 입력 중간을 놓침 | JSON이 길어지면 가운데 있는 계좌를 빠뜨림 | 데이터는 짧게 유지하고 질문 가까이(시스템 프롬프트 끝)에 둔다. 긴 입력의 가운데 정보는 덜 쓰인다는 연구가 있다 |
| 답 숫자 검증이 없음 | 위 모든 경우 | 답에 나온 금액이 미리 읽은 값이나 도구 결과에 실제로 있는지 정규식으로 확인하고 없으면 담당 Agent 길로 다시 보낸다. 작은 코드이고 포트폴리오에서 설명하기 좋다 |

**토큰 비용**

- 재지 않았다. 계좌 몇 개의 목록은 수백 토큰, 카드 목록·한도·최근 거래 10건은 수천 토큰으로 어림한다. 실제 값은 Langfuse의 호출별 토큰 수로 확인해야 한다.
- 무료 티어에서는 돈보다 요청 수 한도가 문제라서 토큰 증가는 비용보다 속도(입력이 길수록 첫 토큰이 늦음) 쪽으로 본다.
- Gemini의 암묵적 캐시(implicit caching)는 2.5 이후 모델에서 자동으로 켜지고 `gemini-3.8-flash`는 입력 4,096토큰 이상부터 적용된다. 공식 문서는 비용 절감만 말하고 **응답 시간 단축은 언급하지 않는다.** 지금 프롬프트는 대부분 이 기준보다 짧을 것이라서 캐시를 노리고 구조를 바꿀 이유는 약하다. 같은 앞부분(공통 규칙, 도구 설명)을 앞에 두는 지금 순서는 그대로 두면 된다.

**큰 JSON을 넣었을 때 Gemini의 동작**

- `gemini-3.8-flash`의 생각 수준 `low`에서 큰 JSON을 다룬 공식 수치는 찾지 못했다. 이 부분은 직접 재야 한다.
- 공식 함수 호출 문서는 한 번에 열어 둘 도구를 10~20개로 유지하라고 권한다. 담당별 도구는 2~7개라서 문제없다.
- 미리 읽은 데이터와 도구를 함께 주면 모델이 데이터로 답할 수 있는데도 도구를 다시 부르는 일이 생길 수 있다. 그러면 시간은 그대로이고 토큰만 는다. 측정에서 "미리 읽었는데도 도구를 부른 비율"을 함께 봐야 한다.

### 1-3. 다른 방법들 비교

| 방법 | 기대 효과 | 위험 | 코드 크기 | 판단 |
|---|---|---|---|---|
| **검색형 빠른 길** (라우터가 기간·업종·방향을 채우고 코드가 `search_transactions` 호출 후 서버 합계로 템플릿 답) | 검색형 질문 4~5번 → 1번. p95를 직접 낮춤 | 라우터의 날짜 계산 실수. 코드가 날짜 형식·범위를 검사하고 빠진 값이 있으면 담당 Agent로 넘김 | 작음~중간 | **1순위** |
| **라우터를 가벼운 모델로** (`gemini-3.5-flash-lite` 또는 `gemini-3.6-flash`, 생각 `minimal`) | 모든 턴에서 라우터 한 번이 빨라짐(어림 1초 안팎) | 라우팅·빠른 길 표시 정확도. 평가 세트로 확인 | 작음 | **2순위** |
| **좁힌 미리 읽기** (계좌 목록·카드 목록만, 기준 시각과 범위 표시) | 빠른 길이 뺀 단순 조회 3번 → 2번 | 위 표의 환각 위험. 숫자 검증으로 줄임 | 중간 | 3순위 |
| 복합 요청의 담당을 동시에 실행 | "카드 한도랑 계좌 거래내역" 같은 복합 요청 p95 일부 | "정지하고 잔액"처럼 순서가 필요한 요청. 답을 합치는 순서 | 중간 | 복합 요청이 많을 때 |
| 한 번의 호출에 도구 호출 여러 개(병렬 함수 호출) | 한 담당이 도구 여러 개를 부를 때 왕복이 줄어듦 | 거의 없음. Gemini가 지원하고 LangGraph의 도구 노드는 여러 도구 호출을 동시에 실행함 | 없음(이미 가능) | 추가 작업 없음. 프롬프트에서 막지만 않으면 됨 |
| 라우터와 담당을 한 호출로 합치기(지난 프로젝트처럼 이해 한 번 + 코드 실행 + 템플릿) | 가장 빠름 | 19개 도구를 한 스키마에 넣으면 고르기가 거칠어짐. 이미 결정 기록에서 버림 | 큼 | 빠른 길을 늘리는 것이 같은 효과를 작게 얻음 |
| 라우터와 동시에 미리 읽기(추측 실행) | 거의 없음 | REST가 수십 밀리초라 숨길 시간이 없음 | 작음 | 하지 않음 |
| 컨텍스트 캐시(명시적 캐시) | 비용. 응답 시간은 공식 문서에 근거 없음 | 캐시 관리 코드 | 중간 | 하지 않음 |
| 턴 안 도구 결과 캐시 | 같은 턴에 같은 도구를 두 번 부를 때만 | 상태 변경 뒤 오래된 값 | 작음 | 측정에서 중복 호출이 보일 때만 |
| 스트리밍 우선 화면 | 체감 시간. 이미 있음(진행 상태와 답 글자를 흘려보냄) | 없음 | 작음 | 빠른 길 템플릿 답도 "도구 부르는 중" 상태를 먼저 보내는지만 확인 |

### 1-4. 이 레포에서 바뀔 파일

**1순위 검색형 빠른 길**

- `agent/quick.py`: `QuickKind`에 지출 검색 종류를 더하고 `LANES`를 담당 하나에 여러 빠른 길을 둘 수 있게 바꾼다. 템플릿은 서버가 준 들어온 돈·나간 돈 합계와 상위 몇 건만 옮긴다.
- `agent/graph.py`: `Plan`에 `from_date`, `to_date`, `category`, `direction` 칸을 더하고 `ROUTER` 규칙에 표시 조건을 적는다. 라우터 프롬프트에 오늘 날짜가 들어가야 한다(지금 라우터 프롬프트에는 날짜가 없고 담당 프롬프트에만 있다).
- `agent/routing.jsonl`, `tests/test_agent.py`: 검색형 질문과 "빠진 값이면 담당 Agent로 넘어가는지" 테스트.
- 결정 기록 하나(빠른 길 결정의 후속).

**2순위 가벼운 라우터**

- `agent/llm.py`: 라우터용 모델을 하나 더 만든다(설정의 모델 이름과 생각 수준).
- `core/config.py`: 라우터 모델 설정 칸.
- `agent/graph.py`: `build`가 라우터용 모델을 따로 받는다.
- `agent/service.py`, `agent/router.py`: 라우터 모델을 넘긴다.

**3순위 좁힌 미리 읽기**

- `agent/graph.py`의 담당 노드에서 계좌·카드 담당일 때 목록 도구를 먼저 부르고 결과를 정리해 사람 말 앞의 안내 메시지에 붙인다. LangChain `create_agent`의 미들웨어(동적 프롬프트)로도 넣을 수 있지만 지금 구조에서는 담당 노드에서 메시지를 붙이는 쪽이 짧다.
- 답 숫자 검증 함수는 `agent/quick.py` 옆에 작은 함수로 둔다.

어떤 경우에도 돈을 옮기거나 상태를 바꾸는 일은 지금처럼 승인 대기를 만들고 사람이 PIN으로 실행한다. 위 방법들은 모두 읽기 질문에만 적용된다.

---

## 2. RAG 검색 엔진: Elasticsearch가 더 나은가

### 2-1. 지금 구조

- 데모 약관 4개(합쳐 약 1만 바이트)를 조항 단위로 잘라 22개, 상품 7개를 더해 청크 29개다.
- 벡터는 PostgreSQL의 pgvector(정확 검색, 근사 인덱스 없음)이고 단어 검색은 Kiwi로 내용어를 뽑아 둔 토큰을 질문마다 전부 읽어 `rank_bm25`로 점수를 매긴다. 두 순위를 RRF로 합쳐 5개를 고른다.
- 평가 38문항: hybrid Hit@1 0.947, 벡터만 Hit@1 1.000, BM25만 Hit@1 0.789.
- 서버는 서울 EC2 t3.small(메모리 2GB) 한 대에 앱·DB·Caddy를 compose로 띄운다.

### 2-2. 비교

| 기준 | 지금(pgvector + Kiwi BM25 in-memory) | Elasticsearch(nori + kNN + RRF) | OpenSearch | ParadeDB pg_search | pg_bigm / tsvector |
|---|---|---|---|---|---|
| 한국어 단어 검색 품질 | Kiwi 형태소 분석. 한국어 품질 좋음 | nori(mecab-ko-dic 사전) 형태소 분석. 좋음 | 공식 문서 목록에 nori가 보이지 않음(확인 못 함) | Lindera 한국어 사전(KoDic) 토크나이저 제공 | pg_bigm은 2글자 단위라 형태소 없이 부분 일치. tsvector는 한국어 설정이 기본으로 없음 |
| 지금 규모의 응답 시간 | 청크 29개라 밀리초. 검색 시간은 임베딩 API와 LLM이 지배 | 같은 수준. 네트워크 한 번 더 | 같음 | 같음 | 같음 |
| 규모가 커질 때 | BM25가 질문마다 전부 읽어서 청크 수에 비례해 느려짐 | 역색인이라 큰 규모에 강함 | 같음 | 역색인(BM25 인덱스) | 인덱스 있음 |
| t3.small 메모리 | 추가 없음 | JVM 힙은 메모리의 50% 이하 권장, 공식 Docker 예시가 1GB. 2GB 서버에 앱·DB와 함께는 무리 | Elasticsearch와 비슷 | Postgres 확장이라 추가 프로세스 없음 | 추가 없음 |
| 운영 복잡도 | 데이터 저장소 하나 | 저장소가 둘이 되고 색인 동기화, nori 플러그인 설치, 인증 설정이 필요 | 같음 | Postgres 이미지를 ParadeDB 이미지로 바꿔야 함. AGPL-3.0 | 확장 설치만 |
| 하이브리드 합치기 | 직접 짠 RRF(18줄) | RRF 리트리버 제공. 라이선스 등급은 확인 못 함 | 하이브리드 검색에 RRF 항목이 있음(세부는 확인 못 함) | SQL로 직접 합침 | SQL로 직접 합침 |
| 포트폴리오 가치(AI Agent·FDE) | "측정해 보고 작게 갔다"를 보여 줌 | 이름값은 크지만 29개 청크에 붙이면 과설계로 보일 수 있음 | 같음 | Postgres 안에서 끝내는 판단을 보여 줌 | 낮음 |

### 2-3. 판단

- **유지한다.** 지금 병목은 검색이 아니라 LLM 호출이다. 검색 품질도 이미 정답 세트에서 Hit@5 1.0이라 엔진을 바꿔 올릴 여지가 없다. 오히려 벡터만 쓸 때 Hit@1이 더 높았다는 결과가 결정 기록에 이미 있다.
- Elasticsearch는 2GB 서버에서 메모리가 부족하고 데이터 저장소가 둘이 되면서 동기화와 장애 지점이 늘어난다. 서버를 키우면 비용이 든다.
- FDE 면접에서 더 설득력 있는 것은 "Elasticsearch를 썼다"보다 "정답 세트로 재 보니 이 규모에서는 벡터만으로도 충분했고 바꿀 조건을 미리 적어 두었다"는 이야기다. 고객 현장에서 이미 Elasticsearch를 쓰면 RRF와 nori로 같은 구조를 옮길 수 있다는 점을 결정 기록에 한 줄 적어 두면 된다.

### 2-4. 바꿀 만한 조건

| 조건 | 먼저 할 일 |
|---|---|
| 청크가 수천 개를 넘어 단어 검색이 눈에 띄게 느려짐(질문마다 전체 토큰을 읽는 구조) | 1단계: BM25 객체를 색인할 때 한 번 만들어 메모리에 두기. 2단계: ParadeDB pg_search(Lindera 한국어)로 옮겨 Postgres 안에서 BM25 인덱스 쓰기 |
| 벡터가 수만 개 이상 | pgvector HNSW 인덱스 추가 |
| 검색이 제품의 중심이 됨(필터·집계·동의어 사전·여러 서비스가 같은 검색을 씀) 또는 서버를 4GB 이상으로 키움 | Elasticsearch(nori + kNN + RRF) |
| 지원하는 회사나 고객사가 Elasticsearch를 쓰고 있어서 보여 줘야 함 | 같은 정답 세트로 두 엔진을 비교하는 평가 스크립트를 따로 만들어 결과를 문서로 남기기(운영 서버는 그대로) |

---

## 출처

- Gemini 함수 호출(병렬·연쇄 호출, 열어 둘 도구 10~20개 권장): https://ai.google.dev/gemini-api/docs/function-calling (현재 https://aistudio.google.com/docs/function-calling 로 이동함)
- Gemini 컨텍스트 캐시(암묵적 캐시, 모델별 최소 토큰, 비용만 언급): https://ai.google.dev/gemini-api/docs/caching
- Gemini 생각 수준(모델별 지원 수준, 낮을수록 빠름): https://ai.google.dev/gemini-api/docs/thinking
- Gemini 모델 목록(flash, flash-lite): https://ai.google.dev/gemini-api/docs/models
- OpenAI 응답 시간 최적화 원칙: https://platform.openai.com/docs/guides/latency-optimization (현재 https://developers.openai.com/api/docs/guides/latency-optimization 로 이동함)
- Anthropic, Building effective agents(워크플로와 Agent, 라우팅, 단순한 것부터): https://www.anthropic.com/engineering/building-effective-agents
- Lost in the Middle(긴 입력 가운데 정보를 덜 씀): https://arxiv.org/abs/2307.03172
- LangChain Agent와 미들웨어: https://docs.langchain.com/oss/python/langchain/agents
- LangChain 컨텍스트 엔지니어링(동적 프롬프트로 상태 넣기): https://docs.langchain.com/oss/python/langchain/context-engineering
- LangGraph 워크플로(라우팅, 병렬 실행): https://docs.langchain.com/oss/python/langgraph/workflows-agents
- Elasticsearch nori 플러그인: https://www.elastic.co/docs/reference/elasticsearch/plugins/analysis-nori
- Elasticsearch RRF: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion
- Elasticsearch 구독 등급(RRF 행은 있으나 등급 표시는 확인 못 함): https://www.elastic.co/subscriptions
- Elasticsearch JVM 힙 설정: https://www.elastic.co/docs/reference/elasticsearch/jvm-settings
- Elasticsearch Docker 설치: https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic
- OpenSearch 언어 분석기 목록: https://docs.opensearch.org/latest/analyzers/language-analyzers/index/
- OpenSearch 하이브리드 검색: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/
- ParadeDB 토크나이저(Lindera 한국어): https://www.paradedb.com/docs/reference/tokenizers/available-tokenizers/lindera.md
- ParadeDB 라이선스(AGPL-3.0): https://github.com/paradedb/paradedb
- pg_bigm 문서: https://github.com/pgbigm/pg_bigm/blob/REL1_2_STABLE/docs/pg_bigm_en.md
- PostgreSQL 텍스트 검색 사전(한국어 기본 설정 없음): https://www.postgresql.org/docs/current/textsearch-dictionaries.html

## 확인하지 못한 것

- Elasticsearch RRF가 무료(Basic) 등급인지: 구독 페이지의 표시를 글로 읽지 못했다.
- OpenSearch의 nori 플러그인 제공 여부와 RRF 지원 버전.
- 미리 읽기의 실제 토큰 수와 `gemini-3.8-flash`가 큰 JSON에서 숫자를 잘못 옮기는 비율. 둘 다 이 레포의 평가 스크립트로 직접 재야 한다.
- 가벼운 라우터 모델의 실제 단축 시간과 라우팅 정확도.
