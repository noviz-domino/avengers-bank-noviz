# ClearingHub 로컬 수신 실험

이 폴더는 ClearingHub [빠른 시작](https://github.com/jjh7757/clearing-hub/blob/main/docs/SPEC.md)의 서명 및 수신 예제를 독립적으로 보관한다. 기존 은행 앱과 DB에 연결하지 않는다. 가짜 계좌 `110-123-000001`만 사용하며 입금 기록은 프로세스 메모리에만 남는다. 재시작하면 기록이 사라지므로 실제 서버나 공개 주소에 배포하지 않는다.

ClearingHub 저장소에서 `uv run python -m clearing_hub.devserver`를 실행하고, 해당 저장소의 빠른 시작 1~4단계를 따라 **로컬에서 생성된** 키와 초대 코드를 사용한다. `BANK_PRIVATE_KEY`와 `HUB_PUBLIC_KEY`를 환경 변수로 설정한 뒤 이 폴더에서 다음 명령으로 수신 서버를 실행한다.

```bash
uv run --with cryptography --with fastapi --with uvicorn uvicorn bank:app --host 127.0.0.1 --port 3000
```

등록할 로컬 주소는 `http://127.0.0.1:3000/interbank`다. 전달받은 실제 초대 코드와 실제 허브에는 사용하지 않는다. 테스트는 이 폴더에서 실행한다.

```bash
uv run --with cryptography --with fastapi --with httpx --with pytest pytest test_bank.py -q
```

예제 출처: ClearingHub `docs/SPEC.md`, 확인한 리비전 `86c3842999235f33ab1baf8d0b2e8fb45e272aab`.

실제 로컬 HTTP 시험을 재현하려면 ClearingHub 의존성이 설치된 Python으로 다음을 실행한다. Git Bash 기준이며 저장소 경로는 본인 위치에 맞춘다.

```bash
/c/Users/USER/AppData/Local/Temp/clearing-hub-local-test/.venv/Scripts/python.exe experiments/clearinghub/demo.py C:/Users/USER/AppData/Local/Temp/clearing-hub-local-test
```

이 명령은 임시 DB로 허브(18080)·가짜 은행(18180)·수신 서버(18300)를 시작하고, 등록·응답 서명·입금·중복 요청·무서명 거부를 assert로 확인한 뒤 종료한다. 비밀값 없는 결과는 `demo-result.json`에 남긴다. 해당 포트는 비어 있어야 한다.
