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
