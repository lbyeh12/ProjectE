"""
POST /events, POST /purchase 테스트.

conftest.py 에서 USE_KAFKA=false 로 강제했기 때문에, 이 테스트들에서
/events 와 /purchase 는 Kafka 대신 raw_events 테이블에 직접 저장하는
폴백 경로를 탄다. 그래서 결과를 DB에서 바로 조회해 검증할 수 있다.
"""
from app.models import RawEvent


def test_log_event_without_login(client):
    """비로그인 상태에서도 view 이벤트는 기록할 수 있어야 한다."""
    res = client.post("/events", json={"event_type": "view", "product_id": "X1", "price": 1.5})
    assert res.status_code == 200
    assert res.json()["user_id"] is None


def test_log_event_rejects_unknown_event_type(client):
    """event_type 은 정해진 7종 외에는 거부되어야 한다 (422)."""
    res = client.post("/events", json={"event_type": "click"})
    assert res.status_code == 422


def test_log_event_uses_token_user_id_not_client_value(client, auth_headers, sample_user, db_session):
    """
    로그인 상태에서는 요청 바디에 다른 user_id를 적어 보내도
    무시되고 토큰의 user_id로 저장되어야 한다 (위조 방지 핵심 동작).
    """
    spoofed_user_id = 111111
    res = client.post(
        "/events",
        json={"event_type": "view", "product_id": "X1", "price": 1.0, "user_id": spoofed_user_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["user_id"] == sample_user.user_id
    assert res.json()["user_id"] != spoofed_user_id

    saved = db_session.query(RawEvent).filter(RawEvent.product_id == "X1").first()
    assert saved is not None
    assert saved.user_id == sample_user.user_id


def test_purchase_requires_auth(client):
    res = client.post("/purchase")
    assert res.status_code == 401


def test_purchase_empty_cart_fails(client, auth_headers):
    res = client.post("/purchase", headers=auth_headers)
    assert res.status_code == 400


def test_purchase_success_creates_events_and_clears_cart(
    client, auth_headers, sample_product, sample_user, db_session
):
    # 장바구니에 담기
    client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": 2},
        headers=auth_headers,
    )

    res = client.post("/purchase", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == sample_user.user_id
    assert body["purchased_items"] == 1  # 상품 종류 수 (수량 아님)
    assert body["total_price"] == round(sample_product.price * 2, 2)

    # 장바구니가 비었는지
    cart = client.get("/cart", headers=auth_headers).json()
    assert cart == []

    # 수량(2)만큼 purchase 이벤트가 각각 기록됐는지
    purchase_events = (
        db_session.query(RawEvent)
        .filter(RawEvent.event_type == "purchase", RawEvent.user_id == sample_user.user_id)
        .all()
    )
    assert len(purchase_events) == 2
    assert all(e.product_id == sample_product.product_id for e in purchase_events)
