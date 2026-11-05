from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.users.models import User

pytestmark = pytest.mark.anyio

SIGNUP = {
    "login_id": "ironman",
    "password": "password1234",
    "name": "토니 스타크",
    "phone": "010-1234-5678",
    "birth_date": "1990-05-29",
}
LOGIN = {"login_id": SIGNUP["login_id"], "password": SIGNUP["password"]}
WRONG = {**LOGIN, "password": "wrong-password"}


async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200


async def test_signup_login_me(client):
    response = await client.post("/users/signup", json={**SIGNUP, "marketing_agreed": True})
    assert response.status_code == 201
    assert response.json()["data"]["birth_date"] == "1990-05-29"
    assert response.json()["data"]["marketing_agreed"] is True

    response = await client.post("/users/login", json=LOGIN)
    assert response.status_code == 200
    token = response.json()["data"]["access_token"]

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["data"]["login_id"] == SIGNUP["login_id"]


async def test_signup_requires_birth_date(client):
    response = await client.post("/users/signup", json={k: v for k, v in SIGNUP.items() if k != "birth_date"})
    assert response.status_code == 422


async def test_signup_duplicate_login_id(client):
    await client.post("/users/signup", json=SIGNUP)
    response = await client.post("/users/signup", json=SIGNUP)
    assert response.status_code == 409


async def test_login_locks_after_five_failures(client):
    await client.post("/users/signup", json=SIGNUP)

    for _ in range(4):
        response = await client.post("/users/login", json=WRONG)
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    response = await client.post("/users/login", json=WRONG)  # 5번째
    assert response.status_code == 423
    assert response.json()["error"]["code"] == "LOGIN_LOCKED"

    response = await client.post("/users/login", json=LOGIN)  # 잠긴 동안은 맞아도 거절
    assert response.status_code == 423


async def test_login_success_resets_fail_count(client):
    await client.post("/users/signup", json=SIGNUP)
    for _ in range(4):
        await client.post("/users/login", json=WRONG)
    assert (await client.post("/users/login", json=LOGIN)).status_code == 200

    for _ in range(4):  # 다시 4번 틀려도 잠기지 않음
        response = await client.post("/users/login", json=WRONG)
    assert response.status_code == 401


async def test_login_unlocks_after_lock_time(client):
    await client.post("/users/signup", json=SIGNUP)
    for _ in range(5):
        await client.post("/users/login", json=WRONG)

    async with SessionLocal() as db:  # 잠금 시간이 지난 상황
        await db.execute(update(User).values(login_locked_until=datetime.now(UTC) - timedelta(seconds=1)))
        await db.commit()

    response = await client.post("/users/login", json=WRONG)  # 지난 잠금 때문에 잠긴 것으로 보지 않음
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert (await client.post("/users/login", json=LOGIN)).status_code == 200
