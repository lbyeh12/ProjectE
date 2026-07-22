"""
data/dataset/products.csv, users.csv 를 PostgreSQL에 적재한다.

전처리(data/preprocess.py)가 먼저 끝나 있어야 한다.

실행:
    cd backend
    python scripts/load_data.py --dataset-dir ../data/dataset
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

# backend/app 모듈을 import 하기 위해 backend 디렉토리를 path에 추가
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Product, User  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="products.csv / users.csv를 DB에 적재")
    p.add_argument("--dataset-dir", default="../data/dataset")
    return p.parse_args()


def load_products(db, dataset_dir: Path):
    path = dataset_dir / "products.csv"
    df = pd.read_csv(path)
    count = 0
    for _, row in df.iterrows():
        existing = db.query(Product).filter(Product.product_id == row["product_id"]).first()
        if existing:
            existing.description = row["description"]
            existing.price = row["price"]
            existing.total_purchase_count = row["total_purchase_count"]
        else:
            db.add(Product(
                product_id=row["product_id"],
                description=row["description"],
                price=row["price"],
                total_purchase_count=row["total_purchase_count"],
            ))
        count += 1
    db.commit()
    print(f"  products: {count:,}건 적재 완료")


def load_users(db, dataset_dir: Path):
    path = dataset_dir / "users.csv"
    df = pd.read_csv(path)
    count = 0
    for _, row in df.iterrows():
        existing = db.query(User).filter(User.user_id == row["user_id"]).first()
        if existing:
            existing.country = row["country"]
            existing.first_purchase_at = row["first_purchase_at"]
            existing.last_purchase_at = row["last_purchase_at"]
        else:
            db.add(User(
                user_id=row["user_id"],
                country=row["country"],
                first_purchase_at=row["first_purchase_at"],
                last_purchase_at=row["last_purchase_at"],
            ))
        count += 1
    db.commit()
    print(f"  users: {count:,}건 적재 완료")


def main():
    args = parse_args()
    dataset_dir = Path(args.dataset_dir)

    print("테이블 생성 확인 (없으면 생성)")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print(f"products 적재 중... ({dataset_dir / 'products.csv'})")
        load_products(db, dataset_dir)

        print(f"users 적재 중... ({dataset_dir / 'users.csv'})")
        load_users(db, dataset_dir)
    finally:
        db.close()

    print("완료.")


if __name__ == "__main__":
    main()
