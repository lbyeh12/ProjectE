"""
POST /auth/signup, POST /auth/login, GET /auth/me 테스트.
"""


def test_signup_requires_existing_user(client):
    """데이터셋에 없는 user_id로는 회원가입할 수 없어야 한다."""
    res = client.post("/auth/signup", json={"user_id": 424242, "password": "testpass123"})
    assert res.status_code == 404


def test_signup_success(client, sample_user):
    res = client.post(
        "/auth/signup",
        json={"user_id": sample_user.user_id, "password": "testpass123"},
    )
    assert res.status_code == 201
    assert res.json()["user_id"] == sample_user.user_id


def test_signup_rejects_short_password(client, sample_user):
    """비밀번호 8자 미만은 Pydantic 검증에서 거부되어야 한다 (422)."""
    res = client.post(
        "/auth/signup",
        json={"user_id": sample_user.user_id, "password": "short"},
    )
    assert res.status_code == 422


def test_signup_twice_fails(client, sample_user):
    """이미 비밀번호가 설정된 계정은 다시 가입할 수 없어야 한다."""
    client.post("/auth/signup", json={"user_id": sample_user.user_id, "password": "testpass123"})
    res = client.post("/auth/signup", json={"user_id": sample_user.user_id, "password": "anotherpass1"})
    assert res.status_code == 400


def test_login_success(client, sample_user):
    client.post("/auth/signup", json={"user_id": sample_user.user_id, "password": "testpass123"})
    res = client.post("/auth/login", json={"user_id": sample_user.user_id, "password": "testpass123"})
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password(client, sample_user):
    client.post("/auth/signup", json={"user_id": sample_user.user_id, "password": "testpass123"})
    res = client.post("/auth/login", json={"user_id": sample_user.user_id, "password": "wrongpassword"})
    assert res.status_code == 401


def test_login_nonexistent_user(client):
    res = client.post("/auth/login", json={"user_id": 999999, "password": "testpass123"})
    assert res.status_code == 401


def test_me_without_token(client):
    """토큰 없이 /auth/me 를 호출하면 401 이어야 한다."""
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_me_with_valid_token(client, auth_headers, sample_user):
    res = client.get("/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["user_id"] == sample_user.user_id


def test_me_with_invalid_token(client):
    res = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401
