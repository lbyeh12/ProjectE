"""
POST /cart, GET /cart, DELETE /cart/{product_id} 테스트.

이 파일에서 가장 중요하게 검증하는 것은 "인증 없이는 아무것도 못 한다"는 부분이다.
JWT 도입 전에는 user_id를 요청에 직접 넣어 보내면 다른 사람 행세가 가능했는데,
그 문제가 실제로 막혔는지를 이 테스트들이 증명한다.
"""


def test_add_to_cart_requires_auth(client, sample_product):
    """토큰 없이 장바구니에 담으려 하면 401 이어야 한다."""
    res = client.post("/cart", json={"product_id": sample_product.product_id, "quantity": 1})
    assert res.status_code == 401


def test_get_cart_requires_auth(client):
    res = client.get("/cart")
    assert res.status_code == 401


def test_add_to_cart_success(client, auth_headers, sample_product):
    res = client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": 2},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["product_id"] == sample_product.product_id
    assert body["quantity"] == 2


def test_add_to_cart_unknown_product(client, auth_headers):
    res = client.post(
        "/cart",
        json={"product_id": "NO_SUCH_PRODUCT", "quantity": 1},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_add_same_product_twice_increments_quantity(client, auth_headers, sample_product):
    """같은 상품을 두 번 담으면 행이 늘어나는 게 아니라 수량만 늘어나야 한다."""
    client.post("/cart", json={"product_id": sample_product.product_id, "quantity": 1}, headers=auth_headers)
    res = client.post(
        "/cart",
        json={"product_id": sample_product.product_id, "quantity": 2},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["quantity"] == 3

    cart = client.get("/cart", headers=auth_headers).json()
    assert len(cart) == 1  # 행 1개만 있어야 함


def test_get_cart_returns_only_own_items(client, auth_headers, sample_product):
    res = client.get("/cart", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []

    client.post("/cart", json={"product_id": sample_product.product_id, "quantity": 1}, headers=auth_headers)
    res = client.get("/cart", headers=auth_headers)
    assert len(res.json()) == 1


def test_remove_from_cart(client, auth_headers, sample_product):
    client.post("/cart", json={"product_id": sample_product.product_id, "quantity": 1}, headers=auth_headers)

    res = client.delete(f"/cart/{sample_product.product_id}", headers=auth_headers)
    assert res.status_code == 200

    cart = client.get("/cart", headers=auth_headers).json()
    assert cart == []


def test_remove_nonexistent_cart_item(client, auth_headers, sample_product):
    res = client.delete(f"/cart/{sample_product.product_id}", headers=auth_headers)
    assert res.status_code == 404
