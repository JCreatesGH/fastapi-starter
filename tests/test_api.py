import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "test.db"))
    return TestClient(app)


@pytest.fixture
def auth(client):
    client.post("/auth/register", json={"email": "a@b.com", "password": "password123"})
    tok = client.post("/auth/login", data={"username": "a@b.com", "password": "password123"}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_register_and_duplicate(client):
    r = client.post("/auth/register", json={"email": "x@y.com", "password": "password123"})
    assert r.status_code == 201 and r.json()["email"] == "x@y.com"
    dup = client.post("/auth/register", json={"email": "x@y.com", "password": "password123"})
    assert dup.status_code == 409


def test_password_min_length(client):
    r = client.post("/auth/register", json={"email": "z@y.com", "password": "short"})
    assert r.status_code == 422


def test_login_bad_credentials(client):
    client.post("/auth/register", json={"email": "a@b.com", "password": "password123"})
    r = client.post("/auth/login", data={"username": "a@b.com", "password": "wrong"})
    assert r.status_code == 401


def test_protected_requires_token(client):
    assert client.get("/me").status_code == 401
    assert client.get("/items").status_code == 401


def test_me(client, auth):
    assert client.get("/me", headers=auth).json()["email"] == "a@b.com"


def test_item_crud_and_isolation(client, auth):
    created = client.post("/items", json={"title": "buy milk"}, headers=auth)
    assert created.status_code == 201
    iid = created.json()["id"]
    assert client.get("/items", headers=auth).json()[0]["title"] == "buy milk"

    toggled = client.patch(f"/items/{iid}", headers=auth)
    assert toggled.json()["done"] is True

    # a different user cannot see or delete the item
    client.post("/auth/register", json={"email": "c@d.com", "password": "password123"})
    tok2 = client.post("/auth/login", data={"username": "c@d.com", "password": "password123"}).json()
    other = {"Authorization": f"Bearer {tok2['access_token']}"}
    assert client.get("/items", headers=other).json() == []
    assert client.delete(f"/items/{iid}", headers=other).status_code == 404

    assert client.delete(f"/items/{iid}", headers=auth).status_code == 204
    assert client.get("/items", headers=auth).json() == []


def test_openapi_served(client):
    assert client.get("/openapi.json").status_code == 200


def test_email_is_normalized(client):
    # registering with mixed case, then logging in lower-case must work...
    r = client.post("/auth/register", json={"email": "Me@Example.com", "password": "password123"})
    assert r.status_code == 201 and r.json()["email"] == "me@example.com"
    tok = client.post("/auth/login", data={"username": "me@example.com", "password": "password123"})
    assert tok.status_code == 200
    # ...and a differently-cased re-register is a duplicate, not a second account
    dup = client.post("/auth/register", json={"email": "ME@example.com", "password": "password123"})
    assert dup.status_code == 409


def test_patch_sets_title_and_done_explicitly(client, auth):
    iid = client.post("/items", json={"title": "draft"}, headers=auth).json()["id"]
    r = client.patch(f"/items/{iid}", json={"title": "final", "done": True}, headers=auth)
    assert r.json() == {"id": iid, "title": "final", "done": True}
    # explicit done=False (not a toggle)
    r2 = client.patch(f"/items/{iid}", json={"done": False}, headers=auth)
    assert r2.json()["done"] is False and r2.json()["title"] == "final"


def test_items_pagination_and_filter(client, auth):
    ids = [client.post("/items", json={"title": f"t{i}"}, headers=auth).json()["id"] for i in range(3)]
    client.patch(f"/items/{ids[1]}", json={"done": True}, headers=auth)
    assert len(client.get("/items?limit=2", headers=auth).json()) == 2
    assert len(client.get("/items?limit=2&offset=2", headers=auth).json()) == 1
    assert client.get("/items?limit=0", headers=auth).status_code == 400
    done = client.get("/items?done=true", headers=auth).json()
    assert [r["id"] for r in done] == [ids[1]]


def test_default_secret_warns(tmp_path, caplog):
    import logging
    from app.main import create_app
    with caplog.at_level(logging.WARNING, logger="fastapi_starter"):
        create_app(db_path=str(tmp_path / "warn.db"))
    assert any("SECRET_KEY" in r.message for r in caplog.records)
