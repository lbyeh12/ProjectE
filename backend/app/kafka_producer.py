"""
Kafka Producer.

앱 시작 시 Producer를 한 번 생성해두고, 이벤트를 JSON 직렬화해서
user-events 토픽으로 전송한다.

이벤트 스키마는 프론트엔드/시뮬레이터가 보내는 것과 동일하다:
  { user_id, event_type, product_id, price, timestamp }

send_event()는 응답을 기다리지 않는 fire-and-forget 방식이라
API 응답 속도에 영향을 주지 않는다.
"""
import json
from datetime import datetime
from typing import Optional

from kafka import KafkaProducer

from app.config import settings

_producer: Optional[KafkaProducer] = None


def _json_serializer(value: dict) -> bytes:
    """dict를 UTF-8 JSON 바이트로 직렬화. datetime은 ISO 문자열로 변환."""
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"직렬화 불가 타입: {type(o)}")

    return json.dumps(value, default=default).encode("utf-8")


def init_producer() -> None:
    """앱 시작 시 호출. Producer를 생성한다."""
    global _producer
    if not settings.use_kafka:
        return
    if _producer is not None:
        return
    _producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
        value_serializer=_json_serializer,
        # 전송 실패 시 재시도, 순서 보장을 위한 기본 설정
        retries=3,
        acks="all",
    )


def close_producer() -> None:
    """앱 종료 시 호출. 남은 메시지를 flush 하고 닫는다."""
    global _producer
    if _producer is not None:
        _producer.flush()
        _producer.close()
        _producer = None


def send_event(event: dict) -> None:
    """
    이벤트 1건을 user-events 토픽으로 전송한다.
    user_id를 메시지 key로 사용해서, 같은 사용자의 이벤트가
    같은 파티션으로 가도록 한다 (사용자별 순서 보장).
    """
    if _producer is None:
        raise RuntimeError("Kafka Producer가 초기화되지 않았습니다.")

    key = None
    if event.get("user_id") is not None:
        key = str(event["user_id"]).encode("utf-8")

    _producer.send(settings.kafka_events_topic, key=key, value=event)


def is_enabled() -> bool:
    """Kafka 사용 여부 + Producer 준비 여부."""
    return settings.use_kafka and _producer is not None
