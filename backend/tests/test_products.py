"""
GET /products, GET /products/{id} 테스트.
인증이 필요 없는 엔드포인트라 가장 단순한 테스트부터 시작한다.
"""


def test_list_products_empty(client):
    """상품이 하나도 없을 때는 빈 배열을 반환해야 한다."""
    res = client.get("/products")
    assert res.status_code == 200
    assert res.json() == []


def test_list_products_returns_created_product(client, sample_product):
    res = client.get("/products")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["product_id"] == sample_product.product_id
    assert body[0]["description"] == sample_product.description


def test_get_product_by_id(client, sample_product):
    res = client.get(f"/products/{sample_product.product_id}")
    assert res.status_code == 200
    assert res.json()["price"] == sample_product.price


def test_get_product_not_found(client):
    res = client.get("/products/NO_SUCH_ID")
    assert res.status_code == 404


def test_search_products_by_description(client, db_session):
    from app.models import Product

    db_session.add_all([
        Product(product_id="A1", description="Blue Mug", price=5.0, total_purchase_count=0),
        Product(product_id="A2", description="Red Plate", price=3.0, total_purchase_count=0),
    ])
    db_session.commit()

    res = client.get("/products", params={"search": "mug"})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["product_id"] == "A1"
