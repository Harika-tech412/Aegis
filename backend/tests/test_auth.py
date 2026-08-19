"""Login and JWT protection."""

from tests.conftest import TEST_PASSWORD, TEST_USERNAME


def test_login_succeeds_with_correct_credentials(client, investigator_token):
    response = client.post(
        "/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2  # JWT shape


def test_login_fails_with_wrong_password(client, investigator_token):
    response = client.post(
        "/auth/login", json={"username": TEST_USERNAME, "password": "wrong_password"}
    )
    assert response.status_code == 401


def test_protected_route_rejects_missing_token(client):
    assert client.get("/applications").status_code == 401


def test_protected_route_rejects_invalid_token(client):
    response = client.get(
        "/applications", headers={"Authorization": "Bearer not.a.real.jwt"}
    )
    assert response.status_code == 401


def test_health_is_public(client):
    assert client.get("/health").status_code == 200
