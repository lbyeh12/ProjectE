"""
ORM 모델.

- Product   : data/dataset/products.csv 에서 적재
- User      : data/dataset/users.csv 에서 적재
- CartItem  : 사용자별 장바구니 항목 (간단한 버전, 로그인/세션 인증은 추후 추가)
- RawEvent  : view / search / add_to_cart / purchase / refund 행동 이벤트 원본 로그
              (현재 단계는 Kafka 없이 FastAPI가 직접 INSERT 한다. 추후 Kafka Producer로
               교체되어도 테이블 스키마는 그대로 유지된다.)
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # 재고가 음수로 내려가는 걸 애플리케이션 로직(비관적 락)으로
        # 막고 있지만, DB 레벨에도 이중 방어를 걸어둔다. 코드에 버그가
        # 있어도 DB가 마지막 방어선이 되어준다 (adrs/0004 참고).
        CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
    )

    product_id = Column(String, primary_key=True)        # StockCode
    description = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    total_purchase_count = Column(Integer, default=0)
    # 재고 수량. 데이터셋에는 원래 없던 개념이라 전처리 단계에서
    # 임의로 채워 넣는다 (adrs/0004-inventory-concurrency-control.md).
    stock = Column(Integer, nullable=False, default=0)


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)            # CustomerID
    country = Column(String, nullable=True)
    first_purchase_at = Column(DateTime, nullable=True)
    last_purchase_at = Column(DateTime, nullable=True)
    # 인증용. data/preprocess.py 로 적재된 기존 유저는 비밀번호가 없는 상태(NULL)로
    # 시작하며, /auth/signup 으로 비밀번호를 설정해야 로그인할 수 있다.
    hashed_password = Column(String, nullable=True)

    cart_items = relationship("CartItem", back_populates="user")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    product_id = Column(String, ForeignKey("products.product_id"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product")


class RawEvent(Base):
    __tablename__ = "raw_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)               # 비로그인 사용자는 null 허용
    event_type = Column(String, nullable=False)            # view/search/add_to_cart/purchase/refund/signup/login
    product_id = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)