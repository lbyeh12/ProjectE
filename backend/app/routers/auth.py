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
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, SignupRequest, TokenOut, UserOut
from app import redis_client

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
    # Rate Limiting (adrs/0007-rate-limiting.md): 브루트포스 방어.
    # DB 조회, 특히 뒤이어 오는 bcrypt 검증(CPU 집약적)보다 먼저
    # 검사해서, 제한에 걸린 요청은 그 무거운 연산까지 가지 않고
    # 바로 거절되게 한다. user_id 기준으로 계정별 카운트한다
    # (같은 계정을 겨냥한 반복 시도를 막는 게 목적이므로 IP보다
    # user_id가 더 직접적인 기준).
    allowed = redis_client.check_rate_limit(
        bucket="login",
        identifier=str(req.user_id),
        limit=settings.login_rate_limit_count,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
        )

    user = db.query(User).filter(User.user_id == req.user_id).first()

    # DB에서 필요한 값(hashed_password)만 파이썬 변수로 즉시 꺼내둔다.
    # 이 시점 이후로는 user(ORM 객체)를 더 이상 건드리지 않는다 -> 뒤이어
    # 오는 bcrypt 검증(CPU 집약적, 느림) 동안 DB 트랜잭션이 불필요하게
    # 열려있지 않게 하기 위함이다.
    #
    # 이전에는 `if not user or ... or not verify_password(...)` 한 줄에
    # DB 접근과 bcrypt 호출이 섞여 있었는데, 대량 동시 로그인 부하
    # 테스트에서 이 때문에 세션이 bcrypt 처리 시간만큼 idle in
    # transaction 상태로 방치되는 문제가 확인됐다
    # (docs/perf/002-stress-test.md 참고, idle_duration 최대 3분 17초 관찰).
    user_exists = user is not None
    hashed_password = user.hashed_password if user_exists else None
    user_id = user.user_id if user_exists else None

    # 값만 변수로 뽑아둔다고 트랜잭션이 끝나는 게 아니다 (SQLAlchemy는
    # commit/rollback을 명시적으로 호출해야 트랜잭션을 닫는다). 조회만
    # 했고 아무것도 안 바꿨으니 commit을 호출해서 트랜잭션을 즉시
    # 종료한다. 이렇게 해야 뒤이어 오는 bcrypt 검증(느림) 동안
    # PostgreSQL에서 "idle in transaction" 상태로 락을 들고 방치되는
    # 일이 없다 (idle in transaction 은 자동 vacuum을 막고, 다른
    # 트랜잭션의 락 대기를 유발할 수 있다).
    db.commit()

    # 여기서부터는 DB를 전혀 건드리지 않는다. bcrypt 검증만 수행.
    password_ok = hashed_password is not None and verify_password(req.password, hashed_password)

    # 사용자가 없거나 비밀번호가 틀린 경우를 구분해서 알려주지 않는다.
    # (계정 존재 여부를 노출하지 않는 것이 일반적인 보안 관례)
    if not user_exists or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user_id 또는 비밀번호가 올바르지 않습니다.",
        )

    access_token = create_access_token(user_id=user_id)
    return TokenOut(access_token=access_token)


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user