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
from app.models import CartItem, Product, RawEvent, User
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
    """
    재고 동시성 제어: 비관적 락 (adrs/0004-inventory-concurrency-control.md)

    관련 상품 행에 SELECT ... FOR UPDATE로 락을 걸고, 그 락을 결제
    완료(커밋)까지 유지한다. 재고 차감과 주문(이벤트) 생성을 하나의
    트랜잭션으로 묶어서, 처리 중 서버가 죽어도 커밋 전이면 전부
    자동으로 롤백되어 재고가 꼬이지 않는다.

    재고가 하나라도 부족하면 전체 구매를 취소한다 (원자성 원칙 —
    "일부만 성공"하는 상태를 만들지 않는다).
    """
    cart_items = db.query(CartItem).filter(CartItem.user_id == current_user.user_id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="장바구니가 비어 있습니다.")

    # 데드락 방지: 여러 상품을 동시에 살 때, 항상 product_id 정렬 순서로
    # 락을 잡는다. 두 사용자가 서로 다른 순서로 여러 상품의 락을 요청하면
    # 서로가 서로를 기다리는 데드락이 생길 수 있는데, 잠그는 순서를
    # 고정해두면 이 문제가 구조적으로 방지된다.
    product_ids = sorted({item.product_id for item in cart_items})

    locked_products = {
        p.product_id: p
        for p in db.query(Product)
        .filter(Product.product_id.in_(product_ids))
        .with_for_update()
        .all()
    }

    # 락을 잡은 "이후"에 재고를 검사한다. 락 없이(또는 락 이전에) 검사하면
    # 그 사이 다른 트랜잭션이 재고를 바꿀 수 있어 검사 자체가 무의미해진다.
    for item in cart_items:
        product = locked_products.get(item.product_id)
        if product is None or product.stock < item.quantity:
            # 하나라도 부족하면 즉시 예외를 던진다. 아직 commit 전이라
            # 지금까지 아무 변경도 반영되지 않은 채로 요청이 끝난다
            # (장바구니도 그대로 남아있어, 사용자가 수량을 조정해 재시도 가능).
            raise HTTPException(
                status_code=409,
                detail=f"'{item.product_id}' 상품의 재고가 부족합니다.",
            )

    total_price = 0.0
    now = datetime.utcnow()

    # 구매 확정 시 각 상품에 대해 purchase 이벤트를 생성한다.
    # view/add_to_cart 와 동일하게 Kafka(user-events 토픽)로 전송하여
    # 모든 이벤트가 하나의 경로로 흐르도록 한다. 실제 PostgreSQL 저장은
    # 다음 단계의 Spark Streaming(Consumer)이 담당한다.
    for item in cart_items:
        product = locked_products[item.product_id]
        price = product.price
        total_price += price * item.quantity

        # 재고 차감 + 판매 카운트 반영. 위에서 잡은 락이 유지되고 있는
        # 상태라, 다른 트랜잭션이 같은 상품을 동시에 건드릴 수 없다.
        product.stock -= item.quantity
        product.total_purchase_count = (product.total_purchase_count or 0) + item.quantity

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

    # 여기서 커밋되는 순간, 재고 차감/판매 카운트/장바구니 삭제가 전부
    # 한 번에 확정되고, 위에서 잡은 상품 행 락도 이때 함께 풀린다.
    db.commit()

    return PurchaseResult(
        user_id=current_user.user_id,
        purchased_items=purchased_count,
        total_price=round(total_price, 2),
    )