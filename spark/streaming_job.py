"""
Spark Structured Streaming 잡.

Kafka의 user-events 토픽을 실시간으로 읽어서:
  1. 원본 이벤트를 PostgreSQL raw_events 테이블에 저장 (append)
  2. 실시간 집계:
     - product_stats : 상품별 조회/구매 수, 매출 (인기 상품)
     - traffic_stats : 1분 윈도우별 방문자 수(순 사용자), 이벤트 수, 매출

실행 (로컬):
    spark-submit \
      --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4,org.postgresql:postgresql:42.7.4 \
      spark/streaming_job.py

  --packages 로 Kafka 커넥터와 PostgreSQL JDBC 드라이버를 받는다.
  (pip 로는 설치되지 않는 부분)

환경변수로 접속 정보를 덮어쓸 수 있다:
    KAFKA_BOOTSTRAP (기본 localhost:9092)
    PG_URL          (기본 jdbc:postgresql://localhost:5432/projecte)
    PG_USER, PG_PASSWORD
"""
import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    from_json,
    to_timestamp,
    window,
    count,
    approx_count_distinct,
    sum as _sum,
    when,
)
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType

# --- 접속 설정 (환경변수로 덮어쓰기 가능) ---
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "user-events")

PG_URL = os.getenv("PG_URL", "jdbc:postgresql://localhost:5432/projecte")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")

# 체크포인트: 스트림이 어디까지 읽었는지 저장 (재시작 시 이어서 처리)
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/tmp/projecte-spark-checkpoints")

# --- 이벤트 JSON 스키마 (FastAPI가 보내는 것과 동일) ---
EVENT_SCHEMA = StructType([
    StructField("user_id", LongType(), True),
    StructField("event_type", StringType(), True),
    StructField("product_id", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("timestamp", StringType(), True),
])


def write_to_postgres(df, table_name, mode="append"):
    """배치 DataFrame을 PostgreSQL 테이블에 쓴다."""
    writer = df.write.mode(mode)
    if mode == "overwrite":
        # 테이블을 DROP/재생성하지 않고 TRUNCATE만 하여
        # 미리 만든 스키마와 인덱스를 유지한다.
        writer = writer.option("truncate", "true")
    (writer
        .format("jdbc")
        .option("url", PG_URL)
        .option("dbtable", table_name)
        .option("user", PG_USER)
        .option("password", PG_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .save())


def main():
    spark = (
        SparkSession.builder
        .appName("projecte-streaming")
        .config("spark.sql.shuffle.partitions", "4")  # 로컬용, 작게
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # --- Kafka 스트림 읽기 ---
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")  # 실행 이후 들어오는 이벤트부터
        .load()
    )

    # value(바이트) -> JSON 파싱 -> 컬럼으로 펼치기
    events = (
        raw.selectExpr("CAST(value AS STRING) AS json_str")
        .select(from_json(col("json_str"), EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_time", to_timestamp(col("timestamp")))
    )

    # ============================================================
    # 싱크 1: 원본 이벤트를 raw_events 테이블에 저장
    # ============================================================
    def save_raw(batch_df, batch_id):
        out = batch_df.select(
            "user_id", "event_type", "product_id", "price",
            col("event_time").alias("timestamp"),
        )
        write_to_postgres(out, "raw_events", mode="append")

    raw_query = (
        events.writeStream
        .foreachBatch(save_raw)
        .outputMode("append")
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/raw_events")
        .start()
    )

    # ============================================================
    # 싱크 2: 상품별 집계 (인기 상품 / 매출)
    #   - 조회수: view 이벤트 수
    #   - 구매수: purchase 이벤트 수
    #   - 매출: purchase 이벤트의 price 합
    # ============================================================
    product_agg = (
        events.filter(col("product_id").isNotNull())
        .groupBy("product_id")
        .agg(
            count(when(col("event_type") == "view", True)).alias("view_count"),
            count(when(col("event_type") == "purchase", True)).alias("purchase_count"),
            _sum(when(col("event_type") == "purchase", col("price")).otherwise(0.0)).alias("revenue"),
        )
    )

    def save_product_stats(batch_df, batch_id):
        # complete 모드 집계 결과를 통째로 덮어쓴다 (최신 누적 상태)
        write_to_postgres(batch_df, "product_stats", mode="overwrite")

    product_query = (
        product_agg.writeStream
        .foreachBatch(save_product_stats)
        .outputMode("complete")
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/product_stats")
        .start()
    )

    # ============================================================
    # 싱크 3: 1분 단위 트래픽 집계 (분당 방문자/이벤트/매출)
    #   워터마크로 늦게 도착한 데이터 처리 (10분까지 허용)
    # ============================================================
    traffic_agg = (
        events.withWatermark("event_time", "10 minutes")
        .groupBy(window(col("event_time"), "1 minute"))
        .agg(
            approx_count_distinct("user_id").alias("unique_users"),
            count("*").alias("event_count"),
            _sum(when(col("event_type") == "purchase", col("price")).otherwise(0.0)).alias("revenue"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            "unique_users", "event_count", "revenue",
        )
    )

    def save_traffic_stats(batch_df, batch_id):
        write_to_postgres(batch_df, "traffic_stats", mode="append")

    traffic_query = (
        traffic_agg.writeStream
        .foreachBatch(save_traffic_stats)
        .outputMode("append")
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/traffic_stats")
        .start()
    )

    print("Spark Streaming 시작됨. Kafka 토픽 구독 중:", KAFKA_TOPIC)
    print("종료하려면 Ctrl+C")

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()