"""
Alembic 환경 설정.

표준 alembic init 이 만드는 파일이지만, 두 곳을 우리 프로젝트에 맞게 고쳤다.

1. sqlalchemy.url 을 alembic.ini의 고정값이 아니라, app.config.settings.database_url
   에서 가져온다. -> .env / 환경변수로 로컬/도커/운영 DB 주소를 그대로 재사용.
2. target_metadata 를 app.models 의 Base.metadata 로 지정.
   -> `alembic revision --autogenerate` 실행 시, models.py 의 클래스들과 실제
      DB 테이블을 비교해서 차이가 나는 부분(컬럼 추가/삭제 등)을 자동으로 감지해
      마이그레이션 스크립트 초안을 만들어준다.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# backend/ 디렉터리를 path에 추가해서 `from app...` import 가 되게 한다.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app import models  # noqa: E402  (모델 클래스들을 Base.metadata 에 등록시키기 위해 import 필요)

config = context.config

# alembic.ini 의 sqlalchemy.url 대신, 프로젝트 설정값을 사용한다.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """DB에 접속하지 않고 SQL 스크립트만 생성하는 모드 (거의 안 씀)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """실제 DB에 접속해서 마이그레이션을 적용하는 일반 모드."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
