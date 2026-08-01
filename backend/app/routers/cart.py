"""
장바구니 API.

모든 엔드포인트는 인증(로그인)이 필요하다. user_id를 경로/바디로 받지 않고
get_current_user 의존성이 토큰에서 추출한 사용자만 사용한다.
이렇게 하면 로그인한 사용자가 "다른 사람의 user_id"를 넣어 장바구니를
조작하는 것이 원천적으로 불가능해진다.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import CartItem, Product, User
from app.schemas import CartItemIn, CartItemOut

router = APIRouter(prefix="/cart", tags=["cart"])


@router.post("", response_model=CartItemOut)
def add_to_cart(
    item: CartItemIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == item.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    # 이미 장바구니에 있는 상품이면 수량만 더한다.
    existing = (
        db.query(CartItem)
        .filter(CartItem.user_id == current_user.user_id, CartItem.product_id == item.product_id)
        .first()
    )
    if existing:
        existing.quantity += item.quantity
        db.commit()
        db.refresh(existing)
        return existing

    new_item = CartItem(
        user_id=current_user.user_id,
        product_id=item.product_id,
        quantity=item.quantity,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.get("", response_model=List[CartItemOut])
def get_cart(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(CartItem).filter(CartItem.user_id == current_user.user_id).all()


@router.delete("/{product_id}")
def remove_from_cart(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(CartItem)
        .filter(CartItem.user_id == current_user.user_id, CartItem.product_id == product_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="장바구니에 해당 상품이 없습니다.")
    db.delete(item)
    db.commit()
    return {"detail": "삭제되었습니다."}