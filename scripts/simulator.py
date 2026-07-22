"""
사용자 행동 시뮬레이터.

전처리(data/preprocess.py)로 생성된 events.csv 를 읽어, 실제 사용자가
웹 서비스를 쓰는 것처럼 FastAPI의 POST /events 로 이벤트를 흘려보낸다.

두 가지 모드:
  1. replay 모드 (기본)
     events.csv 를 시간순으로 재생한다. --speed 로 배속을 조절한다.
     원본 timestamp 간격을 speed 로 나눠서 sleep 하므로, 하루치 데이터를
     몇 분 안에 압축 재생할 수 있다.

  2. random 모드
     products/users 를 기반으로 무한히 랜덤 이벤트를 생성해서 보낸다.
     데이터가 끊기지 않고 계속 흘러야 하는 실시간 대시보드 테스트에 적합.

사용 예:
    # events.csv 를 60배속으로 재생
    python scripts/simulator.py replay --speed 60

    # 초당 약 5건씩 무한 랜덤 생성
    python scripts/simulator.py random --rate 5

    # 앞 10000건만 최대한 빠르게 전송 (부하 테스트)
    python scripts/simulator.py replay --speed 0 --limit 10000
"""
import argparse
import random
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DEFAULT_API = "http://localhost:8000"
EVENT_ENDPOINT = "/events"

# random 모드에서 사용할 이벤트 타입별 가중치 (funnel 비율과 유사하게)
RANDOM_EVENT_WEIGHTS = {
    "view": 10,
    "search": 2,
    "add_to_cart": 3,
    "purchase": 1,
}


def parse_args():
    p = argparse.ArgumentParser(description="사용자 행동 시뮬레이터")
    sub = p.add_subparsers(dest="mode", required=True)

    # --- replay ---
    rp = sub.add_parser("replay", help="events.csv 를 시간순으로 재생")
    rp.add_argument("--events", default="../data/dataset/events.csv")
    rp.add_argument("--speed", type=float, default=60.0,
                    help="재생 배속. 60이면 실제 1분을 1초로 압축. 0이면 대기 없이 최대 속도")
    rp.add_argument("--limit", type=int, default=None, help="앞에서부터 N건만 전송")
    rp.add_argument("--api", default=DEFAULT_API)

    # --- random ---
    rd = sub.add_parser("random", help="products/users 기반 무한 랜덤 이벤트 생성")
    rd.add_argument("--products", default="../data/dataset/products.csv")
    rd.add_argument("--users", default="../data/dataset/users.csv")
    rd.add_argument("--rate", type=float, default=5.0, help="초당 전송 이벤트 수(평균)")
    rd.add_argument("--limit", type=int, default=None, help="N건 전송 후 종료 (기본: 무한)")
    rd.add_argument("--api", default=DEFAULT_API)

    return p.parse_args()


def send_event(session: requests.Session, api: str, event: dict) -> bool:
    """이벤트 1건 전송. 성공하면 True."""
    try:
        resp = session.post(f"{api}{EVENT_ENDPOINT}", json=event, timeout=5)
        if resp.status_code == 200:
            return True
        # 422(스키마 검증 실패) 등은 조용히 스킵하지 않고 로그를 남긴다.
        print(f"  [경고] status={resp.status_code} body={resp.text[:120]}", file=sys.stderr)
        return False
    except requests.RequestException as e:
        print(f"  [에러] 요청 실패: {e}", file=sys.stderr)
        return False


def build_event(user_id, event_type, product_id, price, timestamp) -> dict:
    """None/NaN 을 안전하게 처리해서 이벤트 dict 생성."""
    def clean(v):
        return None if pd.isna(v) else v

    uid = clean(user_id)
    # pandas가 user_id를 float(17850.0)로 읽는 경우가 있어 int로 보정
    if uid is not None:
        uid = int(uid)

    event = {
        "user_id": uid,
        "event_type": event_type,
        "product_id": clean(product_id),
        "price": clean(price),
    }
    ts = clean(timestamp)
    if ts is not None:
        # pandas Timestamp -> ISO 문자열
        event["timestamp"] = pd.Timestamp(ts).isoformat()
    return {k: v for k, v in event.items() if v is not None or k in ("user_id", "product_id", "price")}


# ---------------------------------------------------------------------------
# replay 모드
# ---------------------------------------------------------------------------

def run_replay(args):
    path = Path(args.events)
    if not path.exists():
        sys.exit(f"events 파일을 찾을 수 없습니다: {path}\n먼저 data/preprocess.py 를 실행하세요.")

    print(f"[replay] {path} 로드 중...")
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    if args.limit:
        df = df.head(args.limit)
    print(f"[replay] {len(df):,}건 재생 시작 (speed={args.speed}, api={args.api})")

    session = requests.Session()
    sent = 0
    failed = 0
    prev_ts = None
    start = time.time()

    for row in df.itertuples(index=False):
        # 이전 이벤트와의 시간 간격만큼 대기 (speed로 압축)
        if args.speed > 0 and prev_ts is not None:
            gap_sec = (row.timestamp - prev_ts).total_seconds()
            sleep_sec = max(gap_sec / args.speed, 0)
            # 과도한 대기 방지 (최대 5초)
            time.sleep(min(sleep_sec, 5.0))
        prev_ts = row.timestamp

        event = build_event(row.user_id, row.event_type, row.product_id, row.price, row.timestamp)
        if send_event(session, args.api, event):
            sent += 1
        else:
            failed += 1

        if (sent + failed) % 500 == 0:
            elapsed = time.time() - start
            print(f"  진행: {sent + failed:,}건 (성공 {sent:,} / 실패 {failed:,}) - {elapsed:.1f}s 경과")

    print(f"[replay] 완료. 성공 {sent:,} / 실패 {failed:,}")


# ---------------------------------------------------------------------------
# random 모드
# ---------------------------------------------------------------------------

def run_random(args):
    products_path = Path(args.products)
    users_path = Path(args.users)
    for pth in (products_path, users_path):
        if not pth.exists():
            sys.exit(f"파일을 찾을 수 없습니다: {pth}\n먼저 data/preprocess.py 를 실행하세요.")

    products = pd.read_csv(products_path)
    users = pd.read_csv(users_path)

    product_ids = products["product_id"].tolist()
    product_price = products.set_index("product_id")["price"].to_dict()
    # 인기 상품일수록 자주 뽑히도록 가중치
    product_weights = products["total_purchase_count"].tolist()
    user_ids = users["user_id"].tolist()

    event_types = list(RANDOM_EVENT_WEIGHTS.keys())
    event_weights = list(RANDOM_EVENT_WEIGHTS.values())

    print(f"[random] 무한 랜덤 생성 시작 (rate={args.rate}/s, api={args.api}) — Ctrl+C 로 중단")

    session = requests.Session()
    sent = 0
    interval = 1.0 / args.rate if args.rate > 0 else 0

    try:
        while True:
            user_id = random.choice(user_ids)
            event_type = random.choices(event_types, weights=event_weights, k=1)[0]

            # search 이벤트는 상품을 특정하지 않는 경우가 많음
            if event_type == "search":
                product_id = None
                price = None
            else:
                product_id = random.choices(product_ids, weights=product_weights, k=1)[0]
                price = product_price[product_id]

            event = build_event(user_id, event_type, product_id, price, None)
            if send_event(session, args.api, event):
                sent += 1

            if sent % 100 == 0 and sent > 0:
                print(f"  전송: {sent:,}건")

            if args.limit and sent >= args.limit:
                print(f"[random] limit({args.limit}) 도달, 종료")
                break

            if interval > 0:
                # 약간의 지터를 줘서 더 자연스럽게
                time.sleep(interval * random.uniform(0.5, 1.5))
    except KeyboardInterrupt:
        print(f"\n[random] 중단됨. 총 {sent:,}건 전송")


def main():
    args = parse_args()
    if args.mode == "replay":
        run_replay(args)
    elif args.mode == "random":
        run_random(args)


if __name__ == "__main__":
    main()
