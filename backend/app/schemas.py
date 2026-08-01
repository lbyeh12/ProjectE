"""
요청/응답에 쓰이는 Pydantic 스키마.
ORM 모델과 분리해서, API로 노출할 필드만 명시적으로 관리한다.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Auth ---

class SignupRequest(BaseModel):
    user_id: int = Field(..., description="데이터셋의 기존 CustomerID (예: 17850)")
    password: str = Field(..., min_length=8, description="8자 이상")


class LoginRequest(BaseModel):
    user_id: int
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    country: Optional[str] = None


# --- Product ---

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    description: str
    price: float
    total_purchase_count: int


# --- Cart ---
# user_id는 더 이상 요청 바디로 받지 않는다. 인증된 토큰에서 가져온다
# (get_current_user 의존성). 그래야 다른 사람 계정의 장바구니를 조작할 수 없다.

class CartItemIn(BaseModel):
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
    # user_id는 요청에 포함될 수 있으나(비로그인 이벤트 등), 로그인 상태라면
    # 서버가 토큰의 user_id로 덮어써서 위조를 막는다 (routers/events.py 참고).
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
# user_id를 요청 바디로 받지 않는다. 인증된 사용자 본인만 체크아웃 가능.

class PurchaseResult(BaseModel):
    user_id: int
    purchased_items: int
    total_price: float