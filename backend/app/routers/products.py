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
    products = query.offset(skip).limit(limit).all()

    # commit() 전에 ORM 객체를 순수 Pydantic 객체로 완전히 변환해둔다.
    # (주의: commit() 이후 ORM 객체의 속성을 다시 읽으면, 이미 한 번
    #  읽었던 속성이라도 세션의 expire_on_commit=True 때문에 무조건
    #  새로 SELECT를 날린다. "이미 로드했으니 캐시에서 재사용되겠지"라는
    #  가정은 틀렸다 - expire는 이전 접근 여부와 무관하게 전부 무효화한다.
    #  그래서 아예 ORM 객체와 완전히 분리된 Pydantic 객체로 미리 바꿔두고,
    #  그 이후에만 commit() 한다.)
    result = [ProductOut.model_validate(p) for p in products]

    # 조회만 했으니 트랜잭션을 여기서 명시적으로 끝낸다 (login()에서 발견한
    # 것과 같은 원리: commit/rollback을 안 하면 응답이 클라이언트에 전달될
    # 때까지, 그리고 대량 요청으로 그게 지연될 때까지 트랜잭션이 계속 열려
    # 있는다 -> docs/perf/002-stress-test.md).
    db.commit()

    return result


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    # list_products() 와 동일한 이유로, commit() 전에 Pydantic 객체로
    # 변환해두고 나서 트랜잭션을 닫는다.
    result = ProductOut.model_validate(product)
    db.commit()
    return result