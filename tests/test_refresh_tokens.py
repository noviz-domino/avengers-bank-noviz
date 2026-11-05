from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.users.models import RefreshToken

pytestmark = pytest.mark.anyio

SIGNUP = {"login_id": "ironman", "password": "password1234", "name": "토니", "phone": "010-1234-5678",
          "birth_date": "1990-05-29"}
LOGIN = {"login_id": "ironman", "password": "password1234"}


async def login(client, device: str | None = None) -> dict:
    response = await client.post("/users/login", json={**LOGIN, "device_name": device})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()["data"]


async def refresh(client, token: str):
    return await client.post("/users/token/refresh", json={"refresh_token": token})


@pytest.fixture
async def user(client):
    await client.post("/users/signup", json=SIGNUP)
    return client


async def test_refresh_rotates_token(user):
    first = await login(user, "아이폰")
    response = await refresh(user, first["refresh_token"])
    assert response.status_code == 200
    second = response.json()["data"]
    assert second["refresh_token"] != first["refresh_token"]
    assert (await user.get("/users/me", headers={"Authorization": f"Bearer {second['access_token']}"})).status_code == 200

    async with SessionLocal() as db:  # 원문은 저장하지 않고, 바뀐 토큰은 새 토큰을 가리킨다
        rows = list(await db.scalars(select(RefreshToken).order_by(RefreshToken.token_id)))
    assert all(first["refresh_token"] not in r.token_hash for r in rows)
    assert rows[0].revoked_at is not None and rows[0].replaced_by == rows[1].token_id
    assert rows[1].device_name == "아이폰" and rows[0].family_id == rows[1].family_id


async def test_reused_token_revokes_family(user):
    first = await login(user)
    second = (await refresh(user, first["refresh_token"])).json()["data"]

    response = await refresh(user, first["refresh_token"])  # 이미 바꾼 토큰이 다시 옴 = 도난
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"

    response = await refresh(user, second["refresh_token"])  # 정상 사용자 토큰도 같이 끊김 (교체된 적 없어서 그냥 무효)
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_other_device_survives_reuse(user):
    phone, laptop = await login(user, "폰"), await login(user, "노트북")
    phone_new = (await refresh(user, phone["refresh_token"])).json()["data"]
    response = await refresh(user, phone["refresh_token"])  # 폰 family만 폐기
    assert response.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"
    assert (await refresh(user, phone_new["refresh_token"])).status_code == 401
    assert (await refresh(user, laptop["refresh_token"])).status_code == 200


async def test_expired_or_unknown_token(user):
    tokens = await login(user)
    async with SessionLocal() as db:
        await db.execute(update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await db.commit()

    for token in [tokens["refresh_token"], "not-a-token"]:
        response = await refresh(user, token)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_logout_revokes_this_device_only(user):
    phone, laptop = await login(user, "폰"), await login(user, "노트북")
    response = await user.post("/users/logout", json={"refresh_token": phone["refresh_token"]})
    assert response.status_code == 200

    response = await refresh(user, phone["refresh_token"])  # 로그아웃한 토큰은 도난이 아니라 그냥 무효
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"
    assert (await refresh(user, laptop["refresh_token"])).status_code == 200
    # 없는 토큰으로 로그아웃해도 성공 (이미 로그아웃한 상태와 같음)
    assert (await user.post("/users/logout", json={"refresh_token": "nope"})).status_code == 200
