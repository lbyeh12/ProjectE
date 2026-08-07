"""
인증 API.

- POST /auth/signup : 데이터셋에 이미 존재하는 user_id(CustomerID)에 비밀번호를 설정한다.
                       (이 프로젝트는 UCI 데이터셋의 기존 고객으로 로그인 체험을 하는 컨셉이라,
                        완전히 새로운 회원을 임의 생성하지 않고 기존 user_id에 비밀번호만 부여한다)
- POST /auth/login  : user_id + 비밀번호로 로그인, JWT 액세스 토큰 발급.
- GET  /auth/me     : 현재 로그인한 사용자 정보 확인 (토큰 유효성 테스트용)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, SignupRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="해당 user_id가 데이터셋에 없습니다. users.csv에 있는 CustomerID를 사용하세요.",
        )
    if user.hashed_password is not None:
        raise HTTPException(status_code=400, detail="이미 비밀번호가 설정된 계정입니다.")

    user.hashed_password = hash_password(req.password)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()

    # perf 002에서 발견된 문제 해결. autocommit=False 로 되어있어 명시적으로 트랜잭션 종료
    # expire_on_commit=True 때문에 orm객체가 만료. 때문에 객체에 미리 값 저장 후 이를 사용

    user_exists = user is not None
    hashed_password = user.hashed_password if user_exists else None
    user_id = user.user_id if user_exists else None
    db.commit()  

    password_ok = hashed_password is not None and verify_password(req.password, hashed_password)
 
    # 사용자가 없거나 비밀번호가 틀린 경우를 구분해서 알려주지 않는다.
    # (계정 존재 여부를 노출하지 않는 것이 일반적인 보안 관례)
    if not user_exists or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user_id 또는 비밀번호가 올바르지 않습니다.",
        )
    
    access_token = create_access_token(user_id=user.user_id)
    return TokenOut(access_token=access_token)


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
