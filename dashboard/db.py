"""
대시보드 공용 DB 연결/조회 모듈.

Streamlit 페이지들이 공통으로 쓰는 데이터 조회 함수를 모아둔다.
"""
import os
from typing import Optional

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

# 로컬에서 대시보드를 실행하는 경우 localhost:5432 로 접속.
DATABASE_URL = os.getenv(
    "DASHBOARD_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/projecte",
)


@st.cache_resource
def get_engine():
    """SQLAlchemy 엔진을 세션 동안 재사용 (매 요청마다 새로 만들지 않음)."""
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def run_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """SQL을 실행해서 DataFrame으로 반환. 테이블이 아직 없으면 빈 DataFrame."""
    engine = get_engine()
    try:
        return pd.read_sql(sql, engine, params=params)
    except Exception as e:
        st.warning(f"쿼리 실행 실패 (테이블이 아직 없을 수 있습니다): {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 실시간 페이지용 조회 (Spark Streaming 이 채우는 테이블)
# ---------------------------------------------------------------------------

def get_current_visitors(minutes: int = 5) -> int:
    """최근 N분간 이벤트를 발생시킨 순 사용자 수 (근사치, '현재 접속자' 대용)."""
    df = run_query(
        """
        SELECT COUNT(DISTINCT user_id) AS cnt
        FROM raw_events
        WHERE timestamp >= NOW() - (%(minutes)s || ' minutes')::interval
        """,
        params={"minutes": minutes},
    )
    if df.empty:
        return 0
    return int(df["cnt"].iloc[0] or 0)


def get_top_products(limit: int = 10) -> pd.DataFrame:
    """실시간 인기 상품 (Spark product_stats 기준, 구매수 순)."""
    return run_query(
        f"""
        SELECT ps.product_id, p.description, ps.view_count, ps.purchase_count, ps.revenue
        FROM product_stats ps
        LEFT JOIN products p ON p.product_id = ps.product_id
        ORDER BY ps.purchase_count DESC, ps.view_count DESC
        LIMIT {limit}
        """
    )


def get_recent_traffic(minutes: int = 60) -> pd.DataFrame:
    """
    최근 N분간의 1분 단위 트래픽 (Spark traffic_stats).

    Python 시각과 DB 시각의 시간대 차이로 필터에 안 걸리는 문제를 피하기 위해
    DB의 NOW() 기준으로 필터한다. 그래도 결과가 없으면(예: 오래 전 데이터만 있는 경우)
    가장 최근 윈도우 60개를 폴백으로 보여준다.
    """
    df = run_query(
        """
        SELECT window_start, unique_users, event_count, revenue
        FROM traffic_stats
        WHERE window_start >= NOW() - (%(minutes)s || ' minutes')::interval
        ORDER BY window_start
        """,
        params={"minutes": minutes},
    )
    if not df.empty:
        return df

    # 폴백: 최근 윈도우 60개 (시간대 문제나 과거 데이터만 있는 경우)
    df = run_query(
        """
        SELECT window_start, unique_users, event_count, revenue
        FROM traffic_stats
        ORDER BY window_start DESC
        LIMIT 60
        """
    )
    return df.sort_values("window_start") if not df.empty else df


def get_realtime_revenue_today() -> float:
    """오늘 실시간 누적 매출 (raw_events 의 purchase 합, Spark 저장분 기준)."""
    df = run_query(
        """
        SELECT COALESCE(SUM(price), 0) AS revenue
        FROM raw_events
        WHERE event_type = 'purchase' AND timestamp::date = CURRENT_DATE
        """
    )
    if df.empty:
        return 0.0
    return float(df["revenue"].iloc[0] or 0)


# ---------------------------------------------------------------------------
# 배치 페이지용 조회 (Airflow daily_etl 이 채우는 테이블)
# ---------------------------------------------------------------------------

def get_daily_metrics(days: int = 30) -> pd.DataFrame:
    """최근 N일의 일별 지표 (Airflow daily_metrics)."""
    return run_query(
        f"""
        SELECT metric_date, dau, view_count, purchase_count, conversion_rate, revenue, event_count
        FROM daily_metrics
        ORDER BY metric_date DESC
        LIMIT {days}
        """
    )