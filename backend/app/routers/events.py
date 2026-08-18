"""
행동 이벤트 로깅 + 구매(체크아웃) API.

- POST /events   : view/search/add_to_cart 등 단일 이벤트 기록.
                    로그인은 선택(비로그인 방문자의 view/search도 허용).
                    단, 로그인한 상태라면 클라이언트가 보낸 user_id를 무시하고
                    토큰의 user_id로 덮어쓴다 (다른 사람 행세로 이벤트를 남기는 것 방지).
- POST /purchase : 로그인 필수. 장바구니에 담긴 항목을 구매로 확정하고,
                    각 항목마다 purchase 이벤트를 기록한 뒤 장바구니를 비운다.

두 엔드포인트 모두 이벤트를 Kafka로 직접 보내지 않고, outbox_events
테이블에 기록한다 (adrs/0005-outbox-pattern.md). 별도 Relay
(scripts/outbox_relay.py)가 이 테이블을 폴링해 실제로 Kafka(user-events
토픽)로 전송한다. use_kafka=False 인 경우에만 PostgreSQL(raw_events)에
직접 저장하는 방식으로 폴백한다. 실제 이벤트의 영속 저장은 다음
단계의 Spark Streaming(Consumer)이 담당한다.
"""
import json
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_optional
from app.config import settings
from app.database import get_db
from app.models import CartItem, OutboxEvent, Product, RawEvent, User
from app.schemas import EventIn, EventOut, PurchaseResult
from app import kafka_producer, redis_client

router = APIRouter(tags=["events"])


def _write_to_outbox(db: Session, payload: dict) -> None:
    """
    Kafka로 직접 보내지 않고, outbox_events 테이블에 "보낼 이벤트"를
    기록한다. 호출하는 쪽(log_event, checkout)의 트랜잭션에 그대로
    포함되므로, 그 트랜잭션이 커밋될 때만 이 기록도 같이 확정된다
    (adrs/0005-outbox-pattern.md). 실제 Kafka 전송은 별도 Relay
    (scripts/outbox_relay.py)가 담당한다.
    """
    payload_for_json = dict(payload)
    if isinstance(payload_for_json.get("timestamp"), datetime):
        payload_for_json["timestamp"] = payload_for_json["timestamp"].isoformat()
    db.add(OutboxEvent(payload=json.dumps(payload_for_json)))


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
        # Kafka로 직접 보내지 않고 outbox에 기록한다 (adrs/0005).
        # Relay가 이후 실제로 Kafka로 전송한다.
        _write_to_outbox(db, payload)
        db.commit()
        # outbox 경로에서는 raw_events에 저장하지 않으므로 id는 아직 없다.
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
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """
    재고 동시성 제어: 비관적 락 (adrs/0004-inventory-concurrency-control.md)

    관련 상품 행에 SELECT ... FOR UPDATE로 락을 걸고, 그 락을 결제
    완료(커밋)까지 유지한다. 재고 차감과 주문(이벤트) 생성을 하나의
    트랜잭션으로 묶어서, 처리 중 서버가 죽어도 커밋 전이면 전부
    자동으로 롤백되어 재고가 꼬이지 않는다.

    재고가 하나라도 부족하면 전체 구매를 취소한다 (원자성 원칙 —
    "일부만 성공"하는 상태를 만들지 않는다).

    멱등성 (adrs/0006-idempotency-store-selection.md): 커밋 후 응답
    전달 전에 연결이 끊기면 재시도가 중복 구매로 이어질 수 있다.
    클라이언트가 Idempotency-Key 헤더를 보내면, 같은 키로 이미 처리된
    요청은 재실행하지 않고 이전 결과를 그대로 반환한다. 헤더가 없으면
    기존 호출자와의 호환을 위해 매번 새로 처리한다.
    """
    # Rate Limiting (adrs/0007-rate-limiting.md): 한정 재고에 봇이
    # 반복적으로 구매를 시도하는 걸 방어한다. 멱등성 검사(Redis 조회)
    # 보다도 먼저 걸어서, 과도한 반복 요청은 그 검사조차 없이 바로
    # 거절한다.
    allowed = redis_client.check_rate_limit(
        bucket="purchase",
        identifier=str(current_user.user_id),
        limit=settings.purchase_rate_limit_count,
        window_seconds=settings.purchase_rate_limit_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="구매 요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
        )

    if idempotency_key:
        began = redis_client.try_begin_idempotent_request(idempotency_key)
        if not began:
            cached = redis_client.get_idempotent_result(idempotency_key)
            if cached is not None:
                # 이전에 이미 끝난 요청 - 그때 결과를 그대로 재사용.
                # (성공 응답만 캐싱하므로 여기 저장된 건 항상 200이다.)
                return PurchaseResult(**cached["body"])
            # 아직 "처리 중"인 요청과 겹친 경우 (다른 스레드/워커가 지금
            # 처리하는 중). 결과가 아직 없으니, 완료될 때까지 기다리지
            # 않고 명확하게 "잠시 후 다시 시도"로 응답한다.
            raise HTTPException(
                status_code=409,
                detail="같은 요청이 이미 처리 중입니다. 잠시 후 다시 시도해주세요.",
            )

    try:
        result = _do_checkout(current_user, db)
    except HTTPException:
        # 빈 장바구니(400), 재고 부족(409) 같은 정상적인 도메인 로직
        # 실패는 결과로 캐싱하지 않고 "처리 중" 표시를 지운다. 지우지
        # 않으면, 예를 들어 장바구니를 채우고 재시도해도 계속 "처리
        # 중"이라고만 응답하는 상태로 TTL이 끝날 때까지 막혀버린다.
        if idempotency_key:
            redis_client.clear_idempotent_request(idempotency_key)
        raise

    if idempotency_key:
        redis_client.save_idempotent_result(
            idempotency_key, status_code=200, body=result.model_dump()
        )
    return result


def _do_checkout(current_user: User, db: Session) -> PurchaseResult:
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

        # 수량만큼 purchase 이벤트를 각각 기록. outbox에 기록해 재고
        # 차감과 같은 트랜잭션으로 묶는다 (adrs/0005-outbox-pattern.md).
        for _ in range(item.quantity):
            payload = {
                "user_id": current_user.user_id,
                "event_type": "purchase",
                "product_id": item.product_id,
                "price": price,
                "timestamp": now,
            }
            if kafka_producer.is_enabled():
                _write_to_outbox(db, payload)
            else:
                # 폴백: use_kafka=False 이면 예전처럼 PostgreSQL에 직접 저장
                db.add(RawEvent(**payload))

    purchased_count = len(cart_items)

    # 장바구니 비우기 (이건 애플리케이션 상태라 항상 DB에서 처리)
    for item in cart_items:
        db.delete(item)

    # 장애 주입 지점 (테스트 전용, docs/perf/006-inventory-race.md 재검증용).
    # 재고 차감 + outbox 기록이 같은 트랜잭션이므로, 여기서 죽어도 둘 다
    # 롤백되어 안전하다. 플래그 파일이 없으면 평소엔 영향 없다.
    #
    # 참고: os._exit()로 죽으면 try/except도 못 돌아 Redis의 "처리 중"
    # 표시가 idempotency_ttl_seconds(기본 600초)가 지날 때까지 남는다.
    chaos_flag_path = "/tmp/chaos_crash_before_commit"
    if os.path.exists(chaos_flag_path):
        os.remove(chaos_flag_path)
        os._exit(1)  # 정상 종료 절차 없이 즉시 강제 종료 (실제 크래시와 동일)

    # 여기서 커밋되는 순간, 재고 차감/판매 카운트/장바구니 삭제가 전부
    # 한 번에 확정되고, 위에서 잡은 상품 행 락도 이때 함께 풀린다.
    db.commit()

    return PurchaseResult(
        user_id=current_user.user_id,
        purchased_items=purchased_count,
        total_price=round(total_price, 2),
    )