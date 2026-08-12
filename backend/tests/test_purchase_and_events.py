"""
POST /events, POST /purchase 테스트.

conftest.py 에서 USE_KAFKA=false 로 강제했기 때문에, 이 테스트들에서
/events 와 /purchase 는 Kafka 대신 raw_events 테이블에 직접 저장하는
폴백 경로를 탄다. 그래서 결과를 DB에서 바로 조회해 검증할 수 있다.
"""
import json

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


def test_purchase_decrements_stock(client, auth_headers, sample_product, db_session):
    """
    재고 동시성 제어(adrs/0004-inventory-concurrency-control.md)의
    핵심 동작: 구매 성공 시 재고가 정확히 수량만큼 줄어야 한다.
    """
    initial_stock = sample_product.stock
    client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": 3},
        headers=auth_headers,
    )
    res = client.post("/purchase", headers=auth_headers)
    assert res.status_code == 200

    db_session.refresh(sample_product)
    assert sample_product.stock == initial_stock - 3


def test_purchase_fails_when_stock_insufficient(client, auth_headers, sample_product, db_session):
    """
    재고보다 많은 수량을 담으면 409로 거절되고, 재고는 전혀 줄어들지
    않아야 한다 (원자성 - adrs/0004).
    """
    initial_stock = sample_product.stock
    client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": initial_stock + 1},
        headers=auth_headers,
    )
    res = client.post("/purchase", headers=auth_headers)
    assert res.status_code == 409

    db_session.refresh(sample_product)
    assert sample_product.stock == initial_stock  # 전혀 차감되지 않음


def test_purchase_idempotency_key_prevents_duplicate(
    client, auth_headers, sample_product, db_session
):
    """
    같은 Idempotency-Key로 두 번 요청하면, 실제 처리는 한 번만 되고
    두 번째는 캐싱된 결과를 그대로 반환해야 한다 (adrs/0006).
    """
    client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": 1},
        headers=auth_headers,
    )
    headers = {**auth_headers, "Idempotency-Key": "test-fixed-key-001"}
    initial_stock = sample_product.stock

    res1 = client.post("/purchase", headers=headers)
    assert res1.status_code == 200

    res2 = client.post("/purchase", headers=headers)
    assert res2.status_code == 200
    assert res2.json() == res1.json()  # 완전히 동일한 결과 재반환

    db_session.refresh(sample_product)
    assert sample_product.stock == initial_stock - 1  # 딱 1번만 차감


def test_purchase_rate_limit_blocks_excessive_requests(
    client, auth_headers, sample_product, monkeypatch
):
    """
    Rate Limiting(adrs/0007-rate-limiting.md): 짧은 시간에 과도하게
    반복되는 구매 요청은 429로 거절되어야 한다. 실제 기본값(1분 10회)
    까지 반복하면 테스트가 느려지므로, 제한값을 낮춰서 검증한다.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "purchase_rate_limit_count", 2)

    # 매 요청마다 장바구니를 새로 채운다 (재고 부족으로 인한 409와
    # Rate Limit으로 인한 429를 구분하기 위해 재고를 넉넉히 유지).
    for _ in range(2):
        client.post(
            "/cart",
            json={"product_id": sample_product.product_id, "quantity": 1},
            headers=auth_headers,
        )
        res = client.post("/purchase", headers=auth_headers)
        assert res.status_code == 200

    client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": 1},
        headers=auth_headers,
    )
    res = client.post("/purchase", headers=auth_headers)
    assert res.status_code == 429


def test_purchase_with_kafka_enabled_writes_to_outbox(
    client, auth_headers, sample_product, db_session, monkeypatch
):
    """
    Outbox 패턴(adrs/0005-outbox-pattern.md): use_kafka=true 경로에서는
    이벤트가 Kafka로 직접 전송되지 않고 outbox_events 테이블에 기록되어야
    한다. 실제 Kafka 브로커 연결 없이 이 경로만 검증하기 위해,
    `_producer`를 더미 값으로 바꿔 `is_enabled()`가 True를 반환하게
    만든다 (`_write_to_outbox()`는 Kafka를 전혀 호출하지 않고 DB에만
    쓰므로 이렇게 해도 안전하다).
    """
    from app import kafka_producer
    from app.config import settings
    from app.models import OutboxEvent

    monkeypatch.setattr(settings, "use_kafka", True)
    monkeypatch.setattr(kafka_producer, "_producer", object())

    client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": 2},
        headers=auth_headers,
    )
    res = client.post("/purchase", headers=auth_headers)
    assert res.status_code == 200

    outbox_rows = db_session.query(OutboxEvent).filter(OutboxEvent.sent_at.is_(None)).all()
    assert len(outbox_rows) == 2
    for row in outbox_rows:
        payload = json.loads(row.payload)
        assert payload["event_type"] == "purchase"
        assert payload["product_id"] == sample_product.product_id

    # RawEvent(폴백 경로)에는 기록되지 않아야 한다.
    raw_count = (
        db_session.query(RawEvent)
        .filter(RawEvent.event_type == "purchase", RawEvent.product_id == sample_product.product_id)
        .count()
    )
    assert raw_count == 0


def test_login_rate_limit_blocks_excessive_attempts(client, sample_user, monkeypatch):
    """
    로그인 브루트포스 방어(adrs/0007-rate-limiting.md): 짧은 시간에
    반복되는 로그인 시도는 bcrypt 검증 이전에 429로 차단되어야 한다.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "login_rate_limit_count", 3)

    for _ in range(3):
        res = client.post(
            "/auth/login",
            json={"user_id": sample_user.user_id, "password": "wrong-password"},
        )
        assert res.status_code == 401  # 비밀번호가 틀렸을 뿐, 제한에는 안 걸림

    res = client.post(
        "/auth/login",
        json={"user_id": sample_user.user_id, "password": "wrong-password"},
    )
    assert res.status_code == 429