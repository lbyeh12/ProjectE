"""
행동 이벤트 로깅 + 구매(체크아웃) API.

- POST /events   : view/search/add_to_cart 등 단일 이벤트 기록
                    (지금은 PostgreSQL에 직접 INSERT. 나중에 Kafka Producer로
                     내부 구현만 교체하면 되도록 트래킹 스키마를 그대로 따른다.)
- POST /purchase : 장바구니에 담긴 항목을 구매로 확정하고,
                    각 항목마다 purchase 이벤트를 raw_events에 기록한 뒤 장바구니를 비운다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CartItem, RawEvent, User
from app.schemas import EventIn, EventOut, PurchaseRequest, PurchaseResult
from app import kafka_producer

router = APIRouter(tags=["events"])


@router.post("/events", response_model=EventOut)
def log_event(event: EventIn, db: Session = Depends(get_db)):
    ts = event.timestamp or datetime.utcnow()
    payload = {
        "user_id": event.user_id,
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
            user_id=event.user_id,
            event_type=event.event_type,
            product_id=event.product_id,
            price=event.price,
            timestamp=ts,
        )

    # 폴백: use_kafka=False 이면 예전처럼 PostgreSQL에 직접 저장
    new_event = RawEvent(
        user_id=event.user_id,
        event_type=event.event_type,
        product_id=event.product_id,
        price=event.price,
        timestamp=ts,
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event


@router.post("/purchase", response_model=PurchaseResult)
def checkout(req: PurchaseRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cart_items = db.query(CartItem).filter(CartItem.user_id == req.user_id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="장바구니가 비어 있습니다.")

    total_price = 0.0
    now = datetime.utcnow()

    for item in cart_items:
        price = item.product.price
        total_price += price * item.quantity

        # 수량만큼 purchase 이벤트를 각각 기록 (이벤트 스키마는 단일 상품 단위)
        for _ in range(item.quantity):
            db.add(RawEvent(
                user_id=req.user_id,
                event_type="purchase",
                product_id=item.product_id,
                price=price,
                timestamp=now,
            ))

    purchased_count = len(cart_items)

    # 장바구니 비우기
    for item in cart_items:
        db.delete(item)

    db.commit()

    return PurchaseResult(
        user_id=req.user_id,
        purchased_items=purchased_count,
        total_price=round(total_price, 2),
    )