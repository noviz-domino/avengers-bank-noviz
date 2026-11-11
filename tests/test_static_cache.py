import pytest

pytestmark = pytest.mark.anyio


async def test_frontend_files_are_revalidated_every_time(client):
    # 화면 파일은 쓸 때마다 서버에 확인한다: 배포 뒤 옛 모듈과 새 모듈이 섞이지 않게 (ADR 0028)
    first = await client.get("/app/ui.mjs")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-cache"
    assert first.headers["etag"]

    # 안 바뀌었으면 본문 없이 304로 끝나서 다시 받는 비용이 없다
    again = await client.get("/app/ui.mjs", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.headers["cache-control"] == "no-cache"

    page = await client.get("/app/")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-cache"
