"""
인증 유틸리티.

- 비밀번호 해싱/검증 (bcrypt)
- JWT 액세스 토큰 발급/검증
- get_current_user: 보호된 엔드포인트에서 Depends() 로 사용하는 의존성.
  요청 헤더의 Bearer 토큰을 검증해서 로그인한 User 객체를 돌려준다.
  이걸 쓰면 클라이언트가 보낸 user_id를 그대로 믿지 않고,
  토큰에 담긴(=로그인된) user_id만 신뢰하게 된다.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl은 Swagger UI(/docs)에서 "Authorize" 버튼이 로그인 요청을 보낼 경로.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int) -> str:
    """user_id를 담은 JWT를 발급한다."""
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[int]:
    """토큰을 검증하고 user_id를 반환한다. 유효하지 않으면 None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        return int(user_id_str)
    except (JWTError, ValueError):
        return None


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    보호된 엔드포인트용 의존성. 로그인 필수.
    사용 예: def my_route(current_user: User = Depends(get_current_user)):
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증이 필요합니다. 로그인 후 다시 시도하세요.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception

    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    로그인이 선택적인 엔드포인트용 의존성 (예: 이벤트 트래킹은 비로그인도 허용).
    토큰이 없거나 유효하지 않으면 None을 반환할 뿐 에러를 던지지 않는다.
    """
    if token is None:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    return db.query(User).filter(User.user_id == user_id).first()
