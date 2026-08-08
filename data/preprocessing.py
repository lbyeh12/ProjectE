"""
ecommerce_data.csv (UCI Online Retail 데이터셋) 전처리 스크립트

원본 거래 데이터를 다음으로 분리/가공한다.
  1. products.csv   - 상품 카탈로그
  2. users.csv       - 회원 사용자 목록
  3. purchases.csv   - 정제된 구매 거래 (Quantity > 0)
  4. refunds.csv     - 환불/취소 거래 (Quantity < 0)
  5. events.csv      - view / add_to_cart / purchase / refund 합성 이벤트 로그

실행:
    python preprocessing.py --input ./dataset/ecommerce_data.csv --outdir ./dataset --sample 1.0

--sample 옵션으로 0~1 사이 비율을 주면 빠른 테스트용으로 일부 행만 처리할 수 있다.
"""

import argparse
import os
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 설정값
# ---------------------------------------------------------------------------

# 실제 상품이 아닌 관리용 코드 (배송비, 수수료, 할인, 수동 조정 등)
NON_PRODUCT_CODES = {
    "POST", "D", "C2", "DOT", "M", "BANK CHARGES",
    "PADS", "CRUK", "AMAZONFEE", "S", "B",
}

# 이벤트 funnel 비율 (view : add_to_cart : purchase)
VIEW_RATIO = 10
CART_RATIO = 3
PURCHASE_RATIO = 1

RANDOM_SEED = 42


def parse_args():
    p = argparse.ArgumentParser(description="Online Retail 데이터 전처리 및 이벤트 합성")
    p.add_argument("--input", default="/mnt/user-data/uploads/ecommerce_data.csv")
    p.add_argument("--outdir", default="./data")
    p.add_argument("--sample", type=float, default=1.0, help="0~1 사이, 빠른 테스트용 샘플링 비율")
    return p.parse_args()


# ---------------------------------------------------------------------------
# 1. 적재 및 1차 클리닝
# ---------------------------------------------------------------------------

def load_and_clean(path: str, sample: float) -> pd.DataFrame:
    df = pd.read_csv(path)

    if sample < 1.0:
        df = df.sample(frac=sample, random_state=RANDOM_SEED).reset_index(drop=True)

    # 날짜 파싱 (UCI 원본 포맷: M/D/YYYY H:MM)
    df["InvoiceDate"] = pd.to_datetime(
        df["InvoiceDate"], format="%m/%d/%Y %H:%M", errors="coerce"
    )
    df = df.dropna(subset=["InvoiceDate"])

    # 비상품 코드 제거
    code_upper = df["StockCode"].astype(str).str.upper().str.strip()
    df = df[~code_upper.isin(NON_PRODUCT_CODES)].copy()

    # UnitPrice <= 0 인 행 제거 (가격 정보가 의미 없는 행)
    df = df[df["UnitPrice"] > 0]

    # Description 결측 행 제거 (상품명이 없으면 카탈로그에 못 올림)
    df = df.dropna(subset=["Description"])
    df["Description"] = df["Description"].str.strip()

    # 원본 데이터셋의 UnitPrice 는 GBP(영국 파운드) 기준이다. 우리 서비스는
    # 원화 기준으로 다루기로 해서, 여기서 한 번에 변환한다.
    # 환율은 2026-08 기준 시장가 근처의 고정값을 코드에 박아둔다(실시간
    # 환율 API를 붙일 이유가 없는 배치성 데이터 변환이라, 매번 최신 환율을
    # 조회할 필요는 없다고 판단). 나중에 환율이 크게 바뀌면 이 상수만
    # 조정하면 된다.
    GBP_TO_KRW = 1950

    # 1000원 단위로 반올림. round()가 아니라 정수 나눗셈으로 하는 이유:
    # round(1500, -3) 같은 "은행가 반올림(banker's rounding)"은 .5 지점에서
    # 짝수 쪽으로 반올림되는 파이썬 특유의 동작이 있어 직관과 다르게 동작할
    # 수 있다. 나눗셈+반올림+곱셈 방식이 "500원 이상이면 올림"이라는
    # 일반적인 기대와 정확히 일치한다.
    df["UnitPrice"] = ((df["UnitPrice"] * GBP_TO_KRW / 1000).round() * 1000).astype(int)
    # 반올림 결과가 0원이 되는 행은 제거 (변환 전 가격이 너무 낮아서
    # 1000원 단위로는 0으로 떨어진 경우, 판매 가격으로 의미가 없음)
    df = df[df["UnitPrice"] > 0]

    return df


# ---------------------------------------------------------------------------
# 2. products / users 테이블 생성
# ---------------------------------------------------------------------------

def build_products(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("StockCode")
    products = grouped.agg(
        description=("Description", lambda x: x.mode().iloc[0]),
        # 같은 상품도 거래마다 가격이 조금씩 다를 수 있어(할인 등) 대표값으로
        # median을 쓴다. UnitPrice는 이미 원화 정수로 변환되어 있지만,
        # median 자체가 1000원 단위를 벗어날 수 있어(예: 여러 값의 중간)
        # 한 번 더 1000원 단위로 반올림해서 상품 가격의 일관성을 지킨다.
        price=("UnitPrice", lambda x: int(round(x.median() / 1000) * 1000)),
        total_purchase_count=("StockCode", "count"),
    ).reset_index()
    products = products.rename(columns={"StockCode": "product_id"})

    # 재고(stock) — 원본 데이터셋에는 없던 개념이라 임의로 채워 넣는다
    # (adrs/0004-inventory-concurrency-control.md). "과거에 많이 팔린
    # 상품일수록 최근에도 넉넉히 재입고했다"는 가정으로, 과거 판매량에
    # 비례한 기준치에 약간의 무작위성을 섞어 부여한다. 재현 가능하도록
    # 랜덤 시드를 고정한다.
    rng = np.random.default_rng(RANDOM_SEED)
    base_stock = (products["total_purchase_count"] * 0.3).clip(lower=5).astype(int)
    noise = rng.integers(low=-3, high=10, size=len(products))
    products["stock"] = (base_stock + noise).clip(lower=0)

    return products.sort_values("total_purchase_count", ascending=False).reset_index(drop=True)


def build_users(df: pd.DataFrame) -> pd.DataFrame:
    member_df = df.dropna(subset=["CustomerID"]).copy()
    member_df["CustomerID"] = member_df["CustomerID"].astype(int)

    grouped = member_df.groupby("CustomerID")
    users = grouped.agg(
        country=("Country", lambda x: x.mode().iloc[0]),
        first_purchase_at=("InvoiceDate", "min"),
        last_purchase_at=("InvoiceDate", "max"),
    ).reset_index()
    users = users.rename(columns={"CustomerID": "user_id"})
    return users


# ---------------------------------------------------------------------------
# 3. purchases / refunds 분리
# ---------------------------------------------------------------------------

def split_transactions(df: pd.DataFrame):
    member_df = df.dropna(subset=["CustomerID"]).copy()
    member_df["CustomerID"] = member_df["CustomerID"].astype(int)

    purchases = member_df[member_df["Quantity"] > 0].copy()
    refunds = member_df[member_df["Quantity"] < 0].copy()

    purchases = purchases.rename(
        columns={
            "CustomerID": "user_id",
            "StockCode": "product_id",
            "UnitPrice": "price",
            "InvoiceDate": "timestamp",
            "InvoiceNo": "invoice_no",
        }
    )[["invoice_no", "user_id", "product_id", "Quantity", "price", "timestamp"]]

    refunds = refunds.rename(
        columns={
            "CustomerID": "user_id",
            "StockCode": "product_id",
            "UnitPrice": "price",
            "InvoiceDate": "timestamp",
            "InvoiceNo": "invoice_no",
        }
    )[["invoice_no", "user_id", "product_id", "Quantity", "price", "timestamp"]]

    return purchases, refunds


# ---------------------------------------------------------------------------
# 4. 이벤트 합성
#
#   - 실제 구매 1건마다: view 1회 + add_to_cart 1회 (같은 user/product, 구매 직전)
#     를 만들어 실제 전환 경로(view -> cart -> purchase)를 재현한다.
#   - 여기에 구매로 이어지지 않는 "이탈" 이벤트(조회만 하고 끝, 장바구니까지
#     갔다가 이탈)를 추가로 채워서 전체 view:cart:purchase 비율을
#     VIEW_RATIO : CART_RATIO : PURCHASE_RATIO 에 맞춘다.
#   - 이탈 이벤트는 실제 구매 이력이 없는 임의의 (user, product) 조합에서
#     발생한 것으로 간주하고, 상품은 인기도(구매 빈도)에 비례해 가중 샘플링한다.
#   - 환불(refund)은 원본 음수 Quantity 행을 그대로 이벤트화한다.
# ---------------------------------------------------------------------------

def synthesize_events(
    purchases: pd.DataFrame,
    refunds: pd.DataFrame,
    users: pd.DataFrame,
    products: pd.DataFrame,
) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    n_purchase = len(purchases)

    events = []

    # --- 4-1. 실제 전환 경로: 구매한 건마다 view + cart 이벤트 생성 ---
    purchase_ts = purchases["timestamp"].values.astype("datetime64[m]")

    cart_offset_min = rng.integers(1, 15, size=n_purchase)  # 구매 1~15분 전 장바구니
    view_offset_min = cart_offset_min + rng.integers(5, 60, size=n_purchase)  # 그 전 view

    real_cart = pd.DataFrame({
        "user_id": purchases["user_id"].values,
        "event_type": "add_to_cart",
        "product_id": purchases["product_id"].values,
        "price": purchases["price"].values,
        "timestamp": purchase_ts - cart_offset_min.astype("timedelta64[m]"),
    })
    real_view = pd.DataFrame({
        "user_id": purchases["user_id"].values,
        "event_type": "view",
        "product_id": purchases["product_id"].values,
        "price": purchases["price"].values,
        "timestamp": purchase_ts - view_offset_min.astype("timedelta64[m]"),
    })
    real_purchase = pd.DataFrame({
        "user_id": purchases["user_id"].values,
        "event_type": "purchase",
        "product_id": purchases["product_id"].values,
        "price": purchases["price"].values,
        "timestamp": purchases["timestamp"].values,
    })

    events.extend([real_view, real_cart, real_purchase])

    # --- 4-2. 이탈(미전환) 이벤트로 비율 채우기 ---
    target_view_total = VIEW_RATIO * n_purchase
    target_cart_total = CART_RATIO * n_purchase

    extra_view_count = max(target_view_total - n_purchase, 0)
    extra_cart_count = max(target_cart_total - n_purchase, 0)

    user_pool = users["user_id"].values
    product_pool = products["product_id"].values
    product_price = products.set_index("product_id")["price"]
    # 인기 상품일수록 더 자주 조회/장바구니에 담기도록 가중치 부여
    weights = products["total_purchase_count"].values.astype(float)
    weights = weights / weights.sum()

    ts_min = purchases["timestamp"].min().to_datetime64()
    ts_max = purchases["timestamp"].max().to_datetime64()
    span_minutes = int((ts_max - ts_min) / np.timedelta64(1, "m"))

    def random_browsing_events(n: int, event_type: str) -> pd.DataFrame:
        if n <= 0:
            return pd.DataFrame(columns=["user_id", "event_type", "product_id", "price", "timestamp"])
        sampled_users = rng.choice(user_pool, size=n, replace=True)
        sampled_products = rng.choice(product_pool, size=n, replace=True, p=weights)
        random_minutes = rng.integers(0, span_minutes, size=n)
        timestamps = ts_min + random_minutes.astype("timedelta64[m]")
        return pd.DataFrame({
            "user_id": sampled_users,
            "event_type": event_type,
            "product_id": sampled_products,
            "price": product_price.loc[sampled_products].values,
            "timestamp": timestamps,
        })

    events.append(random_browsing_events(int(extra_view_count), "view"))
    events.append(random_browsing_events(int(extra_cart_count), "add_to_cart"))

    # --- 4-3. 환불 이벤트 ---
    if len(refunds) > 0:
        refund_events = pd.DataFrame({
            "user_id": refunds["user_id"].values,
            "event_type": "refund",
            "product_id": refunds["product_id"].values,
            "price": refunds["price"].values,
            "timestamp": refunds["timestamp"].values,
        })
        events.append(refund_events)

    all_events = pd.concat(events, ignore_index=True)
    all_events = all_events.sort_values("timestamp").reset_index(drop=True)
    return all_events


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    print(f"[1/5] 원본 로드 및 클리닝: {args.input}")
    df = load_and_clean(args.input, args.sample)
    print(f"      -> 클리닝 후 {len(df):,}행")

    print("[2/5] products / users 테이블 생성")
    products = build_products(df)
    users = build_users(df)
    print(f"      -> products {len(products):,}건, users {len(users):,}건")

    print("[3/5] purchases / refunds 분리")
    purchases, refunds = split_transactions(df)
    print(f"      -> purchases {len(purchases):,}건, refunds {len(refunds):,}건")

    print("[4/5] 이벤트 합성 (view/cart/purchase/refund)")
    events = synthesize_events(purchases, refunds, users, products)
    print(f"      -> 총 이벤트 {len(events):,}건")
    print(events["event_type"].value_counts())

    print(f"[5/5] 결과 저장 -> {args.outdir}")
    products.to_csv(os.path.join(args.outdir, "products.csv"), index=False)
    users.to_csv(os.path.join(args.outdir, "users.csv"), index=False)
    purchases.to_csv(os.path.join(args.outdir, "purchases.csv"), index=False)
    refunds.to_csv(os.path.join(args.outdir, "refunds.csv"), index=False)
    events.to_csv(os.path.join(args.outdir, "events.csv"), index=False)

    print("완료.")


if __name__ == "__main__":
    main()