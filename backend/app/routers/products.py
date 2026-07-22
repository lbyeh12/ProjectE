"""
상품 조회 API.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product
from app.schemas import ProductOut

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=List[ProductOut])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="상품명 부분 검색"),
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if search:
        query = query.filter(Product.description.ilike(f"%{search}%"))
    # 인기순(구매 빈도)으로 기본 정렬
    query = query.order_by(Product.total_purchase_count.desc())
    return query.offset(skip).limit(limit).all()


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    return product
