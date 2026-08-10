"""
scripts/outbox_relay.py

Transactional Outbox 패턴의 Relay (adrs/0005-outbox-pattern.md).

outbox_events 테이블에서 sent_at IS NULL 인 행(아직 Kafka로 안 보낸
이벤트)을 주기적으로 조회해서 Kafka로 전송하고, 성공하면 sent_at을
채운다. FastAPI 요청 생명주기와 분리된 독립 프로세스로 계속 돈다 -
이게 Outbox 패턴의 핵심이다: 재고 차감(checkout())은 이 테이블에
"기록"만 하고 끝나고, "실제 전송"은 이 프로세스가 언제까지고 재시도할
수 있다.

전송 순서 보장: id 순서(=커밋된 순서)대로 처리한다. 다만 여러 인스턴스를
동시에 띄우면 같은 행을 중복 처리할 수 있으므로, 이 스크립트는
단일 인스턴스로만 실행한다고 가정한다 (docker-compose에서 replicas 없이
서비스 하나로만 띄움).

실행:
  python scripts/outbox_relay.py
  POLL_INTERVAL_SECONDS, BATCH_SIZE 환경변수로 조정 가능.
"""
import json
import os
import time
from datetime import datetime

from kafka import KafkaProducer
from sqlalchemy import bindparam, text

from app.config import settings
from app.database import SessionLocal

POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "100"))


def _json_serializer(value: dict) -> bytes:
    return json.dumps(value).encode("utf-8")


def create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
        value_serializer=_json_serializer,
        retries=3,
        acks="all",
    )


def relay_once(producer: KafkaProducer) -> int:
    """
    아직 안 보낸 이벤트를 한 배치만큼 처리한다. 처리한 건수를 반환한다.
    """
    db = SessionLocal()
    try:
        # id 순서대로, 아직 안 보낸 것만 batch 단위로 가져온다.
        rows = db.execute(
            text(
                "SELECT id, payload FROM outbox_events "
                "WHERE sent_at IS NULL ORDER BY id ASC LIMIT :limit"
            ),
            {"limit": BATCH_SIZE},
        ).fetchall()

        if not rows:
            return 0

        sent_ids = []
        for row in rows:
            event_id, payload_json = row.id, row.payload
            payload = json.loads(payload_json)

            key = None
            if payload.get("user_id") is not None:
                key = str(payload["user_id"]).encode("utf-8")

            # Kafka로 전송. 실패하면 예외가 발생해서 이 배치 처리가
            # 중단되고, sent_at 갱신도 안 되므로 다음 폴링에서 이
            # 이벤트부터 다시 시도된다 (at-least-once 전달).
            producer.send(settings.kafka_events_topic, key=key, value=payload)
            sent_ids.append(event_id)

        # 이 배치 전체가 Kafka로 전송 요청됐는지 확인 (동기적으로 flush)
        producer.flush()

        # 성공한 것들만 sent_at 을 채운다. 하나의 트랜잭션으로 일괄 갱신.
        # 리스트 파라미터를 안전하게 IN절로 확장하기 위해 expanding
        # bindparam을 명시한다 (단순 :ids 로는 SQLAlchemy가 리스트를
        # 안전하게 바인딩하지 못할 수 있다).
        stmt = text(
            "UPDATE outbox_events SET sent_at = :now WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        db.execute(stmt, {"now": datetime.utcnow(), "ids": sent_ids})
        db.commit()
        return len(sent_ids)
    finally:
        db.close()


def main():
    print(f"[outbox_relay] 시작. poll_interval={POLL_INTERVAL_SECONDS}s batch_size={BATCH_SIZE}")
    producer = create_producer()
    try:
        while True:
            try:
                count = relay_once(producer)
                if count:
                    print(f"[outbox_relay] {count}건 전송 완료")
            except Exception as e:
                # 한 배치가 실패해도 프로세스 자체는 죽지 않고 다음
                # 주기에 다시 시도한다 (sent_at 이 안 채워진 채로 남아
                # 있으므로 안전하게 재시도 가능). backend가 아직 alembic
                # 마이그레이션 전이라 outbox_events 테이블이 없는 초기
                # 기동 시점에도 이 재시도 로직이 그대로 커버해준다 -
                # 별도로 backend의 healthcheck를 기다릴 필요가 없다.
                print(f"[outbox_relay] 에러 발생, 다음 주기에 재시도: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    main()
