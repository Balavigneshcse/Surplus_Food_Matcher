"""Login, /api/me and logout against the real database (the full app, without lifespan), and the real
session cookie: its flags, what it holds, and that a forged one is ignored."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.integration.factories import make_kitchen, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def cook(db):
    kitchen = make_kitchen(db, "MESS9")
    user = make_user(db, "cook", "KITCHEN", password="cook-password", kitchen_id=kitchen.id)
    db.commit()
    return user


def login(client, username, password):
    token = client.get("/api/auth/csrf").json()["csrfToken"]
    return client.post("/api/auth/login", data={"username": username, "password": password},
                       headers={"X-CSRF-Token": token})


def test_login_me_logout(client, cook):
    res = login(client, "cook", "cook-password")
    assert res.status_code == 200
    assert res.json()["role"] == "KITCHEN"

    me = client.get("/api/me").json()
    assert me["username"] == "cook"
    assert me["kitchenCode"] == "MESS9"
    assert me["kitchenName"] == "Test Kitchen MESS9"
    assert me["sampleData"] is False

    token = client.cookies.get("XSRF-TOKEN")
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": token}).status_code == 204
    assert client.get("/api/me").status_code == 401


def test_wrong_password_is_401(client, cook):
    res = login(client, "cook", "not-the-password")
    assert res.status_code == 401
    assert res.json()["code"] == "BAD_CREDENTIALS"


def test_disabling_a_user_ends_their_session_at_once(client, cook, db):
    assert login(client, "cook", "cook-password").status_code == 200
    cook.enabled = False
    db.commit()
    assert client.get("/api/me").status_code == 401


def test_health_checks_the_database(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["db"] == "ok"


# ---------------------------------------------------------------- the real session cookie

def session_set_cookie(res) -> str:
    return next(c for c in res.headers.get_list("set-cookie") if c.startswith("annamsetu_session="))


def session_payload(cookie_value: str) -> dict:
    """The signed cookie is `base64(json).timestamp.signature`: signed, but anyone can read the json."""
    return json.loads(base64.b64decode(cookie_value.split(".")[0]))


def test_session_cookie_is_httponly_samesite_lax_for_12_hours(client, cook):
    res = login(client, "cook", "cook-password")
    flags = [part.strip().lower() for part in session_set_cookie(res).split(";")[1:]]
    assert "httponly" in flags  # JavaScript can't read it
    assert "samesite=lax" in flags
    assert "path=/" in flags
    assert "max-age=43200" in flags  # 12 h from login
    assert "secure" not in flags  # dev/test; APP_SECURE_COOKIES=true adds it in prod


def test_signed_session_cookie_holds_only_ids_never_secrets(client, cook):
    res = login(client, "cook", "cook-password")
    value = session_set_cookie(res).split(";")[0].split("=", 1)[1]
    payload = session_payload(value)
    assert payload == {"uid": cook.id, "csrf": res.json()["csrfToken"]}
    readable = json.dumps(payload)
    assert "cook-password" not in readable and cook.password_hash not in readable


def test_a_tampered_session_cookie_is_ignored(client, cook, db):
    admin = make_user(db, "boss", "ADMIN", password="boss-password")
    db.commit()
    res = login(client, "cook", "cook-password")
    value = session_set_cookie(res).split(";")[0].split("=", 1)[1]
    payload = session_payload(value)
    payload["uid"] = admin.id  # try to become the admin by editing the readable part
    forged = base64.b64encode(json.dumps(payload).encode()).decode() + value[value.index("."):]

    client.cookies.clear()
    client.cookies.set("annamsetu_session", value)
    assert client.get("/api/me").json()["role"] == "KITCHEN"  # the untouched cookie works
    client.cookies.clear()
    client.cookies.set("annamsetu_session", forged)
    res = client.get("/api/me")
    assert res.status_code == 401  # the signature no longer matches, so the session is empty
    assert res.json()["code"] == "NOT_LOGGED_IN"


def test_each_login_gets_a_new_csrf_token_and_session(client, cook):
    first = login(client, "cook", "cook-password").json()["csrfToken"]
    second = login(client, "cook", "cook-password").json()["csrfToken"]
    assert first != second
    assert client.get("/api/me").status_code == 200
