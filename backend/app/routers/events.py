"""
행동 이벤트 로깅 + 구매(체크아웃) API.

- POST /events   : view/search/add_to_cart 등 단일 이벤트 기록.
                    로그인은 선택(비로그인 방문자의 view/search도 허용).
                    단, 로그인한 상태라면 클라이언트가 보낸 user_id를 무시하고
                    토큰의 user_id로 덮어쓴다 (다른 사람 행세로 이벤트를 남기는 것 방지).
- POST /purchase : 로그인 필수. 장바구니에 담긴 항목을 구매로 확정하고,
                    각 항목마다 purchase 이벤트를 기록한 뒤 장바구니를 비운다.

두 엔드포인트 모두 이벤트를 Kafka(user-events 토픽)로 전송한다.
use_kafka=False 인 경우에만 PostgreSQL에 직접 저장하는 방식으로 폴백한다.
실제 이벤트의 영속 저장은 다음 단계의 Spark Streaming(Consumer)이 담당한다.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_optional
from app.database import get_db
from app.models import CartItem, RawEvent, User
from app.schemas import EventIn, EventOut, PurchaseResult
from app import kafka_producer

router = APIRouter(tags=["events"])


@router.post("/events", response_model=EventOut)
def log_event(
    event: EventIn,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    # 로그인한 상태라면 요청 바디의 user_id는 무시하고 토큰 값으로 덮어쓴다.
    # (비로그인이면 event.user_id 그대로 사용 -> None 이어도 허용)
    effective_user_id = current_user.user_id if current_user else event.user_id

    ts = event.timestamp or datetime.utcnow()
    payload = {
        "user_id": effective_user_id,
        "event_type": event.event_type,
        "product_id": event.product_id,
        "price": event.price,
        "timestamp": ts,
    }

    if kafka_producer.is_enabled():
        # 이벤트를 Kafka로 전송한다. 실제 PostgreSQL 저장은
        # 다음 단계의 Spark Streaming(Consumer)이 담당한다.
        kafka_producer.send_event(payload)
        # Kafka 경로에서는 DB에 저장하지 않으므로 id는 아직 없다.
        # 응답 스키마를 맞추기 위해 임시 id(0)로 에코한다.
        return EventOut(
            id=0,
            user_id=effective_user_id,
            event_type=event.event_type,
            product_id=event.product_id,
            price=event.price,
            timestamp=ts,
        )

    # 폴백: use_kafka=False 이면 예전처럼 PostgreSQL에 직접 저장
    new_event = RawEvent(**payload)
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event


@router.post("/purchase", response_model=PurchaseResult)
def checkout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cart_items = db.query(CartItem).filter(CartItem.user_id == current_user.user_id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="장바구니가 비어 있습니다.")

    total_price = 0.0
    now = datetime.utcnow()

    # 구매 확정 시 각 상품에 대해 purchase 이벤트를 생성한다.
    # view/add_to_cart 와 동일하게 Kafka(user-events 토픽)로 전송하여
    # 모든 이벤트가 하나의 경로로 흐르도록 한다. 실제 PostgreSQL 저장은
    # 다음 단계의 Spark Streaming(Consumer)이 담당한다.
    for item in cart_items:
        price = item.product.price
        total_price += price * item.quantity

        # 수량만큼 purchase 이벤트를 각각 기록 (이벤트 스키마는 단일 상품 단위)
        for _ in range(item.quantity):
            payload = {
                "user_id": current_user.user_id,
                "event_type": "purchase",
                "product_id": item.product_id,
                "price": price,
                "timestamp": now,
            }
            if kafka_producer.is_enabled():
                kafka_producer.send_event(payload)
            else:
                # 폴백: use_kafka=False 이면 예전처럼 PostgreSQL에 직접 저장
                db.add(RawEvent(**payload))

    purchased_count = len(cart_items)

    # 장바구니 비우기 (이건 애플리케이션 상태라 항상 DB에서 처리)
    for item in cart_items:
        db.delete(item)

    db.commit()

    return PurchaseResult(
        user_id=current_user.user_id,
        purchased_items=purchased_count,
        total_price=round(total_price, 2),
    )