"""
Redis 클라이언트 (adrs/0006-idempotency-store-selection.md).

앱 시작 시 클라이언트를 한 번 생성해두고, 멱등성 키 검사에 사용한다.
멱등성 검사는 SET NX(값이 없을 때만 저장)의 원자성을 이용한다 - 여러
워커가 동시에 같은 키로 요청해도, Redis가 원자적으로 처리해주기 때문에
"먼저 처리 중"이라고 정확히 한 곳에서만 판정된다.
"""
import json
from typing import Optional

import redis

from app.config import settings

_client: Optional[redis.Redis] = None


def init_client() -> None:
    """앱 시작 시 호출."""
    global _client
    if _client is not None:
        return
    _client = redis.from_url(settings.redis_url, decode_responses=True)


def close_client() -> None:
    """앱 종료 시 호출."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def try_begin_idempotent_request(key: str) -> bool:
    """
    이 멱등성 키로 처리를 "시작"해도 되는지 원자적으로 확인하고 표시한다.

    반환값:
      True  - 이 키로 처리를 시작한 적이 없었다 (지금 이 요청이 처리해도 됨).
              "처리 중" 상태로 표시해뒀으니, 끝나면 반드시
              save_idempotent_result() 를 호출해서 결과로 덮어써야 한다.
      False - 이미 처리했거나 처리 중인 요청이다. 호출하는 쪽에서
              get_idempotent_result() 로 이전 결과를 가져와 그대로
              반환해야 한다.
    """
    # nx=True: 키가 없을 때만 저장(성공 시 True). 이미 있으면 아무것도
    # 안 하고 False를 반환한다 - 이게 원자적 연산이라, 여러 워커가
    # 동시에 같은 키로 들어와도 정확히 하나만 True를 받는다.
    return bool(
        _client.set(
            f"idempotency:{key}",
            json.dumps({"status": "processing"}),
            nx=True,
            ex=settings.idempotency_ttl_seconds,
        )
    )


def save_idempotent_result(key: str, status_code: int, body: dict) -> None:
    """처리가 끝난 뒤, "처리 중" 표시를 실제 결과로 덮어쓴다."""
    _client.set(
        f"idempotency:{key}",
        json.dumps({"status": "done", "status_code": status_code, "body": body}),
        ex=settings.idempotency_ttl_seconds,
    )


def get_idempotent_result(key: str) -> Optional[dict]:
    """
    이 키로 이미 저장된 결과를 가져온다.
    아직 처리 중(status=processing)이면 None을 반환한다 - 호출하는
    쪽에서 이 경우 409 등으로 "아직 처리 중이니 잠시 후 다시 시도"를
    응답하도록 한다.
    """
    raw = _client.get(f"idempotency:{key}")
    if raw is None:
        return None
    data = json.loads(raw)
    if data.get("status") != "done":
        return None
    return data


def clear_idempotent_request(key: str) -> None:
    """
    "처리 중" 표시를 지운다. 재고 부족(409)이나 빈 장바구니(400)처럼
    정상적인 도메인 로직 실패로 끝난 경우에 쓴다. 이런 실패는 결과로
    캐싱해두지 않고 아예 지워서, 사용자가 재시도할 때(예: 장바구니를
    채운 뒤) 깨끗하게 다시 시도할 수 있게 한다. 지우지 않으면
    try_begin_idempotent_request() 가 계속 False를 반환해서, TTL이
    끝날 때까지 "처리 중"이라고만 응답하는 상태로 막혀버린다.
    """
    _client.delete(f"idempotency:{key}")
