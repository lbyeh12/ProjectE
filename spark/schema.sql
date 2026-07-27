-- ============================================================
-- Spark Streaming 집계 결과 테이블 스키마
--
-- raw_events 는 FastAPI(SQLAlchemy)가 자동 생성하지만,
-- 집계 테이블은 여기서 명시적으로 정의한다.
--
-- 적용:
--   docker exec -i projecte-postgres psql -U postgres -d projecte < spark/schema.sql
-- 또는 psql 접속 후 이 파일 내용 실행
-- ============================================================

-- 상품별 집계 (인기 상품 / 매출)
-- Spark가 complete 모드로 매 배치마다 overwrite 한다.
CREATE TABLE IF NOT EXISTS product_stats (
    product_id      TEXT,
    view_count      BIGINT,
    purchase_count  BIGINT,
    revenue         DOUBLE PRECISION
);

-- 1분 단위 트래픽 집계 (분당 방문자/이벤트/매출)
-- Spark가 append 모드로 윈도우가 확정될 때마다 추가한다.
CREATE TABLE IF NOT EXISTS traffic_stats (
    window_start    TIMESTAMP,
    window_end      TIMESTAMP,
    unique_users    BIGINT,
    event_count     BIGINT,
    revenue         DOUBLE PRECISION
);

-- 조회 성능을 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_traffic_window_start ON traffic_stats (window_start);
CREATE INDEX IF NOT EXISTS idx_raw_events_timestamp ON raw_events (timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_events_type ON raw_events (event_type);
