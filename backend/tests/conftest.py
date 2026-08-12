"""
pytest 공통 설정(fixture).

핵심 아이디어:
  - 로컬 개발 DB(projecte)를 건드리지 않도록, 테스트 전용 DB(projecte_test)를 쓴다.
  - 테스트 함수 하나마다 트랜잭션을 시작해서 실행하고, 끝나면 무조건 롤백한다.
    이렇게 하면 테스트가 서로 데이터를 남기거나 간섭하지 않고, 매번 깨끗한 상태에서 시작한다.
  - FastAPI의 get_db 의존성을 이 테스트 세션으로 바꿔치기(override)해서,
    앱 코드는 수정하지 않고도 테스트에서는 테스트 DB를 쓰게 만든다.

실행 전제:
  - TEST_DATABASE_URL 환경변수(또는 기본값)가 가리키는 PostgreSQL이 떠 있어야 한다.
  - CI(GitHub Actions)에서는 postgres 서비스 컨테이너가 이 역할을 한다.
  - Kafka는 테스트에 필요 없다. USE_KAFKA=false 로 강제해서, /events, /purchase 가
    Kafka 대신 PostgreSQL에 직접 저장하는 폴백 경로를 타게 만든다.
    (이 폴백 경로가 이미 app/routers/events.py 에 구현되어 있어, 테스트가 그 결과를
     DB에서 바로 검증할 수 있다는 부수적인 장점도 있다.)
"""
import os

# app.config 는 pydantic-settings 로 만들어져 있어 import 시점에 환경변수를 읽는다.
# 따라서 app 모듈을 import 하기 "전에" 반드시 여기서 환경변수를 먼저 설정해야 한다.
os.environ.setdefault("USE_KAFKA", "false")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-not-for-production")
# 개발용 DB(0번)와 겹치지 않게 별도 인덱스(1번) 사용.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app import redis_client

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/projecte_test",
)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_schema():
    """테스트 세션 시작 시 1회: 테스트 DB에 전체 테이블 생성, 끝나면 정리."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    """
    테스트 함수 하나당 트랜잭션 하나. 테스트가 끝나면 무조건 롤백해서
    테스트끼리 데이터가 섞이지 않게 한다.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def _isolate_redis(client):
    """
    Redis는 DB 트랜잭션 롤백(위 db_session fixture)의 영향을 받지 않으므로,
    멱등성 키/Rate Limit 카운터가 테스트 함수 사이에 그대로 남아 서로
    간섭할 수 있다 (예: 로그인 테스트를 여러 번 하면 같은 user_id의
    Rate Limit 카운터가 쌓여 무관한 다른 테스트가 429를 받는 문제).
    매 테스트 전후로 비워서 격리한다.

    client 를 인자로 받아 의존성을 명시하는 게 중요하다: pytest는
    fixture teardown을 설정의 역순으로 실행하는데, 이 의존성이 없으면
    client fixture(앱 종료 시 redis_client.close_client() 호출 ->
    _client = None)가 먼저 정리된 뒤에 이 fixture의 flush_all() 이
    실행되어, "_client가 없다"며 조용히 아무것도 안 지우는 상태가 된다
    (실제로 이 버그로 여러 테스트가 서로 간섭하는 걸 확인했다).
    client에 의존하게 하면 teardown이 반드시 "flush 먼저, 연결 종료는
    나중"의 순서로 실행된다.
    """
    redis_client.flush_all()
    yield
    redis_client.flush_all()


@pytest.fixture()
def client(db_session):
    """
    FastAPI 앱의 get_db 의존성을 테스트 세션으로 바꿔치기한 TestClient.
    라우터 코드(routers/*.py)는 전혀 수정하지 않고, 이 오버라이드만으로
    테스트가 실제 운영 DB가 아니라 테스트 트랜잭션 안에서 동작하게 만든다.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # 세션 닫기/롤백은 db_session fixture가 책임진다.

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def sample_product(db_session):
    """테스트에서 자주 쓰는 샘플 상품 하나를 만들어 반환."""
    from app.models import Product

    product = Product(
        product_id="TEST001",
        description="테스트 상품",
        price=9.99,
        total_purchase_count=0,
        # 재고 동시성 제어(adrs/0004) 도입 이후 필수 컬럼. 여러 테스트가
        # 이 상품으로 구매를 시도하므로 충분히 넉넉하게 잡는다.
        stock=100,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


@pytest.fixture()
def sample_user(db_session):
    """테스트에서 자주 쓰는 샘플 사용자(비밀번호 미설정 상태)를 만들어 반환."""
    from app.models import User

    user = User(user_id=999001, country="United Kingdom")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def auth_headers(client, sample_user):
    """
    회원가입 + 로그인까지 마친 뒤, Authorization 헤더를 바로 쓸 수 있게 반환.
    로그인이 필요한 테스트(장바구니, 구매 등)에서 재사용한다.
    """
    client.post(
        "/auth/signup",
        json={"user_id": sample_user.user_id, "password": "testpass123"},
    )
    res = client.post(
        "/auth/login",
        json={"user_id": sample_user.user_id, "password": "testpass123"},
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}