"""
장바구니 API.

인증 시스템은 아직 없으므로, user_id를 요청 바디/경로로 직접 받는다.
(이후 로그인 기능이 붙으면 JWT에서 user_id를 추출하는 방식으로 교체)
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CartItem, Product, User
from app.schemas import CartItemIn, CartItemOut

router = APIRouter(prefix="/cart", tags=["cart"])


@router.post("", response_model=CartItemOut)
def add_to_cart(item: CartItemIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == item.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    product = db.query(Product).filter(Product.product_id == item.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    # 이미 장바구니에 있는 상품이면 수량만 더한다.
    existing = (
        db.query(CartItem)
        .filter(CartItem.user_id == item.user_id, CartItem.product_id == item.product_id)
        .first()
    )
    if existing:
        existing.quantity += item.quantity
        db.commit()
        db.refresh(existing)
        return existing

    new_item = CartItem(user_id=item.user_id, product_id=item.product_id, quantity=item.quantity)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.get("/{user_id}", response_model=List[CartItemOut])
def get_cart(user_id: int, db: Session = Depends(get_db)):
    return db.query(CartItem).filter(CartItem.user_id == user_id).all()


@router.delete("/{user_id}/{product_id}")
def remove_from_cart(user_id: int, product_id: str, db: Session = Depends(get_db)):
    item = (
        db.query(CartItem)
        .filter(CartItem.user_id == user_id, CartItem.product_id == product_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="장바구니에 해당 상품이 없습니다.")
    db.delete(item)
    db.commit()
    return {"detail": "삭제되었습니다."}
