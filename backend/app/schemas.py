"""
요청/응답에 쓰이는 Pydantic 스키마.
ORM 모델과 분리해서, API로 노출할 필드만 명시적으로 관리한다.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


# --- Product ---

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    description: str
    price: float
    total_purchase_count: int


# --- Cart ---

class CartItemIn(BaseModel):
    user_id: int
    product_id: str
    quantity: int = 1


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    product_id: str
    quantity: int
    added_at: datetime


# --- Event ---
# event_type 은 README에서 확정한 7종으로 제한한다.
EventType = Literal["view", "search", "add_to_cart", "purchase", "refund", "signup", "login"]


class EventIn(BaseModel):
    user_id: Optional[int] = None
    event_type: EventType
    product_id: Optional[str] = None
    price: Optional[float] = None
    timestamp: Optional[datetime] = None  # 비워두면 서버 시간으로 채움


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    event_type: str
    product_id: Optional[str]
    price: Optional[float]
    timestamp: datetime


# --- Purchase (checkout) ---

class PurchaseRequest(BaseModel):
    user_id: int


class PurchaseResult(BaseModel):
    user_id: int
    purchased_items: int
    total_price: float
